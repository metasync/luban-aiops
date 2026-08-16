# Configuration and Environment Setup

<cite>
**Referenced Files in This Document**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive OpenTelemetry configuration documentation including OTEL_ENABLED, OTEL_EXPORTER_OTLP_ENDPOINT, and authentication headers
- Documented service-specific runtime secret configurations for OpenObserve integration
- Updated observability conventions with opt-in OTel push pipeline details
- Enhanced security guidance for OTLP authentication header management
- Added troubleshooting section for OpenTelemetry setup and connectivity issues

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
This document explains how the Tool Gateway Service manages configuration and environment setup across layers: environment variables, configuration files, and runtime overrides. It details available options, defaults, validation rules, and deployment-specific settings for development, staging, and production. It also provides examples for Docker and Kubernetes (ConfigMaps/Secrets), and outlines security best practices for secrets management and consistent configuration across environments.

**Updated** Enhanced documentation now includes comprehensive OpenTelemetry configuration support with opt-in telemetry push pipeline, OpenObserve integration, and secure authentication header management through runtime secrets.

## Project Structure
The Tool Gateway Service is implemented under products/tool-gateway with its core configuration logic in the core module. Deployment manifests and environment templates are maintained under shared/platform-ops/gitops/dev-k8s/base/tool-gateway. The service image is built using a Dockerfile, and dependencies are declared in pyproject.toml. The service includes integrated OpenTelemetry support for traces, metrics, and logs export to OpenObserve backend.

```mermaid
graph TB
subgraph "Tool Gateway Service"
A["src/tool_gateway/core/config.py"]
B["src/tool_gateway/core/runtime.py"]
C["src/tool_gateway/core/telemetry.py"]
D["src/tool_gateway/policies/policy-default.yaml"]
E["Dockerfile"]
F["pyproject.toml"]
end
subgraph "OpenTelemetry Infrastructure"
G["OTEL_ENABLED"]
H["OTEL_EXPORTER_OTLP_ENDPOINT"]
I["OTEL_EXPORTER_OTLP_HEADERS"]
J["OTEL_SERVICE_NAME"]
K["OpenObserve Backend"]
end
subgraph "Kubernetes Base (dev)"
L["base/tool-gateway/runtime-config.env"]
M["base/tool-gateway/tool-gateway-deployment.yaml"]
N["base/shared/runtime.env"]
O["base/tool-gateway/runtime-secrets.example.env"]
end
A --> L
B --> M
C --> G
C --> H
C --> I
C --> J
L --> M
N --> M
O --> M
D --> A
E --> A
F --> E
G --> K
H --> K
I --> K
J --> K
```

**Diagram sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)

## Core Components
- Configuration loader and model: centralizes environment variable parsing, file-based configuration, and runtime overrides; exposes validated configuration to the application.
- Runtime settings: handles service binding configuration with robust port resolution that ignores Kubernetes service-link formats.
- OpenTelemetry telemetry: opt-in push pipeline for traces, metrics, and logs export via OTLP HTTP/protobuf to configured backend.
- Policy engine configuration: loads default policy definitions from YAML and supports environment-driven overrides.
- Containerization and dependency management: Dockerfile defines runtime environment; pyproject.toml declares Python dependencies used by the gateway.

Key responsibilities:
- Provide a single source of truth for configuration via typed models.
- Enforce validation rules and provide clear error messages on misconfiguration.
- Support layered precedence: defaults < config files < environment variables < runtime overrides.
- Handle DNS-based service discovery with proper fallback mechanisms.
- Ignore Kubernetes service-link environment variables to prevent conflicts.
- Manage opt-in OpenTelemetry telemetry with fail-open behavior and secure authentication.

**Updated** Enhanced core components to include comprehensive OpenTelemetry support with opt-in telemetry push pipeline, secure authentication header management, and integration with OpenObserve backend.

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)

## Architecture Overview
The configuration system follows a layered approach with enhanced observability capabilities:
- Defaults: defined in code or default YAML policies.
- Config files: loaded from container filesystem or mounted volumes.
- Environment variables: injected at runtime via platform orchestration (e.g., Kubernetes).
- Runtime overrides: applied programmatically during startup or request processing.
- DNS-based service discovery: services communicate via Kubernetes DNS names instead of injected environment variables.
- Opt-in OpenTelemetry telemetry: traces, metrics, and logs exported via OTLP HTTP/protobuf to configured backend.

