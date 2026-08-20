# SPEC-018: Kernel Middleware Alignment

## Status

- status: `delivered`
- owner: workspace maintainers
- created: 2026-08-18
- release slice: post-R3 kernel hardening (sequenced after SPEC-017)
- related ADRs: ADR-0002 (AgentScope runtime kernel), ADR-0003
  (platform-owned agent service contract), ADR-0006 (contract purpose
  restated: invariant enforcement over swappability — governs how this
  spec exploits the kernel behind the boundary)

## Summary

Align the agent-platform kernel integration with AgentScope 2.0.6's
middleware system instead of the hand-rolled interception paths built
before it existed. Today the platform subclasses `FunctionTool` to bypass
the interactive permission gate, rebuilds the whole `Toolkit` per request
to attach a trace queue, and mutates `agent.toolkit` mid-flight — all
private-surface maneuvers that upstream upgrades can silently break. This
spec moves those behaviors onto the supported `MiddlewareBase` hooks
(`on_check_permission`, `on_acting`), adopts two out-of-the-box
middlewares (`TracingMiddleware` for OpenTelemetry, `ReplyBudgetControlMiddleware`
for per-reply token budgets), and opts in to the built-in task-planning
tools. Every adoption must pass the four-point adoption gate below;
platform invariants (tool-gateway-only tool surface, policy, audit,
delegated-token identity, Postgres durability, the v2 contract boundary)
stay platform-owned.

### Adoption gate

Every out-of-box feature adopted by this spec must satisfy all four:

1. preserves deny-by-default policy enforcement and the audit trail
   (tool-gateway remains the only tool execution surface);
2. keeps identity carried exclusively by the gateway-forwarded delegated
   token;
3. keeps the read-only operational posture;
4. leaks no agentscope types through the platform-owned v2 contract
   (routes, request/response schemas, SSE event contract unchanged).

## Motivation

- A post-SPEC-017 utilization audit found the kernel integration bypasses
  the agentscope middleware system entirely: permission handling is a
  `FunctionTool` subclass (`GatewayFunctionTool.check_permissions`), tool
  tracing is a per-request `asyncio.Queue` bound into every tool closure,
  and per-request tracing forces a full toolkit rebuild plus an
  `agent.toolkit = ...` mutation — all upgrade-fragile private-surface
  usage.
- agentscope 2.0.6 ships `MiddlewareBase` with seven supported hooks,
  including `on_check_permission` (a first-class replacement for the
  subclass override) and `on_acting` (wraps exactly `toolkit.call_tool`,
  a first-class replacement for closure-based tracing). Verified against
  the locked 2.0.6 install.
- Two out-of-the-box middlewares deliver capability the platform lacks:
  `TracingMiddleware` emits agent/LLM/tool OpenTelemetry spans through the
  existing OTLP pipeline (today only the HTTP layer is traced), and
  `ReplyBudgetControlMiddleware` enforces a weighted per-reply token
  budget (today only `max_iters` bounds runaway loops).
- The built-in task tools (`TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate`)
  store tasks inside `AgentState`, so SPEC-017's Postgres snapshot/restore
  makes multi-step triage planning durable for free.
- Platform direction (maintainer guidance): prefer agentscope out-of-box
  features over hand-rolled equivalents inside the kernel adapter, keeping
  the platform-owned contract boundary intact.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Permission decisions via middleware

The vetted-allow-list permission behavior moves from the `FunctionTool`
subclass to a platform middleware implementing `on_check_permission`.

Acceptance criteria:

- A platform `MiddlewareBase` subclass resolves each tool call: a tool
  that is read-only AND named in the allow-list receives
  `PermissionDecision(ALLOW)` with the same rationale message as today;
  every other call delegates to `next_handler` (the built-in resolution,
  i.e. the ASK default) unchanged.
- The allow-list source is unchanged: `AGENT_GATEWAY_TOOL_AUTO_ALLOW`
  env override or the vetted default set, normalized to sanitized
  `FunctionTool.name` form (dots → underscores).
