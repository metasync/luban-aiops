# SPEC-017: Agent Kernel Utilization and Conversation Durability

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-08-18
- approved: 2026-08-18
- delivered: 2026-08-18
- release slice: post-R3 kernel hardening (pairs with SPEC-016)
- related ADRs: ADR-0002 (AgentScope runtime kernel), ADR-0003
  (platform-owned agent service contract)

## Summary

Use the AgentScope 2.0.6 kernel more fully and close the platform's real
durability gap. agent-platform today constructs `Agent(name, system_prompt,
model, toolkit)` with no tuning and keeps every session's conversation
memory in-process, so a pod restart silently wipes all chat and triage
context. This spec (1) expresses the kernel's config surfaces — ReAct loop
budget, context compression, runtime-state/time injection, model retries —
through platform settings; (2) replaces the fenced-JSON triage-report
discipline with the kernel's native structured output; and (3) persists the
kernel-serializable `AgentState` to Postgres so conversations survive
restarts. Persistence stays platform-owned (snapshot/restore around the
kernel), keeping ADR-0003's swappable-contract promise; the kernel's own
app-layer storage machinery is deliberately not adopted.

## Motivation

- The deployed chat path (`agent-service` runtime entrypoint) caches one
  `Agent` per session in an in-process LRU. Restart or eviction loses the
  whole conversation; this — not Redis's `emptyDir` volume — is the
  durability users actually feel. (`agentscope 2.0.6`'s
  `AsyncSQLAlchemyStorage` makes kernel-side SQL storage possible, but
  adopting the kernel app's session machinery would violate ADR-0003;
  platform-owned snapshots of `AgentState` get the same outcome without the
  coupling.)
- Triage reports (SPEC-015) rely on prompt discipline: a fenced
  `triage-report` JSON block that the model must emit and incident-service
  must parse and repair. AgentScope 2.0.5+ ships native structured output
  (`reply(structured_schema=...)`, backed by a built-in
  `GenerateStructuredOutput` tool that accepts a plain JSON-schema dict and
  validates before returning) — a deterministic replacement.
- Long triage sessions have no context-compression budget, the agent has no
  sense of the current time (weak for "when did this alert fire"
  reasoning), and provider failures fall straight to the platform error
  fallback with no model-level retry. All four knobs exist upstream
  (`ContextConfig`, `InjectionConfig`, `ReActConfig`, `ModelConfig`) and
  are currently left at unexpressed defaults.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Kernel configuration surfaces

`AgentKernel` constructs agents with explicit, settings-driven kernel
configs instead of bare defaults.

Acceptance criteria:

- New `RuntimeSettings` fields, each env-backed, each defaulting to the
  agentscope default so unset deployments behave exactly as today:
  - `AGENTSCOPE_MAX_ITERS` (int, default 20) → `ReActConfig(max_iters=...)`
  - `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` (float, default 0.8) →
    `ContextConfig(trigger_ratio=...)`
  - `AGENTSCOPE_TOOL_RESULT_LIMIT` (int, default 50000) →
    `ContextConfig(tool_result_limit=...)`
  - `AGENTSCOPE_TIMEZONE` (string, default `UTC`) →
    `InjectionConfig(timezone=...)` with `inject_runtime_state` enabled
  - `AGENTSCOPE_MODEL_MAX_RETRIES` (int, default 0) →
    `ModelConfig(max_retries=...)`
- Out-of-range values fail startup with a clear error (same validation
  style as existing settings).
- `ModelConfig.fallback_model` stays unset in this spec (provider registry
  integration is a follow-up option, not a requirement).
- one structured log line at agent construction records the effective
  config values.

### R-2: Structured output for triage reports

The v2 chat API accepts an optional response schema and returns the
kernel-validated structured output; incident-service switches triage to it.

Acceptance criteria:

- `POST /api/v2/chat` accepts an optional `response_schema` (a JSON-schema
  dict). When present, the kernel runs the turn with
  `structured_schema=response_schema` and the response body carries
  `structured_output` (the validated dict, or `null` when the turn ended
  without producing one). Text replies remain in `message` as today.
- The schema dict is passed through unchanged to the kernel's built-in
  structured-output tool; agent-platform performs no schema rewriting.
- incident-service sends `triage-report.schema.json` as `response_schema`
  on triage turns and prefers `structured_output`; the legacy fenced-block
  parser remains as fallback when `structured_output` is `null` (one-turn
  compatibility), and server-minted attribution (incident_id / session_id /
  generated_at / generated_by forced to server-known facts) is unchanged.
- The standing system prompt's fenced-block output discipline is replaced
  with a format-neutral instruction (describe the required fields, defer
  formatting to the structured-output tool), so fenced output is no longer
  demanded when structured output is active.
- The `triage_failed` path and raw-text preservation semantics
  (SPEC-015 R-3) are unchanged.

### R-3: Conversation durability — AgentState persistence

