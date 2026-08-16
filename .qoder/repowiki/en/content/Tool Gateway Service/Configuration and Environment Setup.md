# Configuration and Environment Setup

<cite>
**Referenced Files in This Document**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)
</cite>

## Update Summary
**Changes Made**
- Enhanced SKILLS_SOURCES configuration documentation to include optional path field for git sources
- Added comprehensive documentation for SKILLS_GIT_TOKENS environment variable for private repository authentication
- Updated development environment examples to reflect new git source configuration patterns
- Enhanced Skills Hub federation configuration with detailed guidance on subdirectory selection and token management
- Updated troubleshooting section with new authentication and path validation issues

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

**Updated** Enhanced documentation reflects the architectural shift from Kubernetes service-link injection to DNS-based service discovery, providing clearer guidance on inter-service communication patterns and environment variable handling. Includes comprehensive Skills Hub integration configuration with enhanced git source support for subdirectory selection and improved private repository authentication through SKILLS_GIT_TOKENS.

## Project Structure
The Tool Gateway Service is implemented under products/tool-gateway with its core configuration logic in the core module. Deployment manifests and environment templates are maintained under shared/platform-ops/gitops/dev-k8s/base/tool-gateway. The service image is built using a Dockerfile, and dependencies are declared in pyproject.toml. The Skills Hub service provides federated skill management with configurable storage backends, synchronization intervals, and enhanced git source support with optional subdirectory selection.

```mermaid
graph TB
subgraph "Tool Gateway Service"
A["src/tool_gateway/core/config.py"]
B["src/tool_gateway/core/runtime.py"]
C["src/tool_gateway/policies/policy-default.yaml"]
D["Dockerfile"]
E["pyproject.toml"]
end
subgraph "Skills Hub Service"
F["src/skills_hub/core/config.py"]
G["src/skills_hub/services/sync.py"]
H["skills-runtime-config.env"]
I["runtime-secrets.example.env"]
J["skills-hub-deployment.yaml"]
end
subgraph "Kubernetes Base (dev)"
K["base/tool-gateway/runtime-config.env"]
L["base/tool-gateway/tool-gateway-deployment.yaml"]
M["base/shared/runtime.env"]
end
A --> K
B --> L
K --> L
M --> L
C --> A
D --> A
E --> D
F --> H
F --> I
G --> J
H --> J
I --> J
```

**Diagram sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)

## Core Components
- Configuration loader and model: centralizes environment variable parsing, file-based configuration, and runtime overrides; exposes validated configuration to the application.
- Runtime settings: handles service binding configuration with robust port resolution that ignores Kubernetes service-link formats.
- Policy engine configuration: loads default policy definitions from YAML and supports environment-driven overrides.
- Containerization and dependency management: Dockerfile defines runtime environment; pyproject.toml declares Python dependencies used by the gateway.
- Skills Hub integration: federated skill source management with configurable storage backends, synchronization intervals, and enhanced git source support with optional subdirectory selection.

Key responsibilities:
- Provide a single source of truth for configuration via typed models.
- Enforce validation rules and provide clear error messages on misconfiguration.
- Support layered precedence: defaults < config files < environment variables < runtime overrides.
- Handle DNS-based service discovery with proper fallback mechanisms.
- Ignore Kubernetes service-link environment variables to prevent conflicts.
- Manage Skills Hub federation with local and git-based skill sources, including optional subdirectory selection for monorepo scenarios.
- Support private repository authentication through SKILLS_GIT_TOKENS environment variable.

**Updated** Enhanced core components to support DNS-based service discovery, improved environment variable handling, comprehensive Skills Hub integration with federated skill sources, and enhanced git source configuration with optional path fields and private repository authentication.

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)

## Architecture Overview
The configuration system follows a layered approach with enhanced service discovery:
- Defaults: defined in code or default YAML policies.
- Config files: loaded from container filesystem or mounted volumes.
- Environment variables: injected at runtime via platform orchestration (e.g., Kubernetes).
- Runtime overrides: applied programmatically during startup or request processing.
- DNS-based service discovery: services communicate via Kubernetes DNS names instead of injected environment variables.
- Skills Hub federation: federated skill sources with configurable storage backends, synchronization intervals, and enhanced git source support.