```mermaid
sequenceDiagram
participant App as "Tool Gateway App"
participant Config as "Configuration Loader"
participant Env as "Environment Variables"
participant File as "Config Files"
participant DNS as "Kubernetes DNS"
participant Service as "Identity Service"
participant OTel as "OpenTelemetry Pipeline"
participant Backend as "OpenObserve Backend"
App->>Config : Initialize configuration
Config->>Env : Read environment variables
Config->>File : Load configuration files
Config->>Config : Merge layers with precedence
Config-->>App : Validated configuration
App->>DNS : Resolve service name (identity-service)
DNS-->>App : Service IP address
App->>Service : Connect via DNS name
Service-->>App : Service response
App->>OTel : Check OTEL_ENABLED flag
OTel->>Backend : Export traces/metrics/logs via OTLP
Backend-->>OTel : Acknowledge receipt
App->>App : Continue normal operation
```

**Diagram sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)

## Detailed Component Analysis

### Configuration Loader and Model
- Purpose: Parse and validate configuration from multiple layers and expose it consistently.
- Precedence: Defaults < Config files < Environment variables < Runtime overrides.
- Validation: Type checks, required fields, range constraints, and cross-field validations.
- Error handling: Aggregates validation errors and surfaces actionable messages.
- Service discovery: Uses DNS-based resolution for inter-service communication.

**Updated** Enhanced to support DNS-based service discovery, improved environment variable handling, and integration with OpenTelemetry configuration management.

```mermaid
flowchart TD
Start(["Start"]) --> LoadDefaults["Load defaults"]
LoadDefaults --> LoadFiles["Load config files"]
LoadFiles --> LoadEnv["Load environment variables"]
LoadEnv --> Merge["Merge layers<br/>with precedence"]
Merge --> Validate["Validate merged config"]
Validate --> Valid{"Valid?"}
Valid --> |No| Errors["Collect and return validation errors"]
Valid --> |Yes| Expose["Expose validated config"]
Errors --> End(["End"])
Expose --> End
```

**Diagram sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)

### Runtime Settings and Port Resolution
- Purpose: Handle service binding configuration with robust port resolution.
- Port resolution: Ignores Kubernetes service-link format (`tcp://IP:PORT`) and extracts numeric ports.
- Default behavior: Falls back to default host and port when environment variables are not set.
- Development safety: Prevents conflicts between manual configuration and automatic service-link injection.

**New Section** Enhanced runtime settings with intelligent port resolution that handles Kubernetes service-link formats gracefully.

```mermaid
flowchart TD
PortValue{"Port Value<br/>Available?"}
ParseInt{"Can Parse<br/>as Integer?"}
UseDefault["Use Default<br/>Port"]
ExtractPort["Extract Numeric<br/>Port"]
Success["Resolved Port"]
PortValue --> |No| UseDefault
PortValue --> |Yes| ParseInt
ParseInt --> |No| ExtractPort
ParseInt --> |Yes| Success
```

**Diagram sources**
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)

**Section sources**
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)

### OpenTelemetry Telemetry Pipeline
- Purpose: Opt-in telemetry push pipeline for traces, metrics, and logs export via OTLP HTTP/protobuf.
- Gating: Controlled by `OTEL_ENABLED` environment variable (default false); when disabled, no overhead.
- Authentication: Uses `OTEL_EXPORTER_OTLP_HEADERS` for Basic authentication to OpenObserve backend.
- Fail-open: Setup errors are logged but never raised into request path; exporters drop telemetry on failure.
- Log bridge: Mirrors structured logs to OTLP log pipeline while maintaining stdout as source of truth.
- Service naming: Uses `OTEL_SERVICE_NAME` for resource identification, defaults to service metadata.

**New Section** Comprehensive OpenTelemetry support with opt-in telemetry pipeline, secure authentication, and OpenObserve integration.

