# Observability and Monitoring

<cite>
**Referenced Files in This Document**
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [SPEC-018-kernel-middleware-alignment/spec.md](file://docs/specs/SPEC-018-kernel-middleware-alignment/spec.md)
- [SPEC-025-evidence-persistence-in-transcripts/plan.md](file://docs/specs/SPEC-025-evidence-persistence-in-transcripts/plan.md)
- [SPEC-027-live-model-discovery/spec.md](file://docs/specs/SPEC-027-live-model-discovery/spec.md)
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [agent-platform core observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [agent-platform core telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent-platform kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [agent-platform runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [agent-platform app.py](file://products/agent-platform/src/agent_service/app.py)
- [agent-platform main.py](file://products/agent-platform/src/agent_service/main.py)
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [identity-broker core metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [identity-broker core observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [identity-broker core telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [identity-broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [identity-broker health route](file://products/identity-broker/src/identity_service/api/routes/health.py)
- [tool-gateway core metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [tool-gateway core observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [tool-gateway core telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)
- [tool-gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [tool-gateway health route](file://products/tool-gateway/src/api_gateway/api/routes/health.py)
- [dev-k8s agent-service deployment](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [dev-k8s identity-service deployment](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [dev-k8s api-gateway deployment](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml)
- [dev-k8s shared observability env](file://shared/platform-ops/gitops/dev-k8s/base/shared/observability.env)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive documentation for model discovery metrics including refresh cycle counters (agent_model_discovery_refreshes_total) and published model gauges (agent_model_discovery_models)
- Documented the model discovery fallback ladder with metrics for each tier: override, disabled, live, memory, cache, curated
- Enhanced monitoring dashboard guidance with model discovery performance metrics
- Updated troubleshooting section with model discovery debugging steps
- Added detailed coverage of model discovery configuration and background refresh cycles

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
This document explains the observability and monitoring capabilities across the agent platform services, focusing on:
- Metrics collection and Prometheus exposure
- Structured logging standards and correlation
- Distributed tracing implementation using AgentScope's TracingMiddleware and cross-service correlation
- Evidence emission via ToolEvidenceMiddleware and SSE frames from gateway results
- **New**: Model discovery metrics tracking refresh cycles and published model counts
- Health endpoints for readiness and liveness probes
- Dashboarding and alerting guidance
- Performance monitoring, bottleneck identification, and capacity planning

The platform implements consistent observability patterns across Agent Platform, Identity Broker, and Tool Gateway to enable unified monitoring, debugging, and reliability operations.

## Project Structure
Observability is implemented consistently in each service with a common pattern:
- A core module exposing metrics, observability (logging/tracing), and telemetry utilities
- An application entrypoint wiring these components into the HTTP server
- Kubernetes manifests configuring probes and environment variables for observability backends
- Agent-specific middleware stack for kernel-level observability
- **New**: Model discovery service with dedicated metrics for refresh cycles and model catalog status

```mermaid
graph TB
subgraph "Agent Platform"
AP_app["app.py"]
AP_metrics["core/metrics.py"]
AP_obs["core/observability.py"]
AP_telemetry["core/telemetry.py"]
AP_kernel["runtime_kernel.py"]
AP_middleware["services/kernel_middleware.py"]
AP_evidence["services/evidence_store.py"]
AP_discovery["services/model_discovery.py"]
end
subgraph "Identity Broker"
IB_app["app.py"]
IB_metrics["core/metrics.py"]
IB_obs["core/observability.py"]
IB_telemetry["core/telemetry.py"]
IB_health["api/routes/health.py"]
end
subgraph "Tool Gateway"
TG_app["app.py"]
TG_metrics["core/metrics.py"]
TG_obs["core/observability.py"]
TG_telemetry["core/telemetry.py"]
TG_health["api/routes/health.py"]
end
AP_app --> AP_metrics
AP_app --> AP_obs
AP_app --> AP_telemetry
AP_app --> AP_kernel
AP_kernel --> AP_middleware
AP_kernel --> AP_evidence
AP_app --> AP_discovery
IB_app --> IB_metrics
IB_app --> IB_obs
IB_app --> IB_telemetry
IB_app --> IB_health
TG_app --> TG_metrics
TG_app --> TG_obs
TG_app --> TG_telemetry
TG_app --> TG_health
```

**Diagram sources**
- [agent-platform app.py](file://products/agent-platform/src/agent_service/app.py)
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [agent-platform core observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [agent-platform core telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent-platform kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [identity-broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [identity-broker core metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [identity-broker core observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [identity-broker core telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [identity-broker health route](file://products/identity-broker/src/identity_service/api/routes/health.py)
- [tool-gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [tool-gateway core metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [tool-gateway core observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [tool-gateway core telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)
- [tool-gateway health route](file://products/tool-gateway/src/api_gateway/api/routes/health.py)

**Section sources**
- [agent-platform app.py](file://products/agent-platform/src/agent_service/app.py)
- [identity-broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [tool-gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)

## Core Components
Each service exposes three primary observability primitives:
- Metrics: counters, histograms, gauges, and Prometheus exposition
- Observability: structured logs and trace context propagation
- Telemetry: instrumentation helpers for spans, events, and attributes
- Kernel Middleware: AgentScope-based middleware for tool execution tracing and evidence emission
- **New**: Model Discovery Service: Dedicated metrics for refresh cycles and published model counts
- **Updated**: Evidence Store: Dedicated metrics for persistence operations, frame counting, and truncation tracking

Key responsibilities:
- Initialize and configure metrics collectors and exporters
- Inject request/response lifecycle hooks for metrics and traces
- Enforce structured log formats with correlation IDs
- Expose health endpoints for readiness and liveness checks
- Propagate distributed trace headers across service boundaries
- Implement kernel-level tracing via AgentScope's TracingMiddleware
- Emit evidence frames through ToolEvidenceMiddleware for tool executions
- **New**: Track model discovery refresh cycles and published model counts per provider
- **Updated**: Track evidence store write success/failure rates and frame persistence counts
- **Updated**: Monitor evidence frame truncation events with specific reasons (entry_cap vs session_budget)

**Updated** Added model discovery metrics components for comprehensive refresh cycle monitoring

**Section sources**
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [agent-platform core observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [agent-platform core telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [agent-platform kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [identity-broker core metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [identity-broker core observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [identity-broker core telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [tool-gateway core metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [tool-gateway core observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [tool-gateway core telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)

## Architecture Overview
The observability architecture follows a consistent pattern across services with enhanced kernel-level tracing, evidence persistence monitoring, and model discovery observability:
- Application layer wires middleware that records metrics and emits spans
- Core modules provide reusable metrics definitions and logging/tracing utilities
- Agent kernel uses AgentScope middleware stack for tool execution observability
- **New**: Model discovery service runs background tasks with metrics for refresh cycles and model catalog status
- **Updated**: Evidence store tracks persistence operations with detailed metrics for write success/failure, frames persisted, and truncation events
- Kubernetes deployments expose /metrics and health endpoints and configure probes
- Shared conventions define metric names, labels, and log schemas

```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Tool Gateway"
participant Agent as "Agent Platform"
participant Discovery as "Model Discovery"
participant Kernel as "AgentKernel"
participant EvidenceStore as "Evidence Store"
participant Middleware as "Kernel Middleware"
participant Identity as "Identity Broker"
participant Prom as "Prometheus"
participant OTLP as "OTLP Collector"
Client->>Gateway : "HTTP Request"
Gateway->>Gateway : "Instrument request<br/>Start span"
Gateway->>Identity : "Auth call with trace headers"
Identity-->>Gateway : "Response with trace headers"
Gateway->>Agent : "Agent call with trace headers"
Agent->>Discovery : "Background refresh cycle"
Discovery->>Prom : "Record refresh metrics"
Discovery->>Prom : "Update model count gauge"
Agent->>Kernel : "stream_events()"
Kernel->>Middleware : "ToolEvidenceMiddleware.on_acting"
Middleware-->>Kernel : "Evidence frames via SSE"
Kernel->>EvidenceStore : "save_turn() with prepared frames"
EvidenceStore->>EvidenceStore : "prepare_frames() with entry caps"
EvidenceStore->>EvidenceStore : "_enforce_budget() with session limits"
EvidenceStore->>Prom : "Record evidence metrics"
Kernel->>Middleware : "TracingMiddleware"
Middleware-->>Kernel : "OTel spans"
Agent-->>Gateway : "Response with trace headers"
Gateway-->>Client : "Final response"
Gateway->>Prom : "Expose metrics"
Agent->>Prom : "Expose metrics"
Identity->>Prom : "Expose metrics"
Gateway->>OTLP : "Export spans"
Agent->>OTLP : "Export spans"
Identity->>OTLP : "Export spans"
```

**Updated** Enhanced sequence diagram to show model discovery integration alongside evidence store and existing components

**Diagram sources**
- [tool-gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [agent-platform app.py](file://products/agent-platform/src/agent_service/app.py)
- [identity-broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent-platform kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [tool-gateway core metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [identity-broker core metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [tool-gateway core telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)
- [agent-platform core telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [identity-broker core telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)

## Detailed Component Analysis

### Metrics Collection and Prometheus Exposure
- Each service defines metrics in its core/metrics.py module
- Counters track request counts, errors, and business events
- Histograms capture latency distributions for key operations
- Gauges reflect current state such as active sessions or queue sizes
- Prometheus exposition endpoint is enabled via configuration and exposed by the HTTP server

**New Model Discovery Metrics:**
- `agent_model_discovery_refreshes_total {provider, result}`: Tracks model discovery refresh cycles with outcomes including override, disabled, live, memory, cache, and curated
- `agent_model_discovery_models {provider}`: Gauge showing the number of models currently published per provider after discovery

**Updated Evidence Store Metrics:**
- `evidence_store_writes_total {result=ok|error}`: Tracks evidence persistence attempts and outcomes
- `evidence_frames_persisted_total`: Counts total frames successfully persisted for session replay
- `evidence_frames_truncated_total {reason=entry_cap|session_budget}`: Monitors frame truncation events with specific reasons

Typical usage patterns:
- Increment counters on request start and completion
- Record latencies using histogram observe calls around I/O
- Update gauges for resource utilization and concurrency limits
- **New**: Track model discovery refresh cycles and published model counts for provider health monitoring
- **Updated**: Track evidence store write success/failure rates for reliability monitoring
- **Updated**: Monitor frame persistence counts to validate evidence storage throughput
- **Updated**: Alert on excessive truncation events indicating potential data loss

Prometheus scraping targets are configured through service ports and selectors in Kubernetes manifests.

**Section sources**
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [identity-broker core metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [tool-gateway core metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)

### Structured Logging and Trace Correlation
- Logs follow a structured JSON schema defined by shared conventions
- Every log includes correlation identifiers (request ID, trace ID, span ID)
- Log levels are standardized across services
- Context propagation ensures correlation IDs flow through all downstream calls

Best practices:
- Use structured fields instead of free-form messages
- Include operation names, status codes, and error codes
- Avoid sensitive data in logs; redact secrets and tokens

**Section sources**
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [agent-platform core observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [identity-broker core observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [tool-gateway core observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)

### Distributed Tracing Implementation
- Traces are created at request boundaries and propagated via standard headers
- Spans represent logical operations like HTTP requests, tool invocations, and database calls
- Trace context is attached to outgoing requests to maintain correlation
- Telemetry modules export spans to an OTLP-compatible backend

**Updated** Enhanced with AgentScope kernel tracing capabilities and model discovery background task tracing

Trace correlation across services:
- Incoming requests extract trace context from headers
- Outgoing calls inject trace context into headers
- Errors propagate up the call stack with full trace context
- AgentScope's TracingMiddleware provides kernel-level tracing when enabled via AGENTSCOPE_KERNEL_TRACING setting
- **New**: Model discovery background tasks can be traced when kernel tracing is enabled

**Section sources**
- [agent-platform core telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [agent-platform runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [identity-broker core telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [tool-gateway core telemetry.py](file://products/tool-gateway/src/api_gateway/core/telemetry.py)

### Kernel Middleware and Evidence Emission
**New Section** The agent platform now leverages AgentScope's middleware system for enhanced observability:

- **ToolEvidenceMiddleware**: Emits tool_call and tool_result evidence frames for streamed turns, replacing per-request asyncio.Queue plumbing
- **TracingMiddleware**: Provides kernel-level OpenTelemetry tracing when AGENTSCOPE_KERNEL_TRACING is enabled
- **GatewayPermissionMiddleware**: Pre-answers permission gates for headless SSE runtime

Evidence emission flow:
- ToolEvidenceMiddleware.on_acting intercepts tool executions
- Extracts gateway result metadata from ToolChunk/ToolResponse objects
- Emits structured evidence frames via request-scoped sink (ContextVar)
- SSE frames are consumed by stream_events and forwarded to clients

Configuration:
- Evidence emission is always active for gateway-backed tools
- Kernel tracing is opt-in via AGENTSCOPE_KERNEL_TRACING environment variable
- Reply token budget control is available via ReplyBudgetControlMiddleware

**Section sources**
- [agent-platform kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent-platform gateway_tools.py](file://products/agent-platform/src/agent_service/tools/gateway_tools.py)
- [agent-platform runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)

### Evidence Store Persistence and Metrics
**New Section** The evidence store provides comprehensive metrics for monitoring evidence persistence operations:

**Metrics Implementation:**
- `record_evidence_write(result)`: Tracks successful and failed evidence persistence attempts
- `record_evidence_frames_persisted(count)`: Counts total frames persisted for session replay
- `record_evidence_frame_truncated(reason)`: Monitors truncation events with specific reasons

**Size Cap Enforcement:**
- **Entry Cap**: Per-entry size limits (default 128 KiB) truncate oversized payloads with `truncated.reason = "entry_cap"`
- **Session Budget**: Per-session storage limits (default 4 MiB) evict oldest result payloads with `truncated.reason = "session_budget"`

**Persistence Flow:**
1. Frames are prepared with entry cap enforcement before storage
2. Evidence store persists frames and enforces session budget limits
3. Metrics are recorded for each persistence operation and truncation event
4. Failed persistence attempts are logged but don't fail the turn

**Section sources**
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)

### Model Discovery Service and Metrics
**New Section** The model discovery service provides comprehensive metrics for monitoring model catalog refresh cycles and published model counts:

**Metrics Implementation:**
- `record_model_discovery_refresh(provider, result)`: Tracks refresh cycle outcomes with labels for provider and result type
- `record_model_discovery_models(provider, count)`: Updates gauge with current number of published models per provider

**Refresh Cycle Ladder:**
The discovery service follows a fail-soft ladder with different result types:
- **override**: When `PROVIDER_MODELS` environment variable is set, skips discovery entirely
- **disabled**: When model discovery is globally disabled via `AGENT_MODEL_DISCOVERY_ENABLED=false`
- **live**: Successful fetch from provider's `/models` endpoint
- **memory**: Fallback to in-memory last-good models when live fetch fails
- **cache**: Fallback to Postgres cached models when both live and memory tiers fail
- **curated**: Final fallback to curated model series when all other tiers fail

**Background Refresh Cycle:**
- Runs continuously in the background via `run_loop()` method
- Initial refresh occurs at startup, then periodic refresh based on `model_discovery_refresh_seconds` setting
- Each refresh updates the model catalog and records metrics for all configured providers
- Failures are logged but never block the refresh cycle

**Configuration:**
- `AGENT_MODEL_DISCOVERY_ENABLED`: Enable/disable discovery (default: true)
- `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS`: Refresh interval (default: 1800 seconds)
- `AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS`: Timeout for provider API calls (default: 5.0 seconds)

**Section sources**
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [agent-platform runtime_settings.py](file://products/agent-platform/src/agent_service/runtime_settings.py)
- [agent-platform app.py](file://products/agent-platform/src/agent_service/app.py)

### Health Check Endpoints and Probes
- Readiness probes verify dependencies are available and service can accept traffic
- Liveness probes detect if the process is alive and responsive
- Health endpoints return structured responses indicating component status

Configuration in Kubernetes:
- Probes are defined in deployment manifests with appropriate thresholds
- Health endpoints should respond quickly without heavy operations
- Dependencies like Redis or external APIs are checked during readiness

**Section sources**
- [identity-broker health route](file://products/identity-broker/src/identity_service/api/routes/health.py)
- [tool-gateway health route](file://products/tool-gateway/src/api_gateway/api/routes/health.py)
- [dev-k8s agent-service deployment](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [dev-k8s identity-service deployment](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [dev-k8s api-gateway deployment](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml)

### Application Wiring and Entry Points
- Application modules initialize observability components during startup
- Middleware is registered to capture metrics and traces for all requests
- Configuration is loaded from environment variables and config files
- Graceful shutdown ensures metrics and traces are flushed before termination

**Updated** Enhanced with kernel middleware composition, evidence store integration, and model discovery background task management

**Section sources**
- [agent-platform app.py](file://products/agent-platform/src/agent_service/app.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [identity-broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [tool-gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [agent-platform main.py](file://products/agent-platform/src/agent_service/main.py)

## Dependency Analysis
Observability components have clear dependency relationships:
- Application layers depend on core metrics, observability, and telemetry modules
- Agent kernel depends on AgentScope middleware stack for tool execution observability
- **New**: Model discovery service depends on metrics module for refresh cycle tracking
- **Updated**: Evidence store depends on metrics module for persistence operation tracking
- Health endpoints may depend on service-specific dependencies (databases, caches)
- Kubernetes deployments configure network exposure and probe behavior
- Shared conventions ensure consistency across services

```mermaid
graph LR
App["Application Layer"] --> Metrics["Metrics Module"]
App --> Observability["Observability Module"]
App --> Telemetry["Telemetry Module"]
App --> Discovery["Model Discovery Service"]
Kernel["Agent Kernel"] --> Middleware["Kernel Middleware Stack"]
Kernel --> EvidenceStore["Evidence Store"]
Discovery --> Metrics
EvidenceStore --> Metrics
Middleware --> TracingMW["TracingMiddleware"]
Middleware --> EvidenceMW["ToolEvidenceMiddleware"]
Middleware --> PermissionMW["GatewayPermissionMiddleware"]
Health["Health Endpoints"] --> Dependencies["Service Dependencies"]
K8s["Kubernetes Deployments"] --> App
K8s --> Health
Conventions["Shared Conventions"] --> Metrics
Conventions --> Observability
Conventions --> Telemetry
```

**Updated** Added model discovery service dependency relationships and metrics integration

**Diagram sources**
- [agent-platform app.py](file://products/agent-platform/src/agent_service/app.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [agent-platform kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [identity-broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [tool-gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

**Section sources**
- [agent-platform app.py](file://products/agent-platform/src/agent_service/app.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [identity-broker app.py](file://products/identity-broker/src/identity_service/app.py)
- [tool-gateway app.py](file://products/tool-gateway/src/api_gateway/app.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

## Performance Considerations
- Metrics overhead: Use appropriate bucket sizes for histograms and avoid excessive cardinality in labels
- Logging volume: Implement sampling for high-frequency logs and use structured fields efficiently
- Trace sampling: Configure sampling rates based on performance requirements and cost constraints
- Health checks: Keep health endpoints lightweight and avoid blocking operations
- Resource monitoring: Track CPU, memory, and I/O metrics to identify bottlenecks
- **Updated** Kernel middleware overhead: TracingMiddleware and ToolEvidenceMiddleware add minimal overhead but should be monitored
- **Updated** Evidence store performance: Monitor persistence latency and truncation rates to optimize storage efficiency
- **New**: Model discovery performance: Monitor refresh cycle frequency and provider API call latency

**Model Discovery Performance Guidelines:**
- Track `agent_model_discovery_refreshes_total` to monitor refresh cycle frequency and success rates
- Monitor `agent_model_discovery_models` gauge to validate model catalog updates
- Adjust `model_discovery_refresh_seconds` based on provider API rate limits and model change frequency
- Profile provider API calls during refresh cycles to identify slow responses
- Monitor memory usage for large model catalogs in production environments

**Updated** Enhanced performance guidelines for model discovery and evidence store operations

Capacity planning guidance:
- Monitor request throughput and latency percentiles
- Track error rates and degradation patterns
- Plan scaling based on resource utilization trends
- Set up alerts for critical thresholds and anomalies
- Monitor evidence frame emission rates for high-volume tool usage
- **Updated**: Plan evidence storage capacity based on session growth and retention policies
- **New**: Plan model discovery resources based on number of configured providers and refresh frequency

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolution steps:
- Missing metrics: Verify Prometheus scraping configuration and port exposure
- Incomplete traces: Check trace header propagation and sampling configuration
- High log volume: Adjust log levels and implement structured logging best practices
- Health check failures: Investigate dependency availability and probe configurations
- Performance degradation: Analyze latency histograms and identify slow operations
- **Updated** Kernel tracing issues: Verify AGENTSCOPE_KERNEL_TRACING setting and middleware registration
- **Updated** Evidence frame problems: Check TOOL_EVIDENCE_SINK contextvar and gateway result metadata

**New Model Discovery Troubleshooting:**
- **High refresh failure rates**: Check `agent_model_discovery_refreshes_total{result="live"}` counter and investigate provider API connectivity
- **Stale model catalog**: Verify `agent_model_discovery_models` gauge values match expected model counts
- **Excessive refresh cycles**: Review `model_discovery_refresh_seconds` configuration and adjust based on needs
- **Provider API timeouts**: Check `model_discovery_timeout_seconds` setting and network connectivity to provider endpoints
- **Missing models in catalog**: Verify provider credentials and base URL configuration

**Updated Evidence Store Troubleshooting:**
- **High truncation rates**: Review entry cap settings (`AGENT_EVIDENCE_ENTRY_MAX_CHARS`) and session budget limits (`AGENT_EVIDENCE_SESSION_MAX_BYTES`)
- **Evidence persistence failures**: Check `evidence_store_writes_total{result="error"}` counter and investigate underlying storage connectivity
- **Excessive session budget evictions**: Monitor `evidence_frames_truncated_total{reason="session_budget"}` and adjust session storage limits
- **Missing evidence in replay**: Verify evidence store backend availability and check for connection errors

Debugging workflow:
1. Check service health endpoints for component status
2. Review structured logs with correlation IDs for request flows
3. Examine distributed traces for latency hotspots and errors
4. Analyze metrics for anomalies and trend analysis
5. Scale resources based on observed patterns
6. **Updated** For kernel-level issues, inspect middleware stack composition and evidence frame emission
7. **Updated** For evidence store issues, analyze persistence metrics and truncation patterns
8. **New** For model discovery issues, examine refresh cycle metrics and provider connectivity

**Updated** Enhanced troubleshooting guidance for kernel middleware, evidence store, and model discovery operations

**Section sources**
- [dev-k8s shared observability env](file://shared/platform-ops/gitops/dev-k8s/base/shared/observability.env)
- [agent-platform core observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [agent-platform kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [identity-broker core observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [tool-gateway core observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)

## Conclusion
The agent platform implements comprehensive observability across all services with consistent patterns for metrics, logging, and tracing. The recent enhancement with AgentScope's TracingMiddleware and ToolEvidenceMiddleware provides robust kernel-level observability while maintaining backward compatibility. **The new model discovery metrics provide critical insights into refresh cycle performance and model catalog health, enabling better monitoring of provider connectivity and model availability.** **The enhanced evidence store metrics provide critical insights into persistence operations, enabling better monitoring of evidence storage reliability and performance.** The shared conventions ensure interoperability while individual service implementations provide domain-specific insights. Proper configuration of health checks, dashboards, and alerts enables effective monitoring and troubleshooting of the platform.

**Updated** Enhanced conclusion to reflect new kernel middleware capabilities, evidence store monitoring features, and model discovery observability

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Monitoring Dashboard Setup
Recommended dashboard panels:
- Request rate and latency percentiles per service
- Error rates and failure modes
- Resource utilization (CPU, memory, disk I/O)
- Distributed trace topology and latency breakdowns
- Health check success rates and dependency status
- **Updated** Kernel middleware activity and evidence frame emission rates
- **New**: Model discovery metrics including refresh cycle success rates and published model counts
- **Updated**: Evidence store persistence metrics including write success rates, frame counts, and truncation events

**Model Discovery Dashboard Panels:**
- `agent_model_discovery_refreshes_total` by result type (override/disabled/live/memory/cache/curated) for refresh cycle health
- `agent_model_discovery_models` by provider for model catalog validation
- Provider API call success rates and latency metrics
- Refresh cycle frequency and duration monitoring

**Updated** Enhanced dashboard guidance for model discovery and evidence store operations

Dashboard organization:
- Service-level dashboards for individual components
- Platform-wide dashboards for cross-service visibility
- Alert-focused dashboards for incident response
- **Updated** Kernel observability dashboards for tool execution tracking
- **Updated** Evidence persistence dashboards for storage reliability monitoring
- **New**: Model discovery dashboards for provider connectivity and catalog health

### Alerting Rules Configuration
Critical alerts:
- High error rates (>5% over 5 minutes)
- Latency SLO violations (p99 > threshold)
- Service unavailability (health check failures)
- Resource exhaustion warnings (memory > 80%)
- Queue depth anomalies
- **Updated** Evidence frame emission failures and kernel tracing errors
- **New**: Model discovery refresh failures (`agent_model_discovery_refreshes_total{result="live"} == 0`)
- **New**: Stale model catalogs (no model count updates for extended periods)
- **Updated**: Evidence store persistence failures (`evidence_store_writes_total{result="error"} > 0`)
- **Updated**: Excessive evidence truncation rates (high `evidence_frames_truncated_total` values)

Alert routing:
- PagerDuty integration for critical alerts
- Slack notifications for informational alerts
- Escalation policies based on severity and duration

### Debugging Agent Execution Flows
Step-by-step debugging approach:
1. Enable debug logging for specific components
2. Extract correlation IDs from request logs
3. Follow trace spans through the entire execution path
4. Identify bottlenecks using latency histograms
5. Validate data integrity with structured log fields
6. **Updated** Inspect kernel middleware stack and evidence frame emission
7. **Updated** Analyze evidence store metrics for persistence issues
8. **New**: Monitor model discovery refresh cycles and provider connectivity

**Model Discovery Debugging Steps:**
1. Check `agent_model_discovery_refreshes_total` for refresh cycle success rates
2. Monitor `agent_model_discovery_models` gauge for model catalog updates
3. Verify provider API connectivity and authentication
4. Review refresh interval configuration based on model change frequency
5. Investigate timeout issues with provider API calls

**Updated** Enhanced debugging guidance for kernel middleware, evidence store, and model discovery operations

Performance profiling:
- Use built-in profilers for CPU and memory analysis
- Profile database queries and external API calls
- Monitor garbage collection and memory allocation patterns
- **Updated** Monitor kernel middleware overhead and evidence frame processing
- **Updated** Profile evidence store persistence operations and storage performance
- **New**: Profile model discovery refresh cycles and provider API calls

**Updated** Enhanced performance profiling guidance for all new observability components

**Section sources**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [SPEC-018-kernel-middleware-alignment/spec.md](file://docs/specs/SPEC-018-kernel-middleware-alignment/spec.md)
- [SPEC-025-evidence-persistence-in-transcripts/plan.md](file://docs/specs/SPEC-025-evidence-persistence-in-transcripts/plan.md)
- [SPEC-027-live-model-discovery/spec.md](file://docs/specs/SPEC-027-live-model-discovery/spec.md)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [agent-platform kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
- [agent-platform evidence_store.py](file://products/agent-platform/src/agent_service/services/evidence_store.py)
- [agent-platform model_discovery.py](file://products/agent-platform/src/agent_service/services/model_discovery.py)
- [agent-platform core metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [agent-platform runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)