```mermaid
sequenceDiagram
participant App as "Tool Gateway App"
participant Config as "Configuration Loader"
participant Env as "Environment Variables"
participant File as "Config Files"
participant DNS as "Kubernetes DNS"
participant Service as "Identity Service"
participant SkillsHub as "Skills Hub"
participant GitAuth as "Git Authentication"
App->>Config : Initialize configuration
Config->>Env : Read environment variables
Config->>File : Load configuration files
Config->>Config : Merge layers with precedence
Config-->>App : Validated configuration
App->>DNS : Resolve service name (identity-service)
DNS-->>App : Service IP address
App->>Service : Connect via DNS name
Service-->>App : Service response
App->>DNS : Resolve skills-hub service
DNS-->>App : Skills Hub IP address
App->>SkillsHub : Query skills via API
SkillsHub->>GitAuth : Authenticate with SKILLS_GIT_TOKENS
GitAuth-->>SkillsHub : Authenticated access
SkillsHub->>SkillsHub : Process git sources with optional paths
SkillsHub-->>App : Skill data with federation info
```

**Diagram sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)

## Detailed Component Analysis

### Configuration Loader and Model
- Purpose: Parse and validate configuration from multiple layers and expose it consistently.
- Precedence: Defaults < Config files < Environment variables < Runtime overrides.
- Validation: Type checks, required fields, range constraints, and cross-field validations.
- Error handling: Aggregates validation errors and surfaces actionable messages.
- Service discovery: Uses DNS-based resolution for inter-service communication.

