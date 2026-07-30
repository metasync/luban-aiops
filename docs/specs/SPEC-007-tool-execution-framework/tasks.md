# SPEC-007 Tasks: Read-Only Tool Execution Framework

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Tool execution contract in shared-contracts

- [ ] Create `tool-invocation.schema.json` (`shared/shared-contracts/schemas/`)
- [ ] Create `tool-result.schema.json` (`shared/shared-contracts/schemas/`)
- [ ] Document tool contract and naming convention in `shared/shared-contracts/README.md`

## R-2: Tool registry and base abstraction in tool-gateway

- [ ] Create `tools/__init__.py` package (`products/tool-gateway/src/api_gateway/tools/`)
- [ ] Implement `ToolDefinition`, `ToolResult`, `BaseTool` in `tools/base.py`
- [ ] Implement `ToolRegistry` in `tools/registry.py`
- [ ] Add `get_tool_registry` dependency provider (`products/tool-gateway/src/api_gateway/core/dependencies.py`)

## R-3: Kubernetes read-only connector

- [ ] Add `kubernetes` dependency to `pyproject.toml` (`products/tool-gateway/`)
- [ ] Implement `KubernetesConnector` with 4 tools in `tools/k8s_connector.py`
- [ ] Add `k8s_enabled` and `k8s_namespace` settings to `core/config.py`

## R-4: Tool invocation API routes

- [ ] Create `api/routes/tools.py` with `GET /api/v2/tools` and `POST /api/v2/tools/invoke`
- [ ] Register tools router in `app.py`
- [ ] Implement `invoke_tool()` orchestration in `services/gateway_service.py`

## R-5: Policy bundle extension

- [ ] Add `tools:invoke` rule to `shared/shared-contracts/policies/policy-default.yaml`
- [ ] Sync gateway bundled policy copy (`products/tool-gateway/src/api_gateway/policies/policy-default.yaml`)

## R-6: Agent-platform Toolkit integration

- [ ] Add `tool_gateway_url` to `RuntimeSettings` (`products/agent-platform/src/agent_service/runtime_settings.py`)
- [ ] Create `tools/__init__.py` and `tools/gateway_tools.py` (`products/agent-platform/src/agent_service/tools/`)
- [ ] Wire toolkit registration into `_build_agent()` in `runtime_kernel.py`

## R-7: Dev overlay RBAC and configuration

- [ ] Create `rbac.yaml` with ServiceAccount + Role + RoleBinding (`shared/platform-ops/gitops/dev-k8s/base/tool-gateway/`)
- [ ] Update `api-gateway-deployment.yaml` to reference ServiceAccount
- [ ] Update tool-gateway `runtime-config.env` with K8s settings
- [ ] Update agent-platform `runtime-config.env` with `TOOL_GATEWAY_URL`
- [ ] Add `rbac.yaml` to `base/kustomization.yaml` resources
- [ ] Verify `kustomize build` renders cleanly

## Tests

- [ ] `test_tool_registry.py` — registry CRUD, lookup, unknown tool (`products/tool-gateway/tests/`)
- [ ] `test_tool_invoke.py` — invoke endpoint: success, denied, unknown, error (`products/tool-gateway/tests/`)
- [ ] `test_k8s_connector.py` — mocked K8s client operations (`products/tool-gateway/tests/`)
- [ ] `test_gateway_tools.py` — toolkit registration, invoke forwarding (`products/agent-platform/tests/`)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
