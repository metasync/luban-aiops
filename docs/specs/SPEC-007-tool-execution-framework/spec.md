# SPEC-007: Read-Only Tool Execution Framework

## Status

- status: `draft`
- owner: workspace maintainers
- created: 2026-07-30
- release slice: `Release 1` (read-only operations copilot)
- related ADRs: ADR-0002 (AgentScope runtime kernel), ADR-0003 (platform-owned agent service contract)

## Summary

Deliver the end-to-end tool execution path so the AgentScope LLM kernel can invoke read-only Kubernetes tools through the tool-gateway, with policy enforcement, structured evidence responses, and audit logging. This is the R1 vertical slice that transforms the platform from a chat interface into an operations copilot that provides grounded, evidence-backed answers about live infrastructure.

## Motivation

Release 0 delivered a functioning platform: authenticated portal, streaming chat, session durability, and deny-by-default policy. But the agent cannot observe infrastructure — it can only converse. Operators asking "what's wrong with my pods?" get a language-model answer with no grounding in actual cluster state.

The delivery roadmap (R1: Read-Only Operations Copilot) requires:

- service health query flow
- read-only Kubernetes access
- evidence-backed responses
- audit for read-only tool access

The reference architecture (§6 Tool Gateway Layer) designates tool-gateway as the "normalized integration surface between agents and external systems," responsible for wrapping external systems in approved tool contracts, enforcing schema validation, annotating tools with risk metadata, and separating read-only tools from action tools.

This spec delivers the first concrete implementation of that layer.

## Requirements

### R-1: Tool execution contract in shared-contracts

The tool invocation request and structured result envelope are defined as shared contracts so all platform services agree on the wire format.

Acceptance criteria:

- `tool-invocation.schema.json` defines: `tool_name` (string, required), `parameters` (object, tool-specific), `identity_context` (object, forwarded from gateway auth), `request_id` (string, required)
- `tool-result.schema.json` defines: `tool_name` (string), `status` (`success` | `error` | `denied`), `data` (object — tool-specific payload), `evidence` (object: `executed_at` ISO-8601, `duration_ms` integer, `risk_level` string, `source_system` string), `error` (object or null: `code` string, `message` string)
- both schemas are published in `shared/shared-contracts/schemas/`
- `shared/shared-contracts/README.md` documents the tool contract and naming convention (`<system>.<verb>_<noun>`, e.g. `k8s.list_pods`)

### R-2: Tool registry and base abstraction in tool-gateway

A lightweight in-process registry holds tool definitions and dispatches invocations.

Acceptance criteria:

- `ToolDefinition` dataclass captures: `name`, `description`, `risk_level` (`read` | `write` | `admin`), `category` (e.g. `kubernetes`), `parameters_schema` (JSON Schema dict)
- `BaseTool` abstract class defines `async execute(parameters: dict, identity: dict) -> ToolResult`
- `ToolRegistry` supports: `register(tool)`, `get(name) -> BaseTool | None`, `list_definitions() -> list[ToolDefinition]`
- registry is instantiated at startup and populated from enabled connectors
- unknown tool name returns a structured `error` result (not an unhandled exception)

### R-3: Kubernetes read-only connector

The first concrete connector provides four read-only Kubernetes operations using the official `kubernetes-client/python` library.

Acceptance criteria:

- tools registered: `k8s.list_pods`, `k8s.get_pod`, `k8s.get_events`, `k8s.get_pod_logs`
- `k8s.list_pods` parameters: `namespace` (string, optional — defaults to configured namespace), `label_selector` (string, optional)
- `k8s.get_pod` parameters: `name` (string, required), `namespace` (string, optional)
- `k8s.get_events` parameters: `namespace` (string, optional), `field_selector` (string, optional — e.g. `involvedObject.name=my-pod`)
- `k8s.get_pod_logs` parameters: `name` (string, required), `namespace` (string, optional), `container` (string, optional), `tail_lines` (integer, optional, default 100, max 1000)
- connector uses in-cluster config (`kubernetes.config.load_incluster_config()`) when running in K8s; falls back to kubeconfig (`load_kube_config()`) for local development
- when neither config source is available, tools return a structured `error` result with code `K8S_NOT_CONFIGURED`
- all operations are namespace-scoped; no cluster-wide list/watch
- `GATEWAY_K8S_ENABLED` (bool, default `false`) gates connector registration
- `GATEWAY_K8S_NAMESPACE` (string, optional) sets the default namespace

