# SPEC-017 Plan: Agent Kernel Utilization and Conversation Durability

## Approach

Two directions, both platform-owned per ADR-0003. First, express the
AgentScope 2.0.6 kernel's config surfaces — `ReActConfig`, `ContextConfig`,
`InjectionConfig`, `ModelConfig` — through env-backed `RuntimeSettings`
fields whose defaults equal the agentscope defaults, so unset deployments
behave exactly as today; and replace the SPEC-015 fenced-JSON triage-report
discipline with the kernel's native structured output
(`structured_schema=...`). Second, close the durability gap by snapshotting
the kernel-serializable `AgentState` to Postgres after every turn and
restoring it on agent construction — persistence wraps the kernel rather
than adopting the kernel's app-layer storage machinery, keeping the agent
service contract swappable.

Implementation stages: (1) kernel config settings + `AgentKernel` build
configs, (2) `AgentStateStore` protocol + memory/postgres backends,
(3) snapshot/restore wiring + session-delete cascade, (4) v2 chat
`response_schema`/`structured_output` + shared contracts, (5)
incident-service structured-first triage, (6) platform-gateway mirror-model
parity, (7) dev-k8s wiring, (8) observability, tests, and docs.

## Design Per Requirement

### R-1: Kernel configuration surfaces

- affected files:
  `products/agent-platform/src/agent_service/runtime_settings.py` (new
  fields + validation), `runtime_kernel.py` (agent construction)
- five env-backed fields, each defaulting to the agentscope default:
  `AGENTSCOPE_MAX_ITERS` (20) → `ReActConfig(max_iters=...)`;
  `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` (0.8) and
  `AGENTSCOPE_TOOL_RESULT_LIMIT` (50000) → `ContextConfig(...)`;
  `AGENTSCOPE_TIMEZONE` (`UTC`) → `InjectionConfig(timezone=...)` with
  `inject_runtime_state` enabled; `AGENTSCOPE_MODEL_MAX_RETRIES` (0) →
  `ModelConfig(max_retries=...)`
- out-of-range values fail startup in the existing settings-validation
  style
- `ModelConfig.fallback_model` deliberately unset (provider-registry
  follow-up, not this spec)
- one structured log line at agent construction records the effective
  config values

### R-2: Structured output for triage reports

- affected files:
  `products/agent-platform/src/agent_service/schemas/v2.py` +
  `api/v2/routes.py` (request/response), `runtime_kernel.py`
  (structured turn), `runtime_settings.py` (system prompt),
  `shared/shared-contracts/schemas/agent-chat-response.schema.json`,
  `products/platform-gateway/src/platform_gateway/schemas/api.py`
  (`ChatResponse` mirror),
  `products/incident-service/src/incident_service/services/triage.py`
- `POST /api/v2/chat` accepts optional `response_schema`; when present the
  turn runs with `structured_schema=response_schema` and the response
  carries `structured_output` (validated dict, or `null` when the turn
  ended without producing one); text replies stay in `content`
- the schema dict passes to the kernel's built-in structured-output tool
  unchanged — no schema rewriting in agent-platform
- incident-service sends `triage-report.schema.json` as `response_schema`
  and prefers `structured_output`; the legacy fenced-block parser remains
  as fallback when `structured_output` is `null`; server-minted attribution
  (incident_id / session_id / generated_at / generated_by) unchanged
- the system prompt's fenced-block discipline is replaced with a
  format-neutral instruction; the `triage_failed` path and raw-text
  preservation semantics are unchanged
- contract parity: `agent-chat-response.schema.json` gains
  `structured_output` (`["object", "null"]`); the platform-gateway mirror
  `ChatResponse` model gains the matching field (the `/api/v1/chat` route
  relays the upstream dict verbatim, so no route change is needed)

### R-3: Conversation durability — AgentState persistence

- affected files:
  `products/agent-platform/src/agent_service/services/agent_state_store.py`
  (new: protocol + `InMemoryAgentStateStore` + `PostgresAgentStateStore`),
  `runtime_settings.py` (`AGENT_STATE_STORE_BACKEND`, `AGENT_STATE_DB_URL`,
  `AGENT_STATE_TTL_SECONDS`), `runtime_kernel.py` (snapshot/restore),
  `services/session_service.py` (delete cascade), `core/metrics.py`
- `agent_states` table: `session_id` (PK), `state` (JSONB of
  `agent.state.model_dump_json()`), `updated_at`; parameterized SQL, fixed
  identifiers, synchronous `psycopg[binary]` matching SPEC-016; DDL applied
  idempotently at startup when the postgres backend is active
