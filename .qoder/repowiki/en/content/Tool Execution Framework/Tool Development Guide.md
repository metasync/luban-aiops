# Tool Development Guide

<cite>
**Referenced Files in This Document**
- [base.py](file://products/tool-gateway/src/tool_gateway/tools/base.py)
- [registry.py](file://products/tool-gateway/src/tool_gateway/tools/registry.py)
- [k8s_connector.py](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py)
- [elastic_connector.py](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py)
- [browser_connector.py](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py)
- [gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [app.py](file://products/tool-gateway/src/tool_gateway/app.py)
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [servicenow_native.py](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py)
- [servicenow_binding.py](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_binding.py)
- [ansible_native.py](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_native.py)
- [ansible_binding.py](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_binding.py)
- [adding-a-tool.md](file://docs/guides/adding-a-tool.md)
- [tool-configuration.md](file://docs/guides/tool-configuration.md)
- [test_tool_registry.py](file://products/tool-gateway/tests/test_tool_registry.py)
- [test_tool_invoke.py](file://products/tool-gateway/tests/test_tool_invoke.py)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive documentation for ServiceNow and Ansible connector configurations
- Updated tool configuration section with new connector examples and activation checklists
- Enhanced architecture diagrams to include ingestion connectors
- Added detailed sections on native REST/Table-API patterns and MCP adapter patterns
- Updated troubleshooting guide with new error codes and configuration requirements

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. New Connector Patterns: ServiceNow and Ansible
7. Dependency Analysis
8. Performance Considerations
9. Troubleshooting Guide
10. Conclusion
11. Appendices

## Introduction
This guide explains how to build custom tools for the Luban AIOPS platform's tool execution framework. It covers the BaseTool abstract interface, ToolDefinition metadata, parameter validation, identity context handling, evidence collection, registration and discovery via the registry, risk levels (read, write, admin), policy integration, testing strategies, and secure integration with external systems. The guide now includes comprehensive coverage of the new ServiceNow and Ansible connector patterns that demonstrate both native REST implementations and MCP adapter approaches.

## Project Structure
Tools live under the tool gateway package and are discovered by name through a central registry. The gateway enforces policy before invoking tools and wraps results with redaction and audit logging. New ingestion connectors follow established patterns for both native REST implementations and MCP adapter patterns.

```mermaid
graph TB
subgraph "Tool Gateway"
GW["Gateway Service"]
REG["ToolRegistry"]
BASE["BaseTool / ToolDefinition / ToolResult"]
K8S["Kubernetes Connector Tools"]
ELA["Elastic Connector Tools"]
BRW["Browser Connector Tools"]
SNOW["ServiceNow Native Connector"]
ANSIBLE["Ansible MCP/Native Connectors"]
INGESTION["Ingestion Connectors"]
end
GW --> REG
REG --> BASE
REG --> K8S
REG --> ELA
REG --> BRW
REG --> SNOW
REG --> ANSIBLE
INGESTION --> SNOW
INGESTION --> ANSIBLE
```

**Diagram sources**
- [gateway_service.py:250-305](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L250-L305)
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [app.py:167-209](file://products/tool-gateway/src/tool_gateway/app.py#L167-L209)

**Section sources**
- [gateway_service.py:250-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L250-L376)
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [app.py:167-209](file://products/tool-gateway/src/tool_gateway/app.py#L167-L209)

## Core Components
- BaseTool: Abstract base class defining the contract every tool must implement.
- ToolDefinition: Immutable metadata describing a tool's name, description, risk level, category, and parameters schema.
- ToolResult: Structured envelope returned by execute(), including status, data, evidence, and optional error.
- ToolRegistry: In-process lookup and dispatch that validates risk levels and gates mutating tools.

Key behaviors:
- Risk levels are validated against a fixed vocabulary: read, write, admin.
- Mutating tools (write/admin) are refused registration unless explicitly allowed at runtime.
- All invocations return a ToolResult; exceptions are wrapped into structured errors.

**Section sources**
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)

## Architecture Overview
The gateway service resolves the target tool, applies policy checks based on risk level, builds an identity context, invokes the registry, then applies redaction and emits audit events. New ingestion connectors integrate seamlessly through the same registry pattern.

```mermaid
sequenceDiagram
participant Client as "Caller"
participant GW as "Gateway Service"
participant POL as "Policy Engine"
participant REG as "ToolRegistry"
participant TOOL as "BaseTool.execute()"
participant RED as "Redaction"
participant AUD as "Audit Emitter"
Client->>GW : POST /api/v2/tools/invoke
GW->>REG : get(tool_name)
alt Target is write/admin
GW->>POL : evaluate("tools : mutate")
POL-->>GW : decision + reason
alt denied
GW-->>Client : 403 {status : "denied", code : "POLICY_DENIED"}
else allowed
GW->>REG : invoke(name, parameters, identity)
REG->>TOOL : execute(parameters, identity)
TOOL-->>REG : ToolResult
REG-->>GW : ToolResult
GW->>RED : redact_result()
RED-->>GW : result or error if overflow
GW->>AUD : emit tool_invoked
GW-->>Client : JSON response
end
else read tool
GW->>REG : invoke(name, parameters, identity)
REG->>TOOL : execute(parameters, identity)
TOOL-->>REG : ToolResult
REG-->>GW : ToolResult
GW->>RED : redact_result()
RED-->>GW : result or error if overflow
GW->>AUD : emit tool_invoked
GW-->>Client : JSON response
end
```

**Diagram sources**
- [gateway_service.py:250-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L250-L376)
- [policy_engine.py:287-315](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L287-L315)
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)
- [base.py:58-105](file://products/tool-gateway/src/tool_gateway/tools/base.py#L58-L105)

## Detailed Component Analysis

### BaseTool, ToolDefinition, ToolResult, and Evidence
- BaseTool requires:
  - definition property returning ToolDefinition
  - async execute(parameters, identity) returning ToolResult
- ToolDefinition fields:
  - name: unique tool identifier used by policy and catalog
  - description: LLM-facing explanation
  - risk_level: one of read, write, admin
  - category: grouping label (e.g., kubernetes, observability, browser)
  - parameters_schema: JSON Schema describing inputs
- ToolResult fields:
  - tool_name, status ("success", "error", "denied"), data, evidence, error
- Evidence envelope:
  - executed_at, duration_ms, risk_level, source_system
- Helpers:
  - build_evidence(risk_level, source_system, duration_ms)
  - make_error_result(code, message, risk_level, source_system, duration_ms)
  - make_denied_result(reason, risk_level)

Implementation guidance:
- Always measure duration and attach evidence using build_evidence.
- Never raise from execute(); return structured ToolResult for all failures.
- Use make_error_result for transport and upstream errors; use make_denied_result for policy denials.

**Section sources**
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)

### ToolRegistry: Registration and Discovery
- register(tool):
  - Validates risk_level against the fixed set
  - Refuses write/admin tools unless allow_mutating is enabled
  - Logs warnings for overwrites
- get(name): returns tool instance or None
- list_definitions(): exposes metadata for discovery
- invoke(name, parameters, identity):
  - Unknown tools return TOOL_NOT_FOUND
  - Exceptions during execute are caught and returned as TOOL_EXECUTION_ERROR with correct risk_level and source_system

Discovery flow:
- Connectors call register_tools(registry) to register their tools at startup.
- The gateway lists definitions via list_definitions() for the portal tool catalog.

**Section sources**
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)

### Kubernetes Connector Example
- Provides read-only tools: k8s.list_pods, k8s.get_pod, k8s.get_events, k8s.get_pod_logs
- Provides a bounded mutating tool: k8s.delete_pod (write)
- Uses in-cluster config when available, falls back to kubeconfig; otherwise returns K8S_NOT_CONFIGURED
- Parameter validation:
  - Required fields enforced (e.g., name)
  - tail_lines clamped to [1, MAX_TAIL_LINES]
- Error mapping:
  - 404 -> POD_NOT_FOUND
  - 403 -> K8S_PERMISSION_DENIED
  - Others -> K8S_API_ERROR
- Evidence uses risk_level matching the tool definition

```mermaid
flowchart TD
Start(["execute(k8s.get_pod_logs)"]) --> CheckConfig{"K8s client configured?"}
CheckConfig --> |No| ErrCfg["Return K8S_NOT_CONFIGURED"]
CheckConfig --> |Yes| Validate["Validate 'name' and 'tail_lines'"]
Validate --> Valid{"Valid?"}
Valid --> |No| ErrParam["Return INVALID_PARAMETERS"]
Valid --> |Yes| CallAPI["Call API in executor"]
CallAPI --> Ok{"Success?"}
Ok --> |Yes| BuildRes["Build ToolResult with evidence"]
Ok --> |No| MapErr["Map HTTP status to domain code"]
MapErr --> BuildRes
BuildRes --> End(["Return ToolResult"])
ErrCfg --> End
ErrParam --> End
```

**Diagram sources**
- [k8s_connector.py:376-436](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L376-L436)
- [k8s_connector.py:439-518](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L439-L518)

**Section sources**
- [k8s_connector.py:41-92](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L41-L92)
- [k8s_connector.py:231-276](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L231-L276)
- [k8s_connector.py:376-436](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L376-L436)
- [k8s_connector.py:439-518](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L439-L518)

### Elastic Connector Example
- Provides read-only tools: elastic.search_logs, elastic.get_service_health, elastic.get_active_alerts
- Lazy client initialization; returns ELASTIC_NOT_CONFIGURED when not configured
- Parameter coercion:
  - time_range_minutes clamped to [1, MAX_TIME_RANGE_MINUTES]
  - max_results clamped to [1, MAX_RESULTS]
- Errors map to ELASTIC_CONNECTION_ERROR with evidence duration

**Section sources**
- [elastic_connector.py:40-103](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L40-L103)
- [elastic_connector.py:287-379](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L287-L379)
- [elastic_connector.py:382-456](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L382-L456)
- [elastic_connector.py:459-535](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L459-L535)

### Browser Connector Example
- Bounded web-check tool surface with explicit read/write tiers:
  - Read tier: web.navigate, web.snapshot, web.screenshot, web.fill_credential, web.extract, web.wait_for, web.hover, web.scroll, web.switch_frame
  - Write tier: web.click, web.type, web.select, web.press_key, web.upload_file, web.evaluate
- Enforcement surfaces:
  - Origin allowlist: empty deny-by-default; redirects off-allowlist halt and error
  - Flow binding + deviation guard: skill_id binds web_target/risk_class; interactions checked against bound origin, risk_class, and step budget
  - Credential sets: secrets resolved at fill time and never appear in results or evidence
- Identity handling:
  - Sessions keyed by chat_session_id (falls back to subject); supports owner→approver identity switch across HITL flows
- Per-call serialization per session ensures safe interaction with shared page state

```mermaid
classDiagram
class BrowserConnector {
+register_tools(registry)
+is_origin_allowed(url) bool
+bind_flow(entry, skill_id, url, skill) ToolResult?
+gate_interaction(entry, tool_name, require_write_class, approval_kind) ToolResult?
+gate_capture(entry, tool_name) ToolResult?
}
class _SessionSerializedTool {
+definition ToolDefinition
+execute(parameters, identity) ToolResult
}
class WebNavigateTool
class WebClickTool
class WebScreenshotTool
BrowserConnector --> WebNavigateTool : "registers"
BrowserConnector --> WebClickTool : "registers"
BrowserConnector --> WebScreenshotTool : "registers"
_SessionSerializedTool --> WebNavigateTool : "wraps"
_SessionSerializedTool --> WebClickTool : "wraps"
_SessionSerializedTool --> WebScreenshotTool : "wraps"
```

**Diagram sources**
- [browser_connector.py:315-399](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L315-L399)
- [browser_connector.py:269-313](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L269-313)
- [browser_connector.py:730-800](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L730-L800)

**Section sources**
- [browser_connector.py:1-95](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L1-L95)
- [browser_connector.py:269-313](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L269-L313)
- [browser_connector.py:315-399](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L315-L399)
- [browser_connector.py:482-598](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L482-L598)
- [browser_connector.py:655-698](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L655-L698)

## New Connector Patterns: ServiceNow and Ansible

### ServiceNow Native REST Connector Pattern
The ServiceNow connector demonstrates a native REST implementation pattern for direct API access without MCP substrate. This pattern is ideal when the target system provides a well-defined REST API but lacks MCP support.

#### Key Characteristics:
- **Native REST Implementation**: Direct HTTP calls to ServiceNow Table API
- **Fixed Table Allowlist**: Gateway-owned table names prevent model injection
- **Field Projection Security**: Response fields are strictly filtered to allowlisted columns
- **Read-Only Operations**: Only GET operations exposed, no mutation capabilities
- **Credential Management**: OAuth2 client credentials through SPEC-068 seam

#### Configuration Structure:
```python
@dataclass(frozen=True)
class ServiceNowReadTool:
    """One gateway-owned read-tool declaration."""
    name: str
    table: str
    op: str  # "list" | "get"
    description: str
    fields: tuple[str, ...]
    parameters_schema: dict
```

#### Security Features:
- **Table Name Validation**: Regex validation prevents path injection
- **sys_id Format Validation**: 32-character hex GUID enforcement
- **Field Projection**: Post-response filtering of sensitive columns
- **Timeout Bounds**: Configurable timeout limits (default 10s, max 30s)
- **Limit Clamping**: Request limits capped to prevent resource exhaustion

**Section sources**
- [servicenow_native.py:106-123](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L106-L123)
- [servicenow_native.py:250-311](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L250-L311)
- [servicenow_binding.py:110-175](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_binding.py#L110-L175)

### Ansible MCP Adapter Pattern
The Ansible connector demonstrates the MCP adapter pattern for integrating with external automation platforms through the Model Context Protocol.

#### Key Characteristics:
- **MCP Client Implementation**: Thin adapter over official `mcp` SDK
- **Server-Agnostic Design**: Works with any MCP-compliant server
- **Admission Control**: Fixed allowlist of server operations
- **Transport Flexibility**: Supports streamable-HTTP and stdio transports
- **Credential Integration**: OAuth2 bearer tokens through credential sets

#### Configuration Structure:
```python
ANSIBLE_ADMITTED_TOOLS: tuple[AdmittedTool, ...] = (
    AdmittedTool(
        server_name="controller.inventories_list",
        name="ansible.list_inventories",
        description="List Ansible inventories with optional name filtering.",
        risk_level="read",
        category=CATEGORY,
        parameters_schema=_NAME_FILTER_SCHEMA,
    ),
    # ... additional tools
)
```

#### Fallback Support:
- **Native Inventory Access**: Direct `ansible-inventory` command execution
- **Topology-Only Results**: Group and host membership without variable values
- **Process Isolation**: Subprocess execution with timeout protection
- **Error Handling**: Structured error codes for missing executables and timeouts

**Section sources**
- [ansible_binding.py:91-176](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_binding.py#L91-L176)
- [ansible_native.py:99-130](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_native.py#L99-L130)
- [ansible_native.py:132-217](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_native.py#L132-L217)

### Connector Registration and Wiring
Both ServiceNow and Ansible connectors follow the established registration pattern in the application lifecycle:

```python
if settings.ansible_mcp_enabled:
    from tool_gateway.ingestion.ansible_binding import build_ansible_mcp_connector
    ansible_connector = build_ansible_mcp_connector(settings)
    ansible_connector.register_tools(registry)
elif settings.ansible_native_enabled:
    from tool_gateway.ingestion.ansible_native import AnsibleNativeConnector
    ansible_connector = AnsibleNativeConnector(...)
    ansible_connector.register_tools(registry)

if settings.servicenow_enabled:
    from tool_gateway.ingestion.servicenow_binding import build_servicenow_connector
    servicenow_connector = build_servicenow_connector(settings)
    servicenow_connector.register_tools(registry)
```

**Section sources**
- [app.py:167-209](file://products/tool-gateway/src/tool_gateway/app.py#L167-L209)

### Policy Integration and Permission Checks
- Gateway enforces:
  - tools:invoke for all tools
  - tools:mutate for write/admin tools
- Policy engine validates rule outcomes and approval blocks; invalid rules cause load-time errors.
- Denied mutations produce 403 responses with POLICY_DENIED and preserve the tool's risk_level in evidence.

```mermaid
flowchart TD
A["Incoming tool invocation"] --> B{"risk_level == read?"}
B --> |Yes| C["Check tools:invoke"]
B --> |No| D["Check tools:mutate"]
C --> E{"Allowed?"}
D --> F{"Allowed?"}
E --> |No| G["Return 403 POLICY_DENIED"]
F --> |No| G
E --> |Yes| H["Invoke tool"]
F --> |Yes| H
```

**Diagram sources**
- [gateway_service.py:250-291](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L250-L291)
- [policy_engine.py:287-315](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L287-L315)

**Section sources**
- [gateway_service.py:250-291](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L250-L291)
- [policy_engine.py:287-315](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L287-L315)

## Dependency Analysis
- Base abstractions define the contract and helpers used by all connectors.
- Registry depends on BaseTool and validates risk levels.
- Connectors depend on BaseTool and optionally on registry.register_tools().
- Gateway service depends on registry and policy engine to enforce permissions.
- New ingestion connectors integrate through the same registry pattern.

```mermaid
graph LR
BASE["base.py"] --> REG["registry.py"]
BASE --> K8S["k8s_connector.py"]
BASE --> ELA["elastic_connector.py"]
BASE --> BRW["browser_connector.py"]
BASE --> SNOW["servicenow_native.py"]
BASE --> ANS["ansible_native.py"]
REG --> GW["gateway_service.py"]
POL["policy_engine.py"] --> GW
INGESTION["ingestion/*"] --> GW
```

**Diagram sources**
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)
- [k8s_connector.py:25-33](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L25-L33)
- [elastic_connector.py:22-30](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L22-L30)
- [browser_connector.py:75-90](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L75-L90)
- [servicenow_native.py:60-69](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L60-L69)
- [ansible_native.py:37-44](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_native.py#L37-L44)
- [gateway_service.py:250-305](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L250-L305)
- [policy_engine.py:287-315](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L287-L315)

**Section sources**
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)
- [gateway_service.py:250-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L250-L376)

## Performance Considerations
- Measure execution time accurately and report duration_ms in evidence.
- Run blocking I/O in executors to avoid blocking the event loop (see connector examples).
- Clamp large or unbounded parameters (e.g., tail_lines, max_results) to prevent resource exhaustion.
- Redaction runs once at the gateway choke point; keep payloads minimal to reduce processing overhead.
- For MCP adapters, consider connection pooling and session reuse for high-frequency calls.
- Native REST connectors should implement proper timeout handling and retry logic.

## Troubleshooting Guide
Common issues and resolutions:
- TOOL_NOT_FOUND: Ensure the tool is registered and the name matches exactly.
- TOOL_EXECUTION_ERROR: Inspect logs; ensure execute() catches exceptions and returns structured errors.
- POLICY_DENIED: Verify roles and policy grants for tools:mutate on write/admin tools.
- K8S_NOT_CONFIGURED: Provide in-cluster config or kubeconfig.
- ELASTIC_NOT_CONFIGURED: Configure URL and credentials.
- BROWSER_ORIGIN_NOT_ALLOWED/BROWSER_FLOW_ORIGIN_DEVIATED: Navigate to an allowlisted origin and ensure flow binding matches current page.

**New connector-specific issues:**
- SERVICENOW_NOT_CONFIGURED: Set GATEWAY_SERVICENOW_BASE_URL and enable GATEWAY_SERVICENOW_ENABLED.
- SERVICENOW_INVALID_BASE_URL: Ensure base URL is valid http(s) without userinfo.
- SERVICENOW_TIMEOUT: Increase GATEWAY_SERVICENOW_TIMEOUT_MS or investigate network connectivity.
- ANSIBLE_NOT_CONFIGURED: Set GATEWAY_ANSIBLE_INVENTORY_PATH for native mode or configure MCP endpoint.
- ANSIBLE_EXECUTABLE_NOT_FOUND: Ensure ansible-inventory is installed and accessible.
- MCP_TRANSPORT_ERROR: Verify MCP server endpoint and network connectivity.

Evidence and audit:
- Evidence includes risk_level and source_system; use these to trace denials and errors.
- Audit events include tool_invoked and policy_decision with matched_rule_ids.
- New connectors provide target_identity_mode and failure_class attributes for enhanced auditing.

**Section sources**
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)
- [gateway_service.py:250-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L250-L376)
- [k8s_connector.py:439-518](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L439-L518)
- [elastic_connector.py:287-379](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L287-L379)
- [browser_connector.py:730-800](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L730-L800)
- [servicenow_native.py:430-456](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L430-L456)
- [ansible_native.py:151-201](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_native.py#L151-L201)

## Conclusion
To build robust tools for Luban AIOPS:
- Implement BaseTool with a precise ToolDefinition and a resilient execute() method.
- Validate parameters strictly, handle identity safely, and always attach evidence.
- Register tools via connectors and rely on the registry for discovery and risk-tier enforcement.
- Respect risk levels: read needs tools:invoke; write/admin need tools:mutate and produce approval cards.
- Follow the established patterns from Kubernetes, Elastic, Browser, ServiceNow, and Ansible connectors for secure, testable implementations.
- Choose appropriate integration patterns: native REST for direct API access, MCP adapter for protocol-based integrations.

## Appendices

### Step-by-Step: Building a New Connector
1. Create a connector class that owns configuration and registers tools.
2. Define each tool as a subclass of BaseTool with:
   - A clear ToolDefinition (name, description, risk_level, category, parameters_schema)
   - An execute() that validates parameters, calls upstream, and returns ToolResult with evidence
3. Add settings and wire the connector behind a feature flag in app startup.
4. Ensure policy grants match your risk_level (read vs mutate).
5. Add tests covering parameters, transport, upstream errors, success, and registration.
6. Update operator documentation with activation variables and new error codes.

**Section sources**
- [adding-a-tool.md:29-46](file://docs/guides/adding-a-tool.md#L29-L46)
- [adding-a-tool.md:47-203](file://docs/guides/adding-a-tool.md#L47-L203)
- [adding-a-tool.md:212-248](file://docs/guides/adding-a-tool.md#L212-L248)
- [adding-a-tool.md:250-290](file://docs/guides/adding-a-tool.md#L250-L290)

### Testing Tool Implementations
- Unit tests for registry behavior:
  - Registration, listing definitions, invoke success/failure
  - Mutating tool gating and invalid risk_level rejection
- Integration-style tests for invoke endpoint:
  - Authentication required
  - Successful operator invocation with request correlation
  - Discovery exposing risk_level
  - Approver can invoke mutating tool after approval
  - Observer can still invoke read tools

**Section sources**
- [test_tool_registry.py:10-81](file://products/tool-gateway/tests/test_tool_registry.py#L10-L81)
- [test_tool_registry.py:112-144](file://products/tool-gateway/tests/test_tool_registry.py#L112-L144)
- [test_tool_invoke.py:195-231](file://products/tool-gateway/tests/test_tool_invoke.py#L195-L231)
- [test_tool_invoke.py:456-484](file://products/tool-gateway/tests/test_tool_invoke.py#L456-L484)

### Secure Integration Patterns
- Validate and sanitize all LLM-supplied parameters before use.
- Use strict patterns for values interpolated into URLs or queries.
- Prefer least-privilege credentials and scoped tokens for upstream services.
- Keep payloads minimal; project only necessary fields to reduce exposure.
- Rely on gateway redaction; do not log sensitive data in tool outputs.
- For MCP adapters, validate server responses against expected schemas.
- For native REST connectors, implement proper timeout handling and retry logic.

**Section sources**
- [k8s_connector.py:211-226](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L211-L226)
- [elastic_connector.py:250-282](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L250-L282)
- [servicenow_native.py:250-311](file://products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py#L250-L311)
- [ansible_native.py:120-130](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_native.py#L120-L130)
- [adding-a-tool.md:151-167](file://docs/guides/adding-a-tool.md#L151-L167)

### Configuration Reference for New Connectors

#### ServiceNow Configuration Variables:
- `GATEWAY_SERVICENOW_ENABLED`: Enable/disable ServiceNow connector
- `GATEWAY_SERVICENOW_BASE_URL`: ServiceNow instance base URL
- `GATEWAY_SERVICENOW_CREDENTIAL_SET`: Named OAuth2 credential set
- `GATEWAY_SERVICENOW_CREDENTIAL_SETS`: Path to credential sets file
- `GATEWAY_SERVICENOW_TIMEOUT_MS`: HTTP timeout in milliseconds

#### Ansible Configuration Variables:
- `GATEWAY_ANSIBLE_MCP_ENABLED`: Enable/disable MCP connector
- `GATEWAY_ANSIBLE_MCP_TRANSPORT`: Transport type (streamable_http or stdio)
- `GATEWAY_ANSIBLE_MCP_URL`: MCP server endpoint URL
- `GATEWAY_ANSIBLE_MCP_COMMAND`: Command for stdio transport
- `GATEWAY_ANSIBLE_MCP_ARGS`: Arguments for stdio transport
- `GATEWAY_ANSIBLE_MCP_TIMEOUT_MS`: MCP timeout in milliseconds
- `GATEWAY_ANSIBLE_MCP_CREDENTIAL_SET`: Named bearer credential set
- `GATEWAY_ANSIBLE_MCP_CREDENTIAL_SETS`: Path to credential sets file
- `GATEWAY_ANSIBLE_NATIVE_ENABLED`: Enable/disable native inventory connector
- `GATEWAY_ANSIBLE_INVENTORY_PATH`: Path to ansible inventory file
- `GATEWAY_ANSIBLE_NATIVE_EXECUTABLE`: ansible-inventory executable path

**Section sources**
- [config.py:51-69](file://products/tool-gateway/src/tool_gateway/core/config.py#L51-L69)
- [config.py:180-216](file://products/tool-gateway/src/tool_gateway/core/config.py#L180-L216)
- [config.py:480-532](file://products/tool-gateway/src/tool_gateway/core/config.py#L480-L532)