```mermaid
flowchart TD
Enabled{"OTEL_ENABLED<br/>= true?"}
Setup["Initialize Providers"]
Traces["Tracer Provider"]
Metrics["Meter Provider"]
Logs["Logger Provider"]
Exporters["OTLP Exporters"]
Backend["OpenObserve Backend"]
FailOpen["Fail Open on Error"]
Enabled --> |No| Skip["Skip Initialization"]
Enabled --> |Yes| Setup
Setup --> Traces
Setup --> Metrics
Setup --> Logs
Traces --> Exporters
Metrics --> Exporters
Logs --> Exporters
Exporters --> Backend
Backend --> |Error| FailOpen
FailOpen --> Continue["Continue Service Operation"]
Skip --> Continue
```

**Diagram sources**
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

**Section sources**
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

### DNS-Based Service Discovery
- Purpose: Enable reliable inter-service communication using Kubernetes DNS names.
- Configuration: Service endpoints configured via environment variables pointing to DNS names.
- Benefits: Eliminates service-link conflicts, improves reliability, and simplifies configuration.
- Implementation: Services resolve DNS names like `identity-service` to their cluster IPs.

**New Section** Comprehensive DNS-based service discovery replacing Kubernetes service-link injection.

```mermaid
graph LR
Client["Tool Gateway Pod"] --> DNS["Kubernetes DNS Server"]
DNS --> Identity["identity-service:8000"]
Identity --> Resolver["DNS Resolution"]
Resolver --> IP["Service IP Address"]
IP --> Client
```

**Diagram sources**
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

**Section sources**
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

### Policy Engine Configuration
- Default policy: Loaded from a YAML file defining baseline rules and behaviors.
- Overrides: Can be adjusted via environment variables or mounted config files depending on implementation.
- Usage: Provides decision context for tool invocation, access control, and rate limiting.

```mermaid
classDiagram
class PolicyEngine {
+load_default_policy()
+apply_overrides(env_vars)
+evaluate(context) Decision
}
class PolicyDefault {
+rules : list
+defaults : map
}
PolicyEngine --> PolicyDefault : "loads"
```

**Diagram sources**
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)

**Section sources**
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)

### Docker Configuration
- Image build: Defines base image, working directory, and dependency installation.
- Entrypoint: Runs the Tool Gateway Service with environment variables passed through.
- Best practices: Use multi-stage builds, pin versions, minimize attack surface.

```mermaid
flowchart TD
Build["Build Stage"] --> Install["Install dependencies"]
Install --> Copy["Copy application code"]
Copy --> Entrypoint["Set entrypoint"]
Entrypoint --> Run["Run service with env vars"]
```

**Diagram sources**
- [Dockerfile](file://products/tool-gateway/Dockerfile)

**Section sources**
- [Dockerfile](file://products/tool-gateway/Dockerfile)

### Kubernetes Deployment and ConfigMaps
- Deployment manifest: Mounts environment variables and config files into the pod.
- ConfigMap: Holds non-sensitive configuration values including service endpoints.
- Service discovery: Uses DNS names for inter-service communication.
- Environment injection: Maps ConfigMap entries to environment variables consumed by the configuration loader.
- Secrets management: Handles sensitive data like OpenTelemetry authentication headers separately from ConfigMaps.

**Updated** Enhanced deployment configuration with DNS-based service discovery, disabled service links, comprehensive OpenTelemetry integration, and secure authentication header management.

```mermaid
graph TB
CM["ConfigMap"] --> ENV["Environment Variables"]
ENV --> POD["Pod Spec"]
POD --> APP["Tool Gateway App"]
APP --> CFG["Configuration Loader"]
DNS["Kubernetes DNS"] --> SVC["Service Names"]
SVC --> APP
Secrets["Secrets"] --> AuthHeaders["OTEL_EXPORTER_OTLP_HEADERS"]
AuthHeaders --> APP
OTelEnv["OTEL_* Variables"] --> APP
APP --> OTel["OpenTelemetry Pipeline"]
OTel --> Backend["OpenObserve Backend"]
```

**Diagram sources**
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)

**Section sources**
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)

### Dependency Management
- Python dependencies: Declared in pyproject.toml for reproducible builds.
- Lock file: Ensures deterministic dependency resolution.
- Best practices: Pin versions, separate dev and prod dependencies, audit regularly.

**Section sources**
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)

## Dependency Analysis
Configuration components depend on environment variables and files, while the runtime settings handle DNS-based service discovery. The Docker image encapsulates runtime dependencies, and Kubernetes manifests inject configuration at deployment time. OpenTelemetry integration adds opt-in telemetry capabilities with secure authentication and fail-open behavior.