**Updated** Enhanced to support DNS-based service discovery, improved environment variable handling, Skills Hub federation configuration with strict validation rules, and enhanced git source validation with optional path fields.

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
DNS --> SkillsHub["skills-hub:8000"]
Identity --> Resolver["DNS Resolution"]
SkillsHub --> Resolver
Resolver --> IP["Service IP Address"]
IP --> Client
```

**Diagram sources**
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

**Section sources**
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

### Enhanced Skills Hub Integration Configuration
- Purpose: Configure federated skill sources with flexible storage backends, synchronization intervals, and enhanced git source support.
- Sources configuration: JSON-formatted list defining local directories and git repositories with optional subdirectory selection.
- Storage backends: Memory for development/testing, PostgreSQL for production persistence.
- Synchronization: Configurable intervals for skill source updates and pruning.
- Git source enhancement: Optional `path` field allows selecting specific subdirectories within git repositories for monorepo scenarios.
- Private repository authentication: SKILLS_GIT_TOKENS environment variable provides secure authentication for private git repositories.
- Validation: Strict schema validation for source configurations with fail-fast startup errors and path security validation.

**Updated Section** Comprehensive Skills Hub integration with federated skill sources, configurable storage backends, synchronization management, enhanced git source support with optional path fields, and secure private repository authentication.

```mermaid
flowchart TD
Sources["SKILLS_SOURCES<br/>(JSON)"] --> Parse["Parse & Validate"]
Parse --> Local["Local Sources<br/>(path)"]
Parse --> Git["Git Sources<br/>(url, ref, path*)"]
Local --> Store["Skill Store"]
Git --> TokenCheck{"Has Token?"}
TokenCheck --> |Yes| Auth["Authenticate with<br/>SKILLS_GIT_TOKENS"]
TokenCheck --> |No| Clone["Clone without auth"]
Auth --> Clone
Clone --> PathCheck{"Has path?"}
PathCheck --> |Yes| Subdir["Select subdirectory"]
PathCheck --> |No| Root["Use repo root"]
Subdir --> Store
Root --> Store
Store --> Backend{"Backend Type"}
Backend --> |memory| Memory["In-Memory Store"]
Backend --> |postgres| Postgres["PostgreSQL Store"]
Memory --> Sync["Sync Manager"]
Postgres --> Sync
Sync --> Interval["SKILLS_SYNC_INTERVAL_SECONDS"]
Interval --> Prune["Prune Unconfigured Sources"]
```

**Diagram sources**
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)

**Section sources**
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)

### Git Source Path Validation and Security
- Purpose: Ensure safe subdirectory selection within git repositories to prevent path traversal attacks.
- Validation rules: Rejects absolute paths, parent directory references, and other potentially malicious path patterns.
- Security: Validates that git source paths are relative subdirectories within the checkout directory.
- Monorepo support: Enables selective ingestion of specific directories within large repositories.

**New Section** Enhanced git source configuration with secure path validation for monorepo scenarios.

```mermaid
flowchart TD
GitPath["Git Source Path"] --> CheckAbsolute{"Absolute Path?"}
CheckAbsolute --> |Yes| Reject["Reject - Path Traversal Risk"]
CheckAbsolute --> |No| CheckParent{"Contains '..'?"}
CheckParent --> |Yes| Reject
CheckParent --> |No| Validate["Validate Relative Path"]
Validate --> Accept["Accept - Safe Subdirectory"]
```

**Diagram sources**
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)

**Section sources**
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)

### Private Repository Authentication with SKILLS_GIT_TOKENS
- Purpose: Provide secure authentication for private git repositories through token injection.
- Configuration: JSON map of source_id to authentication tokens.
- Token injection: Automatically injects x-access-token into HTTPS clone URLs for authenticated access.
- Security: Tokens are never logged or exposed in error messages; scrubbed automatically for security.
- Fallback: Without tokens, git sources fail authentication while other sources continue serving.

**New Section** Secure private repository authentication system with automatic token injection and credential protection.

```mermaid
flowchart TD
Source["Git Source Request"] --> CheckToken{"Has Token?"}
CheckToken --> |No| Public["Public Repository Access"]
CheckToken --> |Yes| Inject["Inject Token into URL"]
Inject --> Format["Format: https://x-access-token:token@host/repo.git"]
Format --> Clone["Authenticated Clone"]
Public --> Clone
Clone --> Success["Repository Access Granted"]
```

**Diagram sources**
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)

**Section sources**
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)

### Service Links Disabling Strategy
- Purpose: Prevent Kubernetes from automatically injecting service-link environment variables.
- Configuration: `enableServiceLinks: false` in all deployment manifests.
- Rationale: Avoids conflicts between manual configuration and automatic service-link injection.
- Impact: Requires explicit configuration of service endpoints via environment variables.

**New Section** Strategic disabling of Kubernetes service links to maintain configuration control.

```mermaid
flowchart TD
Deployment["Kubernetes Deployment"] --> Check{"enableServiceLinks<br/>Setting"}
Check --> |true| Inject["Auto-inject SERVICE_* env vars"]
Check --> |false| Manual["Manual env var configuration"]
Inject --> Conflict["Potential conflicts with<br/>manual configuration"]
Manual --> Control["Full control over<br/>service endpoints"]
Conflict --> Issue["Runtime configuration issues"]
Control --> Success["Reliable service discovery"]
```

**Diagram sources**
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)

**Section sources**
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)

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

**Updated** Enhanced deployment configuration with DNS-based service discovery, disabled service links, comprehensive Skills Hub integration, and enhanced git source support with optional path fields and private repository authentication.

```mermaid
graph TB
CM["ConfigMap"] --> ENV["Environment Variables"]
ENV --> POD["Pod Spec"]
POD --> APP["Tool Gateway App"]
APP --> CFG["Configuration Loader"]
DNS["Kubernetes DNS"] --> SVC["Service Names"]
SVC --> APP
SkillsCM["Skills ConfigMap"] --> SkillsENV["Skills Environment Variables"]
SkillsENV --> SkillsPod["Skills Hub Pod"]
SkillsPod --> SkillsStore["Skills Store"]
Secrets["Secrets"] --> GitTokens["SKILLS_GIT_TOKENS"]
GitTokens --> SkillsPod
```

**Diagram sources**
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)

**Section sources**
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)

### Dependency Management
- Python dependencies: Declared in pyproject.toml for reproducible builds.
- Lock file: Ensures deterministic dependency resolution.
- Best practices: Pin versions, separate dev and prod dependencies, audit regularly.

**Section sources**
- [pyproject.toml](file://products/tool-gateway/pyproject.toml)

## Dependency Analysis
Configuration components depend on environment variables and files, while the runtime settings handle DNS-based service discovery. The Docker image encapsulates runtime dependencies, and Kubernetes manifests inject configuration at deployment time. Skills Hub integration adds federated skill source management with configurable storage backends and enhanced git source support.

**Updated** Added dependencies for DNS-based service discovery, enhanced environment variable handling, comprehensive Skills Hub integration with federated skill sources, enhanced git source configuration with optional path fields, and private repository authentication through SKILLS_GIT_TOKENS.

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
SkillsCFG["skills_config.py"] --> SkillsENV["Skills Environment Variables"]
SkillsENV --> SkillsStore["Skills Store Backend"]
SkillsStore --> DB["PostgreSQL Database"]
SkillsSync["sync.py"] --> GitAuth["Git Authentication"]
GitAuth --> Tokens["SKILLS_GIT_TOKENS"]
```

