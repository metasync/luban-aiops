# Configuration and Environment Setup

<cite>
**Referenced Files in This Document**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [sync-skills-secrets.sh](file://shared/platform-ops/gitops/sync-skills-secrets.sh)
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [spec.md](file://docs/specs/SPEC-019-portal-transparency-navigation/spec.md)
</cite>

## Update Summary
**Changes Made**
- Enhanced OpenTelemetry configuration with durable secret provisioning that maintains OTEL_EXPORTER_OTLP_HEADERS across deployment operations
- Improved fallback mechanisms ensure telemetry continues functioning even when local environment files are regenerated
- Updated synchronization scripts to preserve OTel headers during other secret provisioning operations
- Added comprehensive documentation for the enhanced secret management system
- Updated troubleshooting guidance for OTel authentication issues and secret provisioning failures

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
This document explains how the Platform Gateway Service manages configuration and environment setup across layers: environment variables, configuration files, and runtime overrides. It details available options, defaults, validation rules, and deployment-specific settings for development, staging, and production. It also provides examples for Docker and Kubernetes (ConfigMaps/Secrets), and outlines security best practices for secrets management and consistent configuration across environments.

**Updated** Enhanced documentation now includes comprehensive workspace resource integration capabilities through new platform-gateway configuration settings that enable read-only proxies for tools catalog and skills inventory, along with durable OpenTelemetry secret provisioning that maintains authentication headers across all deployment operations.

## Project Structure
The Platform Gateway Service is implemented under products/platform-gateway with its core configuration logic in the core module. Deployment manifests and environment templates are maintained under shared/platform-ops/gitops/dev-k8s/base/platform-gateway. The service includes workspace resource integration features that proxy requests to tool-gateway and skills-hub services for read-only inventory access, plus enhanced OpenTelemetry configuration with durable secret management.

```mermaid
graph TB
subgraph "Platform Gateway Service"
A["src/platform_gateway/core/config.py"]
B["src/platform_gateway/core/runtime.py"]
C["src/platform_gateway/core/telemetry.py"]
D["src/platform_gateway/api/routes/tools.py"]
E["src/platform_gateway/api/routes/skills.py"]
F["src/platform_gateway/services/tool_gateway_client.py"]
G["src/platform_gateway/services/skills_hub_client.py"]
end
subgraph "Workspace Resource Integration"
H["tool_gateway_url"]
I["skills_hub_url"]
J["skills_client_id"]
K["skills_client_secret"]
L["Delegated Token Flow"]
M["Basic Auth Flow"]
end
subgraph "Enhanced OTel Secret Management"
N["sync-otel-secrets.sh"]
O["OTEL_EXPORTER_OTLP_HEADERS"]
P["Cluster Secret Merge"]
Q["Local File Preservation"]
R["Sibling Script Hooks"]
end
subgraph "Kubernetes Base (dev)"
S["base/platform-gateway/runtime-config.env"]
T["base/platform-gateway/platform-gateway-deployment.yaml"]
U["base/platform-gateway/runtime-secrets.example.env"]
V["base/shared/runtime.env"]
end
A --> S
B --> T
C --> N
D --> F
E --> G
F --> H
G --> I
S --> T
U --> T
V --> T
N --> P
N --> Q
N --> R
```

**Diagram sources**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)

**Section sources**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)

## Core Components
- Configuration loader and model: centralizes environment variable parsing, file-based configuration, and runtime overrides; exposes validated configuration to the application.
- Runtime settings: handles service binding configuration with robust port resolution that ignores Kubernetes service-link formats.
- Enhanced telemetry system: opt-in OpenTelemetry push pipeline with fail-open behavior and durable secret provisioning.
- Workspace resource proxies: read-only proxy endpoints for tools catalog and skills inventory with appropriate authentication mechanisms.
- Policy engine configuration: loads default policy definitions from YAML and supports environment-driven overrides.
- Containerization and dependency management: Dockerfile defines runtime environment; pyproject.toml declares Python dependencies used by the gateway.

