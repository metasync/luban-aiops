# Credential Management and Security

<cite>
**Referenced Files in This Document**
- [credential_sets.py](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py)
- [redaction.py](file://products/tool-gateway/src/tool_gateway/tools/redaction.py)
- [url_redaction.py](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py)
- [http_connector.py](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py)
- [browser_connector.py](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py)
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [base.py](file://products/tool-gateway/src/tool_gateway/tools/base.py)
- [request_context.py](file://products/tool-gateway/src/tool_gateway/core/request_context.py)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive documentation for the new HTTP connector with reference-based credential sets
- Updated credential injection section to include HTTP Basic authentication via credential sets
- Enhanced URL redaction system documentation with query parameter masking
- Added HTTP-specific security controls and origin validation
- Expanded troubleshooting guide with HTTP connector-specific issues

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
10. Appendices

## Introduction
This document explains how the Tool Gateway manages credentials and prevents sensitive data from leaking in tool outputs. It covers:
- The credential set architecture for browser login flows and HTTP service authentication with reference-based credential resolution.
- The redaction system that detects and masks secrets, tokens, and personal information in tool results.
- Rotation strategies, access controls, audit logging, and best practices for secure credential management.
- HTTP connector capabilities including origin allowlisting, redirect protection, and URL secret masking.

## Project Structure
The Tool Gateway implements credential handling and output sanitization across a focused set of modules:
- Credential sets: lazy-loaded JSON secret file with named sets for both browser login flows and HTTP Basic authentication.
- Redaction: deterministic, code-owned pattern matching and key-based masking applied to every tool result before it leaves the gateway.
- URL redaction: specialized URL masking for query parameters and userinfo components to prevent secret leakage.
- HTTP connector: bounded HTTP tools with strict origin validation, redirect protection, and credential set integration.
- Browser connector: bounded web tools that consume credential sets and mask sensitive query parameters and screenshots.
- Gateway orchestration: policy checks, tool dispatch, redaction, and audit emission at a single choke point.
- Configuration: environment-driven settings controlling redaction behavior, HTTP connectivity, and credential set injection.

```mermaid
graph TB
A["GatewaySettings<br/>config.py"] --> B["CredentialSetStore<br/>credential_sets.py"]
A --> C["Redaction rules<br/>redaction.py"]
A --> D["URL Redaction<br/>url_redaction.py"]
E["HTTP Connector<br/>http_connector.py"] --> B
E --> D
F["BrowserConnector<br/>browser_connector.py"] --> B
F --> D
G["GatewayService.invoke_tool<br/>gateway_service.py"] --> E
G --> F
G --> H["Redact tool output<br/>redaction.py"]
G --> I["Audit events<br/>audit_emitter (external)"]
```

**Diagram sources**
- [config.py:200-240](file://products/tool-gateway/src/tool_gateway/core/config.py#L200-L240)
- [credential_sets.py:30-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L30-L103)
- [redaction.py:24-57](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L24-L57)
- [url_redaction.py:27-41](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L27-L41)
- [http_connector.py:322-360](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L322-L360)
- [browser_connector.py:174-257](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L174-L257)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)

**Section sources**
- [config.py:200-240](file://products/tool-gateway/src/tool_gateway/core/config.py#L200-L240)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)

## Core Components
- **CredentialSetStore**: Loads a JSON file of named credential sets on demand, validates required fields, and reloads automatically when the file changes.
- **Redaction engine**: Applies value-pattern matches (e.g., PEM private keys, JWTs, Bearer/Basic headers, AWS access key IDs) and explicit sensitive key names to replace values with a marker. It also tracks spans and character counts to fail-closed if too much of the payload would be redacted.
- **URL Redaction**: Specialized URL masking for query parameters and userinfo components using a shared vocabulary of secret-bearing parameter names.
- **HTTP Connector**: Provides bounded `http.get` and `http.post` tools with strict origin validation, redirect protection, credential set integration, and response projection with header filtering.
- **Browser Connector**: Provides bounded web.* tools. It uses credential sets for filling credentials and masks secret-bearing URL query parameters and screenshot content to prevent leaks.
- **GatewayService.invoke_tool**: Orchestrates identity resolution, policy enforcement, tool dispatch, redaction, and audit logging. Redaction is applied once, at the gateway boundary, before both response and audit trail.
- **GatewaySettings**: Environment-driven configuration for redaction toggles, overflow thresholds, HTTP connectivity, and credential set paths.

**Section sources**
- [credential_sets.py:30-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L30-L103)
- [redaction.py:24-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L24-L151)
- [url_redaction.py:27-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L27-L91)
- [http_connector.py:322-699](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L322-L699)
- [browser_connector.py:174-257](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L174-L257)
- [config.py:200-240](file://products/tool-gateway/src/tool_gateway/core/config.py#L200-L240)

## Architecture Overview
The Tool Gateway enforces a strict execution pipeline with multiple security layers:
- Identity and policy are resolved first.
- Tools are invoked through a registry; HTTP and browser tools may use credential sets.
- All tool results pass through redaction before being returned or logged.
- Audit events record decisions and outcomes without leaking secrets.

```mermaid
sequenceDiagram
participant Client as "Caller"
participant GW as "GatewayService.invoke_tool"
participant POL as "PolicyEngine"
participant REG as "ToolRegistry"
participant HC as "HttpConnector"
participant BC as "BrowserConnector"
participant RED as "Redaction"
participant UR as "URL Redaction"
participant AUD as "AuditEmitter"
Client->>GW : POST {tool_name, parameters}
GW->>POL : evaluate("tools : invoke")
POL-->>GW : allow/deny
alt deny
GW-->>Client : 403 denied
GW->>AUD : emit policy_decision(deny)
else allow
GW->>REG : invoke(tool_name, parameters, identity)
alt http.get/post
REG->>HC : execute(http.get/post)
HC->>UR : redact_secret_query(url)
HC->>RED : project_response()
HC-->>REG : ToolResult
else web.fill_credential
REG->>BC : execute(web.fill_credential)
BC->>UR : redact_secret_query(url)
BC-->>REG : ToolResult
end
REG-->>GW : ToolResult
GW->>RED : redact_result()
RED-->>GW : redacted ToolResult + stats
alt overflow
GW-->>Client : error (REDACTION_OVERFLOW)
else ok
GW->>AUD : emit tool_invoked(success/error)
GW-->>Client : JSONResponse
end
end
```

**Diagram sources**
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [http_connector.py:389-492](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L389-L492)
- [url_redaction.py:49-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L49-L91)
- [redaction.py:126-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L126-L151)

## Detailed Component Analysis

### Credential Set Architecture
- Named sets: Each entry maps a human-friendly name to a dictionary containing at least username and password strings.
- Lazy loading: The store reads the file only when needed and caches until mtime changes.
- Validation: Only entries with non-empty username and password are accepted; malformed entries are ignored with warnings.
- Rotation: Because the store reloads on file modification, operators can rotate credentials by updating the mounted secret file without restarting the gateway.
- Safety: Names are safe to expose; values never appear in logs or results and flow only into authentication mechanisms.

```mermaid
flowchart TD
Start(["Access CredentialSetStore"]) --> CheckPath{"Path configured?"}
CheckPath --> |No| ReturnNone["Return None/empty"]
CheckPath --> |Yes| Stat["stat(path)"]
Stat --> MtimeOK{"mtime == cached?"}
MtimeOK --> |Yes| UseCache["Use cached sets"]
MtimeOK --> |No| ReadFile["Read JSON file"]
ReadFile --> Validate{"Valid object?<br/>Required fields present?"}
Validate --> |No| Warn["Log warning, keep last good load"]
Validate --> |Yes| BuildSets["Build parsed sets"]
BuildSets --> UpdateCache["Update cache and mtime"]
UpdateCache --> ReturnSets["Return sets"]
```

**Diagram sources**
- [credential_sets.py:30-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L30-L103)

**Section sources**
- [credential_sets.py:30-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L30-L103)

### Reference-Based Credential Injection into Tool Invocations

**Updated** Added support for HTTP connector with reference-based credential sets and proper secret handling.

#### HTTP Connector Credential Resolution
- **Reference-only approach**: HTTP tools accept `credential_set` parameter (name only), never literal secrets.
- **Basic Authentication**: Credential sets resolve to HTTP Basic auth headers server-side.
- **Origin validation**: Requests must target allowlisted origins; loopback, link-local, and multicast addresses are always refused.
- **Redirect protection**: POST requests never follow redirects; GET requests validate each hop against the allowlist.
- **Secret query parameter handling**: POST URLs cannot carry secret-bearing query parameters; GET URLs mask them in responses.

#### Browser Connector Integration
- **Fill credentials**: Browser connector holds a CredentialSetStore instance and resolves named sets at fill time.
- **Parameter binding**: The web.fill_credential tool consumes a named set and injects username/password into the page via Playwright. Values are not serialized into results, snapshots, or evidence.
- **Screenshot protection**: When capturing screenshots, the connector masks filled password values in the DOM before capture to avoid leaking them in images.
- **Query parameter masking**: URLs reported in evidence have secret-bearing query parameters masked so they do not leak into results or audit trails.

```mermaid
sequenceDiagram
participant Caller as "Caller"
participant GW as "GatewayService"
participant HC as "HttpConnector"
participant CS as "CredentialSetStore"
participant BA as "Basic Auth"
participant UR as "URL Redaction"
Caller->>GW : http.get {url, credential_set}
GW->>HC : execute(...)
HC->>CS : get(credential_set)
CS-->>HC : {username, password}
HC->>BA : create BasicAuth(username, password)
HC->>UR : redact_secret_query(url)
Note over HC,BA : Credentials never leave process in plaintext
HC-->>GW : ToolResult (no secrets)
```

**Diagram sources**
- [http_connector.py:361-388](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L361-L388)
- [http_connector.py:389-492](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L389-L492)
- [url_redaction.py:49-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L49-L91)
- [credential_sets.py:47-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L47-L103)

**Section sources**
- [http_connector.py:322-699](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L322-L699)
- [browser_connector.py:174-257](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L174-L257)
- [credential_sets.py:30-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L30-L103)

### Output Redaction System
- Value patterns: Detects and replaces high-confidence secret shapes such as PEM private keys, JWTs, Bearer/Basic authorization values, and AWS-style access key IDs.
- Explicit key list: Replaces string values under known sensitive field names (password, token, secret, api_key, etc.).
- Overflow control: If more than a configured fraction of the payload would be redacted, the gateway returns an error instead of leaking partial secrets.
- Single choke point: Redaction runs once after tool execution and before any response or audit log serialization.

```mermaid
flowchart TD
In["ToolResult"] --> ToDict["Serialize to dict"]
ToDict --> Walk["Walk nodes recursively"]
Walk --> DictNode{"dict?"}
DictNode --> |Yes| KeyCheck{"key in sensitive set<br/>and value is string?"}
KeyCheck --> |Yes| MaskKey["Replace value with marker"]
KeyCheck --> |No| RecurseChild["Recurse child"]
DictNode --> |No| ListNode{"list?"}
ListNode --> |Yes| RecurseList["Recurse items"]
ListNode --> |No| StrNode{"string?"}
StrNode --> |Yes| PatternScan["Apply value patterns"]
StrNode --> |No| Keep["Keep node"]
PatternScan --> Count["Accumulate spans/chars"]
MaskKey --> Count
RecurseChild --> Count
RecurseList --> Count
Count --> Overflow{"fraction > threshold?"}
Overflow --> |Yes| Error["Return error (REDACTION_OVERFLOW)"]
Overflow --> |No| Out["Return redacted result"]
```

**Diagram sources**
- [redaction.py:24-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L24-L151)
- [gateway_service.py:307-335](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L307-L335)

**Section sources**
- [redaction.py:24-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L24-L151)
- [gateway_service.py:307-335](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L307-L335)

### URL Secret Query Redaction
**New** Dedicated URL masking for query parameters and userinfo components.

- **Shared vocabulary**: Uses a centralized list of secret-bearing parameter names (password, token, api_key, etc.) matched case-insensitively.
- **Userinfo masking**: Masks passwords in `scheme://user:password@host` format.
- **Query parameter masking**: Replaces values of secret-bearing parameters with `***` while preserving parameter names.
- **Preservation**: Non-secret bytes are preserved exactly without re-encoding.
- **Cross-connector usage**: Both HTTP and browser connectors import this module for consistent URL masking.

```mermaid
flowchart TD
URL["Input URL"] --> Parse["Parse URL components"]
Parse --> CheckUserinfo{"Has userinfo?"}
CheckUserinfo --> |Yes| MaskUserinfo["Mask password in netloc"]
CheckUserinfo --> |No| CheckQuery["Check query params"]
MaskUserinfo --> CheckQuery
CheckQuery --> SplitQuery["Split query by &"]
SplitQuery --> ForEachParam{"For each param"}
ForEachParam --> CheckSecret{"Is param name secret?"}
CheckSecret --> |Yes| MaskValue["Replace value with ***"]
CheckSecret --> |No| KeepParam["Keep param unchanged"]
MaskValue --> Rebuild["Rebuild URL"]
KeepParam --> Rebuild
Rebuild --> Output["Masked URL"]
```

**Diagram sources**
- [url_redaction.py:49-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L49-L91)

**Section sources**
- [url_redaction.py:27-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L27-L91)
- [http_connector.py:255-303](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L255-L303)

### Access Controls and Risk Tiers
- Policy enforcement: Every invocation is evaluated against the policy bundle; mutating tools additionally require a mutate permission.
- Risk tiers: Tools declare read/write/admin risk levels; write/admin tools cannot be auto-approved and require explicit authorization.
- Browser-specific guards: Origin allowlists, flow binding, step budgets, and deviation guards ensure interactions stay within approved targets.
- HTTP-specific guards: Origin allowlists, redirect protection, and body size limits ensure safe HTTP operations.

```mermaid
classDiagram
class ToolDefinition {
+name
+description
+risk_level
+category
+parameters_schema
}
class BaseTool {
+definition
+execute(parameters, identity)
}
class HttpConnector {
+register_tools(registry)
+_validate_destination(url, allow_origins)
+_resolve_auth(credential_set)
}
class BrowserConnector {
+register_tools(registry)
+is_origin_allowed(url)
+gate_interaction(...)
}
BaseTool <|-- HttpConnector
BaseTool <|-- BrowserConnector
HttpConnector --> ToolDefinition : "uses"
BrowserConnector --> ToolDefinition : "uses"
```

**Diagram sources**
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [http_connector.py:322-360](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L322-L360)
- [browser_connector.py:315-399](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L315-L399)

**Section sources**
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [gateway_service.py:197-291](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L197-L291)
- [http_connector.py:100-181](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L100-L181)
- [browser_connector.py:533-698](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L533-L698)

### Audit Logging and Correlation
- Request correlation: A stable request ID is resolved from headers, tracing, or generated UUIDs to correlate events across services.
- Audit events: Both policy decisions and tool invocations are emitted with subject, roles, tool name, status, duration, risk level, and redaction span counts—without secrets.
- Evidence integrity: Tool results are redacted before audit emission to prevent leakage in durable logs.

```mermaid
sequenceDiagram
participant GW as "GatewayService"
participant RC as "RequestContext"
participant AE as "AuditEmitter"
GW->>RC : resolve_request_id()
RC-->>GW : request_id
GW->>AE : emit policy_decision(deny/success)
GW->>AE : emit tool_invoked(success/error)
Note over GW,AE : No secrets in audit payloads
```

**Diagram sources**
- [request_context.py:8-35](file://products/tool-gateway/src/tool_gateway/core/request_context.py#L8-L35)
- [gateway_service.py:197-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L197-L376)

**Section sources**
- [request_context.py:8-35](file://products/tool-gateway/src/tool_gateway/core/request_context.py#L8-L35)
- [gateway_service.py:197-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L197-L376)

## Dependency Analysis
- Configuration drives behavior:
  - Redaction enabled/disabled and overflow threshold.
  - HTTP connector feature flags, origin allowlist, timeout, and credential set path.
  - Browser feature flags, origin allowlist, session limits, and credential set path.
- CredentialSetStore depends on filesystem availability and JSON validity; it degrades gracefully when unreadable.
- HTTPConnector depends on origin validation, credential set resolution, and URL redaction.
- BrowserConnector depends on the skills service for flow validation, Playwright for browser automation, and URL redaction.
- GatewayService depends on policy engine, token verifier, and audit emitter; it centralizes redaction and audit emission.

```mermaid
graph LR
CFG["GatewaySettings"] --> GW["GatewayService"]
CFG --> HC["HttpConnector"]
CFG --> BC["BrowserConnector"]
HC --> CS["CredentialSetStore"]
HC --> UR["URL Redaction"]
BC --> CS
BC --> UR
GW --> RED["Redaction"]
GW --> AUD["AuditEmitter"]
BC --> SKILLS["Skills Service"]
```

**Diagram sources**
- [config.py:200-240](file://products/tool-gateway/src/tool_gateway/core/config.py#L200-L240)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [http_connector.py:322-360](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L322-L360)
- [browser_connector.py:174-257](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L174-L257)
- [credential_sets.py:30-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L30-L103)
- [url_redaction.py:27-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L27-L91)

**Section sources**
- [config.py:200-240](file://products/tool-gateway/src/tool_gateway/core/config.py#L200-L240)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)

## Performance Considerations
- Redaction cost: Pattern scanning and recursive traversal run once per tool result; keep payloads reasonable and tune overflow thresholds to avoid excessive masking.
- URL redaction cost: URL parsing and query parameter processing occur for every HTTP request and browser navigation; minimal overhead due to efficient string operations.
- Credential set reload: File stat and JSON parse occur only on mtime change; frequent rotations are supported without restarts.
- HTTP connection pooling: HTTP client instances are created per request but benefit from underlying connection reuse.
- Browser concurrency: Each chat session serializes interactions to avoid race conditions on shared page state.

## Troubleshooting Guide
Common issues and diagnostics:
- **Credential sets file unreadable**:
  - Symptom: Warnings about unreadable files; last good load retained.
  - Action: Verify file path, permissions, and JSON structure; ensure each set has non-empty username and password.
- **Redaction overflow**:
  - Symptom: Tool invocation returns an error indicating too much of the result was redacted.
  - Action: Tighten parameters to reduce secret exposure; review tool logic to avoid returning large secret blobs.
- **HTTP origin not allowed**:
  - Symptom: HTTP requests denied due to off-allowlist origin.
  - Action: Add the target origin to `GATEWAY_HTTP_ALLOW_ORIGINS`; verify hostname normalization.
- **HTTP redirect not allowed**:
  - Symptom: POST requests refuse to follow redirects; GET requests halt on off-allowlist redirects.
  - Action: Ensure upstream services don't redirect unexpectedly; configure appropriate redirect handling.
- **Secret query parameters in HTTP URLs**:
  - Symptom: POST requests rejected with secret-bearing query parameters; GET requests mask them in responses.
  - Action: Move secrets to request bodies for POST; rely on automatic masking for GET responses.
- **Unknown credential set**:
  - Symptom: HTTP requests fail with `CREDENTIAL_SET_NOT_FOUND`.
  - Action: Verify credential set name exists in the configured file; check file path configuration.
- **Browser origin not allowed**:
  - Symptom: Navigation or interaction denied due to off-allowlist origin.
  - Action: Add the target origin to the allowlist; ensure flow binding matches the intended target.
- **Secret-bearing query parameters in browser evidence**:
  - Symptom: URLs in results/evidence contain sensitive query values.
  - Action: Ensure the connector's URL masking is active; verify that reported URLs go through the masking function.

**Section sources**
- [credential_sets.py:52-103](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L52-L103)
- [redaction.py:60-73](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L60-L73)
- [gateway_service.py:307-335](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L307-L335)
- [http_connector.py:100-181](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L100-L181)
- [browser_connector.py:174-257](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L174-L257)

## Conclusion
The Tool Gateway centralizes credential management and output sanitization to minimize risk:
- Credentials are stored as named sets in a secret-mounted file and injected safely into both browser sessions and HTTP Basic authentication.
- Reference-based credential resolution ensures secrets never appear as literals in tool parameters or logs.
- Redaction applies deterministic pattern and key-based masking to all tool outputs, with fail-closed overflow protection.
- URL redaction provides specialized masking for query parameters and userinfo components across all connectors.
- HTTP connector adds robust origin validation, redirect protection, and response projection with header filtering.
- Policy enforcement, risk-tier gating, and audit logging provide strong access controls and traceability without leaking secrets.

## Appendices

### Example: Defining Custom Credential Sets
- Create a JSON file with named sets, each containing username and password strings.
- Mount the file into the gateway container and configure the credential sets path via environment.
- Reference the set name in `web.fill_credential` or HTTP tool parameters; values are injected into the respective systems but never logged or returned.
- HTTP connector supports both browser and HTTP credential sets through shared configuration.

**Section sources**
- [credential_sets.py:11-17](file://products/tool-gateway/src/tool_gateway/tools/credential_sets.py#L11-L17)
- [config.py:230-233](file://products/tool-gateway/src/tool_gateway/core/config.py#L230-L233)

### Example: Configuring HTTP Connector
- Enable HTTP connector via `GATEWAY_HTTP_ENABLED=true`.
- Configure allowed origins via `GATEWAY_HTTP_ALLOW_ORIGINS=http://service:8080,http://api:9090`.
- Set timeouts and size limits via `GATEWAY_HTTP_TIMEOUT_MS`, `GATEWAY_HTTP_MAX_RESPONSE_BYTES`, `GATEWAY_HTTP_MAX_REQUEST_BYTES`.
- Configure credential sets via `GATEWAY_HTTP_CREDENTIAL_SETS` or fall back to browser credential sets.

**Section sources**
- [config.py:200-240](file://products/tool-gateway/src/tool_gateway/core/config.py#L200-L240)
- [http_connector.py:322-360](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L322-L360)

### Example: Using Reference-Based Credentials in HTTP Tools
```python
# HTTP GET with credential set
result = await registry.invoke("http.get", {
    "url": "https://api.example.com/data",
    "credential_set": "my-service",
    "timeout_ms": 5000
}, identity)

# HTTP POST with credential set  
result = await registry.invoke("http.post", {
    "url": "https://api.example.com/update",
    "body": {"action": "update", "value": 42},
    "credential_set": "my-service"
}, identity)
```

**Section sources**
- [http_connector.py:556-592](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L556-L592)
- [http_connector.py:654-698](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L654-L698)

### Best Practices for Managing External System Credentials
- Store credentials in secret-mounted files; never inline values in configuration or code.
- Rotate credentials by updating the mounted file; no restart required.
- Limit HTTP origins to trusted targets and configure appropriate allowlists.
- Use reference-based credentials exclusively; never pass literal secrets in tool parameters.
- Rely on policy and risk tiers to restrict mutating actions.
- Monitor audit logs for policy decisions and tool invocations; investigate denials and redaction overflows promptly.
- Configure appropriate timeouts and size limits to prevent resource exhaustion.
- Test credential rotation procedures regularly to ensure seamless updates.