**Updated** Added dependencies for DNS-based service discovery, enhanced environment variable handling, comprehensive OpenTelemetry integration with opt-in telemetry pipeline, and secure authentication header management.

```mermaid
graph TB
CFG["config.py"] --> ENV["Environment Variables"]
CFG --> FILE["Config Files"]
RT["runtime.py"] --> PORT["Port Resolution"]
DNS["Kubernetes DNS"] --> SVC["Service Discovery"]
DOCKER["Dockerfile"] --> RUNTIME["Runtime Dependencies"]
K8S["tool-gateway-deployment.yaml"] --> INJECT["Env Injection"]
INJECT --> CFG
SVC --> RT
OTel["telemetry.py"] --> OTEL_ENV["OTEL_* Variables"]
OTEL_ENV --> Backend["OpenObserve Backend"]
Secrets["runtime-secrets.env"] --> AuthHeaders["OTEL_EXPORTER_OTLP_HEADERS"]
AuthHeaders --> OTel
```

**Diagram sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

## Performance Considerations
- Minimize configuration lookups by caching validated configuration at startup.
- Avoid heavy I/O during request processing; pre-load policies and dependencies.
- Use efficient serialization formats for configuration files where applicable.
- Monitor configuration-related metrics and errors to detect misconfigurations early.
- Leverage Kubernetes DNS caching for improved service discovery performance.
- Optimize port resolution to avoid unnecessary string parsing operations.
- OpenTelemetry telemetry is opt-in and fails open to avoid performance impact when disabled.
- Batch processors in OpenTelemetry reduce network overhead for telemetry export.
- Configure appropriate OpenTelemetry exporter timeouts and batch sizes for optimal performance.
- Monitor OpenTelemetry setup failures and exporter errors without affecting service operation.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Missing environment variables: Ensure all required variables are set in the deployment manifest or environment.
- Invalid configuration values: Check types, ranges, and cross-field constraints; review validation error messages.
- Policy loading failures: Verify YAML syntax and structure; ensure paths are correct and accessible.
- Secrets not mounted: Confirm Secret objects exist and are referenced correctly in the deployment.
- DNS resolution failures: Verify service names match Kubernetes Service resources and check network policies.
- Service link conflicts: Ensure `enableServiceLinks: false` is set in all deployment manifests.
- Port resolution issues: Check that port values are numeric and not in Kubernetes service-link format.
- Inter-service communication failures: Verify DNS names are resolvable and services are running.
- **New**: OpenTelemetry setup failures: Check OTEL_ENABLED flag and verify endpoint connectivity; setup errors are logged but don't affect service operation.
- **New**: OpenTelemetry authentication failures: Verify OTEL_EXPORTER_OTLP_HEADERS contains valid Basic auth credentials; 401 responses indicate authentication issues.
- **New**: OpenTelemetry endpoint connectivity: Ensure OTEL_EXPORTER_OTLP_ENDPOINT points to reachable OpenObserve backend; unreachable endpoints cause exporter failures but don't break service.
- **New**: OpenTelemetry service naming: Verify OTEL_SERVICE_NAME is set appropriately for trace correlation; defaults to service metadata if not specified.
- **New**: Log bridge issues: When OpenTelemetry is enabled, structured logs are mirrored to OTLP; ensure log level is set to INFO for proper audit trail.

**Updated** Added troubleshooting guidance for DNS-based service discovery, service link issues, comprehensive OpenTelemetry integration problems, authentication failures, and endpoint connectivity issues.

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

## Conclusion
The Tool Gateway Service employs a robust, layered configuration system that integrates environment variables, configuration files, and runtime overrides with strict validation. By following the outlined best practices for Docker and Kubernetes deployments, teams can maintain secure, consistent configurations across environments while ensuring reliability and performance. The architectural shift to DNS-based service discovery eliminates service-link conflicts and provides more reliable inter-service communication patterns. The addition of opt-in OpenTelemetry telemetry enables comprehensive observability with traces, metrics, and logs export to OpenObserve backend, featuring secure authentication header management and fail-open behavior that ensures service continuity even when telemetry infrastructure is unavailable.

**Updated** Enhanced conclusion reflecting the architectural improvements in service discovery, environment variable handling, comprehensive OpenTelemetry integration with opt-in telemetry pipeline, and secure authentication capabilities.

