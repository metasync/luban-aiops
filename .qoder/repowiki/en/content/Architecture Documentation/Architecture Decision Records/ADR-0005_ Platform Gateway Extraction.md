# ADR-0005: Platform Gateway Extraction

<cite>
**Referenced Files in This Document**
- [0005-platform-gateway-extraction.md](file://docs/adr/0005-platform-gateway-extraction.md)
- [spec.md](file://docs/specs/SPEC-010-platform-gateway-extraction/spec.md)
- [app.py](file://products/platform-gateway/src/platform_gateway/app.py)
- [main.py](file://products/platform-gateway/src/platform_gateway/main.py)
- [router.py](file://products/platform-gateway/src/platform_gateway/api/router.py)
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)
- [sessions.py](file://products/platform-gateway/src/platform_gateway/api/routes/sessions.py)
- [auth.py](file://products/platform-gateway/src/platform_gateway/api/routes/auth.py)
- [identity.py](file://products/platform-gateway/src/platform_gateway/api/routes/identity.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/api/routes/runtime.py)
- [health.py](file://products/platform-gateway/src/platform_gateway/api/routes/health.py)
- [tools.py](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [token_verifier.py](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py)
- [policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [delegation_client.py](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py)
- [agent_client.py](file://products/platform-gateway/src/platform_gateway/services/agent_client.py)
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [tool_gw_app.py](file://products/tool-gateway/src/tool_gateway/app.py)
- [tool_gw_router.py](file://products/tool-gateway/src/tool_gateway/api/router.py)
- [tool_gw_gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [tool_registry.py](file://products/tool-gateway/src/tool_gateway/tools/registry.py)
- [platform_deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [tool_deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
</cite>

## Update Summary
**Changes Made**
- Updated all file references to reflect the successful extraction of platform-gateway from tool-gateway
- Revised architecture diagrams to show the new two-product structure
- Updated component analysis to reflect the split between platform-gateway and tool-gateway
- Added deployment configuration details showing both products are now separate services
- Enhanced dependency analysis to show the new service boundaries

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document records the architectural decision to extract the portal-facing API edge from the existing tool-gateway product into a new platform-gateway product, while retaining the tool execution framework and connectors within tool-gateway. The split aligns ownership with the workspace model, clarifies trust boundaries, and prepares the system for future portal-facing features without expanding the blast radius of security-sensitive code.

**Updated** The implementation has been completed successfully, with platform-gateway now operating as a separate product alongside tool-gateway, maintaining all original functionality while achieving clear separation of concerns.

## Project Structure
The extraction has successfully separated the monolithic tool-gateway into two distinct products:

- **platform-gateway**: Hosts the portal-facing edge (authentication, identity normalization, policy enforcement, chat/session proxying, delegation client)
- **tool-gateway**: Retains the tool execution surface (tool registry, tools:list/invoke routes, redaction choke point, Kubernetes connector)

```mermaid
graph TB
subgraph "New Product: platform-gateway"
PG["FastAPI App<br/>app.py"]
PR["Router<br/>api/router.py"]
PAR["Portal Routes<br/>auth, sessions, chat, identity, runtime, health"]
PGS["Platform Gateway Service<br/>gateway_service.py"]
PTV["Platform Token Verifier<br/>token_verifier.py"]
PPE["Platform Policy Engine<br/>policy_engine.py"]
PDC["Platform Delegation Client<br/>delegation_client.py"]
PAC["Platform Agent Client<br/>agent_client.py"]
PCFG["Platform Config<br/>core/config.py"]
end
subgraph "Existing Product: tool-gateway"
TG["Tool Gateway App<br/>app.py"]
TR["Tool Router<br/>api/router.py"]
TAR["Tool Routes<br/>tools"]
TGS["Tool Gateway Service<br/>gateway_service.py"]
TRG["Tool Registry<br/>tools/registry.py"]
end
PG --> PR
PR --> PAR
PAR --> PGS
PGS --> PTV
PGS --> PPE
PGS --> PDC
PGS --> PAC
TG --> TR
TR --> TAR
TAR --> TGS
TGS --> TRG
```

**Diagram sources**
- [app.py:1-44](file://products/platform-gateway/src/platform_gateway/app.py#L1-L44)
- [router.py:1-12](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L12)
- [tool_gw_app.py:1-64](file://products/tool-gateway/src/tool_gateway/app.py#L1-L64)
- [tool_gw_router.py:1-8](file://products/tool-gateway/src/tool_gateway/api/router.py#L1-L8)

**Section sources**
- [app.py:1-44](file://products/platform-gateway/src/platform_gateway/app.py#L1-L44)
- [router.py:1-12](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L12)
- [tool_gw_app.py:1-64](file://products/tool-gateway/src/tool_gateway/app.py#L1-L64)
- [tool_gw_router.py:1-8](file://products/tool-gateway/src/tool_gateway/api/router.py#L1-L8)

## Core Components
The extraction has created two focused components:

### Platform Gateway Components
- FastAPI application bootstrap and middleware: initializes the app, registers portal routers, sets up metrics and telemetry
- Portal routes: auth, identity, runtime, sessions, and chat endpoints that enforce authentication and policy before proxying or delegating
- Platform gateway service: central orchestration for identity resolution, policy enforcement, session management, chat streaming, and agent communication
- Platform token verifier: local JWT verification via JWKS, extracting IdentityContext including actor information
- Platform policy engine: deny-by-default evaluation over a YAML bundle; loaded once per process and cached
- Platform delegation client: per-replica cache and exchange with identity-broker for short-lived delegated tokens, preferring workload tokens when available
- Platform agent client: HTTP client binding to agent-platform's v2 contract for sessions, chat, streaming, runtime metadata, and health
- Platform configuration: environment-driven settings controlling audiences, issuer, token caching, policy path, and feature toggles

### Tool Gateway Components
- Tool gateway application: FastAPI app focused on tool execution with ToolRegistry initialization
- Tool routes: tools:list and tools:invoke endpoints gated by policy and identity verification
- Tool gateway service: orchestrates tool invocation with policy enforcement, redaction, and audit logging
- Tool registry: in-process lookup and dispatch for registered tools
- Tool-specific configuration: environment-driven settings for tool execution and connector configuration

**Section sources**
- [app.py:1-44](file://products/platform-gateway/src/platform_gateway/app.py#L1-L44)
- [gateway_service.py:1-294](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L294)
- [tool_gw_app.py:1-64](file://products/tool-gateway/src/tool_gateway/app.py#L1-L64)
- [tool_gw_gateway_service.py:1-245](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L1-L245)
- [tool_registry.py:1-58](file://products/tool-gateway/src/tool_gateway/tools/registry.py#L1-L58)

## Architecture Overview
The extraction successfully separates the portal-facing edge from the tool execution surface. After the split:
- platform-gateway owns inbound token verification, audience enforcement, action policy, chat/session proxying to agent-platform, broker-mediated delegation, and portal routes
- tool-gateway remains the tool/connector home: ToolRegistry, connectors, tools:list/invoke, redaction choke point, tool audit, and Kubernetes connector
- The portal continues to proxy to a single entrypoint (platform-gateway), preserving external behavior and contracts

```mermaid
graph TB
subgraph "Portal"
P["Browser / Operator UI"]
end
subgraph "New Product: platform-gateway"
PG["FastAPI Edge<br/>auth, identity, sessions, chat"]
PTV["Platform Token Verifier"]
PPE["Platform Policy Engine"]
PDC["Platform Delegation Client"]
PAC["Platform Agent Client"]
end
subgraph "Existing Product: tool-gateway"
TG["Tool Gateway<br/>tools:list, tools:invoke"]
TR["ToolRegistry"]
KC["Kubernetes Connector"]
RD["Redaction Choke Point"]
end
subgraph "Backends"
IB["Identity Broker"]
AP["Agent Platform"]
end
P --> PG
PG --> PTV
PG --> PPE
PG --> PDC
PG --> PAC
PAC --> AP
TG --> TR
TR --> KC
TG --> RD
PDC --> IB
PTV --> IB
```

**Diagram sources**
- [router.py:1-12](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L12)
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [tool_gw_router.py:1-8](file://products/tool-gateway/src/tool_gateway/api/router.py#L1-L8)
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)

## Detailed Component Analysis

### Platform Gateway Implementation
The platform-gateway product successfully implements the portal-facing edge with complete separation from tool execution concerns:

- Authentication flows: login-url, login start/callback, logout-url, refresh, and me endpoint
- Identity normalization and request identity resolution using local JWT verification
- Session lifecycle: create and read sessions proxied to agent-platform
- Chat endpoints: synchronous and streaming chat with delegated token forwarding
- Policy enforcement: deny-by-default evaluation for actions like chat, session:create, session:read
- Delegation: per-user cache and broker exchange for short-lived delegated tokens

```mermaid
sequenceDiagram
participant Browser as "Browser"
participant Edge as "platform-gateway"
participant IDB as "Identity Broker"
participant AG as "Agent Platform"
Browser->>Edge : POST /api/v1/chat
Edge->>Edge : resolve_request_identity()
Edge->>Edge : enforce_policy("chat")
Edge->>IDB : exchange(subject_token, audience)
IDB-->>Edge : delegated_token
Edge->>AG : POST /api/v2/chat (with delegated token)
AG-->>Edge : response
Edge-->>Browser : chat response
```

**Diagram sources**
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [gateway_service.py:1-294](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L294)
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)

**Section sources**
- [chat.py:1-103](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L1-L103)
- [gateway_service.py:1-294](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L294)
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)

### Tool Gateway Implementation
tool-gateway retains the tool execution framework with focused responsibility:

- Tool discovery and invocation routes: tools:list and tools:invoke
- ToolRegistry and connectors (e.g., Kubernetes connector)
- Redaction choke point and audit logging for tool results
- Identity derivation strictly from bearer tokens; no body-based identity trust

```mermaid
flowchart TD
Start(["Request to /api/v2/tools/invoke"]) --> Parse["Parse JSON body<br/>tool_name, parameters"]
Parse --> Resolve["resolve_request_identity()"]
Resolve --> Policy{"enforce_policy('tools:invoke')"}
Policy --> |Deny| DenyResp["Return denied result (403)"]
Policy --> |Allow| Dispatch["registry.invoke(tool_name, parameters, identity)"]
Dispatch --> Redact{"redaction_enabled?"}
Redact --> |Yes| ApplyRedact["Apply redaction choke point"]
Redact --> |No| Audit["Audit log event"]
ApplyRedact --> Overflow{"Overflow?"}
Overflow --> |Yes| ErrorResp["Return error (REDACTION_OVERFLOW)"]
Overflow --> |No| Audit
Audit --> SuccessResp["Return result (status mapped to 200/400/403)"]
DenyResp --> End(["Exit"])
ErrorResp --> End
SuccessResp --> End
```

**Diagram sources**
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)
- [tool_gw_gateway_service.py:1-245](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L1-L245)

**Section sources**
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)
- [tool_gw_gateway_service.py:1-245](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L1-L245)

### Identity and Policy Enforcement
Both services maintain consistent identity and policy enforcement patterns:

- Local JWT verification uses JWKS to validate tokens and extract claims, including optional act for actor attribution
- Policy engine loads a YAML bundle (default packaged or configured path), caches rules, and evaluates actions with deny-by-default semantics
- Identity resolution supports synthetic dev identity when authentication is optional, ensuring consistent policy paths

```mermaid
classDiagram
class PlatformGatewaySettings {
+string agent_service_url
+string identity_service_url
+string identity_jwks_url
+string identity_token_issuer
+string token_audience
+string delegation_audience
+bool require_auth
+bool k8s_enabled
+bool redaction_enabled
}
class PlatformTokenVerifier {
+verify_token(settings, token) IdentityContext
-_get_jwks_client(settings) PyJWKClient
}
class PlatformPolicyEngine {
+load_bundle(settings) list[PolicyRule]
+evaluate(settings, roles, action) PolicyDecision
}
class IdentityContext {
+string subject
+string username
+list roles
+list groups
+string email
+string actor
}
PlatformTokenVerifier --> PlatformGatewaySettings : "uses"
PlatformPolicyEngine --> PlatformGatewaySettings : "uses"
PlatformTokenVerifier --> IdentityContext : "returns"
```

**Diagram sources**
- [config.py:1-95](file://products/platform-gateway/src/platform_gateway/core/config.py#L1-L95)
- [token_verifier.py:1-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L1-L99)
- [policy_engine.py:1-198](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L198)

**Section sources**
- [token_verifier.py:1-99](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py#L1-L99)
- [policy_engine.py:1-198](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L198)
- [config.py:1-95](file://products/platform-gateway/src/platform_gateway/core/config.py#L1-L95)

### Delegation Flow
The delegation flow maintains consistency across both services with platform-gateway handling user-level delegation:

Delegation client manages per-user cached delegated tokens, preferring projected workload tokens when available, otherwise falling back to static credentials. Exchange failures are non-fatal to preserve chat functionality.

```mermaid
sequenceDiagram
participant Edge as "platform-gateway"
participant Cache as "DelegationClient"
participant Broker as "Identity Broker"
Edge->>Cache : get_cached(subject)
alt Cache hit
Cache-->>Edge : delegated_token
else Cache miss
Edge->>Broker : exchange(subject_token, audience)
Broker-->>Edge : access_token, expires_in
Edge->>Cache : put(subject, token, expires_in)
Cache-->>Edge : delegated_token
end
```

**Diagram sources**
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)

**Section sources**
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)

## Dependency Analysis
The extraction successfully decouples portal-edge concerns from tool execution concerns:

- platform-gateway depends on identity-broker (for token verification and delegation) and agent-platform (for sessions/chat)
- tool-gateway depends only on its own ToolRegistry and connectors, plus identity-broker for verifying delegated tokens
- Both services share common patterns but maintain independent codebases and deployment units

```mermaid
graph TB
subgraph "platform-gateway"
PG["portal routes"]
PTV["platform token_verifier"]
PPE["platform policy_engine"]
PDC["platform delegation_client"]
PAC["platform agent_client"]
end
subgraph "tool-gateway"
TG["tools routes"]
TR["ToolRegistry"]
KC["k8s_connector"]
end
subgraph "External Services"
IB["identity-broker"]
AP["agent-platform"]
end
PG --> PTV
PG --> PPE
PG --> PDC
PG --> PAC
TG --> TR
TR --> KC
PDC --> IB
PTV --> IB
PAC --> AP
```

**Diagram sources**
- [router.py:1-12](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L12)
- [tool_gw_router.py:1-8](file://products/tool-gateway/src/tool_gateway/api/router.py#L1-L8)
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)

**Section sources**
- [router.py:1-12](file://products/platform-gateway/src/platform_gateway/api/router.py#L1-L12)
- [tool_gw_router.py:1-8](file://products/tool-gateway/src/tool_gateway/api/router.py#L1-L8)
- [tools.py:1-51](file://products/tool-gateway/src/tool_gateway/api/routes/tools.py#L1-L51)

## Performance Considerations
- JWKS key caching reduces repeated network calls during token verification
- Policy bundle loading is cached per process to avoid repeated YAML parsing
- Delegation client maintains a per-replica cache with refresh-ahead to minimize broker exchanges
- Streaming chat avoids buffering large responses by yielding SSE lines directly
- Redaction overflow protection prevents excessive processing on large outputs
- Separate deployments allow independent scaling of platform-gateway and tool-gateway based on load patterns

## Troubleshooting Guide
Common issues and diagnostics for both services:

### Platform Gateway Issues
- Token verification failures: check issuer, audience, expiration, and JWKS availability. Metrics record verification outcomes
- Policy denials: inspect matched rule IDs and reasons; ensure roles and actions align with policy bundle
- Delegation failures: verify workload token path or static credentials; monitor exchange success/failure metrics
- Health/readiness: use readiness endpoints to detect degraded states due to agent-service or policy load errors

### Tool Gateway Issues
- Tool invocation failures: check tool registration, parameter validation, and connector connectivity
- Redaction overflow: adjust redaction thresholds or tighten tool parameters to reduce sensitive content
- Identity verification: ensure proper bearer token format and audience validation
- Policy enforcement: verify tool-specific policies and role assignments

**Section sources**
- [gateway_service.py:1-294](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L1-L294)
- [tool_gw_gateway_service.py:1-245](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py#L1-L245)
- [delegation_client.py:1-229](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py#L1-L229)

## Conclusion
Extracting the portal-facing API edge into platform-gateway has successfully clarified ownership, strengthened trust boundaries, and simplified future evolution. tool-gateway remains focused on tool execution and connectors, maintaining byte-stable contracts and secure defaults. The implementing spec (SPEC-010) has been delivered with all acceptance criteria met, establishing a clean separation between portal-facing concerns and tool execution capabilities.

**Updated** The extraction is complete and operational, with both products independently deployable and maintainable while preserving all original functionality and security guarantees.

## Appendices

### ADR Summary and Decision Rationale
- Context: tool-gateway hosted two distinct roles (portal edge and tool framework) contradicting workspace model boundaries
- Decision: Extract portal edge into platform-gateway; keep tool framework in tool-gateway
- Alternatives considered and rejected: keeping combined service, inverting split, deferring until Release 4
- Consequences: aligned ownership, reduced blast radius, one additional service hop, living-state doc updates

**Section sources**
- [0005-platform-gateway-extraction.md:1-47](file://docs/adr/0005-platform-gateway-extraction.md#L1-L47)

### Spec Requirements and Acceptance Criteria
- R-1: New platform-gateway product carrying portal edge with parity tests and contracts ✓ Delivered
- R-2: tool-gateway reduced to tool/connector home with retained routes and verification path ✓ Delivered
- R-3: Identity plumbing across boundary preserves deny-by-default and delegation model ✓ Delivered
- R-4: Overlay, build, and deployment alignment including nginx proxy and smoke path ✓ Delivered
- R-5: Living-state docs advanced to reflect two products and mandates ✓ Delivered

**Section sources**
- [spec.md:1-170](file://docs/specs/SPEC-010-platform-gateway-extraction/spec.md#L1-L170)

### Deployment Configuration
Both products are now deployed as separate Kubernetes services with independent configurations:

- platform-gateway: Full deployment with RBAC, secrets, and policy configuration
- tool-gateway: Simplified deployment focused on tool execution with shared policy configuration
- Both services support Prometheus monitoring and health checks
- Independent scaling and resource allocation for each service

**Section sources**
- [platform_deployment.yaml:1-40](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml#L1-L40)
- [tool_deployment.yaml:1-37](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml#L1-L37)