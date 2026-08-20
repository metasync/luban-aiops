# SPEC-018 Plan: Kernel Middleware Alignment

## Approach

Move every cross-cutting kernel behavior off private agentscope surfaces
(FunctionTool subclassing, per-request toolkit rebuilds, `agent.toolkit`
mutation) and onto the supported `MiddlewareBase` hooks, then adopt the
two out-of-the-box middlewares that replace capability we lack (OTel
kernel tracing, per-reply token budget) and opt in to the built-in task
tools. All middleware wiring concentrates in `runtime_kernel.py` plus one
new module; the tool-gateway remains the sole tool-execution surface, so
policy, audit, and delegated-token identity are untouched. The work
groups into four stages: permission alignment (R-1), evidence tracing
alignment (R-2), out-of-box adoption (R-3, R-4, R-5), then deployment +
docs + re-audit (R-6, R-7).

The adoption gate from `spec.md` is enforced per change: any candidate
that fails a gate point is recorded as "kept out" in the R-7 matrix
rather than adapted around.

## Design Per Requirement

### R-1: Permission decisions via middleware

- affected files: new `products/agent-platform/src/agent_service/services/kernel_middleware.py`;
  `products/agent-platform/src/agent_service/tools/gateway_tools.py`;
  `products/agent-platform/src/agent_service/runtime_kernel.py`
- chosen approach: a `GatewayPermissionMiddleware(MiddlewareBase)`
  implements only `on_check_permission`. It reads `input_kwargs["tool"]`
  (a `ToolBase` exposing `.name` and `.is_read_only`) and the validated
  `tool_call`. If `tool.is_read_only and tool.name in allow_list` it
  returns `PermissionDecision(behavior=ALLOW, message=...)` without
  delegating (the documented bypass path); otherwise it returns
  `await next_handler(**input_kwargs)` so built-in resolution (ASK) runs.
  The allow-list loader (`_load_auto_allowed_tools`) moves unchanged into
  the middleware module so the env contract is byte-identical.
- `build_function_tools` stops using the subclass and returns plain
  `FunctionTool` instances; `_build_gateway_function_tool_class` is
  deleted. `is_read_only` is still derived from `risk_level == "read"`.
- Task-tool ALLOW (R-5): the middleware treats the four task tools as an
  always-allow set (they are state-local), registered only when the flag
  is on.
- rejected alternative: keep the `FunctionTool` subclass and also add a
  middleware. Two permission paths for one decision invites drift; the
  subclass is exactly the private-surface usage this spec removes.

### R-2: Tool evidence tracing via middleware

- affected files: `kernel_middleware.py` (new `ToolEvidenceMiddleware`);
  `runtime_kernel.py`; `tools/gateway_tools.py`
- chosen approach: `ToolEvidenceMiddleware.on_acting` reads
  `input_kwargs["tool_call"]` (a `ToolCallBlock` carrying `name`, `id`,
  and `input`) to emit the `tool_call` frame, delegates to
  `next_handler`, captures the final `ToolResponse`, and emits the
  `tool_result` frame. Frame field names and shapes are copied verbatim
  from the current closure so `agent-stream-event.schema.json` parity is
  preserved; the `data_summary` truncation helper is reused as-is.
- per-request delivery: `runtime_kernel.stream_events` sets a
  request-scoped sink via a `contextvars.ContextVar` before calling
  `reply_stream` and clears it after. The middleware reads the contextvar;
  when unset (blocking `reply_text`, or tracing disabled) it emits
  nothing. This replaces the per-request `asyncio.Queue` bound into every
  closure.
- removal: `_build_request_toolkit`, the `agent.toolkit = request_toolkit`
  assignment, and the `trace_queue`/`tq` parameters through
  `build_gateway_toolkit`/`build_function_tools`/`_make_tool_fn` all go
  away. Per-token toolkit caching (`_ensure_toolkit`) remains the single
  toolkit path.
- rejected alternative: keep tracing in the closure and only move the
  permission logic. The whole point is to eliminate the per-request
  toolkit rebuild + `agent.toolkit` mutation; a hybrid leaves both
  private-surface dependencies in place.

### R-3: OpenTelemetry kernel tracing

- affected files: `runtime_kernel.py`, `runtime_settings.py`
- chosen approach: new `AGENTSCOPE_KERNEL_TRACING` boolean (default
  `False`). When true, `AgentKernel._build_middlewares()` includes
  `TracingMiddleware()` from `agentscope.middleware`. It relies on the
  existing OTel SDK TracerProvider already configured by SPEC-005 and
  exports through the existing OTLP HTTP exporter; no new plumbing.
- Verified safety: `TracingMiddleware` short-circuits to `next_handler`
  when no SDK TracerProvider is active, so registering it is inert if
  OTel is misconfigured.
- rejected alternative: wrap model/tool calls ourselves for spans. That
  reinvents exactly what the out-of-box middleware provides.