Session conversation state survives agent-platform restarts.

Acceptance criteria:

- New `AgentStateStore` protocol with two backends:
  `InMemoryAgentStateStore` (code default) and `PostgresAgentStateStore`,
  selected by `AGENT_STATE_STORE_BACKEND` (`memory` | `postgres`; unknown
  values fail startup). `AGENT_STATE_DB_URL` supplies the DSN when the
  backend is `postgres` (vocabulary matches SPEC-016's `SESSION_DB_URL`).
- The store persists `agent.state.model_dump_json()` keyed by platform
  session id in an `agent_states` table: `session_id` (PK), `state`
  (JSONB), `updated_at`. SQL is parameterized everywhere; identifiers are
  fixed constants. The driver is synchronous `psycopg[binary]`, matching
  SPEC-016.
- Snapshot timing: after every completed turn (`reply_text` and the end of
  `stream_events`). A failed snapshot logs a WARNING and increments
  `agent_state_errors_total` but never fails the turn.
- Restore timing: on agent construction for a session (cache miss). When a
  stored state exists it is loaded via
  `AgentState.model_validate_json(...)` and passed to the kernel `Agent`
  constructor; a corrupt row is discarded (WARNING + counter) and the
  agent starts fresh.
- Lifecycle: `delete_state(session_id)` is called when the session service
  deletes a session; storage is additionally bounded by an opportunistic
  sweep of rows older than the session TTL, bounded per operation (same
  pattern as SPEC-016 R-1).
- fail-open parity: if the initial Postgres connection fails, the factory
  falls back to the in-memory store with a WARNING log and increments
  `agent_state_fallbacks_total`.

### R-4: dev-k8s deployment

Acceptance criteria:

- The SPEC-016 sessions-database bootstrap (initdb pattern) also creates
  the `agent_states` table (idempotent DDL applied by agent-platform on
  startup when the postgres backend is active) — one database for
  platform-owned agent session state.
- `dev-k8s/base/agent-platform/runtime-config.env` sets
  `AGENT_STATE_STORE_BACKEND=postgres` and `AGENT_STATE_DB_URL` alongside
  the SPEC-016 session settings; kernel tuning settings are set explicitly
  only where the deployment intentionally deviates from defaults.
- The `redis` deployment is unchanged (still `emptyDir`, `appendonly no`):
  after SPEC-016 + this spec it serves only the kernel message bus and
  caches, which are ephemeral by design — the Redis PV question is
  resolved by removal of the durable data, not by adding persistence.

### R-5: Observability, tests, documentation

Acceptance criteria:

- Metrics: `agent_state_backend` gauge names the active backend;
  `agent_state_errors_total` and `agent_state_fallbacks_total` counters as
  defined in R-3.
- `/health` gains an `agent_state` readiness field following the existing
  `session_store` pattern (`agent-health.schema.json` updated if it
  enumerates fields).
- Tests: settings validation for the new knobs; structured-output chat
  round-trip (schema present → `structured_output`; absent → unchanged
  response shape); triage structured-first + fenced fallback; agent-state
  snapshot/restore round-trip including corrupt-row discard;
  fake-psycopg backend tests mirroring SPEC-016's pattern.
- Docs: `docs/guides/configuration-reference.md` documents the new
  settings; agent-platform README and CHANGELOG updated; the architecture
  guide notes that conversation state is now durable in Postgres.

## Out of Scope

- Middleware-based tracing / permission alignment and built-in task tools —
  SPEC-018.
- MCP exposure of tool-gateway connectors, vector retrieval for skills,
  long-term memory middlewares — roadmap backlog items pending spikes.
- Adopting the agentscope app-layer storage/session machinery
  (`create_app`, `RedisStorage`, `AsyncSQLAlchemyStorage`) — conflicts
  with ADR-0003's platform-owned contract.
- `ModelConfig.fallback_model` wiring (needs provider-registry support).
- A Redis PV / persistence (superseded: see R-4).

## Risks

- **R1: State serialization churn.** `AgentState` round-trips through
  pydantic, but agentscope version bumps could shift `Msg`/block shapes.
  Mitigation: restore failures degrade to a fresh agent (R-3), never a
  crash; pin agentscope deliberately (current lock: 2.0.6).
- **R2: Structured-output availability.** Some models honor tool-based
  structured output less reliably; a turn could end with
  `structured_output: null`. Mitigation: the fenced-block fallback parser
  (R-2) keeps triage functional; `triage_failed` remains the terminal
  failure path.
- **R3: Snapshot size.** Long sessions grow the JSONB payload. Mitigation:
  R-1's context compression bounds the context the state carries; sweep
  bounds storage lifetime.
- **R4: Postgres blast radius grows.** Chat context now shares Postgres
  availability with sessions/audit/incidents. Mitigation: fail-open
  in-memory fallback (R-3) — durability degrades, availability does not.
