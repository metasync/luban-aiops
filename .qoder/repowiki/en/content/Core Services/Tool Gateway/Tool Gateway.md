# Tool Gateway

<cite>
**Referenced Files in This Document**
- [app.py](file://products/tool-gateway/src/tool_gateway/app.py)
- [main.py](file://products/tool-gateway/src/tool_gateway/main.py)
- [registry.py](file://products/tool-gateway/src/tool_gateway/tools/registry.py)
- [base.py](file://products/tool-gateway/src/tool_gateway/tools/base.py)
- [gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [authorization_service.py](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py)
- [authorizations.py](file://products/tool-gateway/src/tool_gateway/api/routes/authorizations.py)
- [authorization.py](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py)
- [user_delegated_client.py](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py)
- [k8s_connector.py](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py)
- [elastic_connector.py](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py)
- [browser_connector.py](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py)
- [incidents_connector.py](file://products/tool-gateway/src/tool_gateway/tools/incidents_connector.py)
- [skills_connector.py](file://products/tool-gateway/src/tool_gateway/tools/skills_connector.py)
- [http_connector.py](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py)
- [secrets_connector.py](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py)
- [url_redaction.py](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py)
- [redaction.py](file://products/tool-gateway/src/tool_gateway/tools/redaction.py)
- [audit_emitter.py](file://products/tool-gateway/services/audit_emitter.py)
- [policy_engine.py](file://products/tool-gateway/services/policy_engine.py)
- [secret_delivery.py](file://products/tool-gateway/tools/secret_delivery.py)
- [router.py](file://products/tool-gateway/src/tool_gateway/api/router.py)
- [ansible_native.py](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_native.py)
- [mcp_adapter.py](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py)
- [ansible_binding.py](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_binding.py)
- [test_tool_registry.py](file://products/tool-gateway/tests/test_tool_registry.py)
- [test_tool_invoke.py](file://products/tool-gateway/tests/test_tool_invoke.py)
- [test_http_connector.py](file://products/tool-gateway/tests/test_http_connector.py)
- [test_redaction.py](file://products/tool-gateway/tests/test_redaction.py)
- [test_ansible_native.py](file://products/tool-gateway/tests/test_ansible_native.py)
- [test_ansible_mcp_ingestion.py](file://products/tool-gateway/tests/test_ansible_mcp_ingestion.py)
- [test_user_delegated_client.py](file://products/tool-gateway/tests/test_user_delegated_client.py)
- [test_delegated_authorization.py](file://products/tool-gateway/tests/test_delegated_authorization.py)
- [delegated_fixtures.py](file://products/tool-gateway/tests/integration/delegated_fixtures.py)
- [ansible-mcp-check.sh](file://shared/platform-ops/e2e/ansible-mcp-check.sh)
- [README.md](file://products/tool-gateway/README.md)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive documentation for the complete OAuth2.0 authorization-code flow with PKCE S256 implementation
- Documented server-side token management with immutable target-account verification
- Added detailed coverage of user-delegated client implementation with secure caching and refresh mechanisms
- Enhanced security documentation with dual trust boundaries for human and workload authentication
- Updated architecture diagrams to include the complete OAuth flow and browser handoff coordination
- Added operator guidance for deploying the OAuth authorization system with proper configuration validation

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. OAuth2.0 Authorization System
6. Detailed Component Analysis
7. Dependency Analysis
8. Performance Considerations
9. Troubleshooting Guide
10. Conclusion

## Introduction
The Tool Gateway is a normalized access layer that exposes external systems through pluggable tool connectors. It centralizes authentication, policy enforcement, parameter validation, output redaction, audit emission, and structured error handling. The platform now provides comprehensive connectivity through eight built-in connectors: Kubernetes, Elasticsearch, browser automation (web-check flows), HTTP services, incidents, skills repositories, secure secret delivery mechanisms, and MCP-ingestion for Ansible/AAP systems. Each connector implements standardized security controls including origin allowlisting, credential set management, parameter validation, and structured error responses. The gateway enforces risk-tier admission for mutating actions and integrates with the platform's audit and policy systems to ensure consistent governance across all tool invocations.

**Updated** The platform now includes a complete OAuth2.0 authorization-code flow with server-side token management, immutable target-account verification, and user-delegated client implementation. This enables secure OAuth-based authorization flows for external targets while maintaining strict security boundaries between human users and platform workloads.

## Project Structure
The Tool Gateway service is organized into:
- Application entrypoint and lifecycle management
- API routing and request orchestration
- Tool registry and base abstractions
- Eight connector implementations per system
- Policy engine and token verification
- Audit emission and observability
- Configuration and runtime settings
- **New** Complete OAuth2.0 authorization system with PKCE S256
- **New** User-delegated client with server-side token management
- MCP-ingestion adapter and bindings

```mermaid
graph TB
A["FastAPI app<br/>lifespan"] --> B["ToolRegistry"]
A --> C["GatewayService<br/>invoke_tool()"]
A --> D["AuthorizationService<br/>OAuth2.0 Flow Management"]
C --> E["PolicyEngine<br/>evaluate()"]
C --> F["AuditEmitter<br/>emit_audit_event()"]
C --> G["Redaction<br/>redact_result()"]
D --> H["UserDelegatedClient<br/>PKCE S256 + Token Management"]
B --> I["KubernetesConnector"]
B --> J["ElasticConnector"]
B --> K["BrowserConnector"]
B --> L["IncidentsConnector"]
B --> M["SkillsConnector"]
B --> N["HttpConnector"]
B --> O["SecretsConnector"]
B --> P["MCP Ingestion<br/>(Ansible Binding)"]
P --> Q["McpIngestionConnector<br/>(server-agnostic)"]
Q --> R["McpTransport<br/>(streamable_http/stdio)"]
N --> S["URL Redaction<br/>secret masking"]
O --> T["SecretDeliveryBuffer<br/>stash/redeem/discard"]
T --> U["InMemory/Redis Backend"]
I --> V["audit_attribution()<br/>opt-in hook"]
J --> V
K --> V
L --> V
M --> V
N --> V
O --> V
P --> V
```

**Diagram sources**
- [app.py:19-268](file://products/tool-gateway/src/tool_gateway/app.py#L19-L268)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [authorization_service.py:181-483](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L181-L483)
- [user_delegated_client.py:202-656](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L202-L656)
- [mcp_adapter.py:234-472](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L234-L472)
- [ansible_binding.py:179-207](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_binding.py#L179-L207)

**Section sources**
- [app.py:19-268](file://products/tool-gateway/src/tool_gateway/app.py#L19-L268)
- [main.py:1-9](file://products/tool-gateway/src/tool_gateway/main.py#L1-L9)

## Core Components
- ToolRegistry: In-process lookup and dispatch; enforces risk-tier admission at registration time and wraps execution errors into structured results.
- BaseTool and ToolDefinition: Abstract interface and metadata schema for tools, including risk_level and parameters_schema.
- GatewayService: Orchestrates identity resolution, policy checks, tool dispatch, redaction, audit emission, and response mapping.
- PolicyEngine: Loads and evaluates policy bundles; deny-by-default semantics with explicit allow/deny and require_approval outcomes.
- Redaction: Deterministic output sanitization using value patterns and sensitive key lists; fail-closed on overflow.
- URL Redaction: Specialized URL secret masking for query parameters and userinfo components.
- AuditEmitter: Fire-and-forget durable audit events to the audit service; non-blocking and failure-tolerant.
- Config: Centralized environment-driven configuration for connectors, policy, auth, and feature flags.
- **New** AuthorizationService: Manages the complete OAuth2.0 authorization flow with dual trust boundaries for human and workload authentication.
- **New** UserDelegatedClient: Handles OAuth authorization code flows with PKCE S256, immutable target-account verification, and secure token caching.
- **New** McpIngestionConnector: Server-agnostic adapter for MCP protocol connections with typed tool registration.
- **New** AnsibleBinding: Configuration-driven binding for Ansible/AAP read-only tools with deny-by-default policy.

**Updated** The platform now includes a complete OAuth2.0 authorization-code flow with server-side token management, enabling secure authorization without exposing user credentials through dedicated endpoints for enrollment, renewal, and browser handoff coordination.

**Section sources**
- [registry.py:18-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L18-L89)
- [base.py:15-123](file://products/tool-gateway/src/tool_gateway/tools/base.py#L15-L123)
- [gateway_service.py:61-156](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L61-L156)
- [policy_engine.py:254-355](file://products/tool-gateway/services/policy_engine.py#L254-L355)
- [redaction.py:1-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L1-L151)
- [url_redaction.py:1-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L1-L91)
- [audit_emitter.py:1-98](file://products/tool-gateway/services/audit_emitter.py#L1-L98)
- [config.py:32-494](file://products/tool-gateway/src/tool_gateway/core/config.py#L32-L494)
- [authorization_service.py:181-483](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L181-L483)
- [user_delegated_client.py:202-656](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L202-L656)
- [mcp_adapter.py:234-472](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L234-L472)
- [ansible_binding.py:1-207](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_binding.py#L1-L207)

## Architecture Overview
The invocation path enforces security and safety at every stage:
- Identity verification via local JWT verification or synthetic dev identity when configured.
- Policy evaluation for tools:invoke and tools:mutate based on roles and loaded bundle.
- Risk-tier gating prevents mutating tools from executing unless explicitly admitted.
- Tool dispatch through the registry with structured error envelopes.
- Safe audit attribution resolution with reserved key collision protection.
- Output redaction before response and audit emission.
- Durable audit trail via fire-and-forget emission.
- **New** Complete OAuth2.0 authorization with PKCE S256 provides secure user delegation with dual trust boundaries.
- **New** Immutable target-account verification ensures authorized users cannot impersonate other accounts.
- **New** MCP-ingestion provides server-agnostic access with deny-by-default policies and typed tool registration.

```mermaid
sequenceDiagram
participant Client as "Caller"
participant Portal as "Portal Browser"
participant PlatformGW as "Platform Gateway"
participant ToolGW as "Tool Gateway"
participant AuthSvc as "AuthorizationService"
participant OAuthClient as "UserDelegatedClient"
participant Provider as "External OAuth Provider"
participant Registry as "ToolRegistry"
participant HttpConn as "HttpConnector"
participant McpAdapter as "McpIngestionConnector"
participant UrlRedact as "URL Redaction"
participant Redact as "Redaction"
participant Attrib as "resolve_audit_attribution"
participant Audit as "AuditEmitter"
Note over Client,Provider : Tool Invocation Flow
Client->>ToolGW : POST /api/v2/tools/invoke
ToolGW->>ToolGW : resolve_request_identity + enforce_policy
ToolGW->>Registry : invoke(tool_name, parameters, identity)
alt http.get/http.post
Registry->>HttpConn : execute(parameters, identity)
HttpConn->>UrlRedact : redact_secret_query(url)
UrlRedact-->>HttpConn : masked URL
HttpConn-->>Registry : ToolResult
else ansible.* tools
Registry->>McpAdapter : execute(server_name, arguments)
McpAdapter->>McpAdapter : validate_parameters + map_arguments
McpAdapter->>McpAdapter : _call(server_name, arguments)
McpAdapter-->>Registry : ToolResult
else secrets.generate_password/secrets.deliver
Registry->>SecretsConn : execute(parameters, identity)
SecretsConn-->>Registry : ToolResult
end
Registry-->>ToolGW : ToolResult
ToolGW->>Attrib : resolve_audit_attribution(target, result, tool_name, request_id)
Attrib-->>ToolGW : safe attribution dict
ToolGW->>Redact : redact_result(result)
Redact-->>ToolGW : redacted result + stats
ToolGW->>Audit : emit_audit_event(...)
ToolGW-->>Client : JSONResponse(status_code)
Note over Portal,Provider : OAuth2.0 Authorization Flow with PKCE S256
Portal->>ToolGW : POST /api/v2/targets/authorizations/{id}/start
ToolGW->>AuthSvc : start(owner, browser_secret)
AuthSvc->>AuthSvc : verify_human_bearer + check_entitlement
AuthSvc-->>Portal : start_token + expires_at
Portal->>PlatformGW : GET /provider-url (with start_token)
PlatformGW->>ToolGW : POST /api/v2/targets/authorizations/provider-url
ToolGW->>AuthSvc : provider_url(start_token, browser_bindings)
AuthSvc->>OAuthClient : build_authorization_url(config, state, verifier)
OAuthClient-->>AuthSvc : provider_url with PKCE S256
AuthSvc-->>PlatformGW : 302 redirect to provider
PlatformGW-->>Portal : 302 redirect
Portal->>Provider : OAuth authorization with PKCE
Provider->>PlatformGW : callback with code
PlatformGW->>ToolGW : POST /api/v2/targets/authorizations/callback
ToolGW->>AuthSvc : callback(code, browser_bindings)
AuthSvc->>OAuthClient : exchange_authorization_code()
OAuthClient->>Provider : token exchange with PKCE verification
Provider-->>OAuthClient : access_token + refresh_token
OAuthClient-->>AuthSvc : verified token bundle with account verification
AuthSvc->>AuthSvc : publish_to_custody()
AuthSvc-->>PlatformGW : status=authorized
PlatformGW-->>Portal : redirect to return_url
```

**Diagram sources**
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [gateway_service.py:43-69](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L43-L69)
- [policy_engine.py:299-355](file://products/tool-gateway/services/policy_engine.py#L299-L355)
- [registry.py:65-89](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L65-L89)
- [http_connector.py:389-491](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L389-L491)
- [mcp_adapter.py:407-453](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L407-L453)
- [url_redaction.py:49-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L49-L91)
- [redaction.py:126-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L126-L151)
- [audit_emitter.py:67-98](file://products/tool-gateway/services/audit_emitter.py#L67-L98)
- [authorization_service.py:321-440](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L321-L440)
- [user_delegated_client.py:244-319](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L244-L319)

## OAuth2.0 Authorization System

### Overview
The OAuth2.0 authorization system provides secure user-delegated authorization flows for external targets, implementing the complete OAuth 2.0 Authorization Code flow with PKCE (Proof Key for Code Exchange) for enhanced security. The system enables users to grant permissions to the platform without exposing their credentials, while maintaining strict security boundaries between human users and platform workloads.

**Key Features:**
- **PKCE S256 Security**: Implements RFC 7636 PKCE for enhanced security against authorization code interception attacks
- **Dual Trust Boundaries**: Separate authentication for human users and platform workloads
- **Immutable Target-Account Verification**: Verifies authorized users cannot impersonate other accounts
- **Server-Side Token Management**: Secure memory-only token storage with bounded caching and automatic refresh
- **Browser Handoff Coordination**: Secure coordination between portal browser and backend services
- **Fail-Closed Design**: All failures return generic error codes without exposing internal details
- **Comprehensive Audit Trail**: Detailed audit logging for all authorization lifecycle events

### Six Authorization Endpoints
The system exposes six `/api/v2/targets/authorizations` endpoints:

1. **POST /{challenge_id}/start**: Human-initiated enrollment start with delegated bearer token
2. **POST /provider-url**: Workload-only provider URL generation with PKCE S256
3. **POST /callback**: Workload-only callback processing with code exchange
4. **POST /browser-reset**: Human-initiated browser session cleanup
5. **GET /{challenge_id}**: Owner-scoped status checking
6. **POST /{challenge_id}/cancel**: Idempotent cancellation

```mermaid
flowchart TD
Start(["Human User"]) --> StartEndpoint["POST /{challenge_id}/start"]
StartEndpoint --> VerifyHuman["Verify human bearer token"]
VerifyHuman --> CheckEntitlement{"Owner entitled for target?"}
CheckEntitlement --> |No| Deny["403 denied"]
CheckEntitlement --> |Yes| MintHandle["Mint single-use start handle"]
MintHandle --> ReturnHandle["Return start_token + expires_at"]
ReturnHandle --> BrowserNav["Browser navigates to provider URL"]
BrowserNav --> ProviderURL["POST /provider-url"]
ProviderURL --> VerifyWorkload["Verify platform workload token"]
VerifyWorkload --> BuildURL["Build OAuth authorization URL with PKCE S256"]
BuildURL --> Redirect["302 redirect to provider"]
Redirect --> OAuthFlow["User completes OAuth flow"]
OAuthFlow --> Callback["POST /callback"]
Callback --> VerifyWorkload2["Verify platform workload token"]
Callback --> ExchangeToken["Exchange code for tokens with PKCE verification"]
ExchangeToken --> VerifyAccount["Verify immutable target account"]
VerifyAccount --> PublishGrant["Publish grant to custody store"]
PublishGrant --> Authorized["Status = authorized"]
Authorized --> ReturnURL["Redirect to return URL"]
```

**Diagram sources**
- [authorization_service.py:321-440](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L321-L440)
- [authorizations.py:73-224](file://products/tool-gateway/src/tool_gateway/api/routes/authorizations.py#L73-L224)
- [user_delegated_client.py:244-319](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L244-L319)

### Authentication and Security Model

#### Human Authentication
Human users authenticate via delegated bearer tokens that are verified against the configured JWKS endpoint. The system extracts owner information from the verified claims rather than accepting caller-provided identities.

**Security Properties:**
- Bearer tokens must be valid RS256 JWTs from the configured issuer
- Claims must include required fields: sub, username, email, roles, groups, act
- Owner namespace is pinned to the configured delegated identity issuer
- Subject is derived from the verified token's sub claim
- All failures return fixed 403 errors without echoing token material

#### Workload Authentication  
Platform workloads authenticate via a dedicated service account token with a specialized audience (`luban-target-authorization-handoff`). This ensures that only the platform gateway can call the bearerless endpoints.

**Security Properties:**
- Tokens must be RS256 JWTs from the configured authorization workload issuer
- Audience must match the dedicated `luban-target-authorization-handoff` value
- Subject must be in the configured allowlist
- All failures return fixed 401 errors without echoing token material

#### Browser Proof Validation
Browser handoffs use cookie-bound proofs to prevent CSRF attacks. The initiating browser presents its whole cookie jar on both the provider URL request and callback, which is validated against stored browser secrets.

**Security Properties:**
- Cookie secrets are generated fresh per challenge
- Maximum 8 cookie bindings per request
- Browser proof validation occurs before any sensitive data is returned
- Failed proofs collapse to no-oracle responses (404)

**Section sources**
- [authorization_service.py:114-166](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L114-L166)
- [authorization_service.py:181-239](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L181-L239)
- [authorizations.py:59-66](file://products/tool-gateway/src/tool_gateway/api/routes/authorizations.py#L59-L66)

### OAuth Flow Implementation

#### Authorization Code Flow with PKCE S256
The system implements the OAuth 2.0 Authorization Code flow with PKCE (Proof Key for Code Exchange) for enhanced security. This prevents authorization code interception attacks while maintaining compatibility with standard OAuth providers.

**Flow Steps:**
1. Generate PKCE verifier and code challenge using SHA-256
2. Construct authorization URL with all required parameters including PKCE
3. Redirect user to provider for authorization
4. Handle callback with authorization code
5. Exchange code for access and refresh tokens with PKCE verification
6. Verify identity against provider's identity endpoint with immutable account check
7. Publish grant to durable custody store

#### Token Management
Access tokens are managed with strict security controls:
- Memory-only storage with LRU eviction (max 1,024 entries)
- Single-flight acquisition per binding to prevent race conditions
- Automatic refresh with bounded lifetime caps
- Grant invalidation on 401/invalid-token responses
- Never persisted, logged, echoed, or returned to callers
- Immutable target-account verification before any token release

```mermaid
flowchart TD
Acquire["access_token_for_send(ctx)"] --> CheckCache{"Cached token valid?"}
CheckCache --> |Yes| ReturnCached["Return cached token"]
CheckCache --> |No| AcquireLock["Acquire per-binding lock"]
AcquireLock --> SyncConfig["Sync configuration from custody"]
SyncConfig --> GetMetadata["Get credential metadata"]
GetMetadata --> CheckMetadata{"Metadata exists?"}
CheckMetadata --> |No| ErrorAuthRequired["Error: authorization_required"]
CheckMetadata --> |Yes| Refresh["Refresh token if needed"]
Refresh --> ValidateResponse["Validate token response"]
ValidateResponse --> VerifyIdentity["Verify immutable target account"]
VerifyIdentity --> CacheToken["Cache token with expiry"]
CacheToken --> ReturnToken["Return DelegatedAccessToken"]
```

**Diagram sources**
- [user_delegated_client.py:269-287](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L269-L287)
- [user_delegated_client.py:402-425](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L402-L425)
- [user_delegated_client.py:485-524](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L485-L524)

**Section sources**
- [user_delegated_client.py:1-656](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L1-L656)
- [authorization_service.py:342-440](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L342-L440)

### Configuration and Deployment

#### Required Environment Variables
The OAuth2.0 authorization system requires extensive configuration for secure operation:

**Delegated Identity Trust (Human Users):**
- `GATEWAY_DELEGATED_IDENTITY_ISSUER`: Trusted JWT issuer for human users
- `GATEWAY_DELEGATED_IDENTITY_JWKS_URL`: JWKS endpoint for verifying human tokens
- `GATEWAY_DELEGATED_IDENTITY_AUDIENCE`: Expected audience for human tokens
- `GATEWAY_DELEGATED_IDENTITY_ACTORS`: Comma-separated list of allowed actor subjects

**Authorization Workload Trust (Platform Services):**
- `GATEWAY_AUTHORIZATION_WORKLOAD_ISSUER`: Trusted JWT issuer for platform workloads
- `GATEWAY_AUTHORIZATION_WORKLOAD_JWKS_URL`: JWKS endpoint for verifying workload tokens
- `GATEWAY_AUTHORIZATION_WORKLOAD_SUBJECTS`: Comma-separated list of allowed workload subjects
- `GATEWAY_AUTHORIZATION_WORKLOAD_AUDIENCE`: Must be `luban-target-authorization-handoff`

**Custody Store Configuration:**
- `GATEWAY_DELEGATED_CUSTODY_DB_URL`: PostgreSQL connection string
- `GATEWAY_DELEGATED_CUSTODY_KEYRING_PATH`: Path to encryption keyring
- `GATEWAY_DELEGATED_CUSTODY_CONFIG_PATH`: Path to delegation configuration files
- `GATEWAY_DELEGATED_CUSTODY_SET_ID`: Identifier for the credential set
- `GATEWAY_DELEGATED_CUSTODY_TRUSTED_CALLBACK`: HTTPS callback URL with exact path

**Feature Flags:**
- `GATEWAY_DELEGATED_AUTHORIZATION_ENABLED=true`: Enable authorization workflow
- `GATEWAY_DELEGATED_ACQUISITION_ENABLED=true`: Enable token acquisition
- `GATEWAY_DELEGATED_INVOKE_ENABLED=true`: Enable private delegated execution route

#### Startup Validation
The system performs extensive startup validation to ensure secure configuration:
- All required environment variables must be present and properly formatted
- URLs must be valid HTTP(S) with no embedded credentials
- Allowlists must be non-empty when features are enabled
- Database connectivity and keyring accessibility are verified
- Callback URL path must exactly match the ratified `CALLBACK_PATH`
- Both human and workload trust sets must be properly configured

**Section sources**
- [config.py:425-498](file://products/tool-gateway/src/tool_gateway/core/config.py#L425-L498)
- [config.py:832-847](file://products/tool-gateway/src/tool_gateway/core/config.py#L832-L847)

## Detailed Component Analysis

### Authorization Service
The AuthorizationService orchestrates the complete OAuth2.0 authorization workflow, managing transaction state, authentication, and integration with the custody store and OAuth client.

**Key Responsibilities:**
- Managing authorization challenges and transactions
- Validating human and workload authentication with dual trust boundaries
- Coordinating browser handoffs between portal and backend
- Processing OAuth callbacks and publishing grants
- Providing owner-scoped status and cancellation operations
- Implementing PKCE S256 for enhanced security

**Security Posture:**
- Dual trust boundaries for human vs. workload authentication
- Fail-closed design with generic error responses
- No persistence of sensitive bearer tokens or codes
- Comprehensive audit trail for all authorization lifecycle events
- Immutable target-account verification prevents impersonation

```mermaid
classDiagram
class AuthorizationService {
+produce_challenge(owner_namespace, owner_sub, session_id, call_id) AuthorizationRequired
+start(settings, identity, challenge_id, request) AuthorizationStartResponse
+provider_url(request) ProviderAuthorizationResponse
+callback(request) AuthorizationCallbackResponse
+status(settings, identity, challenge_id) AuthorizationStatusResponse
+cancel(settings, identity, challenge_id) None
+browser_reset(settings, identity, request) int
-_owner(settings, identity) tuple
-_entitlement(txn) tuple
-_emit_authorization(operation, outcome, txn, reason, delegation_mode) void
}
class AuthorizationTransaction {
+challenge_id : str
+owner_namespace : str
+owner_sub : str
+target : str
+credential_set_id : str
+config_generation : int
+session_id : str
+call_id : str
+return_url : str
+created_at : datetime
+updated_at : datetime
+expires_at : datetime
+status : str
}
class AuthorizationError {
+status_code : int
+detail : str
}
AuthorizationService --> AuthorizationTransaction : manages
AuthorizationService --> AuthorizationError : raises
```

**Diagram sources**
- [authorization_service.py:181-483](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L181-L483)

**Section sources**
- [authorization_service.py:1-483](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L1-L483)

### User-Delegated OAuth Client
The UserDelegatedClient handles all aspects of OAuth authorization code flows with PKCE S256, including token acquisition, validation, caching, and refresh management with immutable target-account verification.

**Core Features:**
- PKCE S256 implementation for enhanced security against code interception
- Strict token response validation with bounded sizes and unique JSON keys
- Process-local LRU-bounded access token cache (1,024 entries max)
- Single-flight acquisition per binding to prevent race conditions
- Automatic token refresh with lifetime caps and safety margins
- Grant invalidation on authentication failures
- Secure identity verification against provider endpoints with immutable account check

**Security Controls:**
- Memory-only token storage with no persistence
- Bounded response sizes (64 KiB max)
- Timeout limits (10 seconds default)
- No redirects, proxies, or automatic retries
- Strict scope validation against configured allowed scopes
- Immutable identity claim verification prevents account impersonation
- Hardened provider channel with no environment proxy inheritance

```mermaid
flowchart TD
Request["access_token_for_send(ctx)"] --> CacheLookup{"Check process-local cache"}
CacheLookup --> |Hit| ReturnCached["Return cached token"]
CacheLookup --> |Miss| AcquireLock["Acquire per-binding async lock"]
AcquireLock --> SyncConfig["Sync configuration from custody store"]
SyncConfig --> GetMetadata["Get credential metadata"]
GetMetadata --> HasMetadata{"Has active grant?"}
HasMetadata --> |No| ErrorAuthRequired["Raise authorization_required"]
HasMetadata --> |Yes| NeedsRefresh{"Token expired?"}
NeedsRefresh --> |No| ReturnCached
NeedsRefresh --> |Yes| BeginRefresh["Begin refresh transaction"]
BeginRefresh --> TokenRequest["Make token request to provider"]
TokenRequest --> ValidateResponse["Validate token response"]
ValidateResponse --> VerifyIdentity["Verify immutable target account"]
VerifyIdentity --> CompleteRefresh["Complete refresh publication"]
CompleteRefresh --> CacheToken["Cache new token"]
CacheToken --> ReturnToken["Return token"]
```

**Diagram sources**
- [user_delegated_client.py:269-287](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L269-L287)
- [user_delegated_client.py:402-483](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L402-L483)

**Section sources**
- [user_delegated_client.py:1-656](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L1-L656)

### Authorization Routes
The authorization routes provide the public API surface for the OAuth2.0 authorization system, implementing proper authentication, policy enforcement, and response formatting.

**Route Security:**
- Human endpoints require delegated bearer tokens plus `targets:authorize` policy
- Workload endpoints require dedicated platform workload tokens with specific audience
- All responses marked with `no-store`, `no-cache`, and `no-referrer` headers
- SecretStr fields unwrapped only at serialization boundary
- Generic error responses without sensitive details

**Endpoints:**
- `POST /{challenge_id}/start`: Human-initiated enrollment with PKCE setup
- `POST /provider-url`: Workload-only provider URL generation with PKCE S256
- `POST /callback`: Workload-only callback processing with code exchange
- `POST /browser-reset`: Human-initiated browser cleanup
- `GET /{challenge_id}`: Owner-scoped status checking
- `POST /{challenge_id}/cancel`: Idempotent cancellation

**Section sources**
- [authorizations.py:1-224](file://products/tool-gateway/src/tool_gateway/api/routes/authorizations.py#L1-L224)

### Authorization Schemas
The authorization schemas define the wire format for all OAuth2.0 authorization-related requests and responses, with strict validation and security constraints.

**Security Features:**
- UUID pattern validation for challenge IDs
- Bounded browser bindings (max 8 cookies)
- SecretStr for all sensitive values
- Literal types for status fields
- Exact-one-of validation for callback payloads
- Local return path validation to prevent open redirects

**Key Types:**
- `ChallengeId`: UUID4 pattern validation
- `BrowserBindings`: Bounded dictionary of cookie secrets
- `DenialReason`: Closed set of normalized denial reasons
- `AuthorizationStatus`: Enumerated status values
- `LocalReturnPath`: Bounded local URL paths

**Section sources**
- [authorization.py:1-169](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L169)

### MCP-Ingestion Adapter Architecture
The MCP-ingestion adapter provides a server-agnostic interface for connecting to external Model Context Protocol servers while maintaining strict security boundaries and deny-by-default policies.

**Key Features:**
- **Server-Agnostic Design**: One reusable adapter class that works with any MCP server implementation
- **Config-Driven Registration**: Tools are registered purely from gateway-owned configuration, never from server metadata
- **Fail-Closed Security**: Missing SDK, unreachable servers, credential failures, and transport errors all become structured errors
- **Typed Tool Mapping**: Each admitted server tool becomes a typed gateway tool with validated parameters
- **Credential Set Integration**: Uses the existing SPEC-068 credential resolution seam for bearer tokens
- **Identity Threading**: Supports both acting-service and user-delegated identity modes

```mermaid
flowchart TD
Start(["AdmittedTool Config"]) --> Register["register_tools(registry)"]
Register --> CreateTool["Create McpTool(spec)"]
CreateTool --> ValidateParams["validate_parameters(schema, params)"]
ValidateParams --> MapArgs["map_arguments(spec, params)"]
MapArgs --> CallServer["_call(server_name, arguments)"]
CallServer --> ResolveAuth["resolve_bearer()"]
ResolveAuth --> OpenSession["_open_mcp_session(transport, token)"]
OpenSession --> ExecuteTool["session.call_tool()"]
ExecuteTool --> Normalize["normalize(result, duration_ms)"]
Normalize --> ToolResult["ToolResult"]
```

**Diagram sources**
- [mcp_adapter.py:275-284](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L275-L284)
- [mcp_adapter.py:407-453](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L407-L453)
- [mcp_adapter.py:285-351](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L285-L351)

**Section sources**
- [mcp_adapter.py:1-472](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L1-L472)
- [test_ansible_mcp_ingestion.py:1-200](file://products/tool-gateway/tests/test_ansible_mcp_ingestion.py#L1-L200)

### Ansible Binding and Deny-by-Default Policy
The Ansible binding provides a secure, configuration-driven interface to Ansible Automation Platform (AAP) read-only tools with deny-by-default policy enforcement.

**Security Model:**
- **Deny-by-Default**: No Ansible tools are exposed unless `GATEWAY_ANSIBLE_MCP_ENABLED=true`
- **Read-Only Access**: Only six specific read-tier tools are admitted; all mutating operations are blocked
- **Allowlist Enforcement**: Server-advertised tools are never trusted; only gateway-configured tools are exposed
- **Structured Error Handling**: All failures return structured error codes without exposing internal details

**Admitted Tools:**
- `ansible.list_inventories`: List inventories with optional name filtering
- `ansible.get_inventory`: Get inventory details including hosts and groups  
- `ansible.list_job_templates`: List job templates with optional name filtering
- `ansible.get_job`: Get job details and current status by ID
- `ansible.get_job_stdout`: Retrieve job stdout/log output with tail-bounding
- `ansible.get_environment_health`: Report control-plane health/readiness

```mermaid
flowchart TD
Config["ANSIBLE_ADMITTED_TOOLS config"] --> Bind["build_ansible_mcp_connector()"]
Bind --> Transport["McpTransport(streamable_http)"]
Bind --> Connector["McpIngestionConnector"]
Connector --> Registry["register_tools(registry)"]
Registry --> TypedTools["Six typed read-only tools"]
TypedTools --> PolicyCheck{"Risk level = 'read'?"}
PolicyCheck --> |Yes| Admit["Admit to registry"]
PolicyCheck --> |No| Deny["Refuse registration"]
```

**Diagram sources**
- [ansible_binding.py:91-176](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_binding.py#L91-L176)
- [ansible_binding.py:179-207](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_binding.py#L179-L207)
- [app.py:167-194](file://products/tool-gateway/src/tool_gateway/app.py#L167-L194)

**Section sources**
- [ansible_binding.py:1-207](file://products/tool-gateway/src/tool_gateway/ingestion/ansible_binding.py#L1-L207)
- [app.py:167-194](file://products/tool-gateway/src/tool_gateway/app.py#L167-L194)
- [ansible-mcp-check.sh:1-395](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L1-L395)

### Operator Guidance for Enabling Ansible MCP-Ingestion
Operators must explicitly enable Ansible MCP-ingestion through configuration. The feature is disabled by default and requires careful setup for production use.

**Configuration Requirements:**
- `GATEWAY_ANSIBLE_MCP_ENABLED=true`: Enable the connector
- `GATEWAY_ANSIBLE_MCP_TRANSPORT=streamable_http`: Use HTTP transport for AAP
- `GATEWAY_ANSIBLE_MCP_URL=https://your-aap-server/mcp`: Point to AAP MCP endpoint
- `GATEWAY_ANSIBLE_MCP_CREDENTIAL_SET=aap-read-only`: Configure credential set for bearer token
- `GATEWAY_ANSIBLE_MCP_CREDENTIAL_SETS_PATH=/path/to/credential-sets.json`: Path to credential store

**Production Deployment Steps:**
1. Deploy the Ansible MCP server (AAP read-only mode or compatible implementation)
2. Configure credential sets with appropriate permissions
3. Set network policies to restrict access to the MCP server
4. Enable the connector with minimal required configuration
5. Verify tool discovery shows exactly six read-only tools
6. Test deny-by-default behavior with unauthenticated requests

**Section sources**
- [config.py:170-191](file://products/tool-gateway/src/tool_gateway/core/config.py#L170-L191)
- [config.py:455-487](file://products/tool-gateway/src/tool_gateway/core/config.py#L455-L487)
- [ansible-mcp-check.sh:188-230](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L188-L230)

### HTTP Connector
The HTTP connector provides bounded HTTP service check capabilities with two tools: `http.get` (read tier) and `http.post` (write tier). It implements strict security controls including origin allowlisting, redirect following with allowlist validation, body size limits, and credential set-based authentication.

Key features:
- **Origin Allowlist**: Deny-by-default with configurable allowed origins
- **Redirect Handling**: Follows up to 3 redirects with allowlist validation at each hop
- **Body Validation**: Limits JSON POST bodies to depth ≤ 2, ≤ 32 keys, and configurable byte limits
- **Credential Management**: Uses named credential sets resolved server-side into HTTP Basic auth
- **URL Secret Masking**: Automatically masks secret-bearing query parameters in reported URLs
- **Response Projection**: Filters response headers to a safe allowlist, excluding credentials

```mermaid
flowchart TD
Start(["http.get/http.post"]) --> ValidateDest{"Validate destination URL"}
ValidateDest --> |Invalid| ErrorParam["Return INVALID_PARAMETERS"]
ValidateDest --> |Valid| CheckAllowlist{"Origin in allowlist?"}
CheckAllowlist --> |No| OriginDenied["HTTP_ORIGIN_NOT_ALLOWED"]
CheckAllowlist --> |Yes| ResolveAuth{"Resolve credential_set"}
ResolveAuth --> |Error| CredError["CREDENTIAL_SET_NOT_FOUND"]
ResolveAuth --> |Success| MakeRequest["Make HTTP request"]
MakeRequest --> Redirect{"3xx redirect?"}
Redirect --> |Yes| ValidateHop{"Validate redirect target"}
ValidateHop --> |Invalid| RedirectDenied["HTTP_REDIRECT_NOT_ALLOWED"]
ValidateHop --> |Valid| FollowHop["Follow redirect"]
Redirect --> |No| ProcessResponse["Process response"]
ProcessResponse --> ProjectHeaders["Project safe headers only"]
ProjectHeaders --> MaskSecrets["Mask secret query params"]
MaskSecrets --> ReturnResult["Return ToolResult"]
```

**Diagram sources**
- [http_connector.py:100-180](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L100-L180)
- [http_connector.py:389-491](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L389-L491)
- [http_connector.py:255-302](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L255-302)

**Section sources**
- [http_connector.py:1-699](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L1-L699)
- [test_http_connector.py:1-789](file://products/tool-gateway/tests/test_http_connector.py#L1-L789)

### Secrets Connector and Secure Delivery System
The SecretsConnector provides secure password generation and delivery capabilities as specified in SPEC-062. This connector introduces two tool primitives with comprehensive security controls and active destruction capabilities.

**Key Features:**
- **`secrets.generate_password`**: A read-tier CSPRNG tool that generates cryptographically strong passwords using Python's `secrets` module, bound to a centralized password policy
- **`secrets.deliver`**: A write-tier tool that securely delivers generated passwords through multiple channels (portal Copy button, email) without ever exposing plaintext in transcripts or evidence
- **Active Destruction**: New DELETE endpoint for immediate destruction of held deliveries without revealing values
- **Password Policy Enforcement**: Centralized password strength rules with configurable tightening
- **One-Time Delivery**: Ephemeral, single-use, TTL-bounded delivery mechanism with owner-scoped access
- **Extensible Channel Interface**: Support for portal Copy button (primary) and email (optional, gated) with extensibility for Teams/Slack

```mermaid
flowchart TD
Start(["secrets.generate_password"]) --> ValidatePolicy{"Validate password policy"}
ValidatePolicy --> |Invalid| ErrorPolicy["Return INVALID_PARAMETERS"]
ValidatePolicy --> |Valid| Generate["Generate CSPRNG password"]
Generate --> StashValue["Stash in delivery buffer"]
StashValue --> ReturnGen["Return masked ToolResult with delivery_id"]
Start2(["secrets.deliver"]) --> ValidateChannel{"Validate channel"}
ValidateChannel --> |Portal| CreateHandle["Create ephemeral handle"]
CreateHandle --> ReturnDeliver["Return delivery_id"]
ValidateChannel --> |Email| GateDelivery{"Gated by secrets:deliver"}
GateDelivery --> |Allowed| SendEmail["Send via SMTP"]
GateDelivery --> |Denied| AccessDenied["Return ACCESS_DENIED"]
SendEmail --> EmitAudit["Emit secret_delivered event"]
EmitAudit --> ReturnDeliver
Start3(["DELETE /delivery/{id}"]) --> ValidateOwner{"Validate owner scope"}
ValidateOwner --> |Valid| DestroyHandle["Destroy delivery handle"]
DestroyHandle --> Return204["Return 204 No Content"]
ValidateOwner --> |Invalid| Return204
```

**Diagram sources**
- [secrets_connector.py:403-620](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L403-L620)
- [secret_delivery.py:50-91](file://products/tool-gateway/tools/secret_delivery.py#L50-L91)

**Section sources**
- [secrets_connector.py:1-664](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L1-L664)
- [secret_delivery.py:1-369](file://products/tool-gateway/tools/secret_delivery.py#L1-L369)

### Secret Delivery Buffer
The SecretDeliveryBuffer provides single-use, owner-scoped, TTL-bounded secret storage with both redemption and active destruction capabilities. It supports both in-memory and Redis backends for different deployment scenarios.

**Key Capabilities:**
- **Single-Use Redemption**: Values can be redeemed exactly once by the authorized owner
- **Active Destruction**: New discard capability allows immediate destruction without revealing values
- **Owner Scoping**: Both redemption and destruction are scoped to the original owner
- **TTL Management**: Automatic expiration with configurable TTL periods
- **Backend Flexibility**: Supports both in-memory (development) and Redis (production) backends
- **Oracle-Free Responses**: All operations return indistinguishable responses regardless of outcome

```mermaid
flowchart TD
Input["delivery_id + owner_sub"] --> Validate{"Valid UUID format?"}
Validate --> |No| ReturnFalse["Return False"]
Validate --> |Yes| Lookup{"Lookup entry"}
Lookup --> |Not Found| ReturnFalse
Lookup --> |Found| CheckExpiry{"Entry expired?"}
CheckExpiry --> |Yes| ReturnFalse
CheckExpiry --> |No| CheckOwner{"Owner matches?"}
CheckOwner --> |No| ReturnFalse
CheckOwner --> |Yes| Operation{"Operation type?"}
Operation --> |Redeem| PopAndReturn["Pop entry and return value"]
Operation --> |Discard| DeleteOnly["Delete entry only"]
PopAndReturn --> SuccessTrue["Return True"]
DeleteOnly --> SuccessTrue
```

**Diagram sources**
- [secret_delivery.py:158-186](file://products/tool-gateway/tools/secret_delivery.py#L158-L186)
- [secret_delivery.py:232-263](file://products/tool-gateway/tools/secret_delivery.py#L232-L263)

**Section sources**
- [secret_delivery.py:50-369](file://products/tool-gateway/tools/secret_delivery.py#L50-L369)

### URL Redaction Module
The URL redaction module provides coordinated secret masking for URLs across HTTP and browser connectors. It masks secret-bearing query parameters and userinfo components while preserving URL structure and non-secret values.

Features:
- **Secret Parameter Detection**: Case-insensitive matching of known secret parameter names
- **Userinfo Masking**: Masks passwords in `scheme://user:password@host` format
- **Query Parameter Masking**: Replaces secret parameter values with `***` markers
- **Preservation**: Maintains exact URL encoding and non-secret parameter values

```mermaid
flowchart TD
Input["URL Input"] --> Parse["Parse URL components"]
Parse --> CheckUserinfo{"Has password in userinfo?"}
CheckUserinfo --> |Yes| MaskUserinfo["Replace password with ***"]
CheckUserinfo --> |No| SkipUserinfo["Skip userinfo processing"]
MaskUserinfo --> ProcessQuery["Process query parameters"]
SkipUserinfo --> ProcessQuery
ProcessQuery --> SplitQuery["Split by & delimiter"]
SplitQuery --> ForEachParam{"For each parameter"}
ForEachParam --> CheckSecret{"Is parameter name secret?"}
CheckSecret --> |Yes| MaskValue["Replace value with ***"]
CheckSecret --> |No| KeepValue["Keep original value"]
MaskValue --> Reconstruct["Reconstruct URL"]
KeepValue --> Reconstruct
Reconstruct --> Output["Masked URL Output"]
```

**Diagram sources**
- [url_redaction.py:49-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L49-L91)

**Section sources**
- [url_redaction.py:1-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L1-L91)

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
participant UrlRedact as "URL Redaction"
Caller->>Browser : web.navigate(url, skill_id?)
Browser->>Pool : get_or_create(session_key)
Pool-->>Browser : BrowserSessionEntry
Browser->>Browser : is_origin_allowed(url)
alt skill_id provided
Browser->>Browser : fetch_skill(skill_id)
Browser->>Browser : bind_flow(entry, skill_id, url, skill)
end
Browser->>UrlRedact : redact_secret_query(url)
UrlRedact-->>Browser : masked URL
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
- [url_redaction.py:49-91](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L49-L91)

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
- Safe audit attribution resolution prevents reserved key collisions from causing failures.
- Redaction applies deterministic masking and fails closed on overflow; audit events emitted for all outcomes.
- **New** Complete OAuth2.0 authorization provides secure user delegation with PKCE S256 and immutable target-account verification.
- **New** MCP-ingestion provides structured error handling for transport failures, SDK availability issues, and credential resolution problems.

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
Result --> Attrib["resolve_audit_attribution()"]
Attrib --> SafeAttrib["Safe attribution with collision protection"]
SafeAttrib --> Redact["Redaction check"]
Redact --> Overflow{"Overflow?"}
Overflow --> |Yes| Withhold["REDACTION_OVERFLOW"]
Overflow --> |No| Emit["Emit audit event"]
Emit --> Resp["JSONResponse"]
```

**Diagram sources**
- [gateway_service.py:61-156](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L61-L156)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [gateway_service.py:43-69](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L43-L69)
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
- HTTP connector uses the same credential set mechanism as browser connector, supporting rotation without restart.
- **New** OAuth2.0 authorization uses secure PKCE S256 flows with memory-only tokens and no persistence of sensitive data.
- **New** Immutable target-account verification ensures authorized users cannot impersonate other accounts.
- **New** MCP-ingestion uses bearer tokens from credential sets, never exposing them in tool results or logs.

**Section sources**
- [browser_connector.py:123-148](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L123-L148)
- [browser_connector.py:174-257](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L174-L257)
- [http_connector.py:361-387](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L361-L387)
- [url_redaction.py:27-41](file://products/tool-gateway/src/tool_gateway/tools/url_redaction.py#L27-L41)
- [config.py:63-73](file://products/tool-gateway/src/tool_gateway/core/config.py#L63-L73)
- [mcp_adapter.py:285-323](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L285-L323)
- [user_delegated_client.py:29-32](file://products/tool-gateway/src/tool_gateway/tools/user_delegated_client.py#L29-L32)

### Integration with Audit and Policy Systems
- PolicyEngine loads bundled rules, computes content fingerprint, and evaluates actions with deny-by-default semantics.
- AuditEmitter emits durable events asynchronously; failures do not degrade the tool path.
- GatewayService records metrics for policy decisions, redaction spans, and token verification outcomes.
- The SecretsConnector integrates with the existing audit and policy systems, introducing a new `secret_delivered` audit event type and `secrets:deliver` policy action for email delivery operations.
- **Updated** The audit attribution system provides safe, opt-in connector-specific enrichment with reserved key collision protection, preventing HTTP 500 errors from malformed attribution data.
- **New** OAuth2.0 authorization provides comprehensive audit trails for all authorization lifecycle events with `target_authorization` operation type.
- **New** MCP-ingestion provides detailed audit attribution including target identity mode and failure classification for transport vs. policy denials.

**Section sources**
- [policy_engine.py:254-355](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L355)
- [audit_emitter.py:29-98](file://products/tool-gateway/services/audit_emitter.py#L29-L98)
- [gateway_service.py:32-69](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L32-L69)
- [gateway_service.py:32-59](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L32-L59)
- [mcp_adapter.py:455-472](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L455-L472)
- [authorization_service.py:240-269](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L240-L269)

## Dependency Analysis
- Application wiring: app creates registry and optional browser connector; lifespan starts/stops browser pool.
- Connectors depend on external clients (kubernetes, elasticsearch, httpx) and register tools conditionally based on configuration.
- GatewayService depends on policy engine, token verifier, redaction, and audit emitter.
- HTTP connector integrates with URL redaction module and shares credential set infrastructure with browser connector.
- SecretsConnector depends on password policy validation and secure delivery buffer backends.
- **Updated** Audit attribution system integrates with all connectors through duck-typed hooks, providing safe enrichment without breaking existing functionality.
- **New** OAuth2.0 authorization service depends on custody store, PKCE S256 client, and dual trust verifiers.
- **New** MCP-ingestion adapter is independent of specific server implementations and uses the existing credential set infrastructure.

```mermaid
graph LR
App["app.create_app"] --> Reg["ToolRegistry"]
App --> Browser["BrowserConnector (optional)"]
App --> AuthSvc["AuthorizationService"]
Reg --> K8s["KubernetesConnector"]
Reg --> ES["ElasticConnector"]
Reg --> Br["BrowserConnector"]
Reg --> Inc["IncidentsConnector"]
Reg --> Sk["SkillsConnector"]
Reg --> Http["HttpConnector"]
Reg --> Secrets["SecretsConnector"]
Reg --> Mcp["MCP Ingestion (Ansible)"]
AuthSvc --> OAuthClient["UserDelegatedClient"]
AuthSvc --> Custody["Custody Store"]
Mcp --> McpAdapter["McpIngestionConnector"]
McpAdapter --> Transport["McpTransport"]
Http --> UrlRedact["URL Redaction"]
Secrets --> Buffer["SecretDeliveryBuffer"]
Buffer --> Memory["InMemory Backend"]
Buffer --> Redis["Redis Backend"]
GS["GatewayService"] --> PE["PolicyEngine"]
GS --> AE["AuditEmitter"]
GS --> RD["Redaction"]
GS --> AA["resolve_audit_attribution"]
AA --> K8s
AA --> ES
AA --> Br
AA --> Inc
AA --> Sk
AA --> Http
AA --> Secrets
AA --> Mcp
```

**Diagram sources**
- [app.py:19-268](file://products/tool-gateway/src/tool_gateway/app.py#L19-L268)
- [gateway_service.py:158-376](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L158-L376)
- [gateway_service.py:43-69](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L43-L69)
- [authorization_service.py:202-214](file://products/tool-gateway/src/tool_gateway/services/authorization_service.py#L202-L214)
- [http_connector.py:350-359](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L350-L359)
- [secret_delivery.py:277-327](file://products/tool-gateway/tools/secret_delivery.py#L277-L327)
- [mcp_adapter.py:234-472](file://products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py#L234-L472)

**Section sources**
- [app.py:19-268](file://products/tool-gateway/src/tool_gateway/app.py#L19-L268)

## Performance Considerations
- Async execution: Connectors run blocking calls in executors to avoid blocking the event loop.
- Connection pooling: Browser sessions pooled with TTL and max sessions; Elasticsearch client initialized once per connector instance.
- Parameter bounds: Time ranges, result limits, and log tail sizes are clamped to prevent resource exhaustion.
- Redaction overhead: Redaction runs once per result; overflow detection prevents excessive processing.
- Observability: Metrics recorded for policy decisions, redaction spans, token verification, and audit emissions.
- HTTP connector uses connection-per-request pattern with timeout limits and response size caps to prevent resource exhaustion.
- SecretsConnector uses efficient CSPRNG generation and minimal memory footprint for ephemeral delivery handles.
- **Updated** Audit attribution resolution is lightweight duck-typed inspection with no performance impact for connectors without attribution hooks.
- **New** OAuth2.0 authorization uses process-local LRU-bounded token caching (1,024 entries) with single-flight acquisition per binding.
- **New** PKCE S256 implementation adds minimal overhead for cryptographic operations.
- **New** MCP-ingestion opens sessions per call with timeout limits and lazy SDK imports to minimize startup overhead.

## Troubleshooting Guide
Common issues and diagnostics:
- Authentication failures: Verify bearer token audience and issuer; check token expiration and JWKS availability.
- Policy denials: Inspect matched rule IDs and reasons; confirm roles and actions align with policy bundle.
- Unknown tools: Ensure tool registration and risk-tier admission; verify tool name matches definition.
- Upstream connectivity: Connectors return structured errors (e.g., K8S_NOT_CONFIGURED, ELASTIC_NOT_CONFIGURED, UPSTREAM_ERROR); check configuration and network reachability.
- Browser flow deviations: Off-origin navigation or stale flow provenance triggers specific denial codes; navigate back to bound target or re-bind flow.
- Redaction overflow: If too much of the result appears sensitive, outputs are withheld; tighten parameters or reduce payload size.
- HTTP connector issues: Origin allowlist denials, redirect loops, credential set resolution failures, and URL secret masking problems.
- SecretsConnector issues: Password policy violations, delivery handle expiration, email delivery configuration problems, and active destruction failures.
- **Updated** Audit attribution issues: Reserved key collisions are now safely handled with warning logs instead of HTTP 500 errors; check logs for "dropped reserved keys" messages if connector attribution is interfering with gateway-managed fields.
- **New** OAuth2.0 authorization issues: Verify all required environment variables are set, check JWKS endpoint connectivity, validate callback URL configuration, and confirm both human and workload trust sets are properly configured.
- **New** PKCE S256 issues: Check PKCE implementation, verify provider compatibility, inspect token response validation, and monitor process-local cache size.
- **New** Immutable target-account verification issues: Verify provider identity endpoint configuration, check account linkage configuration, and ensure authorized users cannot impersonate other accounts.
- **New** MCP-ingestion issues: Verify `GATEWAY_ANSIBLE_MCP_ENABLED=true`, check credential set configuration, validate MCP server connectivity, and confirm exactly six read-only tools are registered.

**Section sources**
- [gateway_service.py:61-156](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L61-L156)
- [gateway_service.py:43-69](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L43-L69)
- [k8s_connector.py:41-92](file://products/tool-gateway/src/tool_gateway/tools/k8s_connector.py#L41-L92)
- [elastic_connector.py:40-103](file://products/tool-gateway/src/tool_gateway/tools/elastic_connector.py#L40-L103)
- [browser_connector.py:533-698](file://products/tool-gateway/src/tool_gateway/tools/browser_connector.py#L533-L698)
- [http_connector.py:100-180](file://products/tool-gateway/src/tool_gateway/tools/http_connector.py#L100-L180)
- [redaction.py:126-151](file://products/tool-gateway/src/tool_gateway/tools/redaction.py#L126-L151)
- [test_tool_invoke.py:184-549](file://products/tool-gateway/tests/test_tool_invoke.py#L184-L549)
- [ansible-mcp-check.sh:188-230](file://shared/platform-ops/e2e/ansible-mcp-check.sh#L188-L230)
- [test_delegated_authorization.py:249-277](file://products/tool-gateway/tests/test_delegated_authorization.py#L249-L277)

## Conclusion
The Tool Gateway provides a secure, extensible, and observable framework for invoking external tools through standardized connectors. It enforces risk-tier admission, policy-based authorization, robust parameter validation, deterministic output redaction, and durable auditing. The platform now includes eight comprehensive built-in connectors covering Kubernetes, Elasticsearch, browser automation, HTTP services, incidents, skills repositories, secure secret delivery, and MCP-ingestion for Ansible/AAP systems, while the registry and base abstractions make it straightforward to add custom connectors with consistent behavior and governance.

**Updated** The critical addition of the complete OAuth2.0 authorization-code flow with PKCE S256 provides secure user delegation for external targets, enabling users to grant permissions without exposing credentials. The system implements dual trust boundaries for human and workload authentication, immutable target-account verification, comprehensive audit trails, and fail-closed security design.

The addition of HTTP connector capabilities extends the platform's ability to perform bounded HTTP service checks with the same security guarantees as other connectors, including origin allowlisting, credential set management, and URL secret masking. The complete implementation of SPEC-062 secure password generation and delivery system provides cryptographically strong password generation, secure one-time delivery mechanisms, and active destruction capabilities through the new DELETE endpoint. 

**New** The MCP-ingestion capabilities provide a secure, server-agnostic interface for connecting to external Model Context Protocol servers, with deny-by-default Ansible integration that requires explicit operator enablement. The architecture ensures that server metadata is never trusted, tools are registered purely from gateway-owned configuration, and all failures return structured error codes without exposing internal details.

This comprehensive connector ecosystem ensures that the Tool Gateway serves as a unified, secure boundary between the platform and external systems, maintaining consistent security policies, audit trails, and operational visibility across all tool invocations while providing flexible integration patterns for diverse operational requirements. The enhanced audit attribution system further strengthens this boundary by enabling rich, connector-specific audit enrichment without compromising system stability or security. The MCP-ingestion adapter extends these capabilities to support modern protocol-based integrations while maintaining the same security and governance standards. The OAuth2.0 authorization system adds another layer of security by enabling secure user delegation with PKCE S256 and immutable target-account verification, ensuring that authorized users cannot impersonate other accounts while maintaining strict separation between human and workload authentication boundaries.