### R-4: Reply token budget

- affected files: `runtime_settings.py`, `runtime_kernel.py`
- chosen approach: three new settings (`AGENTSCOPE_REPLY_TOKEN_BUDGET`,
  `_INPUT_TOKEN_WEIGHT`, `_OUTPUT_TOKEN_WEIGHT`) parsed with the existing
  `_optional_float` helper and validated in `__post_init__`. When a budget
  is set, `_build_middlewares()` appends
  `ReplyBudgetControlMiddleware(token_budget=..., input_token_weight=...,
  output_token_weight=...)`.
- No persistence change: budget state lives in
  `agent.state.middle_context`, already covered by SPEC-017 snapshots.
- rejected alternative: enforce the budget by lowering `max_iters`.
  Iteration count is a poor proxy for token cost; the middleware measures
  actual weighted tokens.

### R-5: Built-in task tools

- affected files: `runtime_settings.py`, `runtime_kernel.py`,
  `tools/gateway_tools.py` (toolkit assembly)
- chosen approach: new `AGENTSCOPE_TASK_TOOLS_ENABLED` boolean (default
  `False`). When true, toolkit construction appends `TaskCreate`,
  `TaskGet`, `TaskList`, `TaskUpdate` (imported from
  `agentscope.tool`) alongside the gateway `FunctionTool`s. These are
  state-injected tools that mutate only `agent.state`, so SPEC-017
  snapshot/restore persists them with no extra work.
- Permission: covered by R-1's always-allow set (never the interactive
  ASK default on a headless stream).
- rejected alternative: implement a platform-owned todo/task tracker.
  Reinvents a durable, kernel-integrated feature that already round-trips
  through our Postgres snapshots.

### R-6: dev-k8s deployment wiring

- affected files: `shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env`
- chosen approach: set `AGENTSCOPE_KERNEL_TRACING=true`. Leave
  `AGENTSCOPE_REPLY_TOKEN_BUDGET` and `AGENTSCOPE_TASK_TOOLS_ENABLED`
  unset (off) with a comment pointing at recommended starting values, so
  the default deployment is behaviorally identical to today except for
  the added OTel spans.

### R-7: Tests, documentation, re-audit

- affected files: `products/agent-platform/tests/*`, docs listed in the
  spec Impact section, new `docs/workspace/agentscope-utilization-audit.md`
- chosen approach: unit tests for the middleware decision/emission logic
  (no live agentscope agent required — middlewares are exercised through
  their hook signatures with stub `next_handler`s); settings validation
  tests; a schema-parity test asserting emitted frames validate against
  `agent-stream-event.schema.json`; a task-tool snapshot/restore
  round-trip. The re-audit memo is a decision matrix over the remaining
  agentscope surfaces.
- The memo explicitly records the entrypoint surface (only
  `agent-service` FastAPI is deployed) and feeds unresolved candidates to
  the delivery-roadmap Exploration Backlog.

## Sequencing And Dependencies

1. Settings additions (`runtime_settings.py`) for R-3/R-4/R-5 — depends on nothing.
2. `kernel_middleware.py` (permission + evidence middlewares) — depends on step 1 only for the allow-list loader move (R-1 is settings-free).
3. `runtime_kernel.py` wiring (`_build_middlewares`, contextvar sink, toolkit simplification) — depends on step 2.
4. `gateway_tools.py` cleanup (plain `FunctionTool`, drop `trace_queue` plumbing) — depends on steps 2 and 3.
5. Task-tool registration — depends on steps 3 and 4.
6. dev-k8s env wiring (R-6) — depends on steps 1–5 being merged-ready.
7. Tests + docs + re-audit memo (R-7) — interleaved; memo last.

## Test Strategy

- unit tests: permission middleware (allow-list hit/miss, task-tool ALLOW,
  ASK delegation via stub `next_handler`); evidence middleware frame
  emission and no-op when the sink contextvar is unset; settings
  validation for the four new knobs; task-tool registration flag.
- contract tests: emitted `tool_call`/`tool_result` frames validate
  against `agent-stream-event.schema.json`; no schema file is modified.
- integration / overlay validation: `make overlays` renders all four
  overlays with the new env var; full `make verify` gate green.
- regression: blocking chat, named sessions, and triage structured-output
  tests from SPEC-015/016/017 remain green unchanged.

## Rollout And Migration

- deployment/config changes: one new env var enabled in dev-k8s
  (`AGENTSCOPE_KERNEL_TRACING=true`); three new opt-in vars left unset.
- backward compatibility: every new behavior is default-off except the
  permission/evidence migration, which is behavior-preserving (same
  decisions, same frames). No contract or schema changes.
- rollback approach: unset the new env vars to revert tracing/budget/task
  behavior; the permission/evidence middleware migration reverts by git
  revert of the kernel/tools changes (no data migration involved).