Key responsibilities:
- Provide a single source of truth for configuration via typed models.
- Enforce validation rules and provide clear error messages on misconfiguration.
- Support layered precedence: defaults < config files < environment variables < runtime overrides.
- Handle DNS-based service discovery with proper fallback mechanisms.
- Ignore Kubernetes service-link environment variables to prevent conflicts.
- Manage workspace resource integration with secure authentication and authorization.
- **New**: Maintain durable OpenTelemetry authentication headers across all deployment operations through cluster-side secret merging and local file preservation.

**Updated** Enhanced core components to include comprehensive workspace resource integration capabilities with read-only proxies for tools catalog and skills inventory, supporting both delegated token flow for tools and Basic authentication for skills, plus durable OpenTelemetry secret provisioning that persists authentication headers across deployment operations.

**Section sources**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)

## Architecture Overview
The configuration system follows a layered approach with enhanced workspace resource integration and durable secret management:
- Defaults: defined in code or default YAML policies.
- Config files: loaded from container filesystem or mounted volumes.
- Environment variables: injected at runtime via platform orchestration (e.g., Kubernetes).
- Runtime overrides: applied programmatically during startup or request processing.
- DNS-based service discovery: services communicate via Kubernetes DNS names instead of injected environment variables.
- Workspace resource proxies: read-only access to tools catalog and skills inventory with appropriate authentication.
- **New**: Durable OTel secret provisioning: cluster-side merging ensures authentication headers persist across all deployment operations.

```mermaid
sequenceDiagram
participant Portal as "Operator Portal"
participant Gateway as "Platform Gateway"
participant Identity as "Identity Broker"
participant Tools as "Tool Gateway"
participant Skills as "Skills Hub"
participant OTel as "OpenObserve"
participant Policy as "Policy Engine"
participant Secrets as "Secret Manager"
Portal->>Gateway : GET /api/v1/tools
Gateway->>Policy : enforce_policy(tools : list)
Policy-->>Gateway : Allow/Deny
Gateway->>Identity : obtain_delegated_token()
Identity-->>Gateway : Delegated Token
Gateway->>Tools : GET /api/v2/tools (Bearer token)
Tools-->>Gateway : Tools List
Gateway-->>Portal : Tools Catalog
Portal->>Gateway : GET /api/v1/skills
Gateway->>Policy : enforce_policy(skills : read)
Policy-->>Gateway : Allow/Deny
Gateway->>Skills : GET /skills (Basic auth)
Skills-->>Gateway : Skills Inventory
Gateway-->>Portal : Skills List
Note over Gateway,OTel : Durable OTel Secret Provisioning
Gateway->>Secrets : Read OTEL_EXPORTER_OTLP_HEADERS
Secrets-->>Gateway : Authenticated Headers
Gateway->>OTel : Export traces/metrics/logs (authenticated)
OTel-->>Gateway : Success/Failure (fail-open)
```

**Diagram sources**
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [spec.md](file://docs/specs/SPEC-019-portal-transparency-navigation/spec.md)

## Detailed Component Analysis

### Configuration Loader and Model
- Purpose: Parse and validate configuration from multiple layers and expose it consistently.
- Precedence: Defaults < Config files < Environment variables < Runtime overrides.
- Validation: Type checks, required fields, range constraints, and cross-field validations.
- Error handling: Aggregates validation errors and surfaces actionable messages.
- Service discovery: Uses DNS-based resolution for inter-service communication.

**Updated** Enhanced to support workspace resource integration with new configuration fields for tool_gateway_url, skills_hub_url, skills_client_id, and skills_client_secret, enabling read-only proxies for tools catalog and skills inventory.

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
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)

**Section sources**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)

### Enhanced Telemetry System
- Purpose: Opt-in OpenTelemetry push pipeline with fail-open behavior and durable secret provisioning.
- Gating: Controlled by OTEL_ENABLED environment variable (default false).
- Authentication: Uses OTEL_EXPORTER_OTLP_HEADERS for Basic auth against OpenObserve ingest endpoint.
- Fail-open: Setup errors are logged but never raised into the request path.
- Signals: Exports traces, metrics, and logs via OTLP HTTP/protobuf.
- **New**: Durable secret provisioning ensures authentication headers persist across all deployment operations.

**New Section** Comprehensive telemetry implementation with enhanced secret management that maintains OTel authentication headers across deployment operations through cluster-side merging and local file preservation.