## Appendices

### Environment-Specific Settings
- Development: Enable verbose logging, relaxed validation, local secrets, optional redaction disablement, memory-based storage, local git sources without authentication, enable OpenTelemetry with local OpenObserve instance.
- Staging: Mirror production settings with test data and limited scope, enable full redaction, PostgreSQL-backed storage, private repository access with test tokens, configure OpenTelemetry with staging backend.
- Production: Strict validation, minimal logging, centralized secret management, mandatory workload identity, optimized sync intervals, secure private repository authentication, configure OpenTelemetry with production backend and proper authentication.

**Updated** Added guidance for DNS-based service discovery configuration, OpenTelemetry telemetry setup across environments, and secure authentication header management.

[No sources needed since this section provides general guidance]

### Security and Secrets Management
- Store secrets in Kubernetes Secrets or external vaults; never hardcode.
- Rotate secrets regularly and audit access logs.
- Use least privilege principles for service accounts and RBAC.
- Prefer workload identity over static credentials in production environments.
- Configure appropriate redaction sensitivity levels based on data classification.
- Monitor redaction metrics and workload identity authentication attempts.
- Use DNS-based service discovery to avoid exposing service endpoints in environment variables.
- Disable service links to prevent accidental exposure of internal service information.
- Secure Skills Hub PostgreSQL connections with proper authentication and network policies.
- Validate Skills Hub source configurations to prevent injection attacks through malicious skill sources.
- Protect SKILLS_GIT_TOKENS secrets with proper Kubernetes Secret management and rotation policies.
- Implement token scoping for git repositories to limit access to minimum required permissions.
- Monitor git authentication attempts and implement rate limiting for failed authentication attempts.
- Validate git source paths to prevent path traversal attacks and ensure only safe subdirectories are selected.
- **New**: Secure OpenTelemetry authentication headers using Kubernetes Secrets; never commit OTEL_EXPORTER_OTLP_HEADERS to version control.
- **New**: Rotate OpenTelemetry authentication credentials regularly and monitor for unauthorized access attempts.
- **New**: Use separate OpenTelemetry endpoints and authentication for different environments to prevent cross-environment telemetry leakage.
- **New**: Monitor OpenTelemetry exporter failures and authentication errors without exposing sensitive credential information in logs.

**Updated** Enhanced security guidance with DNS-based service discovery best practices, comprehensive OpenTelemetry security considerations, and secure authentication header management practices.

[No sources needed since this section provides general guidance]

### Complete Environment Variables Reference
**Updated** Comprehensive reference including DNS-based service discovery variables, OpenTelemetry configuration, and authentication management.

#### Core Configuration
- `AGENT_SERVICE_URL`: Agent service endpoint URL (DNS-based)
- `IDENTITY_SERVICE_URL`: Identity broker service endpoint URL (DNS-based)
- `IDENTITY_JWKS_URL`: Identity service JWKS endpoint
- `IDENTITY_JWCS_CACHE_SECONDS`: JWCS cache duration (default: 300)
- `IDENTITY_TOKEN_ISSUER`: JWT issuer claim (default: "luban-identity-broker")
- `GATEWAY_TOKEN_AUDIENCE`: Token audience (default: "tool-gateway")
- `GATEWAY_DELEGATION_AUDIENCE`: Delegation audience (default: "tool-gateway")

#### Runtime Configuration
- `GATEWAY_HOST`: Service bind host (default: 0.0.0.0)
- `GATEWAY_PORT`: Service bind port (numeric only, service-link format ignored)

#### Operational Configuration
- `GATEWAY_REQUIRE_AUTH`: Require authentication (default: true)
- `GATEWAY_K8S_ENABLED`: Enable Kubernetes integration (default: false)
- `GATEWAY_K8S_NAMESPACE`: Kubernetes namespace
- `GATEWAY_POLICY_PATH`: Policy file path
- `CHAT_RESPONSE_TIMEOUT_SECONDS`: Chat response timeout (default: 30)