- Gateway tools are registered as plain `FunctionTool` instances; the
  `GatewayFunctionTool` subclass and its builder are removed.
- When R-5 task tools are enabled, the middleware also ALLOWs them (they
  mutate only `agent.state`, never infrastructure); with task tools
  disabled they are not registered at all, so the ASK default never fires
  on a headless stream for any registered tool.
- Headless behavior parity: a turn over a session with only
  vetted-allow-listed tools completes with the same tool executions and
  zero `RequireUserConfirmEvent` stalls as before this spec.

### R-2: Tool evidence tracing via middleware

The SSE evidence-panel frames (`tool_call` / `tool_result`, SPEC-011 R-2)
are emitted from a platform `on_acting` middleware instead of per-request
toolkit closures.

Acceptance criteria:

- A platform `on_acting` middleware emits, per tool call, the same frame
  fields the stream carries today: `tool_call` (tool_name, call_id,
  parameters) before execution and `tool_result` (tool_name, call_id,
  status, evidence, data_summary, error) after — validated against
  `agent-stream-event.schema.json`, which is not modified.
- `data_summary` bounding reuses the existing truncation helper and the
  `AGENT_TOOL_DATA_SUMMARY_MAX_CHARS` setting; evidence/error pass
  through from the gateway result exactly as today.
- Per-request delivery uses a kernel-managed request-scoped sink
  (contextvar) set by `stream_events`; when no sink is present (blocking
  `reply_text` path) the middleware is a no-op, matching today's
  stream-only tracing.
- The per-request toolkit rebuild (`_build_request_toolkit`), the
  `agent.toolkit = ...` mutation, and the `trace_queue` closure plumbing
  in `gateway_tools.py` are removed; tool definitions and per-token
  toolkits become the sole toolkit path.
- Blocking chat, named sessions, and triage structured-output behavior
  are unchanged.

### R-3: OpenTelemetry kernel tracing via TracingMiddleware

The kernel adopts agentscope's `TracingMiddleware` for agent/LLM/tool
spans through the existing OTLP pipeline.

Acceptance criteria:

- New `AGENTSCOPE_KERNEL_TRACING` (boolean, default off). When enabled,
  `TracingMiddleware()` is registered on constructed agents; when unset
  the agent behaves exactly as today.
- Spans flow through the existing OTel SDK/OTLP setup (SPEC-005 pipeline,
  OpenObserve backend) nested under the HTTP request span; no new
  exporter or endpoint is introduced.
- The middleware is safe to register when OTel is not configured: it
  short-circuits to the next handler (agentscope-verified behavior) and
  adds no request-visible difference.
- SSE evidence frames remain governed exclusively by R-2 (TracingMiddleware
  emits OTel spans only; the evidence-panel contract does not depend on
  it).

### R-4: Reply token budget via ReplyBudgetControlMiddleware

Runaway turns are bounded by a weighted per-reply token budget using the
out-of-the-box middleware.

Acceptance criteria:

- New settings, each env-backed:
  - `AGENTSCOPE_REPLY_TOKEN_BUDGET` (float; unset = no budget, exactly
    today's behavior)
  - `AGENTSCOPE_REPLY_INPUT_TOKEN_WEIGHT` (float, default 1.0)
  - `AGENTSCOPE_REPLY_OUTPUT_TOKEN_WEIGHT` (float, default 1.0)
- When a budget is set, `ReplyBudgetControlMiddleware` is registered with
  those values; when the budget is exhausted the kernel injects the
  built-in wrap-up hint and forces `tool_choice` to none (agentscope
  behavior, unmodified).
- Out-of-range values fail startup with a clear error (budget must be
  > 0 when set; weights must be >= 0), same validation style as SPEC-017
  R-1.
- Budget state lives in `agent.state.middle_context`, so SPEC-017
  snapshot/restore covers it with no additional persistence work.

### R-5: Built-in task tools (opt-in)

The agentscope task-planning tools are available behind an explicit flag.

Acceptance criteria:

- New `AGENTSCOPE_TASK_TOOLS_ENABLED` (boolean, default off). When
  enabled, `TaskCreate`, `TaskGet`, `TaskList`, and `TaskUpdate` are
  registered alongside gateway tools; when disabled (default) they are
  not registered and nothing else changes.
- Task state is carried in `AgentState`; with the SPEC-017 Postgres
  backend active, tasks survive restarts via the existing snapshot/restore
  (round-trip asserted by test).
- Task tools never bypass the read-only posture: they perform no
  infrastructure access, and their permission path is the explicit ALLOW
  defined in R-1 (never the interactive ASK default).
- The standing system prompt is unchanged; task tools are self-describing
  via their own schemas.

### R-6: dev-k8s deployment wiring

Acceptance criteria:

- `dev-k8s/base/agent-platform/runtime-config.env` sets
  `AGENTSCOPE_KERNEL_TRACING=true` (OTel is already enabled for the
  deployment); `AGENTSCOPE_REPLY_TOKEN_BUDGET` and
  `AGENTSCOPE_TASK_TOOLS_ENABLED` are intentionally left unset (off) and
  documented as opt-in with recommended starting values.
- No other overlay changes; `make overlays` renders all four overlays.

### R-7: Tests, documentation, and post-delivery utilization re-audit

Acceptance criteria:

- Tests: permission middleware decisions (allow-list hit/miss, task-tool
  ALLOW, ASK delegation); evidence-frame parity between the middleware
  path and `agent-stream-event.schema.json`; settings validation for the
  new knobs; task-tool snapshot/restore round-trip; toolkit construction
  registers task tools only when enabled; existing suites remain green.
- Docs: `docs/guides/configuration-reference.md` documents the new
  settings; agent-platform README describes the middleware-based kernel;
  architecture-overview notes which agentscope surfaces are adopted vs.
  platform-owned; CHANGELOG entry references this spec.
- Re-audit deliverable: a utilization memo
  (`docs/workspace/agentscope-utilization-audit.md`) with a decision
  matrix — adopted / kept platform-owned (+reason) / spike needed — for
  every remaining agentscope surface (MCP, RAG/embedding, long-term
  memory middlewares, kernel-side SQL storage, sandboxes, built-in
  file/shell tools, channels/hub). Candidates still needing a spike feed
  the delivery-roadmap Exploration Backlog, unchanged in governance.
- The memo also clarifies the entrypoint surface: only the `agent-service`
  FastAPI entrypoint is deployed; `agent-service-native` and
  `agent-service-runtime` remain available kernel-capability entrypoints
  but are not part of the deployed topology.
- The memo carries forward the Future Scope items above (HITL
  confirmation bridging, ASK → DENY tightening) with their status and
  sequencing constraint (HITL bridging precedes any write/mutating tool).

## Out of Scope

- MCP exposure of tool-gateway connectors, vector (semantic) skill
  retrieval, long-term memory middlewares (Mem0/ReME/Agentic), and
  kernel-side `AsyncSQLAlchemyStorage` — roadmap Exploration Backlog
  items pending spikes; the R-7 memo re-confirms their status.
  ReMe specifically was evaluated 2026-08-20 and does not fit as-is:
  its file-based vault conflicts with the Postgres durability story and
  ephemeral pods, its automatic LLM write-back bypasses audit and risks
  injecting ungrounded claims (anti-fabrication conflict), and its
  workspace-wide retrieval has no per-user isolation on a multi-operator
  platform. A future spike requires a governed storage backend,
  per-tenant scoping, and audit hooks first.
- RAG middleware, embedding models, built-in file/shell tools
  (`Bash`/`Read`/`Write`/...), TTS, sandboxes/workspaces, channels/hub —
  incompatible with the read-only posture or platform ownership; recorded
  as "kept out" in the R-7 matrix.
- The `agentscope.app` application layer (`create_app` FastAPI factory:
  its own routers, access policy, sessions, storage, message bus,
  skill/MCP hubs, RAG, and chat channels) — adopting it as a deployed
  surface would create a second API edge with a second access model,
  duplicate governed capabilities (skills-hub, session durability,
  credential delegation), and re-instate the native-wire-protocol option
  rejected in ADR-0003. Recorded as "kept platform-owned" in the R-7
  matrix; the `native.py` entrypoint remains a capability probe only.
- Any change to the v2 contract schemas, the tool-gateway invocation
  path, policy evaluation, or audit emission.
- Removing the `native.py` / `runtime.py` entrypoints (R-7 documents
  their status instead).

## Future Scope (tracked, not delivered here)

Per ADR-0006, the v2 contract may deliberately grow interaction
semantics. The following is recorded here so it is tracked rather than
rediscovered:

- **HITL confirmation bridging** — map kernel confirmation events
  (agentscope's `ASK` / `RequireUserConfirmEvent`) onto new v2 SSE frame
  types, render approve/deny in the operator portal, and return the
  answer through a small contract endpoint (with session
  suspend/resume semantics). This is a spec of its own and MUST be
  delivered before any write/mutating tool ships; until then the
  headless posture of this spec (pre-answered permission decisions,
  read-only tools only) is what keeps the platform safe.
- **ASK → DENY tightening** — non-allow-listed gateway tools currently
  fall through to the interactive ASK default, which headlessly means
  "silently never runs". Tightening that to an explicit, observable DENY
  is behaviorally equivalent in the deployed topology and a candidate
  follow-up; this spec preserves today's ASK semantics for parity.
- **`agentscope.app` reference components** — the kernel's HITL
  projectors (`_service/_projectors`) may serve as a reference design
  for the HITL confirmation bridging spec, and the AGUI protocol
  middleware may be spiked if interaction richer than the SSE evidence
  frames is ever needed. Neither becomes a runtime dependency without
  its own spec passing the adoption gate.

## Impact

- products touched: `products/agent-platform` (kernel, tools, settings,
  tests, docs)
- deployment touched: `shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env`
- contracts touched: none (`agent-stream-event.schema.json` preserved
  byte-semantics; no schema changes)
- identity / policy / audit / execution safety impact: none by design —
  permission semantics, policy enforcement point, audit chain, and
  delegated-token carriage are behaviorally unchanged; the adoption gate
  is enforced per requirement
- living state docs to update on delivery: `docs/guides/configuration-reference.md`,
  `products/agent-platform/README.md`, `docs/guides/architecture-overview.md`,
  `CHANGELOG.md`, `docs/specs/README.md`

## Open Questions

- none (design decisions verified against the locked agentscope 2.0.6
  install: `Agent(middlewares=[...])` constructor parameter, `on_acting`
  wraps only `toolkit.call_tool`, `TracingMiddleware` short-circuits
  without an SDK TracerProvider, task tools are state-injected into
  `AgentState`)

## Changelog

- 2026-08-20: delivered — all requirements implemented and verified;
  `make verify` green (all product suites, four overlay renders, policy
  and version gates); utilization re-audit memo landed at
  `docs/workspace/agentscope-utilization-audit.md`; status set to
  `delivered`
- 2026-08-20: recorded the `agentscope.app` application layer as kept
  platform-owned (Out of Scope, with rationale) and its HITL
  projectors / AGUI protocol as reference-only future-scope candidates;
  recorded the ReMe long-term-memory evaluation verdict (does not fit
  as-is; spike preconditions noted)
- 2026-08-19: linked ADR-0006; added Future Scope section (HITL
  confirmation bridging, ASK → DENY tightening) and an R-7 criterion to
  carry it into the utilization memo; permission semantics kept at
  today's ASK parity for non-allow-listed tools
- 2026-08-18: created as `draft`
