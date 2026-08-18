# Platform Gateway Service

<cite>
**Referenced Files in This Document**
- [README.md](file://products/platform-gateway/README.md)
- [main.py](file://products/platform-gateway/src/platform_gateway/main.py)
- [app.py](file://products/platform-gateway/src/platform_gateway/app.py)
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [router.py](file://products/platform-gateway/src/platform_gateway/api/router.py)
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)
- [sessions.py](file://products/platform-gateway/src/platform_gateway/api/routes/sessions.py)
- [incidents.py](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [agent_client.py](file://products/platform-gateway/src/platform_gateway/services/agent_client.py)
- [incident_client.py](file://products/platform-gateway/src/platform_gateway/services/incident_client.py)
- [delegation_client.py](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py)
- [token_verifier.py](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py)
- [policy-default.yaml](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml)
- [SPEC-010 spec.md](file://docs/specs/SPEC-010-platform-gateway-extraction/spec.md)
- [ADR-0005](file://docs/adr/0005-platform-gateway-extraction.md)
</cite>

## Update Summary
**Changes Made**
- Added new Incident Proxy Routes section documenting the unified API access to incident service
- Updated Architecture Overview to include incident service integration
- Enhanced Policy Engine section with incident-specific actions and roles
- Added Incident Client component analysis
- Updated Dependency Analysis to include incident service dependencies
- Enhanced Troubleshooting Guide with incident-specific issues

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
The Platform Gateway Service is the portal-facing edge service for the Luban AIOps platform. It authenticates portal users via JWT verification, enforces deny-by-default action policies, proxies chat and session requests to the agent-platform service, mediates short-lived delegated tokens through the identity-broker for downstream tool access, and provides unified API access to the incident service with policy enforcement for incident operations. It exposes health, metrics, and runtime endpoints and maintains request correlation across hops.

Key responsibilities:
- Verify portal bearer tokens (issuer/audience JWKS validation; audience bound to platform-gateway).
- Enforce deny-by-default policy bundle on every portal-facing action (e.g., chat, sessions:*, incidents:*).
- Proxy chat/session traffic to agent-platform, exchanging the portal token for a short-lived delegated token (aud = tool-gateway, act.sub = platform-gateway) via identity-broker before forwarding.
- Provide unified API access to incident-service with per-action policy enforcement (incident:read, incident:create, incident:triage) and Basic credential authentication upstream.
- Relay auth/identity/runtime endpoints to identity-broker and agent-platform as needed.
- Expose /health/live, /health/ready, and /metrics.

**Section sources**
- [README.md:1-46](file://products/platform-gateway/README.md#L1-L46)
- [SPEC-010 spec.md:1-170](file://docs/specs/SPEC-010-platform-gateway-extraction/spec.md#L1-L170)
- [ADR-0005:1-47](file://docs/adr/0005-platform-gateway-extraction.md#L1-L47)

## Project Structure
The product follows a consistent FastAPI layout:
- Entry point and server configuration
- Application factory with middleware and telemetry
- API router aggregating route modules
- Services encapsulating business logic and external calls
- Policy bundle for deny-by-default authorization
- Configuration and runtime settings

```mermaid
graph TB
subgraph "Entry"
M["main.py"]
A["app.py"]
end
subgraph "API"
R["api/router.py"]
RC["api/routes/chat.py"]
RS["api/routes/sessions.py"]
RI["api/routes/incidents.py"]
end
subgraph "Services"
GS["services/gateway_service.py"]
AC["services/agent_client.py"]
IC["services/incident_client.py"]
DC["services/delegation_client.py"]
TV["services/token_verifier.py"]
end
subgraph "Policy"
P["policies/policy-default.yaml"]
end
subgraph "Config"
CFG["core/config.py"]
RT["core/runtime.py"]
end
M --> A
A --> R
R --> RC
R --> RS
R --> RI
RC --> GS
RS --> GS
RI --> IC
GS --> AC
GS --> DC
GS --> TV
GS --> P
A --> CFG
A --> RT
```

**Diagram sources**
- [main.py:1-9](file://products/platform-gateway/src/platform_gateway/main.py#L1-L9)
- [app.py:1-44](file://products/platform-gateway/src/platform_gateway/app.py#L1-L44)
- [router.py:1-23](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L23)
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [sessions.py:1-70](file://products/platform-gateway/src/platform_gateway/api/routes/sessions.py#L1-L70)
- [incidents.py:1-183](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L1-L183)
- [gateway_service.py:1-301](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L301)
- [agent_client.py:1-124](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L1-L124)
- [incident_client.py:1-193](file://products/platform-gateway/src/platform_gateway/services/incident_client.py#L1-L193)
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)
- [token_verifier.py:1-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L1-L99)
- [policy-default.yaml:1-117](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L1-L117)
- [config.py:1-117](file://products/platform-gateway/src/platform_gateway/core/config.py#L1-L117)
- [runtime.py:1-30](file://products/platform-gateway/src/platform_gateway/core/runtime.py#L1-L30)

**Section sources**
- [README.md:1-46](file://products/platform-gateway/README.md#L1-L46)

## Core Components
- Application bootstrap and middleware:
  - Creates FastAPI app, registers HTTP logging middleware, includes routers, sets up metrics and telemetry.
- Settings and runtime:
  - Environment-driven configuration for upstream services, JWKS, audiences, policy path, timeouts, and dev behavior.
  - Run settings for host/port resolution.
- API routes:
  - Chat and Sessions endpoints enforcing identity and policy, delegating to gateway service.
  - **New**: Incident proxy routes providing unified API access to incident-service with per-action policy enforcement.
- Gateway service:
  - Identity resolution, policy enforcement, proxying to agent-platform, streaming chat support.
- External clients:
  - Agent client for agent-platform v2 endpoints.
  - **New**: Incident client for incident-service with Basic credential authentication and error mapping.
  - Delegation client for broker-mediated token exchange with per-user cache and workload-token preference.
- Token verifier:
  - Local JWT verification using JWKS with issuer/audience checks and actor extraction.
- Policy engine:
  - Loads YAML bundle and evaluates actions against roles with deny-by-default semantics.
  - **Updated**: Now includes incident-specific actions (incident:read, incident:create, incident:triage) with appropriate role-based access control.

**Section sources**
- [app.py:1-44](file://products/platform-gateway/src/platform_gateway/app.py#L1-L44)
- [config.py:1-117](file://products/platform-gateway/src/platform_gateway/core/config.py#L1-L117)
- [runtime.py:1-30](file://products/platform-gateway/src/platform_gateway/core/runtime.py#L1-L30)
- [router.py:1-23](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L23)
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [sessions.py:1-70](file://products/platform-gateway/src/platform_gateway/api/routes/sessions.py#L1-L70)
- [incidents.py:1-183](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L1-L183)
- [gateway_service.py:1-301](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L301)
- [agent_client.py:1-124](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L1-L124)
- [incident_client.py:1-193](file://products/platform-gateway/src/platform_gateway/services/incident_client.py#L1-L193)
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)
- [token_verifier.py:1-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L1-L99)
- [policy-default.yaml:1-117](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L1-L117)

## Architecture Overview
The gateway sits between the portal and backend services. It authenticates users, authorizes actions, proxies requests, and obtains delegated tokens for tool execution paths. The architecture now includes unified access to the incident service with proper policy enforcement and credential management.

```mermaid
sequenceDiagram
participant Portal as "Portal Client"
participant GW as "Platform Gateway"
participant ID as "Identity Broker"
participant AG as "Agent Platform"
participant IS as "Incident Service"
Portal->>GW : POST /api/v1/chat or GET /api/v1/incidents
GW->>GW : Resolve identity (JWT verify)
GW->>GW : Enforce policy (deny-by-default)
alt Chat Request
GW->>ID : Exchange subject token for delegated token
ID-->>GW : Delegated token (aud=tool-gateway)
GW->>AG : Forward chat request with delegated token
AG-->>GW : Chat response or stream chunks
else Incident Request
GW->>IS : Forward with Basic credential + headers
IS-->>GW : Incident data or triage result
end
GW-->>Portal : Response or SSE stream
```

**Diagram sources**
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [incidents.py:1-183](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L1-L183)
- [gateway_service.py:1-301](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L301)
- [incident_client.py:1-193](file://products/platform-gateway/src/platform_gateway/services/incident_client.py#L1-L193)
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)
- [agent_client.py:1-124](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L1-L124)

## Detailed Component Analysis

### API Router and Routes
- The router aggregates health, runtime, auth, identity, sessions, chat, audit, and **newly added** incidents routes.
- Chat, Sessions, and **Incident** routes enforce identity and policy before delegating to their respective service functions.
- **Updated**: Incident routes provide unified API access with per-action policy enforcement for incident:read, incident:create, and incident:triage.

```mermaid
classDiagram
class Router {
+include_router(health)
+include_router(runtime)
+include_router(auth)
+include_router(identity)
+include_router(sessions)
+include_router(chat)
+include_router(audit)
+include_router(incidents)
}
class ChatRoutes {
+POST /api/v1/chat
+GET /api/v1/chat/stream
}
class SessionsRoutes {
+POST /api/v1/sessions
+GET /api/v1/sessions/{session_id}
}
class IncidentsRoutes {
+GET /api/v1/incidents
+POST /api/v1/incidents
+GET /api/v1/incidents/{incident_id}
+GET /api/v1/incidents/{incident_id}/report
+POST /api/v1/incidents/{incident_id}/triage
}
Router --> ChatRoutes : "includes"
Router --> SessionsRoutes : "includes"
Router --> IncidentsRoutes : "includes"
```

**Diagram sources**
- [router.py:1-23](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L23)
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [sessions.py:1-70](file://products/platform-gateway/src/platform_gateway/api/routes/sessions.py#L1-L70)
- [incidents.py:1-183](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L1-L183)

**Section sources**
- [router.py:1-23](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L23)
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [sessions.py:1-70](file://products/platform-gateway/src/platform_gateway/api/routes/sessions.py#L1-L70)
- [incidents.py:1-183](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L1-L183)

### Incident Proxy Routes
**New** - Provides unified API access to the incident-service with comprehensive policy enforcement and credential management.

- **List Incidents**: GET /api/v1/incidents with filtering by status, severity, source, limit, and offset
- **Create Incident**: POST /api/v1/incidents for manual incident reporting with reported_by tracking
- **Get Incident Detail**: GET /api/v1/incidents/{incident_id} with incident ID validation
- **Get Report**: GET /api/v1/incidents/{incident_id}/report for triage reports
- **Run Triage**: POST /api/v1/incidents/{incident_id}/triage requiring operator delegation chain

Key features:
- Per-action policy enforcement (incident:read, incident:create, incident:triage)
- Basic credential authentication to incident-service (never forwards user tokens)
- Operator identity forwarding via X-User-ID header for triage operations
- Delegated token forwarding via X-Delegated-Token header for agent turn execution
- Strict incident ID validation (pattern: inc-<lowercase alphanumeric>)
- Comprehensive error mapping (503 when unconfigured, 502 on transport failures, 4xx passthrough)

```mermaid
flowchart TD
Start(["Incident Request"]) --> ValidateId{"Valid Incident ID?"}
ValidateId --> |No| Error400["HTTP 400"]
ValidateId --> |Yes| ResolveId["Resolve Request Identity"]
ResolveId --> AuthCheck{"Auth Required?"}
AuthCheck --> |Yes & No Token| Deny401["HTTP 401"]
AuthCheck --> |No Token & Optional| Synthetic["Create Synthetic Dev Identity"]
AuthCheck --> |Has Token| Verify["Verify JWT Locally"]
Verify --> Valid{"Valid?"}
Valid --> |No| Deny401
Valid --> |Yes| PolicyEnf["Enforce Policy (incident:verb)"]
PolicyEnf --> Allowed{"Allowed?"}
Allowed --> |No| Deny403["HTTP 403"]
Allowed --> |Yes| CheckType{"Operation Type?"}
CheckType --> |Read/Create| BasicAuth["Use Basic Credential"]
CheckType --> |Triage| GetDeleg["Obtain Delegated Token"]
BasicAuth --> Proxy["Proxy to Incident Service"]
GetDeleg --> HasToken{"Has Token?"}
HasToken --> |No| Fail503["HTTP 503"]
HasToken --> |Yes| Proxy
Proxy --> Return(["Return Response"])
```

**Diagram sources**
- [incidents.py:63-183](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L63-L183)
- [incident_client.py:35-193](file://products/platform-gateway/src/platform_gateway/services/incident_client.py#L35-L193)

**Section sources**
- [incidents.py:1-183](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L1-L183)

### Incident Client
**New** - Handles all communication with the incident-service, implementing secure proxy patterns with proper credential management and error handling.

- **Authentication**: Uses gateway-held Basic credentials (INCIDENT_CLIENT_ID/SECRET) - never forwards user tokens
- **Request Handling**: Async HTTP client with configurable timeouts and comprehensive error mapping
- **Header Management**: Adds x-request-id for tracing, x-reported-by for incident creation, x-user-id and x-delegated-token for triage
- **Error Mapping**: Consistent error handling - 503 when service unconfigured, 502 on transport failures, 4xx passthrough with upstream messages

Key capabilities:
- List incidents with filtering parameters (status, severity, source, pagination)
- Create incidents with automatic reporter attribution
- Retrieve incident details and triage reports
- Execute triage operations with operator identity and delegated token forwarding
- Configurable timeout for triage operations (default 120 seconds)

```mermaid
classDiagram
class IncidentClient {
+_base_url(settings) string
+_credential(settings) tuple
+_raise_upstream(response) void
+list_incidents(settings, request_id, params) dict
+get_incident(settings, request_id, incident_id) dict
+get_report(settings, request_id, incident_id) dict
+create_incident(settings, request_id, payload, reported_by) dict
+run_triage(settings, request_id, incident_id, operator, delegated_token) dict
}
class ErrorMapping {
+503 : "incident service not configured"
+502 : "incident service unavailable"
+4xx : "passthrough with upstream message"
}
IncidentClient --> ErrorMapping : "uses"
```

**Diagram sources**
- [incident_client.py:35-193](file://products/platform-gateway/src/platform_gateway/services/incident_client.py#L35-L193)

**Section sources**
- [incident_client.py:1-193](file://products/platform-gateway/src/platform_gateway/services/incident_client.py#L1-L193)

### Gateway Service
- Identity resolution supports local JWT verification and synthetic dev identity when auth is optional.
- Policy enforcement uses evaluate() from the policy engine; denies by default and records decisions.
- Proxies chat and session operations to agent-platform via agent_client.
- Provides streaming chat via StreamingResponse.

```mermaid
flowchart TD
Start(["Request Entry"]) --> ResolveId["Resolve Request Identity"]
ResolveId --> AuthCheck{"Auth Required?"}
AuthCheck --> |Yes & No Token| Deny401["HTTP 401"]
AuthCheck --> |No Token & Optional| Synthetic["Create Synthetic Dev Identity"]
AuthCheck --> |Has Token| Verify["Verify JWT Locally"]
Verify --> Valid{"Valid?"}
Valid --> |No| Deny401
Valid --> |Yes| PolicyEnf["Enforce Policy (action)"]
PolicyEnf --> Allowed{"Allowed?"}
Allowed --> |No| Deny403["HTTP 403"]
Allowed --> |Yes| Delegate["Obtain Delegated Token"]
Delegate --> Proxy["Proxy to Agent Platform"]
Proxy --> Return(["Return Response/Stream"])
```

**Diagram sources**
- [gateway_service.py:1-301](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L301)
- [token_verifier.py:1-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L1-L99)
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)

**Section sources**
- [gateway_service.py:1-301](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L301)

### Agent Client
- Single HTTP client binding to agent-platform v2 endpoints (/api/v2/*).
- Adds x-request-id and X-User-ID headers; forwards Authorization when delegated token present.
- Supports both regular and streaming chat with appropriate timeouts.

```mermaid
classDiagram
class AgentClient {
+create_session(settings, request_id, user_id) dict
+get_session(settings, request_id, session_id, user_id) dict
+chat(settings, request_id, user_id, message, session_id, delegated_token) dict
+stream_chat(settings, request_id, user_id, message, session_id, delegated_token) AsyncIterator[str]
+runtime_metadata(settings) dict
+health(settings) dict
}
```

**Diagram sources**
- [agent_client.py:1-124](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L1-L124)

**Section sources**
- [agent_client.py:1-124](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L1-L124)

### Delegation Client
- Per-replica, per-user cache for delegated tokens with refresh-before-expiry strategy.
- Exchanges subject token at identity-broker using workload token (preferred) or static client credentials.
- Non-fatal failures allow chat to proceed without tools.
- Dev mode mints short-lived subject tokens signed locally.

```mermaid
classDiagram
class DelegationClient {
-_cache : dict
-_dev_key : RSA key
-_workload_fallback_warned : bool
+reset() void
+get_cached(subject) string?
+put(subject, token, expires_in) void
+exchange(settings, subject_token) tuple<string,int>
+mint_dev_subject_token(settings) string
-_read_workload_token(settings) string?
}
class CacheEntry {
+token : string
+expires_at : float
+refresh_at : float
}
DelegationClient --> CacheEntry : "uses"
```

**Diagram sources**
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)

**Section sources**
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)

### Token Verifier
- Local JWT verification via JWKS with caching and lifespan control.
- Validates issuer, audience, required claims, and extracts actor (act.sub) if present.
- Raises typed errors for expired, invalid issuer/audience, and malformed tokens.

```mermaid
classDiagram
class TokenVerifier {
+verify_token(settings, token) IdentityContext
+reset_verifier_state() void
}
class IdentityContext {
+subject : string
+username : string
+email : string?
+groups : list
+roles : list
+actor : string?
}
TokenVerifier --> IdentityContext : "returns"
```

**Diagram sources**
- [token_verifier.py:1-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L1-L99)

**Section sources**
- [token_verifier.py:1-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L1-L99)

### Policy Engine and Default Bundle
- Loads YAML policy bundle and evaluates actions against roles with deny-by-default semantics.
- Explicit deny overrides allow; higher priority rules win among allows; disabled rules ignored.
- **Updated**: Default bundle now includes incident-specific actions with appropriate role-based access control:
  - `incident:read` granted to operational, developer, and read-only observer roles
  - `incident:create` restricted to operational and developer roles  
  - `incident:triage` restricted to operational and developer roles with mandatory delegation chain

```mermaid
flowchart TD
Load["Load Policy Bundle"] --> Evaluate["Evaluate Action vs Rules"]
Evaluate --> Match{"Any Rule Matches?"}
Match --> |No| Deny["Deny (default)"]
Match --> |Yes| Priority["Apply Priority & Explicit Deny"]
Priority --> Decision["Decision: Allow/Deny"]
Decision --> Record["Record Metrics & Log"]
```

**Diagram sources**
- [policy-default.yaml:1-117](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L1-L117)
- [gateway_service.py:222-254](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L222-L254)

**Section sources**
- [policy-default.yaml:1-117](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L1-L117)
- [gateway_service.py:222-254](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L222-L254)

### Application Bootstrap and Middleware
- FastAPI app creation with HTTP request logging middleware capturing method, path, status, duration, and request correlation id.
- Includes routers, sets up metrics and telemetry with service name/version metadata.

```mermaid
sequenceDiagram
participant Uvicorn as "Uvicorn"
participant App as "FastAPI App"
participant MW as "HTTP Logging Middleware"
participant Router as "API Router"
Uvicorn->>App : Create app
App->>MW : Register middleware
App->>Router : Include routers
Uvicorn->>App : Serve requests
App->>MW : log_requests(request, call_next)
MW->>Router : call_next(request)
Router-->>MW : response
MW-->>Uvicorn : response with logs/metrics
```

**Diagram sources**
- [main.py:1-9](file://products/platform-gateway/src/platform_gateway/main.py#L1-L9)
- [app.py:1-44](file://products/platform-gateway/src/platform_gateway/app.py#L1-L44)
- [router.py:1-23](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L23)

**Section sources**
- [main.py:1-9](file://products/platform-gateway/src/platform_gateway/main.py#L1-L9)
- [app.py:1-44](file://products/platform-gateway/src/platform_gateway/app.py#L1-L44)

## Dependency Analysis
High-level dependencies:
- main.py depends on app.py and runtime settings.
- app.py depends on router, metrics, observability, request context, telemetry, and metadata.
- api routes depend on gateway_service, config, schemas, and delegation_client.
- **New**: Incident routes depend on incident_client for service communication.
- gateway_service depends on agent_client, delegation_client, token_verifier, and policy_engine.
- **New**: incident_client depends on httpx and config for incident-service communication.
- agent_client depends on httpx and config.
- delegation_client depends on httpx, jwt, cryptography, and config.
- token_verifier depends on jwt and PyJWKClient.

```mermaid
graph TB
Main["main.py"] --> App["app.py"]
App --> Router["api/router.py"]
Router --> Chat["api/routes/chat.py"]
Router --> Sessions["api/routes/sessions.py"]
Router --> Incidents["api/routes/incidents.py"]
Chat --> GwSvc["services/gateway_service.py"]
Sessions --> GwSvc
Incidents --> IncClient["services/incident_client.py"]
GwSvc --> Agent["services/agent_client.py"]
GwSvc --> Deleg["services/delegation_client.py"]
GwSvc --> Verify["services/token_verifier.py"]
GwSvc --> Policy["policies/policy-default.yaml"]
IncClient --> Config["core/config.py"]
App --> Config
App --> Runtime["core/runtime.py"]
```

**Diagram sources**
- [main.py:1-9](file://products/platform-gateway/src/platform_gateway/main.py#L1-L9)
- [app.py:1-44](file://products/platform-gateway/src/platform_gateway/app.py#L1-L44)
- [router.py:1-23](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L23)
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [sessions.py:1-70](file://products/platform-gateway/src/platform_gateway/api/routes/sessions.py#L1-L70)
- [incidents.py:1-183](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L1-L183)
- [gateway_service.py:1-301](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L301)
- [incident_client.py:1-193](file://products/platform-gateway/src/platform_gateway/services/incident_client.py#L1-L193)
- [agent_client.py:1-124](file://products/platform-gateway/src/platform_gateway/services/agent_client.py#L1-L124)
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)
- [token_verifier.py:1-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L1-L99)
- [policy-default.yaml:1-117](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L1-L117)
- [config.py:1-117](file://products/platform-gateway/src/platform_gateway/core/config.py#L1-L117)
- [runtime.py:1-30](file://products/platform-gateway/src/platform_gateway/core/runtime.py#L1-L30)

**Section sources**
- [README.md:1-46](file://products/platform-gateway/README.md#L1-L46)

## Performance Considerations
- JWKS client caching reduces repeated key fetches; lifespan controlled by environment.
- Delegated token per-user cache avoids frequent broker exchanges; refresh fraction triggers early renewal.
- Streaming chat uses non-blocking async I/O with appropriate timeouts to prevent resource exhaustion.
- Health and readiness checks validate policy load and upstream connectivity to surface degraded states quickly.
- **New**: Incident service requests use configurable timeouts (10s default, 120s for triage) to prevent resource exhaustion.
- **New**: Incident ID validation occurs before upstream calls to avoid unnecessary network overhead.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and diagnostics:
- Authentication failures:
  - Malformed Authorization header or missing token when auth is required results in 401.
  - Expired or invalid issuer/audience raises specific verification errors.
- Policy denials:
  - Actions not matching any allow rule are denied by default; check role membership and action names.
  - **New**: Incident-specific actions require appropriate roles (incident:read for observers, incident:create/triage for operators/developers).
- Delegation failures:
  - If workload token is unavailable, falls back to static credentials; failures are logged and non-fatal, allowing tool-less operation.
  - **New**: Triage operations require successful delegation chain; missing delegated tokens result in 503 errors.
- Readiness degradation:
  - Policy load errors or agent-service connectivity issues mark readiness as degraded.
  - **New**: Missing incident service configuration results in 503 responses for all incident endpoints.
- **New**: Incident service connectivity issues:
  - Transport failures map to 502 with "incident service unavailable" detail.
  - Upstream 5xx errors map to 502, while 4xx errors pass through unchanged.
  - Invalid incident IDs (not matching pattern inc-<lowercase alphanumeric>) return 400 before upstream calls.

Operational tips:
- Inspect logs for "identity verified locally", "policy decision", "delegation exchange failed", and "workload token unavailable".
- Use /health/ready to detect degraded states and underlying error reasons.
- Validate environment variables for JWKS URL, audiences, policy path, and incident service configuration.
- **New**: Verify INCIDENT_SERVICE_URL, INCIDENT_CLIENT_ID, and INCIDENT_CLIENT_SECRET are properly configured.
- **New**: Monitor incident-specific metrics for listing, creation, and triage operations.

**Section sources**
- [gateway_service.py:159-254](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L159-L254)
- [delegation_client.py:190-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L190-L229)
- [token_verifier.py:52-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L52-L99)
- [incidents.py:43-50](file://products/platform-gateway/src/platform_gateway/api/routes/incidents.py#L43-L50)
- [incident_client.py:35-63](file://products/platform-gateway/src/platform_gateway/services/incident_client.py#L35-L63)

## Conclusion
The Platform Gateway Service cleanly separates portal-facing security and control-plane concerns from tool execution capabilities. It enforces strong authentication and authorization, proxies to agent-platform securely with least-privilege delegated tokens, and now provides unified API access to the incident service with comprehensive policy enforcement and credential management. The design aligns with workspace model boundaries and enables future growth without compromising trust or clarity. The addition of incident service integration demonstrates the gateway's extensibility in providing secure, policy-enforced access to additional backend services while maintaining consistent security patterns and operational visibility.

[No sources needed since this section summarizes without analyzing specific files]