```mermaid
flowchart TD
AppStart["Application Start"] --> CheckEnabled{"OTEL_ENABLED?"}
CheckEnabled --> |false| Disabled["Skip initialization"]
CheckEnabled --> |true| InitProviders["Initialize providers"]
InitProviders --> CreateResource["Create Resource"]
CreateResource --> TracerProvider["TracerProvider + BatchSpanProcessor"]
CreateResource --> MeterProvider["MeterProvider + PeriodicExportingMetricReader"]
CreateResource --> LogBridge["Attach Log Bridge"]
LogBridge --> InstrumentHTTPX["Instrument HTTPX Client"]
InstrumentHTTPX --> InstrumentFastAPI["Instrument FastAPI App"]
InstrumentFastAPI --> Ready["Telemetry Ready"]
Disabled --> Ready
Ready --> Export["Export traces/metrics/logs"]
Export --> AuthHeaders["Use OTEL_EXPORTER_OTLP_HEADERS"]
AuthHeaders --> Backend["OpenObserve Backend"]
Backend --> Result{"Success?"}
Result --> |yes| Success["Authenticated export"]
Result --> |no| FailOpen["Fail open - continue operation"]
```

**Diagram sources**
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)

**Section sources**
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)

### Durable Secret Provisioning System
- Purpose: Ensure OpenTelemetry authentication headers persist across all deployment operations.
- Cluster-side merging: Uses `kubectl patch --type merge` to update only the OTEL key in existing secrets.
- Local file preservation: Mirrors headers into local env files to maintain consistency.
- Sibling script hooks: Other sync scripts preserve existing OTel headers during their operations.
- Agent-platform profile handling: Special handling for agent-platform runtime profile files.
- **New**: Automatic workload restarts after secret updates to apply changes immediately.

**New Section** Comprehensive secret provisioning system that maintains OTel authentication headers across all deployment operations through cluster-side merging and local file preservation.

```mermaid
flowchart TD
Provision["sync-otel-secrets.sh"] --> ComputeAuth["Compute Basic Auth Header"]
ComputeAuth --> ProfileCheck{"Profile File Exists?"}
ProfileCheck --> |yes| UpsertProfile["Upsert header in profile file"]
ProfileCheck --> |no| MergeCluster["Merge header into cluster secret"]
UpsertProfile --> ApplyProfile["Apply profile secret"]
MergeCluster --> MergeOthers["Merge into other service secrets"]
ApplyProfile --> RestartAll["Restart all workloads"]
MergeOthers --> RestartAll
RestartAll --> Verify["Verify rollout status"]
Verify --> Complete["Telemetry authenticated"]
```

**Diagram sources**
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [sync-skills-secrets.sh](file://shared/platform-ops/gitops/sync-skills-secrets.sh)

**Section sources**
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [sync-skills-secrets.sh](file://shared/platform-ops/gitops/sync-skills-secrets.sh)

### Workspace Resource Proxy Routes
- Purpose: Provide read-only access to workspace resources (tools catalog and skills inventory) through the platform gateway.
- Tools proxy: `GET /api/v1/tools` enforces `tools:list` policy action and proxies to tool-gateway with delegated token.
- Skills proxy: `GET /api/v1/skills` enforces `skills:read` policy action and proxies to skills-hub with Basic authentication.
- Error handling: Returns 503 when services not configured, 502 on upstream failures, passes through 4xx client errors.

**New Section** Comprehensive workspace resource proxy implementation with appropriate authentication mechanisms and error handling.

```mermaid
flowchart TD
Request["API Request"] --> Route{"Route Type"}
Route --> |Tools| ToolsRoute["GET /api/v1/tools"]
Route --> |Skills| SkillsRoute["GET /api/v1/skills"]
ToolsRoute --> PolicyCheck["enforce_policy(tools:list)"]
SkillsRoute --> PolicyCheck
PolicyCheck --> Auth{"Authentication Method"}
Auth --> |Tools| Delegation["obtain_delegated_token()"]
Auth --> |Skills| BasicAuth["Basic Auth with credentials"]
Delegation --> ToolProxy["Forward to tool-gateway"]
BasicAuth --> SkillsProxy["Forward to skills-hub"]
ToolProxy --> Response["Return tools list"]
SkillsProxy --> Response
Response --> Client["Client Response"]
```

**Diagram sources**
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)

**Section sources**
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)

