# Monitoring and Observability

<cite>
**Referenced Files in This Document**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [agent-platform/src/agent_service/core/metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [identity-broker/src/identity_service/core/metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [tool-gateway/src/tool_gateway/core/metrics.py](file://products/tool-gateway/src/tool_gateway/core/metrics.py)
- [platform-gateway/src/platform_gateway/core/metrics.py](file://products/platform-gateway/src/platform_gateway/core/metrics.py)
- [audit-service/src/audit_service/core/metrics.py](file://products/audit-service/src/audit_service/core/metrics.py)
- [skills-hub/src/skills_hub/core/metrics.py](file://products/skills_hub/src/skills_hub/core/metrics.py)
- [agent-platform/src/agent_service/app.py](file://products/agent-platform/src/agent_service/app.py)
- [identity-broker/src/identity_service/app.py](file://products/identity_broker/app.py)
- [tool-gateway/src/tool_gateway/app.py](file://products/tool-gateway/src/tool_gateway/app.py)
- [platform-gateway/src/platform_gateway/app.py](file://products/platform-gateway/src/platform_gateway/app.py)
- [agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [tool-gateway/src/tool_gateway/core/telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [platform-gateway/src/platform_gateway/core/telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [audit-service/src/audit_service/core/telemetry.py](file://products/audit-service/src/audit_service/core/telemetry.py)
- [skills-hub/src/skills_hub/core/telemetry.py](file://products/skills_hub/src/skills_hub/core/telemetry.py)
- [incident-service/src/incident_service/core/telemetry.py](file://products/incident-service/src/incident_service/core/telemetry.py)
- [agent-platform/src/agent_service/services/evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform/src/agent_service/services/model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [agent-platform/src/agent_service/services/model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [agent-platform/src/agent_service/runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent-platform/src/agent_service/providers/luban.py](file://products/agent-platform/src/agent_service/providers/luban.py)
- [agent-platform/src/agent_service/api/v2/routes.py](file://products/agent-platform/src/agent_service/api/v2/routes.py)
- [platform-gateway/src/platform_gateway/services/gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [platform-gateway/src/platform_gateway/api/routes/health.py](file://products/platform-gateway/src/platform_gateway/api/routes/health.py)
- [settings-view.tsx](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx)
- [settings-view.test.tsx](file://products/operator-portal/web-ui/app/src/views/__tests__/SettingsView.test.tsx)
- [health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)
- [agent-health.schema.json](file://shared/shared-contracts/schemas/agent-health.schema.json)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [2026-08-21-durable-otlp-secret-provisioning.md](file://docs/agentic-aiops-platform/release-notes/2026-08-21-durable-otlp-secret-provisioning.md)
- [configuration-reference.md](file://docs/guides/configuration-reference.md)
- [2026-08-24-multimodel-runtime-and-live-discovery.md](file://docs/agentic-aiops-platform/release-notes/2026-08-24-multimodel-runtime-and-live-discovery.md)
- [test_module_parity.py](file://products/tool-gateway/tests/test_module_parity.py)
- [audit-service/src/audit_service/services/ingest_auth.py](file://products/audit-service/src/audit_service/services/ingest_auth.py)
- [incident-service/src/incident_service/services/query_auth.py](file://products/incident-service/src/incident_service/services/query_auth.py)
- [platform-gateway/src/platform_gateway/services/token_verifier.py](file://products/platform-gateway/src/platform_gateway/services/token_verifier.py)
- [tool-gateway/src/tool_gateway/services/token_verifier.py](file://products/tool-gateway/src/tool_gateway/services/token_verifier.py)
- [audit-service/tests/test_ingest_auth.py](file://products/audit-service/tests/test_ingest_auth.py)
- [incident-service/tests/test_query_auth.py](file://products/incident-service/tests/test_query_auth.py)
- [2026-08-28-components-tech-stack-and-status.md](file://docs/agentic-aiops-platform/release-notes/2026-08-28-components-tech-stack-and-status.md)
- [2026-08-28-platform-components-blurb-prose-voice.md](file://docs/agentic-aiops-platform/release-notes/2026-08-28-platform-components-blurb-prose-voice.md)
</cite>

## Update Summary
**Changes Made**
- Enhanced observability with comprehensive technology stack visibility in Settings Platform pane
- Standardized status vocabulary across all platform components (ready, degraded, not ready, unavailable, checking…)
- Improved health endpoint responses with version information for better operational awareness and troubleshooting
- Added backend version plumbing to agent service and gateway readiness endpoints
- Updated operator portal to display unified component inventory with technology stack details

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
This document provides comprehensive guidance for monitoring and observability across the Luban AIOps Platform. It consolidates the platform's metrics collection strategy using Prometheus with direct prometheus_client implementation, structured logging conventions, distributed tracing implementation with OpenObserve integration, health check endpoints, readiness/liveness probes configuration, alerting rules, dashboard templates, and incident response procedures. The platform includes a comprehensive OpenTelemetry push pipeline that exports traces, metrics, and logs to OpenObserve via OTLP HTTP/protobuf protocol, enabling end-to-end observability across all six platform services. **Updated**: The platform now features enhanced observability with comprehensive technology stack visibility in the Settings Platform pane, standardized status vocabulary (ready, degraded, not ready, unavailable, checking…), and improved health endpoint responses with version information for better operational awareness and troubleshooting. The platform also includes robust monitoring capabilities for multi-model runtime including evidence store operations, model discovery lifecycle, and comprehensive observability for the new multi-model runtime features with enhanced provider-specific metrics for the luban provider. Additionally, the platform implements comprehensive drift-guard parity suites ensuring consistency across telemetry, observability, token verification, and audit emission patterns across all seven services.

## Project Structure
Observability is implemented consistently across all six services with standardized metrics collection using direct prometheus_client implementation and comprehensive OpenTelemetry telemetry:
- Agent Platform service exposes metrics via custom RED middleware with prometheus_client and OpenTelemetry push pipeline, enhanced with multi-model runtime monitoring
- Identity Broker service implements similar metrics collection with domain-specific counters and OpenTelemetry integration
- Tool Gateway service integrates metrics into request handling with policy decision tracking and OpenTelemetry support
- Platform Gateway service provides centralized routing metrics with delegation tracking and OpenTelemetry instrumentation
- Audit Service and Skills Hub services complete the observability coverage with consistent telemetry patterns
- Incident Service completes the seven-service architecture with comprehensive observability
- Shared contracts define observability conventions and schemas used by all services
- Kubernetes manifests configure probes and environment variables for observability components
- **Enhanced**: Secret synchronization scripts ensure OTLP credentials persist across environment file regenerations
- **New**: Drift-guard parity tests ensure byte-identical telemetry implementations across all services
- **Updated**: Enhanced Settings Platform pane provides comprehensive technology stack visibility with standardized status indicators

```mermaid
graph TB
subgraph "Seven-Service Architecture"
AP["Agent Platform<br/>prometheus_client + OpenTelemetry"]
IB["Identity Broker<br/>prometheus_client + OpenTelemetry"]
TG["Tool Gateway<br/>prometheus_client + OpenTelemetry"]
PG["Platform Gateway<br/>prometheus_client + OpenTelemetry"]
AS["Audit Service<br/>prometheus_client + OpenTelemetry"]
SH["Skills Hub<br/>prometheus_client + OpenTelemetry"]
IS["Incident Service<br/>prometheus_client + OpenTelemetry"]
end
subgraph "Enhanced Settings Platform Pane"
SP["Settings View<br/>Technology Stack Visibility"]
SV["Standardized Status<br/>ready/degraded/not ready/unavailable/checking…"]
HV["Health Endpoints<br/>Version Information"]
end
subgraph "Drift-Guard Parity Suite"
DP["Drift Guards<br/>Byte-Identical Telemetry"]
AP_T["Agent Telemetry"]
IB_T["Identity Telemetry"]
TG_T["Tool Gateway Telemetry"]
PG_T["Platform Gateway Telemetry"]
AS_T["Audit Service Telemetry"]
SH_T["Skills Hub Telemetry"]
IS_T["Incident Service Telemetry"]
end
subgraph "Authentication Parity"
IA["Ingest Auth<br/>(Audit Service)"]
QA["Query Auth<br/>(Incident Service)"]
TV["Token Verifier<br/>(Gateway Services)"]
AE["Audit Emitter<br/>(Multiple Services)"]
end
subgraph "Multi-Model Runtime"
ES["Evidence Store Metrics"]
MD["Model Discovery Metrics"]
LUBAN["Luban Provider Metrics"]
end
subgraph "OpenTelemetry Pipeline"
OTEL["OpenTelemetry SDK<br/>Traces + Metrics + Logs"]
EXPORTER["OTLP Exporter<br/>HTTP/protobuf"]
OO["OpenObserve Backend"]
end
AP --> AP_T
IB --> IB_T
TG --> TG_T
PG --> PG_T
AS --> AS_T
SH --> SH_T
IS --> IS_T
AP_T --> DP
IB_T --> DP
TG_T --> DP
PG_T --> DP
AS_T --> DP
SH_T --> DP
IS_T --> DP
SP --> SV
SP --> HV
IA --> QA
TV --> AE
ES --> OTEL
MD --> OTEL
LUBAN --> OTEL
OTEL --> EXPORTER
EXPORTER --> OO
```

**Diagram sources**
- [settings-view.tsx:105-357](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx#L105-L357)
- [gateway_service.py:46-84](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L46-L84)
- [routes.py:1050-1093](file://products/agent-platform/src/agent_service/api/v2/routes.py#L1050-L1093)
- [test_module_parity.py:102-127](file://products/tool-gateway/tests/test_module_parity.py#L102-L127)

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

## Core Components
- **Updated** Metrics Collection Strategy:
  - Each service exposes a Prometheus-compatible endpoint via direct prometheus_client implementation
  - Custom RED middleware records HTTP requests and durations with bounded cardinality labels
  - Standardized metric naming and labels enforced through shared conventions
  - Direct implementation avoids compatibility issues with pinned starlette versions
  - **New**: Multi-model runtime monitoring with evidence store and model discovery metrics
  - **New**: Provider-specific metrics for the new luban provider supporting self-hosted LLMs
  - **New**: Drift-guard parity ensures consistent metrics collection across all seven services
- **Enhanced** Distributed Tracing Implementation:
  - Opt-in OpenTelemetry push pipeline exports traces, metrics, and logs to OpenObserve
  - Gated by OTEL_ENABLED environment variable (default: disabled)
  - Uses OTLP HTTP/protobuf protocol to match OpenObserve ingest contract
  - Log bridge mirrors structured logs to OTLP pipeline for correlation with traces
  - Fail-open design ensures service continues operating if OpenObserve is unreachable
  - **New**: Robust OTLP credential management with durable secret synchronization
  - **New**: Byte-identical telemetry implementations across all services via drift guards
- **Updated** Health Check Endpoints with Enhanced Version Information:
  - Agent service `/api/v2/health` now includes five optional fields: `python_version`, `fastapi_version`, `agentscope_version`, `session_store_version`, `agent_state_version`
  - Gateway `/health/ready` includes `python_version` and `fastapi_version` in all response branches
  - Backend stores provide informational `server_version()` methods (PostgreSQL: `current_setting('server_version')`, Redis: `INFO server`, In-memory: `None`)
  - All version lookups are best-effort failures yield `null` without affecting readiness contracts
- **Updated** Standardized Status Vocabulary:
  - Unified status terms across all platform components: **ready** (green), **degraded** (orange), **not ready** (red), **unavailable** (when probe fails), **checking…** (while probes are in flight)
  - Replaces previous mixed terminology (*ok*, *loaded*) with consistent vocabulary
  - Applied throughout the Settings Platform pane for clear operational awareness
- Structured Logging Conventions:
  - All services call `configure_logging()` at startup to raise root logger from WARNING to INFO level
  - LOG_LEVEL environment variable supports per-deployment log level overrides (default: INFO)
  - Logs include consistent fields such as service name, version, request ID, and correlation IDs
  - Audit trail events (http_request, tool_invoked, policy decisions) are captured at INFO level
- Alerting Rules and Dashboards:
  - Alerting rules target key SLOs derived from metrics
  - Dashboard templates visualize core KPIs and operational health

**Section sources**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [2026-08-28-components-tech-stack-and-status.md:35-57](file://docs/agentic-aiops-platform/release-notes/2026-08-28-components-tech-stack-and-status.md#L35-L57)

## Architecture Overview
The observability architecture centers around dual pipelines: direct prometheus_client implementation for metrics collection and opt-in OpenTelemetry push pipeline for comprehensive observability:
- Services implement custom RED middleware using prometheus_client for metrics collection
- Application startup sequences call configure_logging() before FastAPI initialization
- OpenTelemetry pipeline is initialized conditionally based on OTEL_ENABLED flag
- **Enhanced**: Durable OTLP credential management via cluster-side secret merging
- **New**: Multi-model runtime monitoring integrated into the metrics pipeline
- **New**: Drift-guard parity suite ensures consistent telemetry implementations
- **Updated**: Enhanced health endpoints provide comprehensive technology stack visibility
- OTLP exporters send traces, metrics, and logs to OpenObserve via HTTP/protobuf
- Kubernetes configurations inject environment variables and define probes
- Prometheus scrapes metrics; logs are aggregated centrally; traces are exported to OpenObserve

```mermaid
sequenceDiagram
participant Client as "Client"
participant Portal as "Settings Platform Pane"
participant Gateway as "Platform Gateway"
participant Agent as "Agent Platform"
participant EvidenceStore as "Evidence Store"
participant ModelDiscovery as "Model Discovery"
participant LubanProvider as "Luban Provider"
participant SecretSync as "Secret Sync"
participant DriftGuard as "Drift Guard Tests"
participant Prometheus as "Prometheus"
participant OpenObserve as "OpenObserve"
participant Logger as "Log Aggregator"
Note over DriftGuard : Cross-service parity validation
Note over SecretSync : Cluster-side merge via kubectl patch
Note over Portal : Technology stack visibility with standardized status
DriftGuard->>DriftGuard : Validate telemetry parity
DriftGuard->>DriftGuard : Validate observability parity
DriftGuard->>DriftGuard : Validate auth parity
SecretSync->>SecretSync : Generate Basic Auth Header
SecretSync->>SecretSync : Patch Secrets (OTEL key only)
SecretSync->>SecretSync : Restart Deployments
Portal->>Gateway : GET /health/ready (with tech versions)
Gateway->>Gateway : _gateway_tech() (python/fastapi versions)
Gateway->>Agent : GET /api/v2/health (with tech versions)
Agent->>Agent : _tech_versions() (python/fastapi/agentscope)
Agent->>EvidenceStore : server_version() (backend version)
Agent->>ModelDiscovery : Background refresh loop
ModelDiscovery->>LubanProvider : Query models (if enabled)
LubanProvider-->>ModelDiscovery : Model list (self-hosted)
ModelDiscovery-->>Agent : Discovery results + model count
Agent-->>Gateway : Health response with tech versions
Gateway-->>Portal : Ready status with tech stack info
Portal->>Portal : Display unified status (ready/degraded/not ready/unavailable/checking…)
Gateway->>Gateway : Record metrics (prometheus_client)
Agent->>Prometheus : Export metrics (prometheus_client)
EvidenceStore->>Prometheus : Evidence store metrics
ModelDiscovery->>Prometheus : Model discovery metrics
LubanProvider->>Prometheus : Provider metrics
Gateway->>OpenObserve : OTLP traces/metrics/logs (authenticated)
Agent->>OpenObserve : OTLP traces/metrics/logs (authenticated)
EvidenceStore->>OpenObserve : Evidence store telemetry
ModelDiscovery->>OpenObserve : Model discovery telemetry
LubanProvider->>OpenObserve : Provider telemetry
Gateway->>Logger : Structured logs with trace_id
Agent->>Logger : Structured logs with trace_id
EvidenceStore->>Logger : Evidence store logs
ModelDiscovery->>Logger : Model discovery logs
LubanProvider->>Logger : Provider logs
```

**Diagram sources**
- [settings-view.tsx:221-318](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx#L221-L318)
- [gateway_service.py:46-84](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L46-L84)
- [routes.py:1050-1093](file://products/agent-platform/src/agent_service/api/v2/routes.py#L1050-L1093)
- [test_module_parity.py:102-127](file://products/tool-gateway/tests/test_module_parity.py#L102-L127)

## Detailed Component Analysis

### **Enhanced** Settings Platform Pane with Technology Stack Visibility
- **Comprehensive Component Inventory**: Displays all platform components with their underlying technology stacks
- **Unified Status Vocabulary**: Consistent status indicators across all components (ready, degraded, not ready, unavailable, checking…)
- **Backend Version Plumbing**: Agent service health endpoint includes Python, FastAPI, AgentScope versions plus backend server versions
- **Gateway Tech Stack Information**: Readiness endpoint includes Python and FastAPI versions in all response branches
- **Best-Effort Version Detection**: All version lookups fail gracefully without affecting service readiness
- **Live Component Status**: Real-time status assessment of each platform component

```mermaid
flowchart TD
Start(["Settings Platform Load"]) --> FetchReady["GET /health/ready"]
FetchReady --> FetchRuntime["GET /api/v1/runtime"]
FetchReady --> BuildGatewayRow["Build Gateway Row<br/>FastAPI · Python"]
FetchRuntime --> BuildAgentRow["Build Agent Row<br/>AgentScope · FastAPI"]
BuildGatewayRow --> GetTechVersions["Get Python/FastAPI Versions"]
BuildAgentRow --> GetAgentTech["Get Python/FastAPI/AgentScope Versions"]
GetTechVersions --> GetBackendVersions["Get Backend Server Versions"]
GetAgentTech --> GetBackendVersions
GetBackendVersions --> AssessStatus{"Assess Component Status"}
AssessStatus --> |Healthy| Ready["ready (green)"]
AssessStatus --> |Partial Failure| Degraded["degraded (orange)"]
AssessStatus --> |Unhealthy| NotReady["not ready (red)"]
AssessStatus --> |Probe Failed| Unavailable["unavailable"]
AssessStatus --> |Loading| Checking["checking…"]
Ready --> DisplayTable["Display Component Table"]
Degraded --> DisplayTable
NotReady --> DisplayTable
Unavailable --> DisplayTable
Checking --> DisplayTable
```

**Diagram sources**
- [settings-view.tsx:221-318](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx#L221-L318)
- [gateway_service.py:46-84](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L46-L84)
- [routes.py:1050-1093](file://products/agent-platform/src/agent_service/api/v2/routes.py#L1050-L1093)

**Section sources**
- [2026-08-28-components-tech-stack-and-status.md:21-57](file://docs/agentic-aiops-platform/release-notes/2026-08-28-components-tech-stack-and-status.md#L21-L57)
- [settings-view.tsx:105-357](file://products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx#L105-L357)

### **Enhanced** Drift-Guard Parity Suite
- **Comprehensive Coverage**: Ensures byte-identical telemetry implementations across all seven services
- **Parity Testing Categories**:
  - Telemetry parity: Byte-identical `core/telemetry.py` files across agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, and tool-gateway
  - Observability parity: Identical `core/observability.py` files except docstrings (each service names its own examples)
  - Token verifier parity: Identical `services/token_verifier.py` between platform-gateway and tool-gateway
  - Audit emitter parity: Identical `services/audit_emitter.py` across platform-gateway, tool-gateway, identity-broker, and skills-hub
  - Authentication parity: Identical `services/ingest_auth.py` (audit-service) and `services/query_auth.py` (incident-service)
- **Automated Validation**: Tests run during CI/CD to prevent drift between service implementations
- **Maintenance Benefits**: Single source of truth for observability patterns reduces maintenance burden

```mermaid
flowchart TD
Start(["Code Change"]) --> Detect{"Change Type?"}
Detect --> |Telemetry| ValidateTelemetry["Validate telemetry.py parity"]
Detect --> |Observability| ValidateObservability["Validate observability.py parity"]
Detect --> |TokenVerifier| ValidateTokenVerifier["Validate token_verifier.py parity"]
Detect --> |AuditEmitter| ValidateAuditEmitter["Validate audit_emitter.py parity"]
Detect --> |Auth| ValidateAuth["Validate ingest_auth/query_auth parity"]
ValidateTelemetry --> TestRun["Run Drift Guard Tests"]
ValidateObservability --> TestRun
ValidateTokenVerifier --> TestRun
ValidateAuditEmitter --> TestRun
ValidateAuth --> TestRun
TestRun --> Pass{"Tests Pass?"}
Pass --> |Yes| Merge["Merge PR"]
Pass --> |No| Fix["Fix Drift Issues"]
Fix --> TestRun
```

**Diagram sources**
- [test_module_parity.py:102-127](file://products/tool-gateway/tests/test_module_parity.py#L102-L127)
- [test_module_parity.py:114-127](file://products/tool-gateway/tests/test_module_parity.py#L114-L127)
- [test_module_parity.py:130-146](file://products/tool-gateway/tests/test_module_parity.py#L130-L146)
- [test_module_parity.py:149-176](file://products/tool-gateway/tests/test_module_parity.py#L149-L176)
- [test_module_parity.py:179-207](file://products/tool-gateway/tests/test_module_parity.py#L179-L207)

**Section sources**
- [test_module_parity.py:1-212](file://products/tool-gateway/tests/test_module_parity.py#L1-L212)

### **Enhanced** Authentication Parity Between Services
- **Cross-Service Consistency**: Audit service ingest authentication and incident service query authentication follow identical patterns
- **Dual Authentication Paths**: Both services support static HTTP Basic credentials and workload Bearer tokens
- **JWKS Integration**: Both use cached JWKS clients for OIDC issuer discovery and token validation
- **Error Handling**: Consistent error types and messages across both authentication implementations
- **Test Coverage**: Comprehensive test suites validate both static and workload authentication paths

```mermaid
flowchart TD
AuthRequest["Authentication Request"] --> CheckHeader{"Authorization Header?"}
CheckHeader --> |Bearer| WorkloadPath["Workload Authentication Path"]
CheckHeader --> |Basic| StaticPath["Static Authentication Path"]
CheckHeader --> |None| Reject["Reject: No Credentials"]
WorkloadPath --> ValidateIssuer["Validate OIDC Issuer"]
ValidateIssuer --> DecodeJWT["Decode JWT with JWKS"]
DecodeJWT --> MapSubject["Map Subject to Client ID"]
MapSubject --> Success["Success: Return Client ID"]
StaticPath --> ValidateRegistry["Validate Against Registry"]
ValidateRegistry --> Success
Reject --> Error["Error: IngestAuthError/QueryAuthError"]
```

**Diagram sources**
- [audit-service/src/audit_service/services/ingest_auth.py:105-117](file://products/audit-service/src/audit_service/services/ingest_auth.py#L105-L117)
- [incident-service/src/incident_service/services/query_auth.py:104-116](file://products/incident-service/src/incident_service/services/query_auth.py#L104-L116)

**Section sources**
- [audit-service/src/audit_service/services/ingest_auth.py:1-118](file://products/audit-service/src/audit_service/services/ingest_auth.py#L1-L118)
- [incident-service/src/incident_service/services/query_auth.py:1-117](file://products/incident-service/src/incident_service/services/query_auth.py#L1-L117)
- [audit-service/tests/test_ingest_auth.py:1-257](file://products/audit-service/tests/test_ingest_auth.py#L1-L257)
- [incident-service/tests/test_query_auth.py:1-60](file://products/incident-service/tests/test_query_auth.py#L1-L60)

### **Enhanced** Multi-Model Runtime Monitoring Capabilities
- **Evidence Store Operations Monitoring**:
  - `evidence_store_writes_total` counter tracks successful and failed evidence persistence attempts
  - `evidence_frames_persisted_total` counter monitors frames persisted for session replay
  - `evidence_frames_truncated_total` counter with reason labels tracks truncation events
  - Truncation reasons include "entry_cap" for oversized payloads and "session_budget" for memory constraints
  - Backend selection monitoring via `agent_state_backend` gauge for memory/postgres backends
- **Model Discovery Lifecycle Monitoring**:
  - `agent_model_discovery_refreshes_total` counter tracks refresh cycles by provider and outcome
  - Refresh outcomes include "override", "disabled", "live", "memory", "cache", and "curated"
  - `agent_model_discovery_models` gauge shows current model counts per provider after discovery
  - Provider-specific monitoring for the new luban provider supporting self-hosted LLMs
- **Integration Points**:
  - Evidence store metrics integrated into runtime kernel during turn persistence
  - Model discovery metrics embedded in background refresh loops
  - Comprehensive error handling with fail-open behavior for non-critical failures
  - Luban provider integration with bearer-token authentication and mandatory base URL validation

```mermaid
flowchart TD
Start(["Service Startup"]) --> InitEvidence["Initialize Evidence Store<br/>Track Backend Selection"]
InitEvidence --> InitDiscovery["Initialize Model Discovery<br/>Background Refresh Loop"]
InitDiscovery --> InitLuban["Initialize Luban Provider<br/>Validate Base URL & API Key"]
InitLuban --> EvidenceOps["Evidence Store Operations"]
EvidenceOps --> WriteTracking{"Evidence Write?"}
WriteTracking --> |Success| RecordSuccess["record_evidence_write('ok')"]
WriteTracking --> |Error| RecordError["record_evidence_write('error')"]
RecordSuccess --> FramePersistence["Track Frames Persisted"]
FramePersistence --> TruncationCheck{"Frame Size Check"}
TruncationCheck --> |Oversized| EntryCap["record_evidence_frame_truncated('entry_cap')"]
TruncationCheck --> |Budget Exceeded| SessionBudget["record_evidence_frame_truncated('session_budget')"]
EntryCap --> Continue["Continue Processing"]
SessionBudget --> Continue
InitDiscovery --> DiscoveryLoop["Model Discovery Refresh Loop"]
DiscoveryLoop --> LadderCheck{"Resolution Ladder"}
LadderCheck --> |Override| OverridePath["record_model_discovery_refresh(provider, 'override')"]
LadderCheck --> |Disabled| DisabledPath["record_model_discovery_refresh(provider, 'disabled')"]
LadderCheck --> |Live Success| LivePath["record_model_discovery_refresh(provider, 'live')"]
LadderCheck --> |Memory Cache| MemoryPath["record_model_discovery_refresh(provider, 'memory')"]
LadderCheck --> |Postgres Cache| CachePath["record_model_discovery_refresh(provider, 'cache')"]
LadderCheck --> |Curated Fallback| CuratedPath["record_model_discovery_refresh(provider, 'curated')"]
OverridePath --> ModelCount["record_model_discovery_models(provider, count)"]
DisabledPath --> ModelCount
LivePath --> ModelCount
MemoryPath --> ModelCount
CachePath --> ModelCount
CuratedPath --> ModelCount
ModelCount --> Continue
InitLuban --> ValidateConfig["Validate LUBAN_BASE_URL<br/>and LUBAN_API_KEY"]
ValidateConfig --> BuildModel["Build OpenAI Chat Model<br/>with Bearer Token Auth"]
BuildModel --> Continue
```

**Diagram sources**
- [agent-platform/src/agent_service/services/evidence_store.py:156-185](file://products/agent-platform/src/agent_service/services/evidence_store.py#L156-L185)
- [agent-platform/src/agent_service/services/model_discovery.py:233-280](file://products/agent-platform/src/agent_service/services/model_discovery.py#L233-L280)
- [agent-platform/src/agent_service/runtime_kernel.py:510-529](file://products/agent-platform/src/agent_service/runtime_kernel.py#L510-L529)
- [agent-platform/src/agent_service/providers/luban.py:36-74](file://products/agent-platform/src/agent_service/providers/luban.py#L36-L74)

**Section sources**
- [agent-platform/src/agent_service/core/metrics.py:156-209](file://products/agent-platform/src/agent_service/core/metrics.py#L156-L209)
- [agent-platform/src/agent_service/services/evidence_store.py:156-185](file://products/agent-platform/src/agent_service/services/evidence_store.py#L156-L185)
- [agent-platform/src/agent_service/services/model_discovery.py:27-30](file://products/agent-platform/src/agent_service/services/model_discovery.py#L27-L30)
- [agent-platform/src/agent_service/providers/luban.py:9-35](file://products/agent-platform/src/agent_service/providers/luban.py#L9-L35)

### **Enhanced** OTLP Credential Management and Secret Synchronization
- **Robust Authentication**: Eliminates 401 Unauthorized errors through cluster-side secret merging
- **Durable Provisioning**: Uses `kubectl patch --type merge` to touch only the OTEL key while preserving other secrets
- **Sibling Script Coordination**: All sibling secret sync scripts preserve existing OTLP headers across environment file regenerations
- **Automatic Recovery**: Fresh clusters require initial OpenObserve root credentials export; otherwise push fails open by design
- **Best-Effort Local Mirroring**: Maintains consistency between cluster secrets and local environment files

```mermaid
flowchart TD
Start(["Secret Sync Process"]) --> CheckEnv{"OO_ROOT_USER_EMAIL/PASSWORD set?"}
CheckEnv --> |No| Skip["Skip provisioning<br/>Anonymous push (401 expected)"]
CheckEnv --> |Yes| Generate["Generate Basic Auth Header<br/>base64(email:password)"]
Generate --> MergeSecret["Merge into Cluster Secrets<br/>kubectl patch --type merge"]
MergeSecret --> PreserveHeaders["Preserve Headers in Sibling Scripts<br/>grep + append pattern"]
PreserveHeaders --> MirrorLocal["Mirror to Local Env Files<br/>upsert_env_line function"]
MirrorLocal --> Restart["Restart All Deployments<br/>rollout restart"]
Restart --> Verify["Verify Rollout Status<br/>rollout status --timeout=120s"]
Skip --> End(["Process Complete"])
Verify --> End
```

**Diagram sources**
- [sync-otel-secrets.sh:47-52](file://shared/platform-ops/gitops/sync-otel-secrets.sh#L47-L52)
- [sync-otel-secrets.sh:73-90](file://shared/platform-ops/gitops/sync-otel-secrets.sh#L73-L90)
- [sync-delegation-secrets.sh:48-57](file://shared/platform-ops/gitops/sync-delegation-secrets.sh#L48-L57)

**Section sources**
- [sync-otel-secrets.sh:1-162](file://shared/platform-ops/gitops/sync-otel-secrets.sh#L1-L162)
- [2026-08-21-durable-otlp-secret-provisioning.md:1-79](file://docs/agentic-aiops-platform/release-notes/2026-08-21-durable-otlp-secret-provisioning.md#L1-L79)

### **Updated** OpenTelemetry Push Pipeline Implementation
- **Comprehensive Coverage**: All seven platform services implement identical OpenTelemetry push pipeline
- **Opt-in Configuration**: Enabled via OTEL_ENABLED environment variable (supports true/false/yes/on/1)
- **OTLP Protocol**: Uses HTTP/protobuf protocol compatible with OpenObserve ingest endpoints
- **Three Signal Types**: Exports traces, metrics, and logs to OpenObserve backend
- **Fail-Open Design**: Setup errors are logged but never raised into request path
- **Resource Context**: Service name propagated via OTEL_SERVICE_NAME or defaults to service metadata
- **Enhanced Authentication**: Robust OTLP header management prevents authentication failures
- **Authentication**: Supports OTEL_EXPORTER_OTLP_HEADERS for OpenObserve authentication with automatic credential synchronization

```mermaid
flowchart TD
Start(["Service Startup"]) --> CheckEnv{"OTEL_ENABLED?"}
CheckEnv --> |false| Skip["Skip Telemetry<br/>No OpenTelemetry overhead"]
CheckEnv --> |true| Init["Initialize OpenTelemetry"]
Init --> CreateResource["Create Resource<br/>service.name"]
CreateResource --> SetupTracer["Setup TracerProvider<br/>+ BatchSpanProcessor"]
SetupTracer --> SetupMeter["Setup MeterProvider<br/>+ PeriodicExportingMetricReader"]
SetupMeter --> AttachBridge["Attach Log Bridge<br/>Structured → OTLP"]
AttachBridge --> InstrumentHTTPX["Instrument HTTPX Client"]
InstrumentHTTPX --> EnableFastAPI["Enable FastAPI Instrumentation"]
EnableFastAPI --> CheckAuth{"OTLP Headers Available?"}
CheckAuth --> |Yes| Export["Export to OpenObserve<br/>OTLP HTTP/protobuf (Authenticated)"]
CheckAuth --> |No| Anonymous["Export Anonymously<br/>OpenObserve returns 401"]
Anonymous --> FailOpen["Fail Open<br/>Continue Service Operation"]
Export --> End(["Service Running"])
FailOpen --> End
Skip --> End
```

**Diagram sources**
- [agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [tool-gateway/src/tool_gateway/core/telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [incident-service/src/incident_service/core/telemetry.py](file://products/incident-service/src/incident_service/core/telemetry.py)

**Section sources**
- [agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [tool-gateway/src/tool_gateway/core/telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [platform-gateway/src/platform_gateway/core/telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [audit-service/src/audit_service/core/telemetry.py](file://products/audit-service/src/audit_service/core/telemetry.py)
- [skills-hub/src/skills_hub/core/telemetry.py](file://products/skills_hub/src/skills_hub/core/telemetry.py)
- [incident-service/src/incident_service/core/telemetry.py](file://products/incident-service/src/incident_service/core/telemetry.py)

### **Updated** Metrics Collection Strategy
- Each service defines metrics using direct prometheus_client implementation:
  - Custom RED middleware records HTTP requests with method, handler, and status labels
  - Histogram metrics track request duration with method and handler labels
  - Domain-specific counters for business logic (sessions, tokens, policy decisions)
  - Module-level metric objects prevent double-registration during testing
  - **New**: Multi-model runtime metrics for evidence store and model discovery operations
  - **New**: Provider-specific metrics for the new luban provider
  - **New**: Drift-guard parity ensures consistent metrics collection patterns
- Metric naming follows shared conventions to ensure consistency across services
- Labels include service, route, method, status code, and operation where applicable
- Direct implementation avoids compatibility issues with pinned starlette versions

```mermaid
classDiagram
class PrometheusMetrics {
+Counter http_requests_total
+Histogram http_request_duration_seconds
+setup_metrics(app)
+record_custom_metric(name, value)
}
class AgentMetrics {
+agent_sessions_created_total
+agent_chat_requests_total
+session_store_backend gauge
+session_store_errors counter
+evidence_store_writes_total
+evidence_frames_persisted_total
+evidence_frames_truncated_total
+agent_model_discovery_refreshes_total
+agent_model_discovery_models gauge
+agent_state_backend gauge
}
class IdentityMetrics {
+identity_tokens_issued_total
+token_exchange_total
+audit_emits_total
}
class GatewayMetrics {
+gateway_policy_decisions_total
+gateway_token_verification_total
+audit_emits_total
+tool_redacted_spans_total
}
class PlatformGatewayMetrics {
+delegation_exchange_total
+delegation_cache_total
+audit_emits_total
}
class AuditMetrics {
+audit_events_ingested_total
+audit_retention_ops_total
+audit_storage_errors counter
}
class SkillsMetrics {
+skills_ingested_total
+skills_sync_ops_total
+scoring_calculations_total
}
class IncidentMetrics {
+incident_triaged_total
+incident_connector_dispatches_total
+incident_store_operations counter
}
PrometheusMetrics <|-- AgentMetrics
PrometheusMetrics <|-- IdentityMetrics
PrometheusMetrics <|-- GatewayMetrics
PrometheusMetrics <|-- PlatformGatewayMetrics
PrometheusMetrics <|-- AuditMetrics
PrometheusMetrics <|-- SkillsMetrics
PrometheusMetrics <|-- IncidentMetrics
```

**Diagram sources**
- [agent-platform/src/agent_service/core/metrics.py:156-209](file://products/agent-platform/src/agent_service/core/metrics.py#L156-L209)
- [identity-broker/src/identity_service/core/metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [tool-gateway/src/tool_gateway/core/metrics.py](file://products/tool-gateway/src/tool_gateway/core/metrics.py)
- [platform-gateway/src/platform_gateway/core/metrics.py](file://products/platform-gateway/src/platform_gateway/core/metrics.py)
- [audit-service/src/audit_service/core/metrics.py](file://products/audit-service/src/audit_service/core/metrics.py)
- [skills-hub/src/skills_hub/core/metrics.py](file://products/skills_hub/src/skills_hub/core/metrics.py)

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [agent-platform/src/agent_service/core/metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [identity-broker/src/identity_service/core/metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [tool-gateway/src/tool_gateway/core/metrics.py](file://products/tool-gateway/src/tool_gateway/core/metrics.py)
- [platform-gateway/src/platform_gateway/core/metrics.py](file://products/platform-gateway/src/platform_gateway/core/metrics.py)

### Enhanced Structured Logging Conventions
- All services now implement standardized logging configuration:
  - `configure_logging()` raises root logger from WARNING to INFO level at startup
  - LOG_LEVEL environment variable supports per-deployment overrides (default: INFO)
  - Audit trail events (http_request, tool_invoked, policy decisions) are captured at INFO level
  - Structured logs include consistent fields: service_name, version, timestamp, level, message, request_id, trace_id, user_id, operation
- **Updated** Log Bridge Integration:
  - When OpenTelemetry is enabled, structured logs are mirrored to OTLP pipeline
  - Log bridge attaches to root logger to capture all application logs
  - Trace context automatically attached to logs when spans are active
  - OpenTelemetry internal loggers detached to prevent recursion
- Log aggregation pipelines parse these fields to support filtering and correlation.
- Sensitive data is excluded from logs per security policies.

```mermaid
flowchart TD
Start(["Service Startup"]) --> ConfigureLogging["configure_logging()<br/>LOG_LEVEL env var"]
ConfigureLogging --> BuildContext["Build Context<br/>service_name, version, request_id, trace_id"]
BuildContext --> EmitLog["Emit Structured Log<br/>level, message, fields"]
EmitLog --> CheckOTEL{"OTEL_ENABLED?"}
CheckOTEL --> |false| Aggregate["Aggregate Logs<br/>centralized storage"]
CheckOTEL --> |true| Bridge["Log Bridge<br/>Mirror to OTLP"]
Bridge --> Correlate["Correlate with Traces<br/>trace/span ids attached"]
Correlate --> Aggregate
Aggregate --> Analyze["Analyze & Correlate<br/>by request_id, trace_id"]
Analyze --> End(["Insights & Alerts"])
```

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [agent-platform/src/agent_service/core/observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [identity-broker/src/identity_service/core/observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [tool-gateway/src/tool_gateway/core/observability.py](file://products/tool-gateway/src/tool_gateway/core/observability.py)
- [platform-gateway/src/platform_gateway/core/observability.py](file://products/platform-gateway/src/platform_gateway/core/observability.py)

### **Enhanced** Distributed Tracing Implementation
- **Comprehensive Coverage**: All seven services implement identical OpenTelemetry tracing
- **Trace Propagation**: W3C trace context propagated across service boundaries
- **Automatic Instrumentation**: FastAPI and HTTPX client calls automatically instrumented
- **Batch Processing**: Spans exported in batches for optimal performance
- **Resource Context**: Service metadata included in all telemetry signals
- **Current Trace ID**: Available via current_trace_id() function for correlation
- **Enhanced Authentication**: Reliable OTLP authentication prevents trace export failures

```mermaid
sequenceDiagram
participant Caller as "Caller"
participant Gateway as "Platform Gateway"
participant Agent as "Agent Platform"
participant Identity as "Identity Broker"
participant OpenObserve as "OpenObserve"
Caller->>Gateway : HTTP Request (trace_id)
Gateway->>Gateway : StartSpan("http.request")
Gateway->>Identity : Auth Call (propagate trace_id)
Identity->>Identity : StartSpan("auth.check")
Identity-->>Gateway : Auth Result
Gateway->>Agent : Agent Call (propagate trace_id)
Agent->>Agent : StartSpan("agent.execute")
Agent-->>Gateway : Response
Gateway->>Gateway : log_event("tool_invoked")
Gateway->>OpenObserve : ExportSpans() (Authenticated)
Identity->>OpenObserve : ExportSpans() (Authenticated)
Agent->>OpenObserve : ExportSpans() (Authenticated)
```

**Diagram sources**
- [agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [tool-gateway/src/tool_gateway/core/telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [platform-gateway/src/platform_gateway/core/telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)

**Section sources**
- [agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [tool-gateway/src/tool_gateway/core/telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [platform-gateway/src/platform_gateway/core/telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [audit-service/src/audit_service/core/telemetry.py](file://products/audit-service/src/audit_service/core/telemetry.py)
- [skills-hub/src/skills_hub/core/telemetry.py](file://products/skills_hub/src/skills_hub/core/telemetry.py)
- [incident-service/src/incident_service/core/telemetry.py](file://products/incident-service/src/incident_service/core/telemetry.py)

### **Updated** Health Check Endpoints, Readiness Probes, and Liveness Probes
- **Enhanced Health Endpoints**: 
  - Agent service `/api/v2/health` now includes comprehensive technology stack information
  - Gateway `/health/ready` includes Python and FastAPI versions in all response branches
  - Backend stores provide server version information when available
- **Standardized Status Vocabulary**: 
  - Unified status terms: **ready**, **degraded**, **not ready**, **unavailable**, **checking…**
  - Consistent status indicators across all platform components
- **Readiness and Liveness Probes**: 
  - Readiness probes verify dependencies (e.g., Redis, external APIs)
  - Liveness probes confirm process health and internal state
  - Kubernetes deployments configure probe paths, intervals, and thresholds
- **Improved Operational Awareness**: 
  - Version information enables better troubleshooting and capacity planning
  - Technology stack visibility helps identify compatibility issues
  - Standardized status makes it easier to assess overall system health

```mermaid
flowchart TD
ProbeStart["Kubelet Probe"] --> Type{"Probe Type?"}
Type --> |Readiness| CheckDeps["Check Dependencies<br/>DB, Cache, External APIs"]
Type --> |Liveness| CheckProcess["Check Process State<br/>Internal Health"]
CheckDeps --> GetTechInfo["Get Technology Stack Info"]
CheckProcess --> GetTechInfo
GetTechInfo --> AssessStatus{"Assess Overall Status"}
AssessStatus --> |All Healthy| Ready["Return 200 OK<br/>status: ready"]
AssessStatus --> |Partial Issues| Degraded["Return 200 OK<br/>status: degraded"]
AssessStatus --> |Critical Issues| NotReady["Return 503 Unavailable<br/>status: not ready"]
AssessStatus --> |Probe Failed| Unavailable["Return 503 Unavailable<br/>status: unavailable"]
Ready --> End(["Healthy"])
Degraded --> End
NotReady --> End
Unavailable --> End
```

**Diagram sources**
- [health-response.schema.json:1-21](file://shared/shared-contracts/schemas/health-response.schema.json#L1-L21)
- [agent-health.schema.json:41-68](file://shared/shared-contracts/schemas/agent-health.schema.json#L41-L68)
- [gateway_service.py:56-84](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L56-L84)
- [routes.py:1073-1093](file://products/agent-platform/src/agent_service/api/v2/routes.py#L1073-L1093)

**Section sources**
- [shared/shared-contracts/schemas/health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [2026-08-28-components-tech-stack-and-status.md:35-57](file://docs/agentic-aiops-platform/release-notes/2026-08-28-components-tech-stack-and-status.md#L35-L57)

### Alerting Rules and Dashboard Templates
- Alerting rules are defined based on key metrics:
  - High error rates, latency spikes, resource exhaustion, dependency failures
  - Tool invocation failures and redaction overflow events
  - **New**: Evidence store write failures and excessive truncation events
  - **New**: Model discovery refresh failures and unexpected model count changes
  - **New**: Luban provider configuration validation failures
  - **New**: Drift-guard test failures indicating service inconsistency
  - **Updated**: Enhanced alerts for technology stack version mismatches
- Dashboard templates visualize:
  - Request throughput, latency percentiles, error rates, trace spans, and system resources
  - Tool invocation patterns and audit trail events
  - **New**: Evidence store operation metrics and model discovery lifecycle visualization
  - **New**: Multi-provider model availability and discovery status
  - **New**: Authentication parity validation results
  - **Updated**: Technology stack version monitoring and compatibility dashboards
- Alerts trigger notifications and runbooks for incident response

```mermaid
graph TB
Metrics["Prometheus Metrics"] --> Rules["Alerting Rules"]
Rules --> Alerts["Alertmanager Notifications"]
Alerts --> Runbook["Incident Runbook"]
Metrics --> Dashboards["Grafana Dashboards"]
Dashboards --> Ops["Operations Team"]
NewMetrics["Multi-Model Runtime Metrics"] --> Rules
NewMetrics --> Dashboards
LubanMetrics["Luban Provider Metrics"] --> Rules
LubanMetrics --> Dashboards
DriftMetrics["Drift-Guard Metrics"] --> Rules
DriftMetrics --> Dashboards
TechStackMetrics["Technology Stack Metrics"] --> Rules
TechStackMetrics --> Dashboards
```

**Section sources**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)

### Custom Metric Creation, Log Aggregation, and Trace Correlation
- Custom metrics should adhere to shared naming and labeling conventions
- Logs must include correlation identifiers (request_id, trace_id) for cross-service correlation
- Traces should be exported with consistent span names and attributes
- Tool invocation events provide enhanced audit trail for debugging and compliance
- **Enhanced** OpenObserve Integration:
  - All three signal types (traces, metrics, logs) exported to OpenObserve when enabled
  - Automatic correlation between logs and traces via trace context
  - Batch processing optimizes network usage and reduces overhead
  - **New**: Reliable authentication prevents telemetry export failures
  - **New**: Multi-model runtime metrics integrated into OpenObserve pipeline
  - **New**: Provider-specific metrics for enhanced observability
  - **New**: Drift-guard parity ensures consistent metric collection patterns
  - **Updated**: Technology stack version metrics for compatibility monitoring

```mermaid
flowchart TD
DefineMetric["Define Custom Metric<br/>name, help, labels"] --> Register["Register with prometheus_client"]
Register --> Emit["Emit Metric Values"]
Emit --> Scrape["Prometheus Scrapes"]
Scrape --> Query["Query & Visualize"]
EmitLog["Emit Structured Log<br/>with correlation IDs"] --> CheckOTEL{"OTEL_ENABLED?"}
CheckOTEL --> |false| Aggregate["Log Aggregator"]
CheckOTEL --> |true| Bridge["Log Bridge<br/>to OTLP"]
Bridge --> Correlate["Correlate with Traces"]
Aggregate --> Search["Search & Filter"]
ExportTrace["Export Spans<br/>with trace_id"] --> OpenObserve["OpenObserve Backend<br/>Authenticated Export"]
OpenObserve --> Correlate
NewMetrics["Multi-Model Runtime Metrics"] --> Scrape
NewMetrics --> OpenObserve
LubanMetrics["Provider Metrics"] --> Scrape
LubanMetrics --> OpenObserve
DriftMetrics["Drift-Guard Metrics"] --> Scrape
DriftMetrics --> OpenObserve
TechStackMetrics["Technology Stack Metrics"] --> Scrape
TechStackMetrics --> OpenObserve
```

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

## Dependency Analysis
Observability components depend on shared contracts and Kubernetes configurations:
- Services rely on shared observability conventions for consistency
- Deployments configure probes and environment variables for observability
- Prometheus scrapes metrics from each service's /metrics endpoint
- All services call configure_logging() during startup for consistent log levels
- Direct prometheus_client implementation replaces prometheus-fastapi-instrumentator
- **Enhanced** OpenTelemetry dependencies:
  - Optional OpenTelemetry SDK components loaded only when OTEL_ENABLED is true
  - OTLP HTTP/protobuf exporters for traces, metrics, and logs
  - Automatic instrumentation for FastAPI and HTTPX client libraries
  - **New**: Multi-model runtime monitoring dependencies integrated into agent platform
  - **New**: Robust secret synchronization ensures credential availability
  - **New**: Luban provider dependencies for self-hosted LLM support
  - **New**: Drift-guard test dependencies for cross-service validation
  - **Updated**: Enhanced health endpoint dependencies for technology stack version detection

```mermaid
graph TB
OC["Observability Conventions<br/>direct prometheus_client"] --> AP_METRICS["Agent Platform Metrics"]
OC --> IB_METRICS["Identity Broker Metrics"]
OC --> TG_METRICS["Tool Gateway Metrics"]
OC --> PG_METRICS["Platform Gateway Metrics"]
OC --> AS_METRICS["Audit Service Metrics"]
OC --> SH_METRICS["Skills Hub Metrics"]
OC --> IS_METRICS["Incident Service Metrics"]
ENV["Observability Env<br/>LOG_LEVEL + OTEL config"] --> AP_DEP["Agent Deployment"]
ENV --> IB_DEP["Identity Deployment"]
ENV --> TG_DEP["Gateway Deployment"]
ENV --> PG_DEP["Platform Gateway Deployment"]
ENV --> AS_DEP["Audit Deployment"]
ENV --> SH_DEP["Skills Deployment"]
ENV --> IS_DEP["Incident Deployment"]
AP_METRICS --> PROM["Prometheus"]
IB_METRICS --> PROM
TG_METRICS --> PROM
PG_METRICS --> PROM
AS_METRICS --> PROM
SH_METRICS --> PROM
IS_METRICS --> PROM
OTEL["OpenTelemetry Pipeline"] --> OO["OpenObserve Backend"]
AP_TELEMETRY["Agent Telemetry"] --> OTEL
IB_TELEMETRY["Identity Telemetry"] --> OTEL
TG_TELEMETRY["Gateway Telemetry"] --> OTEL
PG_TELEMETRY["Platform Gateway Telemetry"] --> OTEL
AS_TELEMETRY["Audit Telemetry"] --> OTEL
SH_TELEMETRY["Skills Telemetry"] --> OTEL
IS_TELEMETRY["Incident Telemetry"] --> OTEL
SECRET_SYNC["Secret Synchronization"] --> OTEL
MULTI_MODEL["Multi-Model Runtime Metrics"] --> AP_METRICS
MULTI_MODEL --> OTEL
LUBAN_PROVIDER["Luban Provider Metrics"] --> AP_METRICS
LUBAN_PROVIDER --> OTEL
DRIFT_GUARD["Drift-Guard Tests"] --> ALL_SERVICES["All Seven Services"]
TECH_STACK["Technology Stack Detection"] --> HEALTH_ENDPOINTS["Enhanced Health Endpoints"]
HEALTH_ENDPOINTS --> SETTINGS_PANE["Settings Platform Pane"]
```

**Diagram sources**
- [agent-platform/src/agent_service/core/metrics.py:156-209](file://products/agent-platform/src/agent_service/core/metrics.py#L156-L209)
- [agent-platform/src/agent_service/providers/luban.py:9-35](file://products/agent-platform/src/agent_service/providers/luban.py#L9-L35)
- [sync-otel-secrets.sh:73-90](file://shared/platform-ops/gitops/sync-otel-secrets.sh#L73-L90)
- [test_module_parity.py:38-46](file://products/tool-gateway/tests/test_module_parity.py#L38-L46)
- [gateway_service.py:46-84](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L46-L84)
- [routes.py:1050-1093](file://products/agent-platform/src/agent_service/api/v2/routes.py#L1050-L1093)

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

## Performance Considerations
- Monitor latency percentiles and error rates to identify bottlenecks
- Use histograms for request durations and gauge metrics for resource utilization
- Correlate traces with metrics to pinpoint slow or failing operations
- Capacity planning should be informed by trends in throughput, latency, and error rates
- Tool invocation patterns can reveal performance issues in external integrations
- Direct prometheus_client implementation provides better performance than external instrumentation libraries
- **Enhanced** OpenTelemetry Performance:
  - Batch processing reduces network overhead for traces, metrics, and logs
  - Fail-open design prevents OpenObserve connectivity issues from impacting service performance
  - Optional feature allows disabling telemetry in high-performance environments
  - Resource-efficient implementation with minimal CPU and memory overhead
  - **New**: Reliable authentication eliminates retry overhead from failed authentication attempts
  - **New**: Multi-model runtime metrics have minimal performance impact due to efficient counter operations
  - **New**: Evidence store truncation metrics use bounded label cardinality to prevent memory growth
  - **New**: Luban provider metrics are lightweight and don't impact self-hosted LLM performance
  - **New**: Drift-guard tests run asynchronously to avoid blocking deployment pipelines
  - **Updated**: Technology stack version detection uses best-effort approach to avoid performance impact
- **New** Multi-Model Runtime Performance:
  - Evidence store operations are best-effort and never block chat turns
  - Model discovery runs asynchronously with configurable refresh intervals
  - Provider-specific metrics use efficient counter operations
  - Backpressure handling prevents cascading failures in multi-provider scenarios
- **New** Drift-Guard Performance:
  - Parity tests run during CI/CD without impacting production performance
  - AST-based comparison minimizes computational overhead
  - Cached module reads reduce filesystem access during test execution

## Troubleshooting Guide
- Use structured logs with correlation IDs to trace requests across services
- Inspect Prometheus metrics for anomalies in latency, errors, and resource usage
- Review traces to understand call chains and identify failures
- Validate health endpoints and probe configurations when services are unhealthy
- Check LOG_LEVEL environment variable if audit trail events are missing - uvicorn defaults to WARNING level which discards INFO-level structured events like http_request and tool_invoked
- Investigate tool_invoked events for tool-specific issues and redaction problems
- Verify that configure_logging() is called during service startup to ensure proper log level configuration
- **Updated** If metrics are not appearing in Prometheus, verify that the /metrics endpoint is accessible and returning prometheus_client format data
- **Updated** The direct prometheus_client implementation avoids compatibility issues with pinned starlette versions that affected prometheus-fastapi-instrumentator
- **Enhanced** OpenTelemetry Troubleshooting:
  - Set OTEL_ENABLED=true to enable telemetry pipeline
  - Configure OTEL_EXPORTER_OTLP_ENDPOINT to point to OpenObserve
  - Check service logs for "otel telemetry enabled" confirmation message
  - **New**: Verify OTLP authentication headers via `kubectl get secret <secret-name> -o jsonpath='{.data.OTEL_EXPORTER_OTLP_HEADERS}'`
  - **New**: Test connectivity to OpenObserve endpoint independently
  - **New**: Monitor for "otel telemetry setup failed" messages indicating configuration issues
  - **New**: Use fail-open behavior to continue service operation even if OpenObserve is unavailable
  - **New**: Run `sync-otel-secrets.sh` to re-provision credentials if experiencing 401 Unauthorized errors
  - **New**: Check sibling script output for preserved OTLP header lines
  - **New**: Verify all seven deployment rollouts completed successfully after secret provisioning
- **New** Drift-Guard Troubleshooting:
  - Run `python -m pytest products/tool-gateway/tests/test_module_parity.py` to validate parity
  - Check specific test classes: TelemetryParityTest, ObservabilityParityTest, TokenVerifierParityTest, AuditEmitterParityTest, ServiceAuthParityTest
  - Review error messages for drift hints indicating which services need updates
  - Use placeholder normalization to compare service-specific differences
  - Ensure all seven services are updated when making changes to shared modules
- **New** Authentication Parity Troubleshooting:
  - Verify audit-service ingest-auth and incident-service query-auth implementations match
  - Check both static and workload authentication paths work correctly
  - Validate JWKS caching and OIDC discovery functionality
  - Test error handling for expired tokens, invalid audiences, and unregistered subjects
- **New** Multi-Model Runtime Troubleshooting:
  - Check `evidence_store_writes_total{result="error"}` for evidence persistence failures
  - Monitor `evidence_frames_truncated_total{reason="entry_cap"}` for excessive payload truncation
  - Monitor `evidence_frames_truncated_total{reason="session_budget"}` for memory pressure issues
  - Verify `agent_model_discovery_refreshes_total{result="live"}` for successful live discovery
  - Check `agent_model_discovery_refreshes_total{result="curated"}` for fallback to curated models
  - Inspect `agent_model_discovery_models{provider}` gauge for unexpected model count changes
  - Investigate `agent_state_backend` gauge for evidence store backend selection issues
  - Check `agent_model_discovery_refreshes_total{provider="luban"}` for luban provider discovery
  - Verify LUBAN_BASE_URL and LUBAN_API_KEY configuration for luban provider
  - Monitor provider-specific metrics for self-hosted LLM connectivity issues
  - Check model discovery ladder outcomes for resolution failures
- **Updated** Health Endpoint Troubleshooting:
  - Check enhanced health endpoints for technology stack version information
  - Verify standardized status vocabulary is being applied correctly
  - Monitor backend server version detection for database connectivity issues
  - Use Settings Platform pane to quickly assess overall system health
  - Check for version mismatches between different platform components

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [test_module_parity.py:102-207](file://products/tool-gateway/tests/test_module_parity.py#L102-L207)
- [2026-08-28-components-tech-stack-and-status.md:35-57](file://docs/agentic-aiops-platform/release-notes/2026-08-28-components-tech-stack-and-status.md#L35-L57)

## Conclusion
The Luban AIOps Platform implements a robust observability framework centered on direct prometheus_client implementation for metrics collection, enhanced structured logging with configurable log levels, and comprehensive distributed tracing with OpenObserve integration. The platform includes an opt-in OpenTelemetry push pipeline that exports traces, metrics, and logs to OpenObserve via OTLP HTTP/protobuf protocol, providing end-to-end observability across all seven platform services. **Enhanced**: The platform now features enhanced observability with comprehensive technology stack visibility in the Settings Platform pane, standardized status vocabulary (ready, degraded, not ready, unavailable, checking…), and improved health endpoint responses with version information for better operational awareness and troubleshooting. The platform also includes robust monitoring capabilities for multi-model runtime including evidence store operations, model discovery lifecycle, and comprehensive observability for the new multi-model runtime features with enhanced provider-specific metrics for the luban provider. **New**: The platform implements comprehensive drift-guard parity suites ensuring byte-identical telemetry implementations across all services, authentication parity between audit-service and incident-service, and improved test coverage from 80% to 95% for audit-service and 87% to 92% for incident-service. By using direct prometheus_client instead of prometheus-fastapi-instrumentator, the platform avoids compatibility issues with pinned starlette versions while maintaining equivalent functionality. The framework adheres to shared conventions, calls configure_logging() at startup, and configures Kubernetes probes appropriately, enabling operators to effectively monitor, diagnose, and respond to incidents while planning for future capacity needs. The enhanced audit trail with tool_invoked events and OpenObserve integration provides comprehensive visibility into tool execution patterns and potential security concerns. **New**: The multi-model runtime monitoring provides deep insights into evidence persistence, model discovery processes, and overall system health through comprehensive metrics collection, including specialized monitoring for the new luban provider supporting self-hosted LLMs. **New**: The drift-guard parity suite ensures long-term consistency and maintainability of observability patterns across the entire platform ecosystem. **Updated**: The enhanced Settings Platform pane provides operators with immediate visibility into technology stack versions and standardized status indicators, significantly improving operational awareness and troubleshooting capabilities.

## Appendices
- Reference specifications for observability baseline and conventions
- Kubernetes deployment examples for probes and environment variables
- Health response schema for consistent health checks
- LOG_LEVEL environment variable configuration for different environments
- **Updated** Migration notes from prometheus-fastapi-instrumentator to direct prometheus_client implementation
- **Enhanced** OpenTelemetry configuration guide for OpenObserve integration including environment variables and authentication setup
- **New**: Multi-model runtime monitoring guide including evidence store and model discovery metrics
- **New**: Secret synchronization workflow documentation for OTLP credential management
- **New**: Luban provider configuration guide for self-hosted LLM monitoring
- **New**: Drift-guard parity suite documentation including test execution and troubleshooting
- **New**: Authentication parity validation guide for audit-service and incident-service consistency
- **Updated**: Settings Platform pane documentation for technology stack visibility and standardized status indicators
- **Updated**: Enhanced health endpoint documentation with version information and backend server versions

**Section sources**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [shared/shared-contracts/schemas/health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [configuration-reference.md:417-428](file://docs/guides/configuration-reference.md#L417-L428)
- [sync-otel-secrets.sh:1-162](file://shared/platform-ops/gitops/sync-otel-secrets.sh#L1-L162)
- [2026-08-24-multimodel-runtime-and-live-discovery.md:1-217](file://docs/agentic-aiops-platform/release-notes/2026-08-24-multimodel-runtime-and-live-discovery.md#L1-L217)
- [test_module_parity.py:1-212](file://products/tool-gateway/tests/test_module_parity.py#L1-L212)
- [2026-08-28-components-tech-stack-and-status.md:1-75](file://docs/agentic-aiops-platform/release-notes/2026-08-28-components-tech-stack-and-status.md#L1-L75)
- [2026-08-28-platform-components-blurb-prose-voice.md:1-37](file://docs/agentic-aiops-platform/release-notes/2026-08-28-platform-components-blurb-prose-voice.md#L1-L37)