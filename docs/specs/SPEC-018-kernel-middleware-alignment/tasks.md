# SPEC-018 Tasks: Kernel Middleware Alignment

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Permission decisions via middleware

- [x] Create `services/kernel_middleware.py` with `GatewayPermissionMiddleware` (on_check_permission: allow-list ALLOW, else delegate) (`products/agent-platform/src/agent_service/services/kernel_middleware.py`)
- [x] Move `_load_auto_allowed_tools` + `AGENT_GATEWAY_TOOL_AUTO_ALLOW` contract into the middleware module unchanged (`products/agent-platform/src/agent_service/services/kernel_middleware.py`)
- [x] Switch `build_function_tools` to plain `FunctionTool`; delete `_build_gateway_function_tool_class` (`products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [x] Register the permission middleware in `AgentKernel._build_agent` (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Test: allow-list hit/miss, ASK delegation via stub next_handler, headless no-stall parity (`products/agent-platform/tests/test_kernel_middleware.py`)

## R-2: Tool evidence tracing via middleware

- [x] Implement `ToolEvidenceMiddleware.on_acting` emitting `tool_call`/`tool_result` frames with today's exact fields (`products/agent-platform/src/agent_service/services/kernel_middleware.py`)
- [x] Add request-scoped sink contextvar; set/clear it in `stream_events` (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Remove `_build_request_toolkit`, `agent.toolkit` mutation, and `trace_queue`/`tq` plumbing from toolkit builders (`products/agent-platform/src/agent_service/runtime_kernel.py`, `products/agent-platform/src/agent_service/tools/gateway_tools.py`)
- [x] Test: frame emission parity + no-op when sink unset (`products/agent-platform/tests/test_kernel_middleware.py`)
- [x] Contract test: emitted frames validate against `agent-stream-event.schema.json` (schema unmodified) (`products/agent-platform/tests/`)

## R-3: OpenTelemetry kernel tracing via TracingMiddleware

- [x] Add `AGENTSCOPE_KERNEL_TRACING` setting (boolean, default off) with validation (`products/agent-platform/src/agent_service/runtime_settings.py`)
- [x] Register `TracingMiddleware` in `_build_middlewares` when enabled (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Test: setting parsing/validation + middleware list composition (`products/agent-platform/tests/test_runtime_settings.py`, `products/agent-platform/tests/`)

## R-4: Reply token budget via ReplyBudgetControlMiddleware

- [x] Add `AGENTSCOPE_REPLY_TOKEN_BUDGET` / `_INPUT_TOKEN_WEIGHT` / `_OUTPUT_TOKEN_WEIGHT` settings with fail-fast validation (`products/agent-platform/src/agent_service/runtime_settings.py`)
- [x] Register `ReplyBudgetControlMiddleware` when a budget is set (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Test: budget unset = today's behavior; set = middleware registered; invalid values fail startup (`products/agent-platform/tests/test_runtime_settings.py`)

## R-5: Built-in task tools (opt-in)

- [x] Add `AGENTSCOPE_TASK_TOOLS_ENABLED` setting (boolean, default off) (`products/agent-platform/src/agent_service/runtime_settings.py`)
- [x] Register `TaskCreate`/`TaskGet`/`TaskList`/`TaskUpdate` alongside gateway tools when enabled (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Extend the permission middleware's always-allow set to the task tools (`products/agent-platform/src/agent_service/services/kernel_middleware.py`)
- [x] Test: registration flag behavior + task snapshot/restore round-trip via SPEC-017 store (`products/agent-platform/tests/`)

## R-6: dev-k8s deployment wiring

- [x] Set `AGENTSCOPE_KERNEL_TRACING=true`; document opt-in budget/task-tools vars with recommended starting values (`shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env`)
- [x] Render all four overlays (`make overlays`)

## R-7: Tests, documentation, and post-delivery utilization re-audit

- [x] Full `make verify` gate green (all product suites + overlays + policy + version gates)
- [x] Document new settings (`docs/guides/configuration-reference.md`)
- [x] Update agent-platform README (middleware-based kernel) (`products/agent-platform/README.md`)
- [x] Note adopted vs. platform-owned agentscope surfaces (`docs/guides/architecture-overview.md`)
- [x] Write the utilization re-audit memo with adopted / kept-platform-owned / spike-needed decision matrix, entrypoint-surface clarification, and the Future Scope carry-forward (HITL bridging, ASK → DENY tightening) (`docs/workspace/agentscope-utilization-audit.md`)
- [x] Feed unresolved candidates back to the delivery-roadmap Exploration Backlog (`docs/agentic-aiops-platform/delivery-roadmap.md`)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified, including the four-point adoption gate per adopted feature
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