### Workspace Resource Clients
- Purpose: Handle HTTP communication with downstream workspace resource services.
- Tool gateway client: Forwards delegated tokens obtained through identity broker exchange.
- Skills hub client: Uses Basic authentication with configured client credentials.
- Error mapping: Consistent error handling with 503 for unconfigured services, 502 for upstream failures, 4xx passthrough for client errors.

**New Section** Dedicated client implementations for workspace resource integration with appropriate authentication and error handling patterns.

```mermaid
classDiagram
class ToolGatewayClient {
+list_tools(settings, request_id, delegated_token) list
+_base_url(settings) str
+_raise_upstream(response) None
}
class SkillsHubClient {
+list_skills(settings, request_id, params) dict
+_base_url(settings) str
+_credential(settings) tuple
+_raise_upstream(response) None
}
class PlatformGatewaySettings {
+tool_gateway_url : str
+skills_hub_url : str
+skills_client_id : str
+skills_client_secret : str
}
ToolGatewayClient --> PlatformGatewaySettings
SkillsHubClient --> PlatformGatewaySettings
```

**Diagram sources**
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)

**Section sources**
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)

### Runtime Settings and Port Resolution
- Purpose: Handle service binding configuration with robust port resolution.
- Port resolution: Ignores Kubernetes service-link format (`tcp://IP:PORT`) and extracts numeric ports.
- Default behavior: Falls back to default host and port when environment variables are not set.
- Development safety: Prevents conflicts between manual configuration and automatic service-link injection.

**Section sources**
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)

### DNS-Based Service Discovery
- Purpose: Enable reliable inter-service communication using Kubernetes DNS names.
- Configuration: Service endpoints configured via environment variables pointing to DNS names.
- Benefits: Eliminates service-link conflicts, improves reliability, and simplifies configuration.
- Implementation: Services resolve DNS names like `identity-service` to their cluster IPs.

**Section sources**
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)

### Policy Engine Configuration
- Default policy: Loaded from a YAML file defining baseline rules and behaviors.
- Overrides: Can be adjusted via environment variables or mounted config files depending on implementation.
- Usage: Provides decision context for tool invocation, access control, and rate limiting.

**Section sources**
- [spec.md](file://docs/specs/SPEC-019-portal-transparency-navigation/spec.md)

### Docker Configuration
- Image build: Defines base image, working directory, and dependency installation.
- Entrypoint: Runs the Platform Gateway Service with environment variables passed through.
- Best practices: Use multi-stage builds, pin versions, minimize attack surface.

**Section sources**
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)

### Kubernetes Deployment and ConfigMaps
- Deployment manifest: Mounts environment variables and config files into the pod.
- ConfigMap: Holds non-sensitive configuration values including service endpoints.
- Service discovery: Uses DNS names for inter-service communication.
- Environment injection: Maps ConfigMap entries to environment variables consumed by the configuration loader.
- Secrets management: Handles sensitive data like workspace resource credentials separately from ConfigMaps.
- **New**: Enhanced secret management with durable OTel header provisioning through cluster-side merging.

**Updated** Enhanced deployment configuration with workspace resource integration, including tool gateway URL, skills hub URL, and skills client credentials for read-only workspace resource access, plus durable OpenTelemetry secret provisioning that maintains authentication headers across deployment operations.

```mermaid
graph TB
CM["ConfigMap"] --> ENV["Environment Variables"]
ENV --> POD["Pod Spec"]
POD --> APP["Platform Gateway App"]
APP --> CFG["Configuration Loader"]
DNS["Kubernetes DNS"] --> SVC["Service Names"]
SVC --> APP
Secrets["Secrets"] --> WorkspaceCreds["Workspace Resource Credentials"]
Secrets --> OTelCreds["OTel Authentication Headers"]
WorkspaceCreds --> APP
OTelCreds --> APP
AppEnv["PLATFORM_GATEWAY_* Variables"] --> APP
APP --> ToolsProxy["Tools Catalog Proxy"]
APP --> SkillsProxy["Skills Inventory Proxy"]
ToolsProxy --> ToolsSvc["Tool Gateway Service"]
SkillsProxy --> SkillsSvc["Skills Hub Service"]
APP --> OTelExport["OTel Export Pipeline"]
OTelExport --> Backend["OpenObserve Backend"]
```