**Diagram sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [Dockerfile](file://products/tool-gateway/Dockerfile)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

## Performance Considerations
- Minimize configuration lookups by caching validated configuration at startup.
- Avoid heavy I/O during request processing; pre-load policies and dependencies.
- Use efficient serialization formats for configuration files where applicable.
- Monitor configuration-related metrics and errors to detect misconfigurations early.
- Leverage Kubernetes DNS caching for improved service discovery performance.
- Optimize port resolution to avoid unnecessary string parsing operations.
- Configure appropriate Skills Hub sync intervals based on skill source update frequency.
- Use PostgreSQL backend for production Skills Hub deployments to ensure data persistence.
- Monitor Skills Hub storage backend performance and database connection pools.
- Optimize git source cloning with shallow clones (--depth 1) for faster synchronization.
- Implement proper caching for git checkouts to reduce network overhead.
- Monitor git authentication performance and token refresh cycles.

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
- Skills Hub configuration errors: Validate SKILLS_SOURCES JSON format and required fields for each source type.
- Skills Hub storage backend issues: Verify PostgreSQL connectivity and database permissions for production deployments.
- Skills Hub sync failures: Check SKILLS_SYNC_INTERVAL_SECONDS settings and network connectivity to git sources.
- Federated skill source problems: Validate local path mounts and git repository accessibility.
- **New**: Git source path validation errors: Ensure git source paths are relative subdirectories without path traversal attempts.
- **New**: Private repository authentication failures: Verify SKILLS_GIT_TOKENS configuration and token validity for private repositories.
- **New**: Git source subdirectory not found: Check that specified subdirectories exist in cloned repositories.
- **New**: Token injection issues: Verify HTTPS URLs and proper token formatting for private repository access.

**Updated** Added troubleshooting guidance for DNS-based service discovery, service link issues, comprehensive Skills Hub integration problems, enhanced git source configuration with path validation, and private repository authentication issues.

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)

## Conclusion
The Tool Gateway Service employs a robust, layered configuration system that integrates environment variables, configuration files, and runtime overrides with strict validation. By following the outlined best practices for Docker and Kubernetes deployments, teams can maintain secure, consistent configurations across environments while ensuring reliability and performance. The architectural shift to DNS-based service discovery eliminates service-link conflicts and provides more reliable inter-service communication patterns. The addition of Skills Hub integration enables federated skill source management with configurable storage backends and synchronization intervals, enhanced with optional git source path selection for monorepo scenarios and secure private repository authentication through SKILLS_GIT_TOKENS.

**Updated** Enhanced conclusion reflecting the architectural improvements in service discovery, environment variable handling, comprehensive Skills Hub integration with federated skill sources, enhanced git source configuration with optional path fields, and secure private repository authentication capabilities.

## Appendices

### Environment-Specific Settings
- Development: Enable verbose logging, relaxed validation, local secrets, optional redaction disablement, memory-based Skills Hub storage, local git sources without authentication.
- Staging: Mirror production settings with test data and limited scope, enable full redaction, PostgreSQL-backed Skills Hub storage, private repository access with test tokens.
- Production: Strict validation, minimal logging, centralized secret management, mandatory workload identity, optimized Skills Hub sync intervals, secure private repository authentication with scoped tokens.

