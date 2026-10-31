# Platform Gateway

<cite>
**Referenced Files in This Document**
- [app.py](file://products/platform-gateway/src/platform_gateway/app.py)
- [main.py](file://products/platform-gateway/src/platform_gateway/main.py)
- [router.py](file://products/platform-gateway/src/platform_gateway/api/router.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [token_verifier.py](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py)
- [delegation_client.py](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py)
- [audit_emitter.py](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py)
- [target_authorization.py](file://products/platform-gateway/src/platform_gateway/services/target_authorization.py)
- [authorizations.py](file://products/platform-gateway/src/platform_gateway/api/routes/authorizations.py)
- [authorization.py](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py)
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [policy-default.yaml](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml)
- [SPEC-010-platform-gateway-extraction/spec.md](file://docs/specs/SPEC-010-platform-gateway-extraction/spec.md)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive coverage of Owner-Scoped Target Authorization Routes with browser-bound OAuth flows
- Enhanced security boundaries documentation for secure cookie handling and workload token validation
- Updated configuration section to include new target authorization settings
- Expanded architecture diagrams to show user-delegated identity flow integration with PKCE S256
- Added detailed security analysis of browser cookie binding and challenge-response mechanisms

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
The Platform Gateway is the operator portal's single HTTP entry point and policy enforcement edge. It authenticates requests by verifying platform tokens locally, delegates to the Identity Broker for token exchange when needed, evaluates centralized policies before forwarding requests to backend services (agent-platform, audit-service, tool-gateway, skills-hub), and emits durable audit events. Its design preserves deny-by-default authorization, supports approval workflows for mutating actions, and provides transparency endpoints that render the effective permission matrix from the live policy bundle.

Key responsibilities:
- Single entrypoint for all operator portal API requests
- Local JWT verification via JWKS with audience and issuer checks
- Token delegation to the Identity Broker for downstream tool execution
- Centralized policy evaluation against a YAML bundle with allow/deny/require_approval outcomes
- Request/response proxying to backend services with robust error posture
- Audit event emission for every policy decision and key operations
- Transparency surfaces exposing the effective role-to-action matrix
- **New**: Browser-bound owner-scoped target authorization routes with secure cookie binding, PKCE S256 support, and workload token validation for user-delegated identity flows

**Section sources**
- [SPEC-010-platform-gateway-extraction/spec.md:13-22](file://docs/specs/SPEC-010-platform-gateway-extraction/spec.md#L13-L22)
- [app.py:16-41](file://products/platform-gateway/src/platform_gateway/app.py#L16-L41)

## Project Structure
The product follows a consistent FastAPI service layout:
- Application bootstrap and middleware in app.py and main.py
- API routes under api/routes grouped by feature (auth, sessions, chat, incidents, documents, models, approvals, tools, policy, runtime, health, identity, authorizations)
- Services layer implementing business logic: gateway orchestration, policy engine, token verification, delegation, audit emission, client helpers, and target authorization
- Policies directory holding the default YAML bundle loaded at runtime
- Core configuration and telemetry/metrics setup

```mermaid
graph TB
subgraph "Platform Gateway"
A["FastAPI App<br/>app.py"]
B["Router<br/>api/router.py"]
C["Gateway Service<br/>services/gateway_service.py"]
D["Policy Engine<br/>services/policy_engine.py"]
E["Token Verifier<br/>services/token_verifier.py"]
F["Delegation Client<br/>services/delegation_client.py"]
G["Audit Emitter<br/>services/audit_emitter.py"]
H["Target Authorization<br/>services/target_authorization.py"]
I["Config<br/>core/config.py"]
J["Default Policy Bundle<br/>policies/policy-default.yaml"]
K["Authorizations Routes<br/>api/routes/authorizations.py"]
L["Authorization Schemas<br/>schemas/authorization.py"]
end
A --> B
B --> C
B --> K
K --> H
C --> D
C --> E
C --> F
C --> G
D --> J
C --> I
H --> I
H --> L
```

**Diagram sources**
- [app.py:16-41](file://products/platform-gateway/src/platform_gateway/app.py#L16-L41)
- [gateway_service.py:204-300](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L204-L300)
- [policy_engine.py:390-443](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L443)
- [token_verifier.py:52-89](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L52-L89)
- [delegation_client.py:190-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L190-L229)
- [audit_emitter.py:30-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L30-L99)
- [target_authorization.py:1-326](file://products/platform-gateway/src/platform_gateway/services/target_authorization.py#L1-L326)
- [authorizations.py:1-66](file://products/platform-gateway/src/platform_gateway/api/routes/authorizations.py#L1-L66)
- [authorization.py:1-56](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py#L1-L56)
- [config.py:23-53](file://products/platform-gateway/src/platform_gateway/core/config.py#L23-L53)
- [policy-default.yaml:1-52](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L1-L52)

**Section sources**
- [app.py:16-41](file://products/platform-gateway/src/platform_gateway/app.py#L16-L41)
- [main.py:6-8](file://products/platform-gateway/src/platform_gateway/main.py#L6-L8)
- [config.py:23-53](file://products/platform-gateway/src/platform_gateway/core/config.py#L23-L53)

## Core Components
- FastAPI application and middleware: request logging, metrics, telemetry setup, router inclusion
- Identity resolution: local JWT verification or synthetic dev identity based on settings
- Policy enforcement: evaluate action against loaded bundle; emit audit; raise 403 on deny
- Delegation: per-user cached delegated tokens exchanged with Identity Broker using workload token or static credentials
- Proxies: session, chat, incident, document, model, skill, tool, and approval endpoints with consistent upstream error mapping
- Transparency: live permission matrix derived from the enforced bundle
- **New**: Owner-scoped target authorization routes providing browser-bound OAuth coordination with secure cookie management, PKCE S256 support, and workload token validation for user-delegated identity acquisition

**Section sources**
- [app.py:16-41](file://products/platform-gateway/src/platform_gateway/app.py#L16-L41)
- [gateway_service.py:204-300](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L204-L300)
- [delegation_client.py:190-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L190-L229)
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)
- [target_authorization.py:1-326](file://products/platform-gateway/src/platform_gateway/services/target_authorization.py#L1-L326)

## Architecture Overview
The gateway sits between the operator portal and backend services. Every request is logged, authenticated, authorized, proxied, and audited. The new target authorization flow adds browser-bound OAuth coordination for user-delegated identity acquisition with PKCE S256 protection.

```mermaid
sequenceDiagram
participant Portal as "Operator Portal"
participant GW as "Platform Gateway"
participant ID as "Identity Broker"
participant TG as "Tool-Gateway"
participant AG as "Agent Platform"
participant AUD as "Audit Service"
Note over Portal,TG : Standard Flow
Portal->>GW : HTTP request (Bearer JWT)
GW->>GW : verify_token()
alt Valid token
GW->>GW : enforce_policy(action)
alt Allow
GW->>AG : Proxy request
AG-->>GW : Response
GW->>AUD : Emit audit event
GW-->>Portal : Response
else Require Approval
GW-->>Portal : 403 with approval details
GW->>AUD : Emit audit event
else Deny
GW-->>Portal : 403 denial
GW->>AUD : Emit audit event
end
else Missing/Invalid token
GW-->>Portal : 401
end
Note over Portal,TG : Target Authorization Flow with PKCE S256
Portal->>GW : POST /api/v1/targets/authorizations/{challenge_id}/start
GW->>GW : human() + owned_status()
GW->>TG : Internal POST /api/v2/targets/authorizations/{id}/start
TG-->>GW : {start_token, expires_at}
GW-->>Portal : Set __Host-luban-oauth-* cookies
Portal->>GW : GET /api/v1/targets/authorizations/start/{start_token}
GW->>TG : POST /api/v2/targets/authorizations/provider-url
TG-->>GW : provider_url (with code_challenge_method=S256)
GW-->>Portal : 302 redirect to provider
Portal->>GW : GET /api/v1/targets/authorizations/callback?code=...
GW->>TG : POST /api/v2/targets/authorizations/callback
TG-->>GW : {status, return_url}
GW-->>Portal : 302 redirect to safe return URL
```

**Diagram sources**
- [token_verifier.py:52-89](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L52-L89)
- [gateway_service.py:204-300](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L204-L300)
- [audit_emitter.py:30-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L30-L99)
- [target_authorization.py:201-326](file://products/platform-gateway/src/platform_gateway/services/target_authorization.py#L201-L326)
- [authorizations.py:11-66](file://products/platform-gateway/src/platform_gateway/api/routes/authorizations.py#L11-L66)

## Detailed Component Analysis

### Authentication and Identity Resolution
- Local JWT verification uses JWKS with issuer and audience validation
- Missing or invalid bearer tokens result in 401 unless authentication is disabled in dev mode
- Synthetic dev identity can be used when no token is present and auth is optional

```mermaid
flowchart TD
Start(["Request Received"]) --> HasAuth{"Authorization header?"}
HasAuth --> |No| RequireAuth{"require_auth enabled?"}
RequireAuth --> |Yes| Return401["Return 401"]
RequireAuth --> |No| DevIdentity["Create synthetic dev identity"]
HasAuth --> |Yes| Verify["verify_token()"]
Verify --> Ok{"Valid?"}
Ok --> |No| Return401
Ok --> |Yes| Next["Proceed to policy"]
```

**Diagram sources**
- [gateway_service.py:204-264](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L204-L264)
- [token_verifier.py:52-89](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L52-L89)
- [config.py:23-53](file://products/platform-gateway/src/platform_gateway/core/config.py#L23-L53)

**Section sources**
- [gateway_service.py:204-264](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L204-L264)
- [token_verifier.py:52-89](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L52-L89)
- [config.py:23-53](file://products/platform-gateway/src/platform_gateway/core/config.py#L23-L53)

### Policy Engine and Rule Evaluation
- Loads a YAML bundle (packaged default or configured path) and caches it per process
- Evaluates actions against roles with deny-by-default semantics
- Outcomes: allow, deny, require_approval; precedence: deny > require_approval > allow; higher priority wins within an outcome class
- Approval rules carry tier and decider roles; only bridged actions may use require_approval

```mermaid
flowchart TD
Start(["evaluate(roles, action)"]) --> Load["load_bundle()"]
Load --> Match["Find enabled rules matching roles and action"]
Match --> AnyDeny{"Any deny?"}
AnyDeny --> |Yes| Deny["Return deny with matched rule ids"]
AnyDeny --> |No| Approvals["Collect require_approval matches"]
Approvals --> HasApproval{"Any approvals?"}
HasApproval --> |Yes| BestApproval["Pick highest priority approval"]
BestApproval --> Require["Return require_approval with approval block"]
HasApproval --> |No| Allows["Collect allow matches"]
Allows --> HasAllow{"Any allows?"}
HasAllow --> |Yes| BestAllow["Pick highest priority allow"]
BestAllow --> Allow["Return allow"]
HasAllow --> |No| DefaultDeny["Return deny (no matching rule)"]
```

**Diagram sources**
- [policy_engine.py:334-371](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L334-L371)
- [policy_engine.py:390-443](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L443)
- [policy-default.yaml:53-326](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L53-L326)

**Section sources**
- [policy_engine.py:334-371](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L334-L371)
- [policy_engine.py:390-443](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L443)
- [policy-default.yaml:53-326](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L53-L326)

### Owner-Scoped Target Authorization Routes
**Updated** New owner-scoped authorization routes provide browser-bound OAuth coordination for user-delegated identity acquisition without retaining human tokens or performing tool dispatch. This implementation includes comprehensive security measures including PKCE S256 support and secure cookie handling.

Key features:
- **Browser Cookie Binding**: Uses `__Host-luban-oauth-*` prefixed cookies with UUID keys and cryptographically random secrets for challenge-response binding
- **Owner Scoping**: Validates that the requesting user owns the authorization challenge through session verification
- **Workload Token Validation**: Requires absolute path to workload token file with strict ASCII validation
- **Secure Callback Handling**: Processes OAuth callbacks with bounded query parameters and validated denial codes
- **PKCE S256 Support**: Integrates with Identity Broker's PKCE implementation for enhanced security
- **Policy Enforcement**: Requires `targets:authorize` policy for start operations and `session:read` for status checks

```mermaid
sequenceDiagram
participant Browser as "User Browser"
participant GW as "Platform Gateway"
participant TG as "Tool-Gateway"
participant Provider as "OAuth Provider"
Note over Browser,GW : Challenge Start with PKCE S256
Browser->>GW : POST /api/v1/targets/authorizations/{challenge_id}/start
GW->>GW : human() - verify JWT + policy
GW->>GW : owned_status() - validate ownership
GW->>TG : POST /{challenge_id}/start (workload token + browser_secret)
TG-->>GW : {start_token, expires_at}
GW-->>Browser : Set __Host-luban-oauth-{challenge_id}=secret cookie
Note over Browser,Provider : Provider Navigation with PKCE
Browser->>GW : GET /api/v1/targets/authorizations/start/{start_token}
GW->>TG : POST /provider-url (workload token + browser_bindings + code_challenge_method=S256)
TG-->>GW : {provider_url, expires_at}
GW-->>Browser : 302 redirect to provider
Note over Browser,Provider : OAuth Flow with PKCE Verification
Browser->>Provider : Complete OAuth authorization (code_challenge_method=S256)
Provider->>GW : GET /api/v1/targets/authorizations/callback?code=...
GW->>TG : POST /callback (workload token + browser_bindings + code_verifier)
TG-->>GW : {status, return_url}
GW-->>Browser : 302 redirect to safe return URL
```

**Diagram sources**
- [target_authorization.py:253-326](file://products/platform-gateway/src/platform_gateway/services/target_authorization.py#L253-L326)
- [authorizations.py:11-66](file://products/platform-gateway/src/platform_gateway/api/routes/authorizations.py#L11-L66)

**Security Boundaries:**
- Cookie values are bounded to 43-character Base64-like strings with UUID key validation
- Maximum 8 cookies per request with duplicate name rejection
- Query string parsing enforces strict field limits and character sets
- Workload token files are read with size limits (16KB max) and ASCII-only validation
- All internal requests to Tool-Gateway use bounded timeouts (10s) and response sizes (64KB)
- No raw exceptions or provider values leak to responses
- PKCE S256 ensures secure authorization code exchange with cryptographic proof
- Browser bindings are validated as complete units before any operation proceeds

**Section sources**
- [target_authorization.py:1-326](file://products/platform-gateway/src/platform_gateway/services/target_authorization.py#L1-L326)
- [authorizations.py:1-66](file://products/platform-gateway/src/platform_gateway/api/routes/authorizations.py#L1-L66)
- [authorization.py:1-56](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py#L1-L56)

### Authorization Matrix and Transparency
- Builds a role x action matrix from the enforced bundle
- Admin scope shows full matrix; other identities see only their own roles
- require_approval cells appear as false in boolean matrix plus additive approval_requirements structure

```mermaid
classDiagram
class PolicyMatrix {
+build_policy_matrix(settings, identity) dict
}
class PolicyEngine {
+evaluate(settings, roles, action) PolicyDecision
+bundle_metadata(settings) dict
+load_bundle(settings) list
}
PolicyMatrix --> PolicyEngine : "uses"
```

**Diagram sources**
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)
- [policy_engine.py:390-443](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L443)

**Section sources**
- [policy_matrix.py:31-87](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L87)

### Token Delegation and Tool Execution Path
- Exchanges verified user tokens for short-lived delegated tokens bound to the tool-gateway audience
- Per-user cache avoids repeated exchanges; refreshes near expiry
- Uses projected workload token when available, otherwise falls back to static service credentials
- Failure is non-fatal: proceeds without tools rather than breaking chat

```mermaid
sequenceDiagram
participant GW as "Platform Gateway"
participant ID as "Identity Broker"
participant TG as "Tool-Gateway"
GW->>GW : obtain_delegated_token(subject, subject_token)
alt Cache hit
GW-->>GW : return cached token
else Cache miss
GW->>ID : POST /api/v1/auth/exchange (workload token or client creds)
ID-->>GW : {access_token, expires_in}
GW->>GW : put(subject, token, expires_in)
GW-->>TG : Forward request with delegated bearer
end
```

**Diagram sources**
- [delegation_client.py:78-101](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L78-L101)
- [delegation_client.py:190-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L190-L229)

**Section sources**
- [delegation_client.py:78-101](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L78-L101)
- [delegation_client.py:190-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L190-L229)

### Request Routing and Proxy Patterns
- Routes are organized by feature and delegate to gateway_service functions
- Each proxy enforces a consistent error posture: upstream 4xx pass through; transport or upstream 5xx map to 502
- House headers propagate correlation IDs; timeouts and retries are controlled by settings

```mermaid
graph LR
R["Routes<br/>api/routes/*"] --> S["Gateway Service<br/>services/gateway_service.py"]
S --> A["Agent Platform"]
S --> T["Tool-Gateway"]
S --> SH["Skills Hub"]
S --> AU["Audit Service"]
```

**Diagram sources**
- [gateway_service.py:331-800](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L331-L800)

**Section sources**
- [gateway_service.py:331-800](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L331-L800)

### Approval Workflow Integration
- Mutating tool execution requires tier_2 approval; the policy engine returns require_approval with an approval block
- The gateway bridges the confirmation flow so designated approvers can approve parked calls
- Approval decisions are scoped to specific roles and cannot self-approve at tier_2

```mermaid
sequenceDiagram
participant OP as "Operator"
participant GW as "Platform Gateway"
participant POL as "Policy Engine"
participant AUD as "Audit Service"
OP->>GW : chat : confirm (mutating action)
GW->>POL : evaluate("tools : mutate", roles)
POL-->>GW : require_approval {tier : tier_2, decided_by_roles}
GW-->>OP : 403 with approval details
Note over OP,GW : Designated approver reviews and confirms
OP->>GW : confirm approved call
GW->>AUD : emit policy_decision
GW-->>OP : proceed with execution
```

**Diagram sources**
- [policy_engine.py:390-443](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L443)
- [policy-default.yaml:130-152](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L130-L152)
- [audit_emitter.py:30-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L30-L99)

**Section sources**
- [policy_engine.py:390-443](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L443)
- [policy-default.yaml:130-152](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L130-L152)

### Audit Event Emission
- Every policy decision is emitted as a durable audit event
- Emission is fire-and-forget on a daemon thread with a short timeout; failures do not degrade the request path
- Events include subject, username, actor, roles, and structured details

```mermaid
flowchart TD
Decision["Policy Decision"] --> Build["build_audit_event(...)"]
Build --> Emit["emit_audit_event(...)"]
Emit --> Thread{"Audit URL configured?"}
Thread --> |No| LogOnly["Log-only behavior"]
Thread --> |Yes| Deliver["POST /api/v1/audit/events"]
Deliver --> Result{"Success?"}
Result --> |Yes| Record["record_audit_emit('ok')"]
Result --> |No| Fail["record_audit_emit('error') + log"]
```

**Diagram sources**
- [gateway_service.py:303-328](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L303-L328)
- [audit_emitter.py:30-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L30-L99)

**Section sources**
- [gateway_service.py:303-328](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L303-L328)
- [audit_emitter.py:30-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L30-L99)

### Error Handling for Policy Denials
- Deny results in a structured 403 with action, reason, and matched rule ids
- Metrics record the decision; audit event captures the denial context
- Upstream errors are normalized to 502 to avoid leaking internal failures

```mermaid
flowchart TD
Enforce["enforce_policy(...)"] --> Eval["evaluate(...)"]
Eval --> Outcome{"decision == 'deny'?"}
Outcome --> |Yes| Audit["_emit_policy_decision(...)"]
Audit --> Raise["Raise 403 with detail"]
Outcome --> |No| Continue["Continue to proxy"]
```

**Diagram sources**
- [gateway_service.py:267-300](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L267-L300)

**Section sources**
- [gateway_service.py:267-300](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L267-L300)

## Configuration Options
**Updated** The Platform Gateway now includes new configuration options for target authorization and enhanced delegation support:

### Target Authorization Settings
- `PLATFORM_GATEWAY_TARGET_AUTHORIZATION_ENABLED`: Enable/disable owner-scoped target authorization routes (default: false)
- `PLATFORM_GATEWAY_AUTHORIZATION_WORKLOAD_TOKEN_PATH`: Absolute path to workload token file for internal Tool-Gateway communication

### Delegation Configuration
- `PLATFORM_GATEWAY_DELEGATION_AUDIENCE`: Audience for delegated tokens (default: "tool-gateway")
- `PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH`: Path to projected workload token for service-to-service authentication

### Environment Variables
```bash
# Target Authorization (optional)
export PLATFORM_GATEWAY_TARGET_AUTHORIZATION_ENABLED=true
export PLATFORM_GATEWAY_AUTHORIZATION_WORKLOAD_TOKEN_PATH=/var/run/secrets/workload-token

# Delegation (existing)
export PLATFORM_GATEWAY_DELEGATION_AUDIENCE=tool-gateway
export PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH=/var/run/secrets/workload-token

# Service URLs
export AGENT_SERVICE_URL=http://agent-service:8000
export IDENTITY_SERVICE_URL=http://identity-service:8000
export PLATFORM_GATEWAY_TOOL_GATEWAY_URL=https://tool-gateway.internal
```

**Section sources**
- [config.py:23-53](file://products/platform-gateway/src/platform_gateway/core/config.py#L23-L53)
- [config.py:56-129](file://products/platform-gateway/src/platform_gateway/core/config.py#L56-L129)
- [target_authorization.py:55-68](file://products/platform-gateway/src/platform_gateway/services/target_authorization.py#L55-L68)

## Dependency Analysis
- The gateway depends on:
  - Identity Broker for token exchange and JWKS
  - Agent Platform for sessions, chat, incidents, documents, models, skills
  - Tool-Gateway for tool invocation (via delegated tokens) and target authorization coordination
  - Audit Service for durable audit ingestion
- Configuration drives service URLs, audiences, and feature toggles

```mermaid
graph TB
GW["Platform Gateway"]
IDB["Identity Broker"]
AGP["Agent Platform"]
TGW["Tool-Gateway"]
AUD["Audit Service"]
GW --> IDB
GW --> AGP
GW --> TGW
GW --> AUD
```

**Diagram sources**
- [config.py:23-53](file://products/platform-gateway/src/platform_gateway/core/config.py#L23-L53)
- [delegation_client.py:78-101](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L78-L101)
- [audit_emitter.py:68-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L68-L99)

**Section sources**
- [config.py:23-53](file://products/platform-gateway/src/platform_gateway/core/config.py#L23-L53)
- [delegation_client.py:78-101](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L78-L101)
- [audit_emitter.py:68-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L68-L99)

## Performance Considerations
- Local JWT verification eliminates per-request introspection latency
- JWKS keys are cached with a configurable lifespan
- Delegated tokens are cached per user subject with early refresh near expiry
- Audit emission is asynchronous and non-blocking
- Policy bundle is loaded once and cached per process; metadata includes version and SHA-256 fingerprint
- **New**: Target authorization routes use bounded timeouts (10s) and response sizes (64KB) to prevent resource exhaustion
- **New**: Browser cookie parsing validates complete cookie jars with strict bounds checking
- **New**: PKCE S256 adds minimal overhead while significantly enhancing security posture

## Troubleshooting Guide
Common issues and diagnostics:
- 401 Unauthorized: missing or malformed Authorization header; expired or invalid token; wrong issuer/audience
- 403 Forbidden: explicit deny rule matched; no matching rule; require_approval not yet satisfied; target authorization disabled
- 404 Not Found: invalid challenge ID format; expired authorization challenge; unauthorized access attempt
- 409 Conflict: duplicate challenge cookie detected; terminal challenge state; insufficient browser bindings
- 502 Bad Gateway: upstream service unavailable or returned 5xx; identity service unreachable during login flows; target authorization backend failure
- 503 Service Unavailable: target authorization misconfigured; workload token path invalid; required dependencies missing

Operational checks:
- Readiness endpoint exposes policy rule count and bundle SHA-256
- Live status reports service name and version
- Audit logs capture policy decisions and emit failures
- **New**: Target authorization routes validate configuration on first request and return appropriate error codes for misconfiguration
- **New**: Browser cookie validation failures are logged with sanitized error messages to prevent information leakage

**Section sources**
- [gateway_service.py:57-88](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L57-L88)
- [gateway_service.py:204-300](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L204-L300)
- [audit_emitter.py:68-99](file://products/platform-gateway/src/platform_gateway/services/audit_emitter.py#L68-L99)
- [target_authorization.py:55-68](file://products/platform-gateway/src/platform_gateway/services/target_authorization.py#L55-L68)

## Conclusion
The Platform Gateway centralizes security and policy enforcement for the operator portal. It authenticates via local JWT verification, delegates tokens for tool execution, evaluates a strict deny-by-default policy bundle, integrates approval workflows for mutating actions, proxies requests to backend services with robust error handling, and emits durable audit events. Transparency endpoints expose the effective permission matrix, ensuring operators can understand and validate their access.

**Updated** The addition of owner-scoped target authorization routes extends the gateway's capabilities to coordinate browser-bound OAuth flows for user-delegated identity acquisition with PKCE S256 protection. These routes maintain strict security boundaries through cookie binding, workload token validation, and policy enforcement while providing seamless integration with the broader user-delegated identity ecosystem. The implementation ensures that sensitive OAuth state never leaks to the browser, that PKCE challenges are properly validated, and that all authorization decisions remain scoped to verified owners. The comprehensive input validation and bounded processing ensure resilience against malicious inputs while maintaining high performance for legitimate authorization flows.