### R-4: Tool invocation API routes

Tool-gateway exposes REST endpoints for tool discovery and invocation.

Acceptance criteria:

- `GET /api/v2/tools` returns the list of registered `ToolDefinition` objects (name, description, risk_level, category, parameters_schema)
- `POST /api/v2/tools/invoke` accepts a `tool-invocation` body, evaluates policy, dispatches to the registry, and returns a `tool-result`
- both routes require authentication (existing gateway auth middleware)
- policy action for invocation is `tools:invoke`; the existing policy engine evaluates it before dispatch
- a policy denial returns `tool-result` with `status: "denied"` and HTTP 403
- invocation emits a structured audit log entry: `tool_invoked` with tool_name, status, duration_ms, user_id, request_id

### R-5: Policy bundle extension

The default policy bundle grants `tools:invoke` to operational roles.

Acceptance criteria:

- `shared/shared-contracts/policies/policy-default.yaml` adds a rule granting `tools:invoke` to `platform-admin`, `operator`, and `developer`
- `read-only-observer` is NOT granted `tools:invoke` (tool access requires an operational role)
- the gateway's bundled policy copy is updated in sync
- existing tests covering policy sync continue to pass

### R-6: Agent-platform Toolkit integration

The AgentScope kernel registers gateway-backed tools so the LLM can autonomously decide when to call them.

Acceptance criteria:

- `RuntimeSettings` gains `tool_gateway_url: str | None` (env: `TOOL_GATEWAY_URL`)
- when `tool_gateway_url` is configured, `_build_agent()` fetches `GET /api/v2/tools` from the gateway at agent creation and registers each tool as an AgentScope Toolkit function
- each toolkit function calls `POST /api/v2/tools/invoke` with the tool name, LLM-provided parameters, and the session's identity context
- when `tool_gateway_url` is not configured, the agent builds with an empty Toolkit (existing behavior preserved)
- tool fetch failure at agent creation logs a warning and proceeds with an empty Toolkit (graceful degradation)

### R-7: Dev overlay RBAC and configuration

The dev-k8s overlay grants the tool-gateway ServiceAccount read-only Kubernetes API access.

Acceptance criteria:

- a `ServiceAccount`, `Role`, and `RoleBinding` are defined in `dev-k8s/base/tool-gateway/rbac.yaml`
- the Role grants: `get`, `list` on `pods`, `events`, `pods/log` in the `dev-luban-aiops` namespace
- the tool-gateway Deployment references the ServiceAccount
- `runtime-config.env` sets `GATEWAY_K8S_ENABLED=true` and `GATEWAY_K8S_NAMESPACE=dev-luban-aiops`
- agent-platform `runtime-config.env` sets `TOOL_GATEWAY_URL=http://api-gateway.dev-luban-aiops.svc:8080`
- `kustomize build` renders without errors

## Non-Goals

- write or mutating Kubernetes operations (R4: Approval-Gated Bounded Actions)
- approval workflow for tool invocations (R4)
- MCP server/client integration (R5 or later)
- isolated execution workers for risky tools (R4)
- multi-cluster or cluster-wide access (future)
- observability-platform connectors (Prometheus, Grafana, Elastic) — separate follow-up spec within R1
- UI evidence panels (portal changes deferred; tool results are returned in chat stream for now)

## Impact

- products touched: `products/tool-gateway/`, `products/agent-platform/`, `shared/platform-ops/gitops/dev-k8s/`
- contracts touched: `shared/shared-contracts/schemas/tool-invocation.schema.json`, `shared/shared-contracts/schemas/tool-result.schema.json`, `shared/shared-contracts/policies/policy-default.yaml`
- identity / policy / audit / execution safety impact: new `tools:invoke` policy action; audit log for every tool invocation; read-only RBAC boundary
- living state docs to update on delivery: `products/tool-gateway/README.md`, `products/agent-platform/README.md`, `shared/platform-ops/README.md`, `CHANGELOG.md`

## Open Questions

(none — all decisions resolved during planning)

## Changelog

- 2026-07-30: created as `draft`
