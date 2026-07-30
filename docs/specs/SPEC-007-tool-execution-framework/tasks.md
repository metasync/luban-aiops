# SPEC-007 Tasks: Read-Only Tool Execution Framework

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Tool execution contract in shared-contracts

- [x] Create `tool-invocation.schema.json` (`shared/shared-contracts/schemas/`)
- [x] Create `tool-result.schema.json` (`shared/shared-contracts/schemas/`)
- [x] Document tool contract and naming convention in `shared/shared-contracts/README.md`
- [ ] Bind both schemas in `test_contracts.py` so gateway code cannot drift from them

## R-2: Tool registry and base abstraction in tool-gateway

- [x] Create `tools/__init__.py` package (`products/tool-gateway/src/api_gateway/tools/`)
- [x] Implement `ToolDefinition`, `ToolResult`, `BaseTool` in `tools/base.py`
- [x] Implement `ToolRegistry` in `tools/registry.py`
- [x] Add `get_tool_registry` dependency provider (`products/tool-gateway/src/api_gateway/core/dependencies.py`)

## R-3: Kubernetes read-only connector

- [x] Add `kubernetes` dependency to `pyproject.toml` (`products/tool-gateway/`)
- [x] Implement `KubernetesConnector` with 4 tools in `tools/k8s_connector.py`
- [x] Add `k8s_enabled` and `k8s_namespace` settings to `core/config.py`
- [ ] Decide whether `namespace` may exceed `GATEWAY_K8S_NAMESPACE` (today only K8s RBAC constrains it — spec Q-3 neighbour)

## R-4: Tool invocation API routes

- [x] Create `api/routes/tools.py` with `GET /api/v2/tools` and `POST /api/v2/tools/invoke`
- [x] Register tools router in `app.py`
- [x] Implement `invoke_tool()` orchestration in `services/gateway_service.py`
- [ ] Require authentication on `GET /api/v2/tools` (blocked on spec Q-2)

## R-5: Policy bundle extension

- [x] Add `tools:invoke` rule to `shared/shared-contracts/policies/policy-default.yaml`
- [x] Sync gateway bundled policy copy (`products/tool-gateway/src/api_gateway/policies/policy-default.yaml`)

## R-6: Agent-platform Toolkit integration

- [x] Add `tool_gateway_url` to `RuntimeSettings` (`products/agent-platform/src/agent_service/runtime_settings.py`)
- [x] Create `tools/__init__.py` and `tools/gateway_tools.py` (`products/agent-platform/src/agent_service/tools/`)
- [x] Wire toolkit registration into `_build_agent()` in `runtime_kernel.py`
- [ ] Authenticate the loopback call to the gateway (blocked on spec Q-1)
- [ ] Forward the session's identity context on invocation (blocked on spec Q-1)
- [ ] Map gateway HTTP errors to `tool-result` envelopes in `invoke_gateway_tool()`
- [ ] Stop caching an empty Toolkit permanently after a failed discovery

## R-7: Dev overlay RBAC and configuration

- [x] Create `rbac.yaml` with ServiceAccount + Role + RoleBinding (`shared/platform-ops/gitops/dev-k8s/base/tool-gateway/`)
- [x] Update `api-gateway-deployment.yaml` to reference ServiceAccount
- [x] Update tool-gateway `runtime-config.env` with K8s settings
- [x] Update agent-platform `runtime-config.env` with `TOOL_GATEWAY_URL`
- [x] Add `rbac.yaml` to `base/kustomization.yaml` resources
- [x] Verify `kustomize build` renders cleanly

## Tests

- [x] `test_tool_registry.py` — registry CRUD, lookup, unknown tool (`products/tool-gateway/tests/`)
- [x] `test_tool_invoke.py` — invoke endpoint: success, denied, unknown, raising tool, missing registry (`products/tool-gateway/tests/`)
- [x] `test_k8s_connector.py` — mocked K8s client operations, parameter validation (`products/tool-gateway/tests/`)
- [x] `test_gateway_tools.py` — toolkit registration, invoke forwarding (`products/agent-platform/tests/`)
- [x] `test_runtime_kernel.py` — concurrent `ensure_agent` builds one agent per session
- [ ] end-to-end test of the authenticated agent→gateway→K8s path (blocked on spec Q-1)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified — R-4 and R-6 outstanding
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered` — held at `draft` pending Q-1/Q-2