**Diagram sources**
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)

**Section sources**
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)

## Dependency Analysis
Configuration components depend on environment variables and files, while the runtime settings handle DNS-based service discovery. The Docker image encapsulates runtime dependencies, and Kubernetes manifests inject configuration at deployment time. Workspace resource integration adds dependencies on tool-gateway and skills-hub services with appropriate authentication mechanisms.

**Updated** Added dependencies for workspace resource integration including tool-gateway delegation flow and skills-hub Basic authentication, with proper error handling and service discovery, plus enhanced OpenTelemetry secret provisioning dependencies that ensure authentication headers persist across deployment operations.

```mermaid
graph TB
CFG["config.py"] --> ENV["Environment Variables"]
CFG --> FILE["Config Files"]
RT["runtime.py"] --> PORT["Port Resolution"]
TELEMETRY["telemetry.py"] --> SECRETS["Secret Management"]
SECRETS --> SYNC["sync-otel-secrets.sh"]
SYNC --> CLUSTER["Cluster Secrets"]
CLUSTER --> SECRETS
DNS["Kubernetes DNS"] --> SVC["Service Discovery"]
DOCKER["Deployment Manifest"] --> RUNTIME["Runtime Dependencies"]
K8S["platform-gateway-deployment.yaml"] --> INJECT["Env Injection"]
INJECT --> CFG
SVC --> RT
WS["Workspace Resources"] --> TOOLS["Tool Gateway"]
WS --> SKILLS["Skills Hub"]
CFG --> WS
Tools["tools.py"] --> ToolsClient["tool_gateway_client.py"]
Skills["skills.py"] --> SkillsClient["skills_hub_client.py"]
ToolsClient --> TOOLS
SkillsClient --> SKILLS
TELEMETRY --> BACKEND["OpenObserve Backend"]
```

**Diagram sources**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)

**Section sources**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)

## Performance Considerations
- Minimize configuration lookups by caching validated configuration at startup.
- Avoid heavy I/O during request processing; pre-load policies and dependencies.
- Use efficient serialization formats for configuration files where applicable.
- Monitor configuration-related metrics and errors to detect misconfigurations early.
- Leverage Kubernetes DNS caching for improved service discovery performance.
- Optimize port resolution to avoid unnecessary string parsing operations.
- Workspace resource proxies use timeout-based connections to prevent hanging requests.
- Delegated token acquisition is cached where possible to reduce identity broker load.
- Skills hub requests use connection pooling for improved performance.
- Monitor workspace resource proxy latency and error rates for capacity planning.
- **New**: OTel export pipeline uses batch processors for efficient telemetry collection.
- **New**: Secret provisioning operations are optimized to minimize cluster API calls.
- **New**: Failed OTel exports fail open to avoid impacting service performance.

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
- **New**: Workspace resource proxy failures: Check tool_gateway_url and skills_hub_url configuration; verify downstream services are running.
- **New**: Tools catalog proxy issues: Verify delegated token acquisition works; check identity broker configuration and permissions.
- **New**: Skills inventory proxy issues: Verify skills_client_id and skills_client_secret are properly configured; check skills-hub authentication.
- **New**: Workspace resource 503 errors: Indicates workspace resource services are not configured; verify PLATFORM_GATEWAY_TOOL_GATEWAY_URL and PLATFORM_GATEWAY_SKILLS_HUB_URL.
- **New**: Workspace resource 502 errors: Indicates upstream service failures; check tool-gateway and skills-hub service health and connectivity.
- **New**: Workspace resource 4xx errors: Indicates client-side issues; verify delegated token validity and skills authentication credentials.
- **New**: OTel authentication failures: Check if OTEL_EXPORTER_OTLP_HEADERS is properly provisioned; verify sync-otel-secrets.sh has been run successfully.
- **New**: OTel export failures: Verify OTEL_EXPORTER_OTLP_ENDPOINT is configured; check OpenObserve backend connectivity and authentication.
- **New**: Secret provisioning issues: Ensure OO_ROOT_USER_EMAIL and OO_ROOT_USER_PASSWORD are exported before running sync-otel-secrets.sh.
- **New**: Header persistence problems: Check that sibling sync scripts have preserved existing OTel headers during their operations.

