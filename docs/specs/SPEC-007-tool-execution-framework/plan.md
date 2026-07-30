# SPEC-007 Plan: Read-Only Tool Execution Framework

## Approach

The implementation follows a bottom-up sequence: contracts first, then the tool-gateway execution layer (registry, connector, routes, policy), then agent-platform integration, and finally the dev overlay. Each stage is independently testable.

The tool-gateway owns tool execution. The agent-platform owns tool discovery and LLM-facing registration. Communication is over HTTP (`POST /api/v2/tools/invoke`), keeping the services loosely coupled and independently deployable.

## Design Per Requirement

### R-1: Tool execution contract in shared-contracts

- affected files: `shared/shared-contracts/schemas/tool-invocation.schema.json`, `shared/shared-contracts/schemas/tool-result.schema.json`, `shared/shared-contracts/README.md`
- approach: JSON Schema (draft-07) matching the existing contract style; tool naming convention `<system>.<verb>_<noun>`
- the evidence sub-object in tool-result provides provenance for downstream audit and UI rendering

### R-2: Tool registry and base abstraction in tool-gateway

- affected files: `products/tool-gateway/src/api_gateway/tools/__init__.py`, `tools/base.py`, `tools/registry.py`
- approach: simple in-memory dict-based registry; `BaseTool` ABC with a single `execute` coroutine; `ToolResult` dataclass for structured responses
- alternatives: plugin discovery via entry_points — rejected as over-engineered for 1 connector

### R-3: Kubernetes read-only connector

- affected files: `products/tool-gateway/src/api_gateway/tools/k8s_connector.py`, `products/tool-gateway/pyproject.toml`
- approach: single module with a `KubernetesConnector` class that registers 4 tool instances; uses `kubernetes-client/python` async support (`kubernetes_asyncio` not needed — sync client in thread executor is sufficient for read-only ops at this scale)
- K8s client initialization is lazy (first invocation) to avoid startup failure when not in-cluster
- alternatives: raw httpx to K8s API — rejected (more manual work, no schema support); kubectl subprocess — rejected (harder to secure, unstructured output)

### R-4: Tool invocation API routes

- affected files: `products/tool-gateway/src/api_gateway/api/routes/tools.py`, `products/tool-gateway/src/api_gateway/app.py`
- approach: new APIRouter mounted at `/api/v2/tools`; invoke route delegates to `gateway_service.invoke_tool()` which orchestrates policy → dispatch → audit
- auth is handled by the existing middleware (routes are under `/api/v2/`)

### R-5: Policy bundle extension

- affected files: `shared/shared-contracts/policies/policy-default.yaml`, `products/tool-gateway/src/api_gateway/policies/policy-default.yaml`
- approach: add one rule `allow-operators-tools` granting `tools:invoke` to `platform-admin`, `operator`, `developer` at priority 100
- `read-only-observer` excluded — tool access is an operational capability

### R-6: Agent-platform Toolkit integration

- affected files: `products/agent-platform/src/agent_service/tools/__init__.py`, `tools/gateway_tools.py`, `runtime_kernel.py`, `runtime_settings.py`
- approach: at agent build time, fetch tool list from gateway; create a closure per tool that POSTs to `/api/v2/tools/invoke`; register closures with AgentScope `Toolkit`
- identity context is passed from the session (user_name available in kernel); request_id generated per invocation
- graceful degradation: if gateway unreachable, log warning, proceed without tools

### R-7: Dev overlay RBAC and configuration

- affected files: `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/rbac.yaml`, `api-gateway-deployment.yaml`, `runtime-config.env`, agent-platform `runtime-config.env`, `base/kustomization.yaml`
- approach: dedicated ServiceAccount `api-gateway` with a namespace-scoped Role granting read-only access to pods, events, pods/log

## Sequencing And Dependencies

1. Shared contracts (schemas + README) — depends on nothing
2. Tool-gateway base + registry — depends on stage 1 (result shape)
3. Tool-gateway K8s connector — depends on stage 2
4. Tool-gateway routes + service + policy — depends on stages 2-3
5. Tool-gateway tests — depends on stage 4
6. Agent-platform toolkit wiring — depends on stage 4 (API shape)
7. Agent-platform tests — depends on stage 6
8. Dev overlay RBAC + config — depends on stage 4
9. Full verification + docs — depends on all

## Test Strategy

- unit tests: registry CRUD, K8s connector with mocked client, tool invoke endpoint (policy allow/deny, unknown tool, K8s error), agent toolkit registration
- contract tests: tool-result serialization matches schema shape
- integration / overlay validation: `kustomize build` renders cleanly with RBAC resources

## Rollout And Migration

- `GATEWAY_K8S_ENABLED` defaults to `false` — no behavior change until explicitly enabled
- `TOOL_GATEWAY_URL` unset by default — agent builds with empty Toolkit (existing behavior)
- no database migrations, no breaking API changes
- rollback: unset env vars to disable tools entirely