#### Service Discovery Configuration
- `IDENTITY_SERVICE_URL`: Identity service URL using DNS names (e.g., http://identity-service:8000)
- `AGENT_SERVICE_URL`: Agent service URL using DNS names (e.g., http://agent-service:8000)

#### OpenTelemetry Configuration
- `OTEL_ENABLED`: Enable/disable OpenTelemetry push pipeline (default: false)
- `OTEL_EXPORTER_OTLP_ENDPOINT`: OTLP HTTP endpoint for OpenObserve (e.g., http://openobserve-router:5080/api/default)
- `OTEL_EXPORTER_OTLP_HEADERS`: Authentication headers for OTLP export (Basic auth for OpenObserve)
- `OTEL_SERVICE_NAME`: Service name for telemetry resource identification (defaults to service metadata)

#### OpenTelemetry Authentication
- `OTEL_EXPORTER_OTLP_HEADERS`: Contains `Authorization=Basic <base64(email:password)>` for OpenObserve authentication
- Provisioned via runtime-secrets Secret and managed by sync-otel-secrets.sh script
- Never committed to version control; always stored in Kubernetes Secrets

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)

### OpenTelemetry Setup Guide
**New Section** Step-by-step guide for configuring OpenTelemetry telemetry pipeline with OpenObserve integration.

#### Prerequisites
- OpenObserve backend deployed and accessible
- Basic authentication credentials for OpenObserve ingest endpoint
- Kubernetes cluster with network access to OpenObserve service
- Proper secrets management for authentication headers

#### Configuration Steps
1. Set `OTEL_ENABLED=true` in shared runtime configuration
2. Configure `OTEL_EXPORTER_OTLP_ENDPOINT` to point to OpenObserve ingest endpoint
3. Generate Basic auth credentials and set `OTEL_EXPORTER_OTLP_HEADERS` in runtime secrets
4. Deploy with proper secret mounting for authentication headers
5. Verify telemetry export by checking OpenObserve backend

#### Example Configuration
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: platform-runtime-config
data:
  OTEL_ENABLED: "true"
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://openobserve-router.openobserve.svc.cluster.local:5080/api/default"
---
apiVersion: v1
kind: Secret
metadata:
  name: tool-gateway-runtime-secrets
type: Opaque
stringData:
  OTEL_EXPORTER_OTLP_HEADERS: "Authorization=Basic base64-encoded-email-colon-password"
```

#### Authentication Header Generation
Generate Basic auth header using email:password combination:
```bash
echo -n "email@example.com:password" | base64
# Output: base64-encoded-string
# Then use: Authorization=Basic base64-encoded-string
```

**Section sources**
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)

### Service Links Migration Guide
**New Section** Migration strategy from Kubernetes service-link injection to DNS-based discovery.

#### Migration Steps
1. Identify all auto-generated service-link environment variables
2. Replace with explicit DNS-based configuration in ConfigMaps
3. Add `enableServiceLinks: false` to all deployment manifests
4. Test DNS resolution and service connectivity
5. Remove any legacy service-link references

#### Common Migration Patterns
- `SERVICE_NAME_PORT` → `SERVICE_NAME_URL=http://service-name:port`
- `SERVICE_NAME_HOST` → Part of URL configuration
- `SERVICE_NAME_PROTO` → Not needed with DNS-based approach

**Section sources**
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)

### OpenTelemetry Troubleshooting Guide
**New Section** Comprehensive troubleshooting guide for OpenTelemetry configuration and connectivity issues.

#### Common Issues and Solutions
- **OTEL_ENABLED not taking effect**: Verify environment variable is properly set and service restarts after configuration changes
- **Authentication failures (401)**: Check OTEL_EXPORTER_OTLP_HEADERS contains valid Basic auth credentials; verify OpenObserve user permissions
- **Endpoint connectivity issues**: Ensure OTEL_EXPORTER_OTLP_ENDPOINT is reachable from pod network; check firewall rules and service availability
- **High CPU usage**: Review OpenTelemetry batch processor settings; adjust batch sizes and export intervals for optimal performance
- **Missing traces/metrics**: Verify service instrumentation is active; check that FastAPI and HTTPX instrumentors are properly initialized
- **Log bridge not working**: Ensure log level is set to INFO; verify OTLP log exporter is properly configured

#### Monitoring and Diagnostics
- Check service logs for OpenTelemetry initialization messages
- Monitor exporter error rates and authentication failures
- Verify OpenObserve backend receives telemetry data
- Use OpenObserve dashboards to validate trace correlation and metric collection

**Section sources**
- [telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env)