**Updated** Added comprehensive troubleshooting guidance for workspace resource integration including proxy configuration, authentication issues, and downstream service connectivity problems, plus detailed guidance for OpenTelemetry secret provisioning and authentication issues.

**Section sources**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [platform-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)

## Conclusion
The Platform Gateway Service employs a robust, layered configuration system that integrates environment variables, configuration files, and runtime overrides with strict validation. By following the outlined best practices for Docker and Kubernetes deployments, teams can maintain secure, consistent configurations across environments while ensuring reliability and performance. The architectural shift to DNS-based service discovery eliminates service-link conflicts and provides more reliable inter-service communication patterns. The addition of workspace resource integration enables operators to gain self-service visibility into their workspace resources through read-only proxies for tools catalog and skills inventory, enhancing operational transparency and reducing dependency on agent-mediated resource discovery.

**Updated** Enhanced conclusion reflecting the architectural improvements in service discovery, environment variable handling, comprehensive workspace resource integration capabilities that provide operators with direct visibility into their workspace resources, plus durable OpenTelemetry secret provisioning that ensures authentication headers persist across all deployment operations, maintaining consistent telemetry collection regardless of deployment sequence or environment regeneration.

## Appendices

### Environment-Specific Settings
- Development: Enable verbose logging, relaxed validation, local secrets, optional redaction disablement, memory-based storage, local git sources without authentication, enable workspace resource proxies with local tool-gateway and skills-hub instances, configure OTel with dev OpenObserve credentials.
- Staging: Mirror production settings with test data and limited scope, enable full redaction, PostgreSQL-backed storage, private repository access with test tokens, configure workspace resource proxies with staging backend services, provision OTel secrets with staging OpenObserve credentials.
- Production: Strict validation, minimal logging, centralized secret management, mandatory workload identity, optimized sync intervals, secure private repository authentication, configure workspace resource proxies with production backend services and proper authentication, ensure OTel secrets are provisioned with production OpenObserve credentials.

**Updated** Added guidance for workspace resource proxy configuration across environments, including tool gateway URL, skills hub URL, and skills client credentials for read-only workspace resource access, plus comprehensive OTel secret provisioning requirements for each environment.

### Security and Secrets Management
- Store secrets in Kubernetes Secrets or external vaults; never hardcode.
- Rotate secrets regularly and audit access logs.
- Use least privilege principles for service accounts and RBAC.
- Prefer workload identity over static credentials in production environments.
- Configure appropriate redaction sensitivity levels based on data classification.
- Monitor redaction metrics and workload identity authentication attempts.
- Use DNS-based service discovery to avoid exposing service endpoints in environment variables.
- Disable service links to prevent accidental exposure of internal service information.
- **New**: Secure workspace resource credentials using Kubernetes Secrets; never commit PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET to version control.
- **New**: Validate delegated token acquisition for tools catalog access; ensure proper identity broker configuration.
- **New**: Monitor workspace resource proxy authentication attempts and failed authentication attempts.
- **New**: Implement rate limiting for workspace resource proxy endpoints to prevent abuse.
- **New**: Audit workspace resource access patterns for security monitoring and compliance.
- **New**: Protect OTel authentication headers using Kubernetes Secrets; never commit OTEL_EXPORTER_OTLP_HEADERS to version control.
- **New**: Restrict access to sync-otel-secrets.sh script to authorized personnel only.
- **New**: Monitor OTel export success/failure rates for security and operational insights.
- **New**: Implement alerting for OTel authentication failures and secret provisioning issues.

**Updated** Enhanced security guidance with workspace resource integration security considerations, including credential management, authentication monitoring, and access pattern auditing, plus comprehensive OpenTelemetry secret management security practices.

### Complete Environment Variables Reference
**Updated** Comprehensive reference including workspace resource integration variables for tools catalog and skills inventory access, plus enhanced OpenTelemetry configuration variables.

#### Core Configuration
- `AGENT_SERVICE_URL`: Agent service endpoint URL (DNS-based)
- `IDENTITY_SERVICE_URL`: Identity broker service endpoint URL (DNS-based)
- `IDENTITY_JWKS_URL`: Identity service JWKS endpoint
- `IDENTITY_JWKS_CACHE_SECONDS`: JWCS cache duration (default: 300)
- `IDENTITY_TOKEN_ISSUER`: JWT issuer claim (default: "luban-identity-broker")
- `PLATFORM_GATEWAY_TOKEN_AUDIENCE`: Token audience (default: "platform-gateway")
- `PLATFORM_GATEWAY_DELEGATION_AUDIENCE`: Delegation audience (default: "tool-gateway")

