# Monitoring and Observability

<cite>
**Referenced Files in This Document**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [agent-platform/src/agent_service/core/observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [agent-platform/src/agent_service/core/metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [agent-platform/src/agent_service/app.py](file://products/agent-platform/src/agent_service/app.py)
- [identity-broker/src/identity_service/core/observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [identity-broker/src/identity_service/core/metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [identity-broker/src/identity_service/api/routes/health.py](file://products/identity-broker/src/identity_service/api/routes/health.py)
- [identity-broker/src/identity_service/app.py](file://products/identity-broker/src/identity_service/app.py)
- [tool-gateway/src/tool_gateway/core/observability.py](file://products/tool-gateway/src/tool_gateway/core/observability.py)
- [tool-gateway/src/tool_gateway/core/metrics.py](file://products/tool-gateway/src/tool_gateway/core/metrics.py)
- [tool-gateway/src/tool_gateway/api/routes/health.py](file://products/tool-gateway/src/tool_gateway/api/routes/health.py)
- [tool-gateway/src/tool_gateway/services/gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [tool-gateway/src/tool_gateway/app.py](file://products/tool-gateway/src/tool_gateway/app.py)
- [platform-gateway/src/platform_gateway/core/observability.py](file://products/platform-gateway/src/platform_gateway/core/observability.py)
- [platform-gateway/src/platform_gateway/core/telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [platform-gateway/src/platform_gateway/app.py](file://products/platform-gateway/src/platform_gateway/app.py)
- [shared/shared-contracts/schemas/health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
</cite>

## Update Summary
**Changes Made**
- Enhanced structured logging conventions section to reflect standardized `configure_logging()` implementation across all four services
- Updated distributed tracing documentation with enhanced tool_invoked events from tool gateway
- Added LOG_LEVEL environment variable support details for per-deployment log level configuration
- Updated application startup sequence documentation to include logging configuration calls
- Enhanced audit trail documentation with comprehensive tool invocation tracking
- Updated troubleshooting guide to address missing audit trail events due to uvicorn's default WARNING log level

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
This document provides comprehensive guidance for monitoring and observability across the Luban AIOps Platform. It consolidates the platform's metrics collection strategy using Prometheus, structured logging conventions with standardized logging configuration, distributed tracing implementation with enhanced tool invocation tracking, health check endpoints, readiness/liveness probes configuration, alerting rules, dashboard templates, and incident response procedures. It also includes guidance on custom metric creation, log aggregation, trace correlation, performance monitoring, bottleneck identification, capacity planning, debugging techniques, and troubleshooting workflows using available observability tools.

## Project Structure
Observability is implemented consistently across all four services with standardized logging configuration:
- Agent Platform service exposes metrics, telemetry, and observability utilities with configure_logging() integration
- Identity Broker service implements similar observability primitives and health routes with logging configuration
- Tool Gateway service integrates observability into request handling and policy enforcement with tool_invoked event tracking
- Platform Gateway service provides centralized routing with enhanced observability capabilities
- Shared contracts define observability conventions and schemas used by all services
- Kubernetes manifests configure probes and environment variables for observability components

```mermaid
graph TB
subgraph "Services"
AP["Agent Platform<br/>configure_logging(), metrics.py, telemetry.py"]
IB["Identity Broker<br/>configure_logging(), metrics.py, health.py"]
TG["Tool Gateway<br/>configure_logging(), tool_invoked events, metrics.py"]
PG["Platform Gateway<br/>configure_logging(), telemetry.py"]
end
subgraph "Shared Contracts"
OC["Observability Conventions<br/>LOG_LEVEL support, structured logging"]
HR["Health Response Schema<br/>health-response.schema.json"]
end
subgraph "Kubernetes"
OBS_ENV["Observability Env<br/>LOG_LEVEL + OTEL config"]
AP_DEP["Agent Service Deployment<br/>probes + env"]
IB_DEP["Identity Service Deployment<br/>probes + env"]
TG_DEP["Tool Gateway Deployment<br/>probes + env"]
PG_DEP["Platform Gateway Deployment<br/>probes + env"]
end
AP --> OC
IB --> OC
TG --> OC
PG --> OC
IB --> HR
TG --> HR
AP --> AP_DEP
IB --> IB_DEP
TG --> TG_DEP
PG --> PG_DEP
AP_DEP --> OBS_ENV
IB_DEP --> OBS_ENV
TG_DEP --> OBS_ENV
PG_DEP --> OBS_ENV
```

**Diagram sources**
- [agent-platform/src/agent_service/core/observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [identity-broker/src/identity_service/core/observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [tool-gateway/src/tool_gateway/core/observability.py](file://products/tool-gateway/src/tool_gateway/core/observability.py)
- [platform-gateway/src/platform_gateway/core/observability.py](file://products/platform-gateway/src/platform_gateway/core/observability.py)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [shared/shared-contracts/schemas/health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

## Core Components
- Metrics Collection Strategy:
  - Each service exposes a Prometheus-compatible endpoint via its metrics module.
  - Standardized metric naming and labels are enforced through shared conventions.
- **Updated** Structured Logging Conventions:
  - All services now call `configure_logging()` at startup to raise root logger from WARNING to INFO level
  - LOG_LEVEL environment variable supports per-deployment log level overrides (default: INFO)
  - Logs include consistent fields such as service name, version, request ID, and correlation IDs
  - Audit trail events (http_request, tool_invoked, policy decisions) are captured at INFO level
- Distributed Tracing Implementation:
  - Telemetry modules propagate trace context across service boundaries
  - Enhanced tool invocation tracking with tool_invoked events in tool gateway
  - Spans are created for key operations (HTTP requests, tool invocations, policy checks)
- Health Check Endpoints:
  - Services expose health endpoints conforming to shared schema definitions.
  - Readiness and liveness probes are configured in Kubernetes deployments.
- Alerting Rules and Dashboards:
  - Alerting rules target key SLOs derived from metrics.
  - Dashboard templates visualize core KPIs and operational health.

**Section sources**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

## Architecture Overview
The observability architecture centers around standardized libraries and shared contracts with enhanced logging configuration:
- Services implement metrics, telemetry, and observability helpers with unified logging setup
- Application startup sequences call configure_logging() before FastAPI initialization
- Kubernetes configurations inject environment variables and define probes
- Prometheus scrapes metrics; logs are aggregated centrally; traces are exported to a collector

```mermaid
sequenceDiagram
participant Client as "Client"
participant Gateway as "Tool Gateway"
participant Agent as "Agent Platform"
participant Identity as "Identity Broker"
participant Prometheus as "Prometheus"
participant Logger as "Log Aggregator"
participant Tracer as "Tracing Collector"
Client->>Gateway : HTTP Request
Gateway->>Gateway : configure_logging() + Create Span (trace_id)
Gateway->>Identity : Auth Call (propagate trace_id)
Identity-->>Gateway : Auth Result
Gateway->>Agent : Agent Call (propagate trace_id)
Agent-->>Gateway : Response
Gateway->>Gateway : log_event("tool_invoked")
Gateway-->>Client : Response
Gateway->>Prometheus : Record metrics
Agent->>Prometheus : Record metrics
Identity->>Prometheus : Record metrics
Gateway->>Logger : Structured logs with trace_id
Agent->>Logger : Structured logs with trace_id
Identity->>Logger : Structured logs with trace_id
Gateway->>Tracer : Export spans
Agent->>Tracer : Export spans
Identity->>Tracer : Export spans
```

**Diagram sources**
- [tool-gateway/src/tool_gateway/services/gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [tool-gateway/src/tool_gateway/app.py](file://products/tool-gateway/src/tool_gateway/app.py)
- [agent-platform/src/agent_service/app.py](file://products/agent-platform/src/agent_service/app.py)
- [identity-broker/src/identity_service/app.py](file://products/identity-broker/src/identity_service/app.py)
- [platform-gateway/src/platform_gateway/app.py](file://products/platform-gateway/src/platform_gateway/app.py)

## Detailed Component Analysis

### Metrics Collection Strategy
- Each service defines metrics in a dedicated module:
  - Agent Platform metrics module registers counters, histograms, and gauges.
  - Identity Broker metrics module tracks authentication flows and token operations.
  - Tool Gateway metrics module records API latency, throughput, and policy decisions.
  - Platform Gateway metrics module handles routing and policy enforcement metrics.
- Metric naming follows shared conventions to ensure consistency across services.
- Labels include service, route, method, status code, and operation where applicable.

```mermaid
classDiagram
class MetricsModule {
+register_counter(name, help, labels)
+register_histogram(name, help, labels)
+register_gauge(name, help, labels)
+increment_counter(name, labels, value)
+observe_histogram(name, labels, value)
+set_gauge(name, labels, value)
}
class AgentMetrics {
+request_count
+latency_histogram
+error_rate
}
class IdentityMetrics {
+auth_success_count
+auth_failure_count
+token_duration_histogram
}
class GatewayMetrics {
+route_latency_histogram
+policy_decision_count
+tool_invocation_count
}
class PlatformGatewayMetrics {
+routing_latency
+policy_checks_total
+delegation_requests
}
MetricsModule <|-- AgentMetrics
MetricsModule <|-- IdentityMetrics
MetricsModule <|-- GatewayMetrics
MetricsModule <|-- PlatformGatewayMetrics
```

**Diagram sources**
- [agent-platform/src/agent_service/core/metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [identity-broker/src/identity_service/core/metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [tool-gateway/src/tool_gateway/core/metrics.py](file://products/tool-gateway/src/tool_gateway/core/metrics.py)

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [agent-platform/src/agent_service/core/metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [identity-broker/src/identity_service/core/metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [tool-gateway/src/tool_gateway/core/metrics.py](file://products/tool-gateway/src/tool_gateway/core/metrics.py)

### **Updated** Structured Logging Conventions
- All services now implement standardized logging configuration:
  - `configure_logging()` raises root logger from WARNING to INFO level at startup
  - LOG_LEVEL environment variable supports per-deployment overrides (default: INFO)
  - Audit trail events (http_request, tool_invoked, policy decisions) are captured at INFO level
  - Structured logs include consistent fields: service_name, version, timestamp, level, message, request_id, trace_id, user_id, operation
- Log aggregation pipelines parse these fields to support filtering and correlation.
- Sensitive data is excluded from logs per security policies.

```mermaid
flowchart TD
Start(["Service Startup"]) --> ConfigureLogging["configure_logging()<br/>LOG_LEVEL env var"]
ConfigureLogging --> BuildContext["Build Context<br/>service_name, version, request_id, trace_id"]
BuildContext --> EmitLog["Emit Structured Log<br/>level, message, fields"]
EmitLog --> Aggregate["Aggregate Logs<br/>centralized storage"]
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
- Telemetry modules create spans for critical operations:
  - HTTP request lifecycle, policy evaluation, tool invocation, agent execution
  - Enhanced tool invocation tracking with tool_invoked events
- Trace context is propagated across service calls using standard headers.
- Spans are exported to a tracing backend for visualization and analysis.
- OpenTelemetry push pipeline is opt-in via OTEL_ENABLED environment variable.

```mermaid
sequenceDiagram
participant Caller as "Caller"
participant Gateway as "Tool Gateway"
participant Agent as "Agent Platform"
participant Identity as "Identity Broker"
participant Tracer as "Tracing Backend"
Caller->>Gateway : HTTP Request (trace_id)
Gateway->>Gateway : StartSpan("http.request")
Gateway->>Identity : Auth Call (propagate trace_id)
Identity->>Identity : StartSpan("auth.check")
Identity-->>Gateway : Auth Result
Gateway->>Agent : Agent Call (propagate trace_id)
Agent->>Agent : StartSpan("agent.execute")
Agent-->>Gateway : Response
Gateway->>Gateway : log_event("tool_invoked")
Gateway->>Tracer : ExportSpans()
Identity->>Tracer : ExportSpans()
Agent->>Tracer : ExportSpans()
```

**Diagram sources**
- [tool-gateway/src/tool_gateway/services/gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [platform-gateway/src/platform_gateway/core/telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)

**Section sources**
- [agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [tool-gateway/src/tool_gateway/services/gateway_service.py](file://products/tool-gateway/src/tool_gateway/services/gateway_service.py)
- [platform-gateway/src/platform_gateway/core/telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)

### Health Check Endpoints, Readiness Probes, and Liveness Probes
- Health endpoints return responses conforming to the shared health schema.
- Readiness probes verify dependencies (e.g., Redis, external APIs).
- Liveness probes confirm process health and internal state.
- Kubernetes deployments configure probe paths, intervals, and thresholds.

```mermaid
flowchart TD
ProbeStart["Kubelet Probe"] --> Type{"Probe Type?"}
Type --> |Readiness| CheckDeps["Check Dependencies<br/>DB, Cache, External APIs"]
Type --> |Liveness| CheckProcess["Check Process State<br/>Internal Health"]
CheckDeps --> Ready{"Ready?"}
CheckProcess --> Alive{"Alive?"}
Ready --> |Yes| ReturnOK["Return 200 OK"]
Ready --> |No| ReturnFail["Return 503 Unavailable"]
Alive --> |Yes| ReturnOK
Alive --> |No| ReturnFail
ReturnOK --> End(["Healthy"])
ReturnFail --> End(["Unhealthy"])
```

**Diagram sources**
- [identity-broker/src/identity_service/api/routes/health.py](file://products/identity-broker/src/identity_service/api/routes/health.py)
- [tool-gateway/src/tool_gateway/api/routes/health.py](file://products/tool-gateway/src/tool_gateway/api/routes/health.py)
- [shared/shared-contracts/schemas/health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)

**Section sources**
- [shared/shared-contracts/schemas/health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)
- [identity-broker/src/identity_service/api/routes/health.py](file://products/identity-broker/src/identity_service/api/routes/health.py)
- [tool-gateway/src/tool_gateway/api/routes/health.py](file://products/tool-gateway/src/tool_gateway/api/routes/health.py)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)

### Alerting Rules and Dashboard Templates
- Alerting rules are defined based on key metrics:
  - High error rates, latency spikes, resource exhaustion, dependency failures.
  - Tool invocation failures and redaction overflow events.
- Dashboard templates visualize:
  - Request throughput, latency percentiles, error rates, trace spans, and system resources.
  - Tool invocation patterns and audit trail events.
- Alerts trigger notifications and runbooks for incident response.

```mermaid
graph TB
Metrics["Prometheus Metrics"] --> Rules["Alerting Rules"]
Rules --> Alerts["Alertmanager Notifications"]
Alerts --> Runbook["Incident Runbook"]
Metrics --> Dashboards["Grafana Dashboards"]
Dashboards --> Ops["Operations Team"]
```

**Section sources**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)

### Custom Metric Creation, Log Aggregation, and Trace Correlation
- Custom metrics should adhere to shared naming and labeling conventions.
- Logs must include correlation identifiers (request_id, trace_id) for cross-service correlation.
- Traces should be exported with consistent span names and attributes.
- Tool invocation events provide enhanced audit trail for debugging and compliance.

```mermaid
flowchart TD
DefineMetric["Define Custom Metric<br/>name, help, labels"] --> Register["Register with Metrics Module"]
Register --> Emit["Emit Metric Values"]
Emit --> Scrape["Prometheus Scrapes"]
Scrape --> Query["Query & Visualize"]
EmitLog["Emit Structured Log<br/>with correlation IDs"] --> Aggregate["Log Aggregator"]
Aggregate --> Search["Search & Filter"]
ExportTrace["Export Spans<br/>with trace_id"] --> TracingBackend["Tracing Backend"]
TracingBackend --> Correlate["Correlate Across Services"]
```

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

## Dependency Analysis
Observability components depend on shared contracts and Kubernetes configurations:
- Services rely on shared observability conventions for consistency.
- Deployments configure probes and environment variables for observability.
- Prometheus scrapes metrics from each service's endpoint.
- All services call configure_logging() during startup for consistent log levels.

```mermaid
graph TB
OC["Observability Conventions"] --> AP_METRICS["Agent Platform Metrics"]
OC --> IB_METRICS["Identity Broker Metrics"]
OC --> TG_METRICS["Tool Gateway Metrics"]
OC --> PG_METRICS["Platform Gateway Metrics"]
ENV["Observability Env<br/>LOG_LEVEL + OTEL config"] --> AP_DEP["Agent Deployment"]
ENV --> IB_DEP["Identity Deployment"]
ENV --> TG_DEP["Gateway Deployment"]
ENV --> PG_DEP["Platform Gateway Deployment"]
AP_METRICS --> PROM["Prometheus"]
IB_METRICS --> PROM
TG_METRICS --> PROM
PG_METRICS --> PROM
```

**Diagram sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

## Performance Considerations
- Monitor latency percentiles and error rates to identify bottlenecks.
- Use histograms for request durations and gauge metrics for resource utilization.
- Correlate traces with metrics to pinpoint slow or failing operations.
- Capacity planning should be informed by trends in throughput, latency, and error rates.
- Tool invocation patterns can reveal performance issues in external integrations.

## Troubleshooting Guide
- Use structured logs with correlation IDs to trace requests across services.
- Inspect Prometheus metrics for anomalies in latency, errors, and resource usage.
- Review traces to understand call chains and identify failures.
- Validate health endpoints and probe configurations when services are unhealthy.
- **Updated** Check LOG_LEVEL environment variable if audit trail events are missing - uvicorn defaults to WARNING level which discards INFO-level structured events like http_request and tool_invoked.
- **Updated** Investigate tool_invoked events for tool-specific issues and redaction problems.
- **Updated** Verify that configure_logging() is called during service startup to ensure proper log level configuration.

**Section sources**
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [identity-broker/src/identity_service/api/routes/health.py](file://products/identity-broker/src/identity_service/api/routes/health.py)
- [tool-gateway/src/tool_gateway/api/routes/health.py](file://products/tool-gateway/src/tool_gateway/api/routes/health.py)

## Conclusion
The Luban AIOps Platform implements a robust observability framework centered on standardized metrics, enhanced structured logging with configurable log levels, and distributed tracing with tool invocation tracking. By adhering to shared conventions, calling configure_logging() at startup, and configuring Kubernetes probes appropriately, operators can effectively monitor, diagnose, and respond to incidents while planning for future capacity needs. The enhanced audit trail with tool_invoked events provides comprehensive visibility into tool execution patterns and potential security concerns.

## Appendices
- Reference specifications for observability baseline and conventions.
- Kubernetes deployment examples for probes and environment variables.
- Health response schema for consistent health checks.
- LOG_LEVEL environment variable configuration for different environments.

**Section sources**
- [SPEC-005-observability-baseline/spec.md](file://docs/specs/SPEC-005-observability-baseline/spec.md)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [shared/shared-contracts/schemas/health-response.schema.json](file://shared/shared-contracts/schemas/health-response.schema.json)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)