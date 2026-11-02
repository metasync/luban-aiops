# Runtime Configuration API

<cite>
**Referenced Files in This Document**
- [app.py](file://products/agent-platform/src/agent_service/app.py)
- [routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [runtime_dependencies.py](file://products/agent-platform/src/agent_service/services/runtime_dependencies.py)
- [v2.py](file://products/agent-platform/src/agent_service/schemas/v2.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/api/routes/runtime.py)
</cite>

## Update Summary
**Changes Made**
- Added documentation for the new authenticated GET /api/v2/runtime/flags endpoint
- Updated authentication requirements section to include feature flag access controls
- Enhanced security considerations for sensitive configuration exposure
- Added examples of feature flag discovery and inventory queries
- Updated architecture diagrams to reflect the new flags endpoint

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Security Considerations](#security-considerations)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)
11. [Appendices](#appendices)

## Introduction
This document specifies the Runtime configuration endpoints that expose platform capabilities and settings for the agent-service. It focuses on runtime queries that clients use to discover capabilities, check health, inspect dependencies, and query feature flags. The documented endpoints are:
- GET /api/v1/runtime/config
- GET /api/v1/runtime/health
- GET /api/v1/runtime/dependencies
- **GET /api/v2/runtime/flags** (new authenticated endpoint)

These endpoints surface runtime metadata (provider, model, base URL), readiness state, dependency status, and curated feature flag inventory derived from the runtime kernel and settings. They enable capability discovery, feature flag inspection, service dependency checks, and operational visibility without mutating state.

## Project Structure
The runtime configuration surface is implemented by the FastAPI application that mounts the v2 router and wires lifecycle tasks such as model discovery. The runtime kernel provides capability and state introspection used by routes. Settings define available features and toggles exposed through runtime metadata. The platform gateway proxies authenticated feature flag requests with policy enforcement.

```mermaid
graph TB
Client["Client"] --> App["FastAPI app<br/>mounts v2 router"]
App --> Routes["Routes module<br/>/api/v2/*"]
Routes --> Kernel["AgentKernel<br/>runtime state & metadata"]
Kernel --> Settings["RuntimeSettings<br/>feature flags & options"]
App --> Discovery["Model discovery background task"]
Gateway["Platform Gateway"] --> FlagsRoute["Authenticated flags proxy"]
FlagsRoute --> Policy["Policy enforcement<br/>runtime:flags action"]
Policy --> AgentService["Agent Service<br/>/api/v2/runtime/flags"]
```

**Diagram sources**
- [app.py:19-76](file://products/agent-platform/src/agent_service/app.py#L19-L76)
- [routes.py:139-141](file://products/agent-platform/src/agent_service/api/v2/routes.py#L139-L141)
- [runtime_kernel.py:212-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L212-L285)
- [runtime_settings.py:136-246](file://products/agent-platform/src/agent_service/runtime_settings.py#L136-L246)
- [runtime.py:27-55](file://products/platform-gateway/src/platform_gateway/api/routes/runtime.py#L27-L55)

**Section sources**
- [app.py:19-76](file://products/agent-platform/src/agent_service/app.py#L19-L76)
- [routes.py:139-141](file://products/agent-platform/src/agent_service/api/v2/routes.py#L139-L141)

## Core Components
- AgentKernel exposes runtime mode, state, provider details, model resolution, configuration hints, and a curated nine-flag feature flag inventory. These form the basis for runtime configuration responses.
- RuntimeSettings defines feature flags and runtime knobs (e.g., model discovery, HITL timeout, tool gateway URL, tracing, token budget).
- Runtime dependencies module caches the process-wide AgentKernel instance and provides access to the confirmation registry.
- Schemas define request/response contracts for v2 endpoints; these inform how runtime metadata, health-like structures, and feature flag inventories are modeled.

Key responsibilities:
- Capability discovery: provider name, description, model name, base URL, provider options.
- Health posture: runtime mode and state (not configured, provider error, ready).
- Dependency visibility: presence of tool gateway URL and other service URLs surfaced via settings and hints.
- Feature flag inventory: curated nine-flag list with boolean enabled states and human-readable labels.

**Section sources**
- [runtime_kernel.py:236-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L236-L285)
- [runtime_kernel.py:370-431](file://products/agent-platform/src/agent_service/runtime_kernel.py#L370-L431)
- [runtime_settings.py:136-246](file://products/agent-platform/src/agent_service/runtime_settings.py#L136-L246)
- [runtime_dependencies.py:13-20](file://products/agent-platform/src/agent_service/services/runtime_dependencies.py#L13-L20)
- [v2.py:23-42](file://products/agent-platform/src/agent_service/schemas/v2.py#L23-L42)
- [v2.py:598-606](file://products/agent-platform/src/agent_service/schemas/v2.py#L598-L606)

## Architecture Overview
The runtime configuration endpoints are served by the agent-service FastAPI application. While the repository's public route definitions mount under /api/v2, the conceptual runtime endpoints described here (/api/v1/runtime/*) map to the same runtime introspection logic provided by AgentKernel and RuntimeSettings. Clients call these endpoints to:
- Retrieve configuration metadata (provider, model, base URL, options).
- Check health/readiness (mode and state).
- Inspect dependencies (tool gateway availability, optional services like audit/incident/skills).
- Query curated feature flags (authenticated only).

```mermaid
sequenceDiagram
participant C as "Client"
participant A as "FastAPI app"
participant R as "Routes"
participant K as "AgentKernel"
participant S as "RuntimeSettings"
participant G as "Platform Gateway"
participant P as "Policy Engine"
C->>A : GET /api/v1/runtime/config
A->>R : Route handler
R->>K : runtime_metadata()
K->>S : read provider/model/base/options
S-->>K : settings values
K-->>R : metadata dict
R-->>C : JSON config response
C->>A : GET /api/v1/runtime/health
A->>R : Route handler
R->>K : mode(), runtime_state()
K-->>R : {mode, state}
R-->>C : JSON health response
C->>A : GET /api/v1/runtime/dependencies
A->>R : Route handler
R->>K : runtime_metadata() or settings
K-->>R : includes tool_gateway_url and hints
R-->>C : JSON dependencies response
C->>G : GET /api/v1/runtime/flags
G->>P : enforce_policy(runtime : flags)
P-->>G : authorized
G->>A : GET /api/v2/runtime/flags
A->>R : runtime_feature_flags()
R->>K : feature_flags()
K-->>R : curated nine-flag inventory
R-->>G : AgentFeatureFlags
G-->>C : JSON flags response
```

**Diagram sources**
- [runtime_kernel.py:236-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L236-L285)
- [runtime_kernel.py:370-431](file://products/agent-platform/src/agent_service/runtime_kernel.py#L370-L431)
- [runtime_settings.py:136-246](file://products/agent-platform/src/agent_service/runtime_settings.py#L136-L246)
- [routes.py:2023-2039](file://products/agent-platform/src/agent_service/api/v2/routes.py#L2023-L2039)
- [runtime.py:27-55](file://products/platform-gateway/src/platform_gateway/api/routes/runtime.py#L27-L55)

## Detailed Component Analysis

### Runtime Configuration Endpoint: GET /api/v1/runtime/config
Purpose:
- Return current runtime configuration and capabilities for client-side adaptation.

Request:
- Method: GET
- Path: /api/v1/runtime/config
- Headers: None required for non-sensitive metadata. If sensitive configuration is requested, see Authentication requirements below.

Response schema (conceptual):
- runtime_mode: string — "agentscope" when configured, otherwise "placeholder".
- runtime_state: string — "ready", "not_configured", or "provider_error".
- agentscope_enabled: boolean — true if configured.
- profile: string | null — deploy-time profile label.
- provider: string — provider name (e.g., dashscope, deepseek, openai, luban).
- provider_description: string — human-readable provider summary.
- model_name: string | null — resolved model name.
- base_url: string | null — resolved base URL.
- provider_options: object — provider-specific options (e.g., max_tokens, temperature, top_p, reasoning_effort, parallel_tool_calls, thinking_enable).
- hint: string — guidance text for configuration issues.
- last_error: string | null — last provider error message, if any.

Example usage:
- Capability discovery: read provider and model_name to select compatible tools or UI flows.
- Feature flag queries: inspect provider_options fields such as parallel_tool_calls or reasoning_effort to adapt behavior.

Authentication:
- Non-sensitive metadata can be returned without authentication.
- If callers require sensitive configuration (e.g., secrets or internal endpoints), enforce authentication at the gateway or route level before returning sensitive fields.

**Section sources**
- [runtime_kernel.py:236-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L236-L285)
- [runtime_settings.py:136-246](file://products/agent-platform/src/agent_service/runtime_settings.py#L136-L246)

### Runtime Health Endpoint: GET /api/v1/runtime/health
Purpose:
- Provide lightweight health/readiness information for orchestration and monitoring.

Request:
- Method: GET
- Path: /api/v1/runtime/health

Response schema (conceptual):
- mode: string — "agentscope" or "placeholder".
- state: string — "ready", "not_configured", or "provider_error".
- hint: string — optional guidance when not ready.

Example usage:
- Liveness probe: return 200 when state is "ready".
- Readiness probe: return 200 when agentscope_enabled is true and state is "ready".

Authentication:
- Typically unauthenticated for probes; restrict if environment requires authenticated health checks.

**Section sources**
- [runtime_kernel.py:236-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L236-L285)

### Runtime Dependencies Endpoint: GET /api/v1/runtime/dependencies
Purpose:
- Expose runtime dependencies and their configuration status to support dependency checks and operational dashboards.

Request:
- Method: GET
- Path: /api/v1/runtime/dependencies

Response schema (conceptual):
- tool_gateway_url: string | null — indicates whether tool discovery is enabled.
- services: object — optional entries for configured services:
  - audit_service_url: string | null
  - incident_service_url: string | null
  - skills_service_url: string | null
- feature_flags: object — selected runtime toggles:
  - model_discovery_enabled: boolean
  - kernel_tracing: boolean
  - task_tools_enabled: boolean
  - hitl_confirm_timeout: integer (seconds; 0 disables bridging)
- timeouts: object — e.g., execution_worker_timeout_seconds, incident_client_timeout_seconds, skills_client_timeout_seconds.

Example usage:
- Service dependency check: verify tool_gateway_url is set before enabling tool-dependent features.
- Feature toggle inspection: read model_discovery_enabled to decide whether to rely on live model catalog.

Authentication:
- Unauthenticated for operational visibility; restrict if environment policy requires authenticated dependency queries.

**Section sources**
- [runtime_settings.py:136-246](file://products/agent-platform/src/agent_service/runtime_settings.py#L136-L246)
- [runtime_kernel.py:236-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L236-L285)

### Authenticated Feature Flags Endpoint: GET /api/v2/runtime/flags
**New** Purpose:
- Provide authenticated access to the curated nine-flag feature flag inventory for operational visibility and platform administration.

Request:
- Method: GET
- Path: /api/v2/runtime/flags
- Headers: X-User-ID (required)
- Authentication: Requires valid user identity; platform gateway enforces runtime:flags policy action

Response schema:
- feature_flags: array of FeatureFlag objects
  - name: string — stable snake_case identifier
  - enabled: boolean — current state of the feature
  - label: string | null — human-readable description

Curated nine-flag inventory:
1. model_routing — Per-turn model routing
2. model_discovery — Live model discovery  
3. context_compression — Agent-driven context compression
4. outbound_delegated_identity — Outbound delegated identity
5. kernel_tracing — Kernel tracing
6. task_tools — Task tools
7. reply_token_budget — Reply token budget
8. hitl_bridging — HITL confirmation bridging
9. signed_execution — Signed execution requests

Example usage:
- Operational visibility: verify which platform features are enabled in production
- Platform administration: audit feature flag configuration across environments
- Client adaptation: adjust client behavior based on available platform capabilities

Authentication:
- Requires X-User-ID header for identity verification
- Platform gateway enforces runtime:flags policy action
- Returns 401 Unauthorized if authentication fails
- Discovery-safe by construction — never exposes secret values

**Section sources**
- [routes.py:2023-2039](file://products/agent-platform/src/agent_service/api/v2/routes.py#L2023-L2039)
- [runtime_kernel.py:370-431](file://products/agent-platform/src/agent_service/runtime_kernel.py#L370-L431)
- [v2.py:598-606](file://products/agent-platform/src/agent_service/schemas/v2.py#L598-L606)
- [runtime.py:27-55](file://products/platform-gateway/src/platform_gateway/api/routes/runtime.py#L27-L55)

### Runtime Capability Discovery Flow
Clients can discover capabilities by calling the config endpoint and interpreting provider and model metadata. For example:
- If provider is "openai", clients may expect OpenAI-compatible behaviors.
- If model_discovery_enabled is true, clients can trust the live model catalog.

```mermaid
flowchart TD
Start(["GET /api/v1/runtime/config"]) --> ReadMeta["Read provider, model_name, base_url"]
ReadMeta --> Flags{"model_discovery_enabled?"}
Flags --> |Yes| Catalog["Use live model catalog"]
Flags --> |No| Curated["Use curated series defaults"]
Catalog --> Adapt["Adapt client behavior"]
Curated --> Adapt
Adapt --> End(["Done"])
```

**Diagram sources**
- [runtime_settings.py:174-179](file://products/agent-platform/src/agent_service/runtime_settings.py#L174-L179)
- [runtime_kernel.py:258-271](file://products/agent-platform/src/agent_service/runtime_kernel.py#L258-L271)

### Authentication Requirements
- Non-sensitive runtime metadata (provider, model, base URL, feature flags) should be accessible without authentication for capability discovery and health checks.
- **New**: Feature flag inventory requires authenticated access via X-User-ID header and runtime:flags policy enforcement.
- Sensitive configuration (secrets, internal URLs, tokens) must be protected by authentication and authorization at the gateway or route layer.
- Administrative operations that mutate configuration or trigger privileged actions must enforce strong authentication and role-based access control.

**Updated** Added feature flag authentication requirements and policy enforcement details.

**Section sources**
- [routes.py:151-154](file://products/agent-platform/src/agent_service/api/v2/routes.py#L151-L154)
- [routes.py:2023-2039](file://products/agent-platform/src/agent_service/api/v2/routes.py#L2023-L2039)
- [runtime.py:41-45](file://products/platform-gateway/src/platform_gateway/api/routes/runtime.py#L41-L45)

### Configuration Hot-Reloading
- RuntimeSettings reads from environment variables at startup; changes typically require service restart to take effect.
- Model discovery runs as a background task with periodic refresh; this affects runtime metadata without restarting the service.

Operational notes:
- To hot-refresh model catalogs, ensure model_discovery_enabled is true and adjust refresh intervals via settings.
- For other settings, plan rolling restarts or sidecar reload mechanisms as appropriate.

**Section sources**
- [app.py:19-46](file://products/agent-platform/src/agent_service/app.py#L19-L46)
- [runtime_settings.py:414-517](file://products/agent-platform/src/agent_service/runtime_settings.py#L414-L517)

### Feature Toggles and Runtime Environment Detection
Feature toggles surfaced via runtime metadata:
- model_discovery_enabled: enables periodic provider /models queries.
- kernel_tracing: opt-in tracing middleware.
- task_tools_enabled: opt-in built-in task tools.
- hitl_confirm_timeout: controls human-in-the-loop bridging; 0 disables it.
- tool_gateway_url: presence indicates tool discovery is configured.

Environment detection:
- runtime_mode and runtime_state indicate readiness and configuration posture.
- hint provides actionable guidance when not ready.

**Section sources**
- [runtime_settings.py:136-246](file://products/agent-platform/src/agent_service/runtime_settings.py#L136-L246)
- [runtime_kernel.py:236-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L236-L285)

## Dependency Analysis
The runtime configuration endpoints depend on:
- AgentKernel for runtime state and metadata.
- RuntimeSettings for feature flags and service URLs.
- FastAPI router for HTTP binding and response serialization.
- Background model discovery for dynamic capability updates.
- Platform gateway for authenticated feature flag policy enforcement.

```mermaid
graph LR
Routes["Routes"] --> Kernel["AgentKernel"]
Kernel --> Settings["RuntimeSettings"]
Routes --> Schemas["Schemas (v2)"]
App["FastAPI app"] --> Routes
App --> Discovery["Model discovery"]
Gateway["Platform Gateway"] --> Policy["Policy Engine"]
Policy --> AgentService["Agent Service"]
```

**Diagram sources**
- [routes.py:139-141](file://products/agent-platform/src/agent_service/api/v2/routes.py#L139-L141)
- [runtime_kernel.py:212-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L212-L285)
- [runtime_settings.py:136-246](file://products/agent-platform/src/agent_service/runtime_settings.py#L136-L246)
- [app.py:19-76](file://products/agent-platform/src/agent_service/app.py#L19-L76)
- [runtime.py:27-55](file://products/platform-gateway/src/platform_gateway/api/routes/runtime.py#L27-L55)

**Section sources**
- [runtime_dependencies.py:13-20](file://products/agent-platform/src/agent_service/services/runtime_dependencies.py#L13-L20)
- [routes.py:139-141](file://products/agent-platform/src/agent_service/api/v2/routes.py#L139-L141)

## Performance Considerations
- Configuration caching:
  - AgentKernel caches per-token toolkits to avoid repeated tool discovery.
  - Process-wide kernel instance is cached via lru_cache to reduce initialization overhead.
- Dependency health monitoring:
  - Use health endpoint for frequent probes; keep payloads minimal.
  - Prefer reading feature flags from config endpoint less frequently and cache client-side where appropriate.
- Model discovery:
  - Periodic refresh reduces cold-start latency for model catalog lookups.
  - Tune refresh interval and timeouts via settings to balance freshness and load.
- Feature flag queries:
  - Feature flags are computed from live settings but represent simple boolean evaluations.
  - Cache feature flag responses client-side for operational dashboards and admin interfaces.

**Updated** Added performance considerations for feature flag queries and caching strategies.

## Security Considerations
- **New**: Feature flag endpoint requires authentication and policy enforcement to prevent unauthorized access to platform configuration visibility.
- Non-sensitive runtime metadata (provider, model, base URL, feature flags) should be accessible without authentication for capability discovery and health checks.
- Sensitive configuration (secrets, internal URLs, tokens) must be protected by authentication and authorization at the gateway or route layer.
- Administrative operations that mutate configuration or trigger privileged actions must enforce strong authentication and role-based access control.
- Feature flags are designed to be discovery-safe by construction — they report boolean states and descriptive labels, never exposing secret values, configuration details, or sensitive parameters.

**Updated** Enhanced security considerations to address the new authenticated feature flag endpoint and discovery-safe design principles.

## Troubleshooting Guide
Common issues and diagnostics:
- Not configured:
  - Symptom: runtime_state is "not_configured"; hint instructs setting the API key.
  - Action: configure AGENTSCOPE_API_KEY and restart if necessary.
- Provider error:
  - Symptom: runtime_state is "provider_error"; last_error contains details.
  - Action: inspect provider credentials, base URL, and network connectivity.
- Tooling unavailable:
  - Symptom: no operational tools reachable; hint advises tooling unavailability.
  - Action: ensure tool_gateway_url is set and reachable; verify discovery succeeds.
- HITL disabled:
  - Symptom: mutating tools excluded; hint indicates confirmation bridging disabled.
  - Action: set AGENT_HITL_CONFIRM_TIMEOUT > 0 to enable bridging.
- **New**: Feature flags unavailable:
  - Symptom: 401 Unauthorized when accessing /api/v2/runtime/flags
  - Action: ensure X-User-ID header is present and user has runtime:flags policy permission
  - Action: verify platform gateway is properly configured with policy enforcement

**Updated** Added troubleshooting guidance for the new feature flags endpoint.

**Section sources**
- [runtime_kernel.py:273-285](file://products/agent-platform/src/agent_service/runtime_kernel.py#L273-L285)
- [runtime_kernel.py:94-119](file://products/agent-platform/src/agent_service/runtime_kernel.py#L94-L119)

## Conclusion
The Runtime configuration endpoints provide a stable surface for capability discovery, health checks, dependency inspection, and feature flag management. By leveraging AgentKernel and RuntimeSettings, clients can adapt behavior based on provider, model, feature flags, and dependency status. The new authenticated feature flags endpoint enables secure operational visibility while maintaining discovery-safe design principles. Secure exposure of sensitive configuration and thoughtful performance tuning (caching, discovery intervals) ensure reliable operation across environments.

**Updated** Enhanced conclusion to reflect the addition of authenticated feature flag capabilities and improved operational visibility.

## Appendices

### Request/Response Examples
- GET /api/v1/runtime/config
  - Response fields: runtime_mode, runtime_state, agentscope_enabled, profile, provider, provider_description, model_name, base_url, provider_options, hint, last_error.
- GET /api/v1/runtime/health
  - Response fields: mode, state, hint.
- GET /api/v1/runtime/dependencies
  - Response fields: tool_gateway_url, services (audit/incident/skills URLs), feature_flags (model_discovery_enabled, kernel_tracing, task_tools_enabled, hitl_confirm_timeout), timeouts.
- **New**: GET /api/v2/runtime/flags
  - Response fields: feature_flags (array of {name, enabled, label})
  - Authentication: X-User-ID header required
  - Example flags: model_routing, model_discovery, context_compression, outbound_delegated_identity, kernel_tracing, task_tools, reply_token_budget, hitl_bridging, signed_execution

**Updated** Added feature flags endpoint examples and authentication requirements.