#### Runtime Configuration
- `PLATFORM_GATEWAY_HOST`: Service bind host (default: 0.0.0.0)
- `PLATFORM_GATEWAY_PORT`: Service bind port (numeric only, service-link format ignored)

#### Operational Configuration
- `PLATFORM_GATEWAY_REQUIRE_AUTH`: Require authentication (default: true)
- `PLATFORM_GATEWAY_POLICY_PATH`: Policy file path
- `CHAT_RESPONSE_TIMEOUT_SECONDS`: Chat response timeout (default: 30)

#### Workspace Resource Integration
- `PLATFORM_GATEWAY_TOOL_GATEWAY_URL`: Tool gateway URL for tools catalog proxy (e.g., http://tool-gateway:8000)
- `PLATFORM_GATEWAY_SKILLS_HUB_URL`: Skills hub URL for skills inventory proxy (e.g., http://skills-hub:8000)
- `PLATFORM_GATEWAY_SKILLS_CLIENT_ID`: Skills hub client ID for Basic authentication (default: "platform-gateway")
- `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET`: Skills hub client secret for Basic authentication (stored in secrets)

#### Audit and Incident Services
- `PLATFORM_GATEWAY_AUDIT_SERVICE_URL`: Audit service URL for durable audit trail
- `PLATFORM_GATEWAY_AUDIT_CLIENT_ID`: Audit service client ID (default: "platform-gateway")
- `PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET`: Audit service client secret (stored in secrets)
- `PLATFORM_GATEWAY_INCIDENT_SERVICE_URL`: Incident service URL for incident triage
- `PLATFORM_GATEWAY_INCIDENT_CLIENT_ID`: Incident service client ID (default: "platform-gateway")
- `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET`: Incident service client secret (stored in secrets)
- `PLATFORM_GATEWAY_INCIDENT_TRIAGE_TIMEOUT_SECONDS`: Incident triage timeout (default: 120)

#### Enhanced OpenTelemetry Configuration
- `OTEL_ENABLED`: Enable/disable OTel push pipeline (default: false)
- `OTEL_EXPORTER_OTLP_ENDPOINT`: OTLP endpoint for traces/metrics/logs (e.g., http://openobserve:5080)
- `OTEL_EXPORTER_OTLP_HEADERS`: Authentication headers for OTLP endpoint (provisioned by sync-otel-secrets.sh)
- `OTEL_SERVICE_NAME`: Service name for telemetry (default: derived from service)

**Section sources**
- [config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [runtime.py](file://products/platform-gateway/src/platform_gateway/core/runtime.py)
- [telemetry.py](file://products/platform-gateway/src/platform_gateway/core/telemetry.py)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)

### Workspace Resource Integration Guide
**New Section** Step-by-step guide for configuring workspace resource integration with tools catalog and skills inventory proxies.

#### Prerequisites
- Tool-gateway service deployed and accessible
- Skills-hub service deployed and accessible
- Identity broker configured for delegated token exchange
- Skills-hub configured with query clients registry
- Proper network policies allowing platform-gateway to reach workspace resources
- OpenTelemetry backend configured and accessible

#### Configuration Steps
1. Set `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` to point to tool-gateway service
2. Set `PLATFORM_GATEWAY_SKILLS_HUB_URL` to point to skills-hub service
3. Configure `PLATFORM_GATEWAY_SKILLS_CLIENT_ID` and `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` in secrets
4. Deploy with proper secret mounting for workspace resource credentials
5. Run `sync-otel-secrets.sh` to provision OTel authentication headers
6. Verify workspace resource proxies by accessing `/api/v1/tools` and `/api/v1/skills`
7. Verify OTel telemetry is flowing to backend

#### Example Configuration
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: platform-runtime-config
data:
  PLATFORM_GATEWAY_TOOL_GATEWAY_URL: "http://tool-gateway:8000"
  PLATFORM_GATEWAY_SKILLS_HUB_URL: "http://skills-hub:8000"
  PLATFORM_GATEWAY_SKILLS_CLIENT_ID: "platform-gateway"
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://openobserve:5080"
---
apiVersion: v1
kind: Secret
metadata:
  name: platform-gateway-runtime-secrets
type: Opaque
stringData:
  PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET: "your-skills-client-secret"
  # OTEL_EXPORTER_OTLP_HEADERS will be provisioned by sync-otel-secrets.sh
```

#### Authentication Flow
- Tools catalog: Uses delegated token flow through identity broker exchange
- Skills inventory: Uses Basic authentication with configured client credentials
- Both proxies enforce appropriate policy actions before forwarding requests
- OTel exports use Basic authentication via OTEL_EXPORTER_OTLP_HEADERS

**Section sources**
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)

### Enhanced Secret Provisioning Guide
**New Section** Comprehensive guide for managing OpenTelemetry secret provisioning and maintenance.

#### Prerequisites
- OpenObserve root credentials (OO_ROOT_USER_EMAIL, OO_ROOT_USER_PASSWORD)
- Access to Kubernetes cluster with kubectl configured
- Network connectivity to OpenObserve backend

#### Provisioning Steps
1. Export OpenObserve credentials: `export OO_ROOT_USER_EMAIL=your-email@example.com`
2. Export password: `export OO_ROOT_USER_PASSWORD=your-password`
3. Run provisioning script: `shared/platform-ops/gitops/sync-otel-secrets.sh`
4. Verify all secrets were updated: `kubectl get secrets -o custom-columns=NAME:.metadata.name,KEYS:.data | grep OTEL`
5. Check rollout status: `kubectl rollout status deployment/platform-gateway`

#### Maintenance Operations
- **Rotate credentials**: Re-run sync-otel-secrets.sh with new credentials
- **Verify headers**: Check pod environment variables for OTEL_EXPORTER_OTLP_HEADERS
- **Monitor exports**: Verify telemetry is flowing to OpenObserve backend
- **Troubleshoot failures**: Check pod logs for authentication errors

#### Security Considerations
- Never commit OpenObserve credentials to version control
- Restrict access to sync-otel-secrets.sh script
- Monitor secret rotation events and authentication failures
- Implement proper RBAC for secret management operations

**Section sources**
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)

### Workspace Resource Troubleshooting Guide
**New Section** Comprehensive troubleshooting guide for workspace resource integration configuration and connectivity issues.

#### Common Issues and Solutions
- **Workspace resource 503 errors**: Indicates workspace resource services are not configured; verify PLATFORM_GATEWAY_TOOL_GATEWAY_URL and PLATFORM_GATEWAY_SKILLS_HUB_URL are set correctly
- **Tools catalog 502 errors**: Indicates tool-gateway connectivity issues; check tool-gateway service health and network policies
- **Skills inventory 401 errors**: Indicates skills authentication failures; verify PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET matches skills-hub configuration
- **Delegated token acquisition failures**: Check identity broker configuration and permissions for platform-gateway service
- **High latency on workspace resource requests**: Monitor downstream service performance and consider increasing timeouts if needed
- **OTel export failures**: Verify OTEL_EXPORTER_OTLP_HEADERS is present and valid; check OpenObserve backend connectivity
- **Secret provisioning failures**: Ensure OO_ROOT_USER_EMAIL and OO_ROOT_USER_PASSWORD are exported; verify kubectl access to cluster

#### Monitoring and Diagnostics
- Check platform-gateway logs for workspace resource proxy errors
- Monitor delegated token acquisition success rates
- Track skills authentication attempt success/failure ratios
- Verify workspace resource proxy endpoint availability and response times
- Monitor OTel export success/failure rates and authentication errors
- Check secret provisioning logs for sync-otel-secrets.sh execution results

**Section sources**
- [tool_gateway_client.py](file://products/platform-gateway/src/platform_gateway/services/tool_gateway_client.py)
- [skills_hub_client.py](file://products/platform-gateway/src/platform_gateway/services/skills_hub_client.py)
- [tools.py](file://products/platform-gateway/src/platform_gateway/api/routes/tools.py)
- [skills.py](file://products/platform-gateway/src/platform_gateway/api/routes/skills.py)
- [sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)