**Updated** Added guidance for DNS-based service discovery configuration, enhanced git source configuration with path selection, and private repository authentication across environments.

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
- **New**: Protect SKILLS_GIT_TOKENS secrets with proper Kubernetes Secret management and rotation policies.
- **New**: Implement token scoping for git repositories to limit access to minimum required permissions.
- **New**: Monitor git authentication attempts and implement rate limiting for failed authentication attempts.
- **New**: Validate git source paths to prevent path traversal attacks and ensure only safe subdirectories are selected.

**Updated** Enhanced security guidance with DNS-based service discovery best practices, Skills Hub security considerations, and comprehensive git source authentication security measures.

[No sources needed since this section provides general guidance]

### Complete Environment Variables Reference
**Updated** Comprehensive reference including DNS-based service discovery variables, Skills Hub integration configuration, enhanced git source options, and private repository authentication.

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
- `GATEWAY_SKILLS_SERVICE_URL`: Skills Hub service URL using DNS names (e.g., http://skills-hub:8000)

#### Skills Hub Configuration
- `SKILLS_SOURCES`: Federated skill sources (JSON array with source_id, type, path/url/ref, and optional path for git sources)
- `SKILLS_STORE_BACKEND`: Storage backend type (memory or postgres)
- `SKILLS_DB_URL`: PostgreSQL connection URL for persistent storage
- `SKILLS_SYNC_INTERVAL_SECONDS`: Skill source synchronization interval (default: 300)
- `SKILLS_DATA_PATH`: Working directory for git checkouts (default: /var/lib/skills-hub)
- `SKILLS_QUERY_CLIENTS`: Registered query clients (client_id=secret format)
- `SKILLS_GIT_TOKENS`: Git authentication tokens for private repositories (JSON map of source_id -> token)
- `SKILLS_WORKLOAD_ISSUER_URL`: OIDC issuer for workload identity (production)
- `SKILLS_WORKLOAD_AUDIENCE`: Workload token audience (default: "skills-hub")
- `SKILLS_WORKLOAD_CLIENTS`: Workload client mappings (subject=client_id format)

#### Enhanced Git Source Configuration Examples
- Local source: `{"source_id": "local-skills", "type": "local", "path": "/skills/local"}`
- Git source (full repo): `{"source_id": "team-repo", "type": "git", "url": "https://github.com/team/repo.git", "ref": "main"}`
- Git source (subdirectory): `{"source_id": "monorepo-skills", "type": "git", "url": "https://github.com/team/monorepo.git", "ref": "main", "path": "skills/runbooks"}`

**Section sources**
- [config.py](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [runtime.py](file://products/tool-gateway/src/tool_gateway/core/runtime.py)
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)

### DNS-Based Service Discovery Setup Guide
**New Section** Step-by-step guide for configuring DNS-based service discovery.

#### Prerequisites
- Kubernetes cluster with DNS service enabled (default in most distributions)
- Service resources created for all dependent services
- Network policies allowing inter-service communication

#### Configuration Steps
1. Create Service resources for each dependent service
2. Set service endpoint URLs using DNS names in environment variables
3. Disable service links in deployment manifests (`enableServiceLinks: false`)
4. Configure shared runtime configuration in ConfigMaps
5. Verify DNS resolution works within the cluster

#### Example Configuration
```yaml
apiVersion: v1
kind: Service
metadata:
  name: identity-service
spec:
  selector:
    app: identity-service
  ports:
    - name: http
      port: 8000
      targetPort: 8000
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: platform-runtime-config
data:
  IDENTITY_SERVICE_URL: "http://identity-service:8000"
  AGENT_SERVICE_URL: "http://agent-service:8000"
  GATEWAY_SKILLS_SERVICE_URL: "http://skills-hub:8000"
```

**Section sources**
- [runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [tool-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)

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

### Enhanced Skills Hub Federation Setup Guide
**Updated Section** Comprehensive guide for configuring Skills Hub with federated skill sources, enhanced git source support, and private repository authentication.

#### Prerequisites
- PostgreSQL database for production deployments
- Git repositories containing skill sources (optional)
- Local directories with skill files (optional)
- Proper network policies for database and git access
- GitHub Personal Access Tokens (PAT) for private repositories

#### Configuration Steps
1. Define skill sources in SKILLS_SOURCES JSON format with optional path fields for git sources
2. Choose appropriate storage backend (memory for dev, postgres for prod)
3. Configure synchronization intervals based on update frequency
4. Set up SKILLS_GIT_TOKENS for private repository authentication
5. Validate configuration before deployment

#### Enhanced SKILLS_SOURCES Configuration Examples
```json
[
  {"source_id": "sre-alerting", "type": "local", "path": "/skills/sre-alerting"},
  {"source_id": "platform-runbooks", "type": "local", "path": "/skills/platform-runbooks"},
  {"source_id": "team-skills", "type": "git", "url": "https://github.com/team/skills.git", "ref": "main"},
  {"source_id": "monorepo-runbooks", "type": "git", "url": "https://github.com/team/monorepo.git", "ref": "main", "path": "docs/runbooks"}
]
```

#### Private Repository Authentication
```json
{
  "team-skills": "ghp_your_personal_access_token",
  "monorepo-runbooks": "ghp_another_token_for_monorepo"
}
```

#### Production Deployment Considerations
- Use PostgreSQL backend for data persistence
- Configure appropriate sync intervals to balance freshness and performance
- Set up proper database backups and monitoring
- Implement network policies for database access
- Monitor skill source health and synchronization status
- Implement proper token rotation and secret management for private repositories
- Use scoped tokens with minimum required permissions for git repositories

**Section sources**
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)
- [skills-hub-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)

### Skills Hub Storage Backend Configuration
**New Section** Detailed configuration for different storage backends.

#### Memory Backend (Development)
- Default backend for development and testing
- No persistent storage - data lost on restart
- Fastest performance for local development
- No additional infrastructure requirements

#### PostgreSQL Backend (Production)
- Persistent storage for skill data
- Requires PostgreSQL database setup
- Supports concurrent access and scaling
- Needs proper backup and maintenance procedures

#### Database Connection Configuration
- Use connection strings with proper authentication
- Configure connection pooling for high availability
- Monitor database performance and connection usage
- Implement proper SSL/TLS encryption for production

**Section sources**
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)
- [skills-runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env)

### Git Source Path Validation Rules
**New Section** Detailed documentation for git source path validation and security rules.

#### Allowed Path Patterns
- Relative paths only (no absolute paths starting with `/`)
- No parent directory references (`..`)
- Must be within the git repository checkout directory
- Trailing slashes are automatically removed

#### Security Validation
- Prevents path traversal attacks
- Ensures subdirectories are properly scoped
- Validates against common attack patterns
- Provides clear error messages for invalid paths

#### Examples
- ✅ Valid: `"path": "skills/runbooks"`
- ✅ Valid: `"path": "docs/guides"`
- ❌ Invalid: `"path": "/etc/passwd"` (absolute path)
- ❌ Invalid: `"path": "../../../etc"` (parent directory traversal)
- ❌ Invalid: `"path": "a/../../b"` (path traversal attempt)

**Section sources**
- [skills_config.py](file://products/skills-hub/src/skills_hub/core/config.py)

### Private Repository Authentication Setup
**New Section** Comprehensive guide for setting up private repository authentication with SKILLS_GIT_TOKENS.

#### Prerequisites
- GitHub Personal Access Token (PAT) with appropriate permissions
- Kubernetes Secret management for token storage
- Network access to private git repositories

#### Configuration Steps
1. Generate GitHub PAT with read-only repository access
2. Create Kubernetes Secret with SKILLS_GIT_TOKENS configuration
3. Map source_ids to corresponding tokens in JSON format
4. Deploy with proper secret mounting
5. Verify authentication works for private repositories

#### Token Format and Security
- JSON object mapping source_id to token
- Tokens are automatically injected into HTTPS clone URLs
- Credentials are never logged or exposed in error messages
- Implement proper token rotation and access controls

#### Example Configuration
```json
{
  "private-repo-1": "ghp_abc123def456ghi789",
  "private-repo-2": "ghp_xyz789abc123def456"
}
```

**Section sources**
- [sync.py](file://products/skills-hub/src/skills_hub/services/sync.py)
- [runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-secrets.example.env)