- snapshot after every completed turn (`reply_text` and end of
  `stream_events`); a failed snapshot logs WARNING +
  `agent_state_errors_total` and never fails the turn
- restore on agent construction for a session (cache miss):
  `AgentState.model_validate_json(...)` feeds the kernel `Agent`
  constructor; a corrupt row is discarded (WARNING + counter) and the agent
  starts fresh
- lifecycle: `delete_state(session_id)` on session deletion; opportunistic
  sweep of rows older than the session TTL, bounded per operation
  (SPEC-016 pattern)
- fail-open parity: initial Postgres connection failure falls back to the
  in-memory store with WARNING + `agent_state_fallbacks_total`

### R-4: dev-k8s deployment

- affected files:
  `shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env`,
  initdb/bootstrap for the sessions database
- the SPEC-016 `sessions` database also hosts the `agent_states` table —
  one database for platform-owned agent session state; DDL applied by
  agent-platform on startup
- `runtime-config.env` sets `AGENT_STATE_STORE_BACKEND=postgres` +
  `AGENT_STATE_DB_URL` alongside the SPEC-016 session settings; kernel
  tuning knobs are intentionally left unset in dev (defaults apply)
- redis deployment unchanged (`emptyDir`, `appendonly no`): after
  SPEC-016 + this spec it serves only kernel message bus and caches, which
  are ephemeral by design

### R-5: Observability, tests, documentation

- affected files: `core/metrics.py`, `api/v2/routes.py` (health),
  `shared/shared-contracts/schemas/agent-health.schema.json`, tests, docs
- metrics: `agent_state_backend` gauge names the active backend;
  `agent_state_errors_total` and `agent_state_fallbacks_total` counters
- `/health` gains the `agent_state` readiness field following the
  `session_store` pattern; `agent-health.schema.json` updated
- docs: configuration-reference documents the kernel knobs +
  `AGENT_STATE_*` vars; agent-platform README gains the durability section;
  CHANGELOG entry; architecture guide notes conversations are durable in
  Postgres

## Sequencing And Dependencies

1. RuntimeSettings kernel-config fields + `AgentKernel` build configs —
   depends on nothing
2. `AgentStateStore` protocol + memory/postgres backends — depends on (1)
   only for the TTL setting vocabulary
3. Snapshot/restore wiring + session-delete cascade — depends on (2)
4. v2 chat `response_schema`/`structured_output` + contract schema —
   parallel with (2)/(3)
5. incident-service structured-first triage — depends on (4) request shape
6. platform-gateway `ChatResponse` mirror parity — depends on (4) schema
   change
7. dev-k8s initdb + `runtime-config.env` — depends on SPEC-016 sessions DB
   + (2) env contract
8. Metrics/health, tests, living docs — depends on all

## Test Strategy

- unit tests (agent-platform): settings validation for the five kernel
  knobs and `AGENT_STATE_*` fields; `AgentKernel` config construction +
  effective-config log; structured-output chat round-trip (schema present →
  `structured_output`, absent → unchanged response shape); agent-state
  snapshot/restore round-trip including corrupt-row discard, fallback
  factory, TTL sweep against the fake psycopg driver double; session-delete
  cascade
- unit tests (incident-service): triage structured-first path + fenced
  fallback when `structured_output` is null; attribution forcing unchanged;
  `triage_failed` semantics unchanged
- unit tests (platform-gateway): contract parity between `ChatResponse` and
  the updated `agent-chat-response.schema.json`
- contract tests: both chat schemas and the updated health schema
- integration / overlay validation: `kustomize build` renders dev-k8s via
  `make verify` with the new env settings; live verification is
  delivery-time, not part of the gate

## Rollout And Migration

- deployment: dev-k8s commits `AGENT_STATE_STORE_BACKEND=postgres` +
  `AGENT_STATE_DB_URL` on the sessions database; kernel tuning knobs unset
  (defaults) — no behavior change until an operator opts in
- backward compatibility: `AGENT_STATE_STORE_BACKEND` defaults to `memory`;
  chat requests without `response_schema` behave exactly as before; the
  fenced-block fallback keeps triage functional even when a model ignores
  structured output
- rollback: unset `AGENT_STATE_STORE_BACKEND` (falls back to in-process
  memory) — durability degrades, availability does not; kernel knobs revert
  by unsetting the env vars
