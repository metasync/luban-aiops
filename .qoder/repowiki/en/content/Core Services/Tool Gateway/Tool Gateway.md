# Tool Gateway

<cite>
**Referenced Files in This Document**
- [app.py](file://products/tool-gateway/src/tool_gateway/app.py)
- [main.py](file://products/tool-gateway/src/tool_gateway/main.py)
- [registry.py](file://products/tool-gateway/src/tool_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/tool_gateway/tools/base.py)
- [gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [k8s_connector.py](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py)
- [elastic_connector.py](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py)
- [browser_connector.py](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py)
- [incidents_connector.py](file://products/tool-gateway/src/tool_gateway/tools/incidents_connector.py)
- [skills_connector.py](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py)
- [redaction.py](file://products/tool-gateway/src/tool_gateway/tools/redaction.py)
- [audit_emitter.py](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py)
- [policy_engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [test_tool_registry.py](file://products/tool-gateway/tests/test_tool_registry.py)
- [test_tool_invoke.py](file://products/tool-gateway/tests/test_tool_invoke.py)
</cite>

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. Dependency Analysis
7. Performance Considerations
8. Troubleshooting Guide
9. Conclusion

## Introduction
The Tool Gateway is a normalized access layer that exposes external systems through pluggable tool connectors. It centralizes authentication, policy enforcement, parameter validation, output redaction, audit emission, and structured error handling. Built-in connectors provide safe, bounded access to Kubernetes, Elasticsearch, browser automation (web-check flows), incidents, and skills repositories. The gateway enforces risk-tier admission for mutating actions and integrates with the platform’s audit and policy systems to ensure consistent governance across all tool invocations.

## Project Structure
The Tool Gateway service is organized into:
- Application entrypoint and lifecycle management
- API routing and request orchestration
- Tool registry and base abstractions
- Connector implementations per system
- Policy engine and token verification
- Audit emission and observability
- Configuration and runtime settings

```mermaid
graph TB
A["FastAPI app<br/>lifespan"] --> B["ToolRegistry"]
A --> C["GatewayService<br/>invoke_tool()"]
C --> D["PolicyEngine<br/>evaluate()"]
C --> E["AuditEmitter<br/>emit_audit_event()"]
C --> F["Redaction<br/>redact_result()"]
B --> G["KubernetesConnector"]
B --> H["ElasticConnector"]
B --> I["BrowserConnector"]
B --> J["IncidentsConnector"]
B --> K["SkillsConnector"]
```

**Diagram sources**
- [app.py:19-142](file://products/tool-gateway/src/tool_gateway/app.py#L19-L142)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [policy_engine.py:299-355](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L299-L355)
- [audit_emitter.py:67-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L67-L98)
- [redaction.py:126-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L126-L151)

**Section sources**
- [app.py:19-142](file://products/tool-gateway/src/tool_gateway/app.py#L19-L142)
- [main.py:1-9](file://products/tool-gateway/src/tool_gateway/main.py#L1-L9)

## Core Components
- ToolRegistry: In-process lookup and dispatch; enforces risk-tier admission at registration time and wraps execution errors into structured results.
- BaseTool and ToolDefinition: Abstract interface and metadata schema for tools, including risk_level and parameters_schema.
- GatewayService: Orchestrates identity resolution, policy checks, tool dispatch, redaction, audit emission, and response mapping.
- PolicyEngine: Loads and evaluates policy bundles; deny-by-default semantics with explicit allow/deny and require_approval outcomes.
- Redaction: Deterministic output sanitization using value patterns and sensitive key lists; fail-closed on overflow.
- AuditEmitter: Fire-and-forget durable audit events to the audit service; non-blocking and failure-tolerant.
- Config: Centralized environment-driven configuration for connectors, policy, auth, and feature flags.

**Section sources**
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [gateway_service.py:61-156](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L61-L156)
- [policy_engine.py:254-355](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L355)
- [redaction.py:1-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L1-L151)
- [audit_emitter.py:1-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L1-L98)
- [config.py:32-190](file://products/tool-gateway/src/tool_gateway/core/config.py#L32-L190)

## Architecture Overview
The invocation path enforces security and safety at every stage:
- Identity verification via local JWT verification or synthetic dev identity when configured.
- Policy evaluation for tools:invoke and tools:mutate based on roles and loaded bundle.
- Risk-tier gating prevents mutating tools from executing unless explicitly admitted.
- Tool dispatch through the registry with structured error envelopes.
- Output redaction before response and audit emission.
- Durable audit trail via fire-and-forget emission.

```mermaid
sequenceDiagram
participant Client as "Caller"
participant Gateway as "FastAPI App"
participant Service as "GatewayService.invoke_tool"
participant Policy as "PolicyEngine.evaluate"
participant Registry as "ToolRegistry.invoke"
participant Connector as "Connector.execute"
participant Redact as "Redaction"
participant Audit as "AuditEmitter"
Client->>Gateway : POST /api/v2/tools/invoke
Gateway->>Service : resolve_request_identity + enforce_policy
Service->>Policy : evaluate("tools : invoke")
Policy-->>Service : decision
alt denied
Service-->>Client : 403 {status : "denied"}
else allowed
Service->>Registry : invoke(tool_name, parameters, identity)
Registry->>Connector : execute(parameters, identity)
Connector-->>Registry : ToolResult
Registry-->>Service : ToolResult
Service->>Redact : redact_result(result)
Redact-->>Service : redacted result + stats
Service->>Audit : emit_audit_event(...)
Service-->>Client : JSONResponse(status_code)
end
```

**Diagram sources**
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [policy_engine.py:299-355](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L299-L355)
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)
- [redaction.py:126-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L126-L151)
- [audit_emitter.py:67-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L67-L98)

## Detailed Component Analysis

### Tool Registry and Base Abstraction
- ToolRegistry validates risk_level against a fixed vocabulary and refuses mutating tools unless allow_mutating is enabled.
- Registry.invoke returns structured ToolResult for both unknown tools and exceptions, ensuring callers always receive a consistent envelope.
- BaseTool defines the contract: definition and async execute(parameters, identity).

```mermaid
classDiagram
class BaseTool {
+definition : ToolDefinition
+execute(parameters, identity) ToolResult
}
class ToolDefinition {
+name : string
+description : string
+risk_level : string
+category : string
+parameters_schema : dict
+to_dict() dict
}
class ToolResult {
+tool_name : string
+status : string
+data : dict|None
+evidence : dict
+error : dict|None
+to_dict() dict
}
class ToolRegistry {
-_tools : dict
-_allow_mutating : bool
+register(tool) void
+get(name) BaseTool|None
+list_definitions() list
+invoke(name, parameters, identity) ToolResult
}
BaseTool <|-- KubernetesConnector
BaseTool <|-- ElasticConnector
BaseTool <|-- BrowserConnector
BaseTool <|-- IncidentsConnector
BaseTool <|-- SkillsConnector
ToolRegistry --> BaseTool : "dispatches"
```

**Diagram sources**
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)

**Section sources**
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [test_tool_registry.py:56-172](file://products/tool-gateway/tests/test_tool_registry.py#L56-L172)

### Kubernetes Connector
- Provides read-only tools: k8s.list_pods, k8s.get_pod, k8s.get_events, k8s.get_pod_logs.
- Offers one bounded mutating tool: k8s.delete_pod (write risk), only registered when mutating tools are admitted.
- Uses in-cluster config or kubeconfig; returns structured K8S_NOT_CONFIGURED when unavailable.
- Parameter validation includes clamping tail_lines and enforcing required fields.

```mermaid
flowchart TD
Start(["k8s.get_pod_logs"]) --> CheckConfig{"K8s client configured?"}
CheckConfig --> |No| ErrorCfg["Return K8S_NOT_CONFIGURED"]
CheckConfig --> |Yes| ValidateParams["Validate name, container, tail_lines"]
ValidateParams --> Invalid{"Valid?"}
Invalid --> |No| ErrorParam["Return INVALID_PARAMETERS"]
Invalid --> |Yes| Exec["Run sync call in executor"]
Exec --> Success["Return success with logs"]
Exec --> ApiError["Map ApiException -> POD_NOT_FOUND/K8S_PERMISSION_DENIED/K8S_API_ERROR"]
```

**Diagram sources**
- [k8s_connector.py:41-92](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L41-L92)
- [k8s_connector.py:376-518](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L376-L518)

**Section sources**
- [k8s_connector.py:41-518](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L41-L518)

### Elasticsearch Connector
- Read-only tools: elastic.search_logs, elastic.get_service_health, elastic.get_active_alerts.
- Supports API-key or basic auth; verifies connectivity at initialization.
- Parameter coercion clamps time ranges and result limits to safe bounds.

```mermaid
flowchart TD
Start(["elastic.search_logs"]) --> EnsureClient{"Client ready?"}
EnsureClient --> |No| ErrNotCfg["Return ELASTIC_NOT_CONFIGURED"]
EnsureClient --> |Yes| CoerceParams["Coerce time_range_minutes, max_results"]
CoerceParams --> Valid{"Valid?"}
Valid --> |No| ErrParam["Return INVALID_PARAMETERS"]
Valid --> |Yes| Query["Execute search query"]
Query --> Ok["Return hits, total, query metadata"]
Query --> ConnErr["Return ELASTIC_CONNECTION_ERROR"]
```

**Diagram sources**
- [elastic_connector.py:40-103](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L40-L103)
- [elastic_connector.py:287-379](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L287-L379)

**Section sources**
- [elastic_connector.py:40-535](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L40-L535)

### Browser Connector
- Bounded web-check surface over Chromium sidecar via CDP with session pooling.
- Origin allowlist enforcement; flow binding validates skill declarations and risk_class.
- Interaction guards prevent off-origin navigation and enforce step budgets; read captures re-check live origin.
- Credential sets resolved from secret-mounted files; screenshots mask password-tier values.
- Write-tier tools include web.click, web.type, web.select, web.press_key, web.upload_file, web.evaluate; read-tier includes web.navigate, web.snapshot, web.screenshot, web.fill_credential, web.extract, web.wait_for, web.hover, web.scroll, web.switch_frame.

```mermaid
sequenceDiagram
participant Caller as "Caller"
participant Browser as "BrowserConnector"
participant Pool as "BrowserSessionPool"
participant Page as "Page/Frame"
Caller->>Browser : web.navigate(url, skill_id?)
Browser->>Pool : get_or_create(session_key)
Pool-->>Browser : BrowserSessionEntry
Browser->>Browser : is_origin_allowed(url)
alt skill_id provided
Browser->>Browser : fetch_skill(skill_id)
Browser->>Browser : bind_flow(entry, skill_id, url, skill)
end
Browser->>Page : goto(url)
Page-->>Browser : active_target.url
Browser->>Browser : gate_capture() for snapshots/screenshots
Browser-->>Caller : ToolResult(evidence URL masked)
```

**Diagram sources**
- [browser_connector.py:315-399](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L315-L399)
- [browser_connector.py:425-531](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L425-L531)
- [browser_connector.py:655-698](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L655-L698)
- [browser_connector.py:730-800](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L730-L800)

**Section sources**
- [browser_connector.py:1-800](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L1-L800)

### Incidents Connector
- Read-only access to incident-service: incidents.list, incidents.get.
- Validates incident_id pattern and filters by status/severity/source with bounded limits.
- Maps upstream HTTP errors to structured codes like INCIDENT_NOT_FOUND.

**Section sources**
- [incidents_connector.py:68-339](file://products/tool-gateway/src/tool_gateway/tools/incidents_connector.py#L68-L339)

### Skills Connector
- Read-only access to skills-hub: skills.search, skills.get, skills.list.
- Enforces namespaced skill_id pattern and projects stable match/list keys.
- Forwards request_id for downstream usage audit correlation.

**Section sources**
- [skills_connector.py:71-419](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py#L71-L419)

### Invocation Lifecycle and Error Handling
- Identity resolution supports bearer tokens and synthetic dev identity when configured.
- Policy enforcement denies without identity or matching allow rules; mutating tools additionally require tools:mutate.
- Registry.invoke catches exceptions and returns TOOL_EXECUTION_ERROR with evidence.
- Redaction applies deterministic masking and fails closed on overflow; audit events emitted for all outcomes.

```mermaid
flowchart TD
Req["Incoming request"] --> Auth["Resolve identity"]
Auth --> PolicyCheck{"tools:invoke allowed?"}
PolicyCheck --> |No| Deny["403 denied"]
PolicyCheck --> |Yes| MutateCheck{"Risk level != read?"}
MutateCheck --> |Yes| MutatePolicy{"tools:mutate allowed?"}
MutatePolicy --> |No| MutDeny["403 denied"]
MutatePolicy --> |Yes| Dispatch["Registry.invoke"]
MutateCheck --> |No| Dispatch
Dispatch --> Result["ToolResult"]
Result --> Redact["Redaction check"]
Redact --> Overflow{"Overflow?"}
Overflow --> |Yes| Withhold["REDACTION_OVERFLOW"]
Overflow --> |No| Emit["Emit audit event"]
Emit --> Resp["JSONResponse"]
```

**Diagram sources**
- [gateway_service.py:61-156](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L61-L156)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)
- [redaction.py:126-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L126-L151)

**Section sources**
- [gateway_service.py:61-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L61-L376)
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)
- [test_tool_invoke.py:184-549](file://products/tool-gateway/tests/test_tool_invoke.py#L184-L549)

### Credential Management and Security
- Browser credential sets loaded from a secret-mounted file path; never inline.
- Sensitive query parameters masked in reported URLs for evidence.
- Screenshots mask password-tier values to avoid leaking secrets.
- All connector credentials are passed via configuration and never exposed in results or audit payloads.

**Section sources**
- [browser_connector.py:123-148](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L123-L148)
- [browser_connector.py:174-257](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L174-L257)
- [config.py:63-73](file://products/tool-gateway/src/tool_gateway/core/config.py#L63-L73)

### Integration with Audit and Policy Systems
- PolicyEngine loads bundled rules, computes content fingerprint, and evaluates actions with deny-by-default semantics.
- AuditEmitter emits durable events asynchronously; failures do not degrade the tool path.
- GatewayService records metrics for policy decisions, redaction spans, and token verification outcomes.

**Section sources**
- [policy_engine.py:254-355](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L355)
- [audit_emitter.py:29-98](file://products/tool-gateway/src/tool_gateway/services/audit_emitter.py#L29-L98)
- [gateway_service.py:32-59](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L32-L59)

## Dependency Analysis
- Application wiring: app creates registry and optional browser connector; lifespan starts/stops browser pool.
- Connectors depend on external clients (kubernetes, elasticsearch, httpx) and register tools conditionally based on configuration.
- GatewayService depends on policy engine, token verifier, redaction, and audit emitter.

```mermaid
graph LR
App["app.create_app"] --> Reg["ToolRegistry"]
App --> Browser["BrowserConnector (optional)"]
Reg --> K8s["KubernetesConnector"]
Reg --> ES["ElasticConnector"]
Reg --> Br["BrowserConnector"]
Reg --> Inc["IncidentsConnector"]
Reg --> Sk["SkillsConnector"]
GS["GatewayService"] --> PE["PolicyEngine"]
GS --> AE["AuditEmitter"]
GS --> RD["Redaction"]
```

**Diagram sources**
- [app.py:19-142](file://products/tool-gateway/src/tool_gateway/app.py#L19-L142)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)

**Section sources**
- [app.py:19-142](file://products/tool-gateway/src/tool_gateway/app.py#L19-L142)

## Performance Considerations
- Async execution: Connectors run blocking calls in executors to avoid blocking the event loop.
- Connection pooling: Browser sessions pooled with TTL and max sessions; Elasticsearch client initialized once per connector instance.
- Parameter bounds: Time ranges, result limits, and log tail sizes are clamped to prevent resource exhaustion.
- Redaction overhead: Redaction runs once per result; overflow detection prevents excessive processing.
- Observability: Metrics recorded for policy decisions, redaction spans, token verification, and audit emissions.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and diagnostics:
- Authentication failures: Verify bearer token audience and issuer; check token expiration and JWKS availability.
- Policy denials: Inspect matched rule IDs and reasons; confirm roles and actions align with policy bundle.
- Unknown tools: Ensure tool registration and risk-tier admission; verify tool name matches definition.
- Upstream connectivity: Connectors return structured errors (e.g., K8S_NOT_CONFIGURED, ELASTIC_NOT_CONFIGURED, UPSTREAM_ERROR); check configuration and network reachability.
- Browser flow deviations: Off-origin navigation or stale flow provenance triggers specific denial codes; navigate back to bound target or re-bind flow.
- Redaction overflow: If too much of the result appears sensitive, outputs are withheld; tighten parameters or reduce payload size.

**Section sources**
- [gateway_service.py:61-156](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L61-L156)
- [k8s_connector.py:41-92](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L41-L92)
- [elastic_connector.py:40-103](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L40-L103)
- [browser_connector.py:533-698](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L533-L698)
- [redaction.py:126-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L126-L151)
- [test_tool_invoke.py:184-549](file://products/tool-gateway/tests/test_tool_invoke.py#L184-L549)

## Conclusion
The Tool Gateway provides a secure, extensible, and observable framework for invoking external tools through standardized connectors. It enforces risk-tier admission, policy-based authorization, robust parameter validation, deterministic output redaction, and durable auditing. Built-in connectors cover Kubernetes, Elasticsearch, browser automation, incidents, and skills repositories, while the registry and base abstractions make it straightforward to add custom connectors with consistent behavior and governance.