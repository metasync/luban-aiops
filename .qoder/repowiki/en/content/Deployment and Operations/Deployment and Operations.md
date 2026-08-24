# Deployment and Operations

<cite>
**Referenced Files in This Document**
- [Makefile](file://Makefile)
- [README.md](file://README.md)
- [VERSION](file://VERSION)
- [products/agent-platform/Dockerfile](file://products/agent-platform/Dockerfile)
- [products/agent-platform/Makefile](file://products/agent-platform/Makefile)
- [products/identity-broker/Dockerfile](file://products/identity-broker/Dockerfile)
- [products/identity-broker/Makefile](file://products/identity-broker/Makefile)
- [products/tool-gateway/Dockerfile](file://products/tool-gateway/Dockerfile)
- [products/tool-gateway/Makefile](file://products/tool-gateway/Makefile)
- [products/audit-service/Dockerfile](file://products/audit-service/Dockerfile)
- [products/audit-service/src/audit_service/core/config.py](file://products/audit-service/src/audit_service/core/config.py)
- [products/audit-service/src/audit_service/metadata.py](file://products/audit-service/src/audit_service/metadata.py)
- [products/audit-service/src/audit_service/__init__.py](file://products/audit-service/src/audit_service/__init__.py)
- [products/incident-service/src/incident_service/metadata.py](file://products/incident-service/src/incident_service/metadata.py)
- [products/incident-service/src/incident_service/__init__.py](file://products/incident-service/src/incident_service/__init__.py)
- [mk/image.mk](file://mk/image.mk)
- [mk/python.mk](file://mk/python.mk)
- [shared/platform-ops/gitops/dev-k8s/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/deploy.sh](file://shared/platform-ops/gitops/dev-k8s/deploy.sh)
- [shared/platform-ops/gitops/deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [shared/platform-ops/gitops/select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [shared/platform-ops/gitops/sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/sync-skills-secrets.sh](file://shared/platform-ops/gitops/sync-skills-secrets.sh)
- [shared/platform-ops/gitops/verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env](file://shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env)
- [shared/platform-ops/gitops/runtime-profiles/README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)
- [shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env)
- [shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/redis-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-service.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/postgres-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-service.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-service.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-service.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-service.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-service.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/policy.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/policy.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/rbac.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/rbac.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-service.yaml)
- [shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh](file://shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh)
- [products/agent-platform/src/agent_service/core/metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [products/agent-platform/src/agent_service/core/observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [products/agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [products/agent-platform/src/agent_service/services/model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [products/agent-platform/src/agent_service/providers/deepseek.py](file://products/agent-platform/src/agent_service/providers/deepseek.py)
- [products/agent-platform/src/agent_service/providers/dashscope.py](file://products/agent-platform/src/agent_service/providers/dashscope.py)
- [products/identity-broker/src/identity_service/core/metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [products/identity-broker/src/identity_service/core/observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [products/identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [products/tool-gateway/src/api_gateway/core/metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [products/tool-gateway/src/api_gateway/core/observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [products/tool-gateway/src/tool_gateway/core/telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [products/platform-gateway/src/platform_gateway/services/delegation_client.py](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py)
- [products/identity-broker/src/identity_service/services/exchange_service.py](file://products/identity-broker/src/identity_service/services/exchange_service.py)
- [products/platform-gateway/src/platform_gateway/core/config.py](file://products/platform-gateway/src/platform_gateway/core/config.py)
- [shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)
</cite>

## Update Summary
**Changes Made**
- Enhanced model pinning best practices in runtime secrets configuration example, recommending fixed-point model IDs over rolling tier aliases for better audit attribution and traceability
- Updated multi-model catalog implementation with SPEC-026 and SPEC-027 specifications for improved model discovery and management
- Added comprehensive documentation for live model discovery with fail-soft fallback mechanisms
- Enhanced provider-specific model series management with curated lists and override capabilities
- Improved model resolution logic with request > pinned > default precedence and credential-gated catalog validation

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
This document provides comprehensive deployment and operations guidance for the Luban AIOps Platform. It focuses on Kubernetes deployment using GitOps with Kustomize overlays, container build processes, image management, automation scripts, environment configuration, secrets management (including enhanced delegation secret auto-provisioning, audit secrets synchronization, and OpenTelemetry credential provisioning), scaling strategies, monitoring setup (Prometheus metrics, structured logging, health checks, and OpenTelemetry push pipeline), operational procedures (updates, rollbacks, disaster recovery, capacity planning), performance tuning, resource optimization, and troubleshooting common issues. The platform now operates at version 0.5.0 with synchronized service versions across all components. Enhanced model pinning best practices ensure better audit attribution and traceability through fixed-point model IDs rather than rolling tier aliases.

## Project Structure
The platform is organized into multiple products and shared operational assets:
- Products: agent-platform, identity-broker, tool-gateway, operator-portal, platform-gateway, audit-service, incident-service
- Shared ops: GitOps manifests under shared/platform-ops/gitops with base and runtime profiles
- Build system: Makefiles per product and shared mk rules for images and Python packaging
- Version management: Centralized version control with validation across all services
- Model catalog: Multi-provider model management with live discovery and curated series

```mermaid
graph TB
subgraph "Products"
AP["Agent Platform"]
IB["Identity Broker"]
TG["Tool Gateway"]
OP["Operator Portal"]
PG["Platform Gateway"]
AS["Audit Service"]
IS["Incident Service"]
SH["Skills Hub"]
end
subgraph "Shared Ops"
BASE["Kustomize Base"]
OVL["Kustomize Overlays"]
RP["Runtime Profiles"]
DS["Delegation Secrets"]
ASecrets["Audit Secrets"]
OTEL["OpenTelemetry Secrets"]
VM["Version Management"]
MC["Model Catalog"]
end
subgraph "Infrastructure"
Redis["Redis"]
Postgres["PostgreSQL"]
OO["OpenObserve"]
end
subgraph "Build System"
MK["mk/image.mk<br/>mk/python.mk"]
PMK["Product Makefiles"]
end
AP --> BASE
IB --> BASE
TG --> BASE
OP --> BASE
PG --> BASE
AS --> BASE
IS --> BASE
SH --> BASE
BASE --> OVL
RP --> OVL
DS --> OVL
ASecrets --> OVL
OTEL --> OVL
VM --> BASE
MC --> AP
Redis --> AS
Postgres --> AS
PMK --> MK
PMK --> AP
PMK --> IB
PMK --> TG
PMK --> OP
PMK --> PG
PMK --> AS
PMK --> IS
PMK --> SH
```

**Diagram sources**
- [shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [mk/image.mk](file://mk/image.mk)
- [mk/python.mk](file://mk/python.mk)
- [products/agent-platform/Makefile](file://products/agent-platform/Makefile)
- [products/identity-broker/Makefile](file://products/identity-broker/Makefile)
- [products/tool-gateway/Makefile](file://products/tool-gateway/Makefile)
- [products/audit-service/Dockerfile](file://products/audit-service/Dockerfile)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

**Section sources**
- [README.md](file://README.md)
- [VERSION](file://VERSION)
- [shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [mk/image.mk](file://mk/image.mk)
- [mk/python.mk](file://mk/python.mk)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

## Core Components
- Agent Platform: Provides agent runtime services, session management, and provider integrations. Exposes metrics and observability hooks with enhanced model catalog support.
- Identity Broker: Handles authentication, token issuance, and identity context propagation. Supports token delegation and exchange operations.
- Tool Gateway: API gateway enforcing policies, routing to agents/tools, and exposing metrics and observability hooks.
- Operator Portal: Web UI for operators to manage platform resources and configurations with OIDC authentication.
- Platform Gateway: Central gateway that handles user authentication and delegates tokens to downstream services through the identity broker.
- **Audit Service**: Durable audit trail service that ingests, stores, and queries audit events from all platform components with PostgreSQL persistence.
- **Incident Service**: Incident management service providing intake, triage, and collaboration capabilities with version 0.5.0 synchronization.
- **Skills Hub**: Skills management service providing reusable capabilities across the platform.

Key operational artifacts:
- Dockerfiles per product define container images.
- Product Makefiles orchestrate builds and pushes.
- mk/image.mk and mk/python.mk provide reusable build targets.
- Kustomize base defines Kubernetes resources; overlays select runtime profiles and apply environment-specific patches.
- Shell scripts automate deployment, secret synchronization, profile selection, verification, delegation secret provisioning, audit secret management, and OpenTelemetry credential provisioning.
- **Version Management**: Centralized version validation ensuring all services maintain consistent version 0.5.0.
- **Model Catalog**: Multi-provider model management with live discovery, curated series, and credential-gated access.

**Section sources**
- [products/agent-platform/Dockerfile](file://products/agent-platform/Dockerfile)
- [products/identity-broker/Dockerfile](file://products/identity-broker/Dockerfile)
- [products/tool-gateway/Dockerfile](file://products/tool-gateway/Dockerfile)
- [products/audit-service/Dockerfile](file://products/audit-service/Dockerfile)
- [products/agent-platform/Makefile](file://products/agent-platform/Makefile)
- [products/identity-broker/Makefile](file://products/identity-broker/Makefile)
- [products/tool-gateway/Makefile](file://products/tool-gateway/Makefile)
- [mk/image.mk](file://mk/image.mk)
- [mk/python.mk](file://mk/python.mk)
- [products/audit-service/src/audit_service/metadata.py](file://products/audit-service/src/audit_service/metadata.py)
- [products/incident-service/src/incident_service/metadata.py](file://products/incident-service/src/incident_service/metadata.py)

## Architecture Overview
The platform deploys as a set of Kubernetes workloads orchestrated via Kustomize. The GitOps workflow uses overlays to compose base manifests with environment-specific settings and runtime profiles. Enhanced with automated delegation secret provisioning for secure cross-service communication, durable audit trail storage, OpenTelemetry credential provisioning for centralized observability, centralized version management ensuring all services operate at version 0.5.0, and advanced model catalog management with live discovery capabilities.

```mermaid
graph TB
DevOps["Developer / CI"]
Git["Git Repository"]
Kustomize["Kustomize Overlay"]
Secrets["Delegation & Audit & OTel Secrets"]
VersionMgr["Version Manager"]
ModelCatalog["Model Catalog"]
K8s["Kubernetes Cluster"]
subgraph "Base Manifests"
BaseNS["Namespace"]
BaseInfra["Redis & PostgreSQL StatefulSets"]
BaseAP["Agent Service Deployment/Service"]
BaseIB["Identity Service Deployment/Service"]
BaseTG["API Gateway Deployment/Service"]
BaseOP["Web UI Deployment/Service"]
BasePG["Platform Gateway Deployment/Service"]
BaseAS["Audit Service Deployment/Service"]
BaseIS["Incident Service Deployment/Service"]
BaseSH["Skills Hub Deployment/Service"]
end
subgraph "Runtime Profiles"
ProfileDefault["Default ConfigMap"]
ProfileSecrets["Runtime Secrets"]
end
subgraph "Observability"
OpenObserve["OpenObserve Backend"]
OTLP["OTLP Exporters"]
end
DevOps --> Git
Git --> Kustomize
Git --> Secrets
Git --> VersionMgr
Git --> ModelCatalog
Kustomize --> BaseNS
Kustomize --> BaseInfra
Kustomize --> BaseAP
Kustomize --> BaseIB
Kustomize --> BaseTG
Kustomize --> BaseOP
Kustomize --> BasePG
Kustomize --> BaseAS
Kustomize --> BaseIS
Kustomize --> BaseSH
Kustomize --> ProfileDefault
Kustomize --> ProfileSecrets
Secrets --> K8s
VersionMgr --> K8s
ModelCatalog --> BaseAP
Kustomize --> K8s
BaseAP --> OTLP
BaseIB --> OTLP
BaseTG --> OTLP
BaseOP --> OTLP
BasePG --> OTLP
BaseAS --> OTLP
BaseIS --> OTLP
BaseSH --> OTLP
OTLP --> OpenObserve
```

**Diagram sources**
- [shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

## Detailed Component Analysis

### Container Build Process and Image Management
- Each product has a Dockerfile defining its runtime image.
- Product Makefiles encapsulate build, test, and push steps.
- Shared mk rules standardize image tagging, multi-arch builds, and Python packaging.
- **Version Synchronization**: All services are built and tagged with version 0.5.0, ensuring consistent deployments across the platform.

Recommended flow:
- Use product Makefiles to build images locally or in CI.
- Tag images consistently (semantic versioning or commit SHA).
- Push images to a registry accessible by the target cluster.
- Reference exact image tags in Kustomize overlays to ensure deterministic deployments.
- Validate version consistency using the shared version validation script.

```mermaid
flowchart TD
Start(["Start Build"]) --> CheckDeps["Check Dependencies"]
CheckDeps --> ValidateVersion["Validate Version Consistency"]
ValidateVersion --> BuildImage["Build Container Image"]
BuildImage --> TagImage["Tag Image with v0.5.0"]
TagImage --> PushImage["Push to Registry"]
PushImage --> UpdateOverlay["Update Overlay Image Tag"]
UpdateOverlay --> Commit["Commit Changes"]
Commit --> End(["End"])
```

**Section sources**
- [products/agent-platform/Dockerfile](file://products/agent-platform/Dockerfile)
- [products/identity-broker/Dockerfile](file://products/identity-broker/Dockerfile)
- [products/tool-gateway/Dockerfile](file://products/tool-gateway/Dockerfile)
- [products/audit-service/Dockerfile](file://products/audit-service/Dockerfile)
- [products/agent-platform/Makefile](file://products/agent-platform/Makefile)
- [products/identity-broker/Makefile](file://products/identity-broker/Makefile)
- [products/tool-gateway/Makefile](file://products/tool-gateway/Makefile)
- [mk/image.mk](file://mk/image.mk)
- [mk/python.mk](file://mk/python.mk)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

### GitOps Deployment with Kustomize Overlays
- Base manifests define core resources (namespaces, services, deployments, RBAC, policies).
- Runtime profiles inject model provider configurations via ConfigMaps and secrets.
- Overlays select profiles and apply environment-specific patches.
- Scripts automate deploy, profile selection, secret sync, verification, delegation secret provisioning, audit secret management, and OpenTelemetry credential provisioning.
- **Version Validation**: Pre-deployment validation ensures all services maintain version 0.5.0 consistency.

Operational steps:
- Select runtime profile using the provided script.
- Sync runtime secrets to the cluster.
- Provision delegation secrets for cross-service authentication.
- Provision audit secrets for audit event ingestion.
- Provision OpenTelemetry credentials for centralized observability.
- Deploy overlay to the target cluster.
- Verify runtime profile and health endpoints.
- Validate version consistency across all deployed services.

```mermaid
sequenceDiagram
participant Dev as "Developer"
participant Script as "deploy-overlay.sh"
participant Delegation as "sync-delegation-secrets.sh"
participant Audit as "sync-audit-secrets.sh"
participant OTel as "sync-otel-secrets.sh"
participant Version as "validate_version.py"
participant Kustomize as "Kustomize"
participant K8s as "Kubernetes"
Dev->>Script : Run deploy-overlay.sh
Script->>Version : Validate version consistency
Version-->>Script : Version check passed
Script->>Delegation : Provision delegation secrets
Delegation->>K8s : Create/update secrets
Script->>Audit : Provision audit secrets
Audit->>K8s : Create/update secrets
Script->>OTel : Provision OpenTelemetry credentials
OTel->>K8s : Create/update secrets
Script->>Kustomize : kustomize build <overlay>
Kustomize-->>Script : Rendered manifests
Script->>K8s : kubectl apply -f <rendered>
K8s-->>Dev : Resources created/updated
```

**Diagram sources**
- [shared/platform-ops/gitops/deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)
- [shared/platform-ops/gitops/dev-k8s/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)

**Section sources**
- [shared/platform-ops/gitops/dev-k8s/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [shared/platform-ops/gitops/deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [shared/platform-ops/gitops/select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [shared/platform-ops/gitops/sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

### Environment Configuration and Secrets Management
- Environment variables are supplied via env files mounted into pods.
- Observability settings are centralized in a shared env file.
- Runtime secrets are synchronized via dedicated scripts.
- OIDC client reconciliation is supported by a helper script.
- **Enhanced**: Delegation secrets are automatically provisioned for secure cross-service authentication.
- **New**: Audit secrets are automatically provisioned for audit event ingestion across all platform components.
- **Updated**: OpenTelemetry credentials are automatically provisioned for centralized observability via OpenObserve with enhanced CI/CD support and durable cluster-side merging.
- **Version Management**: All services configured with version 0.5.0 metadata and consistent versioning.
- **Model Pinning Best Practices**: Enhanced runtime secrets configuration recommends fixed-point model IDs over rolling tier aliases for better audit attribution and traceability.

Best practices:
- Keep sensitive values out of version control; use secret sync scripts to populate secure stores.
- Separate non-sensitive config from secrets.
- Validate overlays before applying to prevent misconfiguration.
- Use delegation secret provisioning to ensure consistent service-to-service authentication.
- Use audit secret provisioning to ensure consistent audit event ingestion credentials.
- Use OpenTelemetry secret provisioning to ensure consistent telemetry authentication headers with durable cluster-side merging.
- **CI/CD Integration**: Set `SKIP_OTEL_SECRETS=true` in CI environments where secrets are injected externally.
- **Version Validation**: Ensure all services maintain version 0.5.0 consistency during deployment.
- **Model Pinning**: Prefer fixed-point generation IDs (e.g., `qwen3.8-max`) over rolling tier aliases (e.g., `qwen-plus`) for precise audit attribution and traceability.

```mermaid
flowchart TD
EnvFiles["Environment Files"] --> Overlay["Kustomize Overlay"]
Secrets["Runtime Secrets"] --> SecretSync["sync-runtime-secret.sh"]
DelegationSecrets["Delegation Secrets"] --> DelegationSync["sync-delegation-secrets.sh"]
AuditSecrets["Audit Secrets"] --> AuditSync["sync-audit-secrets.sh"]
OTELSecrets["OpenTelemetry Credentials"] --> OTESync["sync-otel-secrets.sh"]
VersionCheck["Version Validation"] --> Overlay
ModelPinning["Model Pinning Config"] --> Overlay
DelegationSync --> K8sSecrets["Cluster Secrets"]
AuditSync --> K8sSecrets
OTESync --> K8sSecrets
SecretSync --> K8sSecrets
Overlay --> K8sApply["kubectl apply"]
K8sApply --> Pods["Pod Environments"]
K8sSecrets --> Pods
```

**Diagram sources**
- [shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env)
- [shared/platform-ops/gitops/sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh](file://shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

**Section sources**
- [shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env)
- [shared/platform-ops/gitops/sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh](file://shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

### Token Delegation and Cross-Service Authentication
**Updated** Enhanced with automated delegation secret provisioning and improved GitOps workflow for secure cross-service authentication.

The platform implements a sophisticated token delegation system that enables secure service-to-service communication:

- **Delegation Client**: The platform-gateway exchanges user JWTs for short-lived, audience-bound delegated tokens at the identity-broker
- **Token Exchange**: The identity-broker validates subject tokens and mints delegated tokens with restricted audiences
- **Secret Management**: Automated provisioning ensures consistent service credentials across platform-gateway and identity-broker
- **Workload Identity Support**: Optional projected workload tokens for enhanced security in production environments
- **Version Consistency**: All services operating at version 0.5.0 ensure compatible token handling

```mermaid
sequenceDiagram
participant User as "User"
participant PG as "Platform Gateway"
participant IB as "Identity Broker"
participant TG as "Tool Gateway"
Note over PG,IB : Token Delegation Flow
User->>PG : Request with JWT
PG->>IB : Exchange JWT for delegated token
IB->>IB : Validate subject token
IB->>PG : Return delegated token (audience : tool-gateway)
PG->>TG : Call with delegated token
TG->>TG : Validate delegated token
TG-->>PG : Tool execution result
PG-->>User : Response
```

**Diagram sources**
- [products/platform-gateway/src/platform_gateway/services/delegation_client.py](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py)
- [products/identity-broker/src/identity_service/services/exchange_service.py](file://products/identity-broker/src/identity_service/services/exchange_service.py)

**Section sources**
- [products/platform-gateway/src/platform_gateway/services/delegation_client.py](file://products/platform-gateway/src/platform_gateway/services/delegation_client.py)
- [products/identity-broker/src/identity_service/services/exchange_service.py](file://products/identity-broker/src/identity_service/services/exchange_service.py)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env)

### Audit Event Ingestion and Storage
**New Section** The audit service provides durable audit trail storage with PostgreSQL backend and supports ingestion from all platform components.

The audit service implements a comprehensive audit trail system:

- **Event Ingestion**: All platform components emit audit events to the audit-service via authenticated HTTP endpoints
- **Client Authentication**: Static client registry validates ingest requests using shared secrets
- **PostgreSQL Persistence**: Durable storage with configurable retention policies and automatic eviction
- **Query Interface**: REST API for querying audit events with filtering capabilities
- **Health Monitoring**: Readiness and liveness probes for reliable operation
- **Version 0.5.0**: Fully integrated with platform version synchronization

```mermaid
sequenceDiagram
participant TG as "Tool Gateway"
participant PG as "Platform Gateway"
participant IB as "Identity Broker"
participant AS as "Audit Service"
participant DB as "PostgreSQL"
Note over TG,DB : Audit Event Flow
TG->>AS : POST /api/v1/audit/events (with auth)
PG->>AS : POST /api/v1/audit/events (with auth)
IB->>AS : POST /api/v1/audit/events (with auth)
AS->>DB : Store audit event
DB-->>AS : Confirmation
AS-->>TG : 201 Created
AS-->>PG : 201 Created
AS-->>IB : 201 Created
```

**Diagram sources**
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml)
- [products/audit-service/src/audit_service/core/config.py](file://products/audit-service/src/audit_service/core/config.py)

**Section sources**
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [products/audit-service/src/audit_service/core/config.py](file://products/audit-service/src/audit_service/core/config.py)
- [products/audit-service/src/audit_service/metadata.py](file://products/audit-service/src/audit_service/metadata.py)

### OpenTelemetry Push Pipeline and OpenObserve Integration
**Updated Section** Comprehensive OpenTelemetry support with enhanced automated credential provisioning for centralized observability and improved CI/CD integration.

The platform implements a unified observability pipeline using OpenTelemetry with OpenObserve as the backend:

- **Opt-in Pipeline**: Controlled by `OTEL_ENABLED` environment variable (default false) with zero overhead when disabled
- **Unified Signals**: Traces, metrics, and logs exported via OTLP HTTP/protobuf to OpenObserve
- **Enhanced Authentication**: `sync-otel-secrets.sh` provisions Basic auth headers for OpenObserve ingestion with intelligent fallback handling and durable cluster-side merging
- **Fail-open Design**: Telemetry failures don't impact application functionality
- **Centralized Configuration**: Shared endpoint configuration via ConfigMap with per-service secret headers
- **CI/CD Integration**: Skip mechanism (`SKIP_OTEL_SECRETS=true`) for environments where secrets are injected externally
- **Intelligent Secret Handling**: Uses `kubectl patch --type merge` for atomic header updates instead of wholesale file rewrites, preserving other secret keys
- **Robust Synchronization**: Sibling scripts (delegation, audit, skills) preserve existing OTLP headers during their env-file rewrites
- **Version 0.5.0**: All services emit telemetry with consistent version metadata

```mermaid
sequenceDiagram
participant App as "Application Services"
participant OTel as "OTel Exporters"
participant OO as "OpenObserve"
Note over App,OO : OpenTelemetry Push Flow
App->>OTel : Generate traces/metrics/logs
OTel->>OTel : Apply Authorization header
OTel->>OO : POST /api/default/v1/{signal}
OO-->>OTel : 200 OK
OTel-->>App : Continue processing
Note over OTel : On failure : drop telemetry, continue app
```

**Diagram sources**
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)

**Section sources**
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [products/agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [products/identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [products/tool-gateway/src/tool_gateway/core/telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)

### Multi-Model Catalog and Live Discovery
**New Section** Advanced model catalog management with live discovery capabilities and enhanced model pinning best practices.

The platform implements a sophisticated model catalog system that manages LLM models across multiple providers with live discovery and credential gating:

- **Credential-Gated Access**: Only providers with resolvable API keys contribute to the catalog
- **Live Model Discovery**: Periodic queries to provider `/models` endpoints with fail-soft fallback ladder
- **Curated Series**: Provider-specific curated model lists with override capabilities
- **Model Resolution**: Request > pinned > default precedence with strict validation
- **Fixed-Point Model IDs**: Recommendation to use specific model IDs (e.g., `qwen3.8-max`) over rolling tier aliases (e.g., `qwen-plus`) for better audit attribution
- **Provider-Specific Filtering**: Intelligent filtering of non-chat modalities and dated snapshots
- **Atomic Catalog Swaps**: Thread-safe catalog updates without disrupting active sessions

Key features:
- **SPEC-026 Compliance**: Multi-model runtime catalog with credential gating and curated series
- **SPEC-027 Implementation**: Live model discovery with cached fallback mechanisms
- **Enhanced Model Pinning**: Fixed-point model IDs recommended for precise audit attribution and traceability
- **Provider Integration**: DeepSeek, DashScope, and OpenAI provider support with tailored model series

```mermaid
sequenceDiagram
participant Client as "Client Request"
participant Catalog as "Model Catalog"
participant Provider as "Provider API"
participant Cache as "Cache Layer"
Note over Client,Catalog : Model Resolution Flow
Client->>Catalog : Request with model_id
Catalog->>Catalog : Check request model
alt Request model exists
Catalog-->>Client : Use requested model
else No request model
Catalog->>Catalog : Check pinned model
alt Pinned model exists
Catalog-->>Client : Use pinned model
else No pinned model
Catalog->>Provider : GET /models (if discovery enabled)
Provider-->>Catalog : Model list
Catalog->>Cache : Fallback to last-good
Cache-->>Catalog : Cached models
Catalog-->>Client : Use default model
end
end
```

**Diagram sources**
- [products/agent-platform/src/agent_service/services/model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [products/agent-platform/src/agent_service/providers/deepseek.py](file://products/agent-platform/src/agent_service/providers/deepseek.py)
- [products/agent-platform/src/agent_service/providers/dashscope.py](file://products/agent-platform/src/agent_service/providers/dashscope.py)

**Section sources**
- [products/agent-platform/src/agent_service/services/model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [products/agent-platform/src/agent_service/providers/deepseek.py](file://products/agent-platform/src/agent_service/providers/deepseek.py)
- [products/agent-platform/src/agent_service/providers/dashscope.py](file://products/agent-platform/src/agent_service/providers/dashscope.py)
- [shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env](file://shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env)
- [shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [shared/platform-ops/gitops/runtime-profiles/README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)

### Scaling Strategies
- Horizontal Pod Autoscaler (HPA): Configure based on CPU/memory utilization or custom metrics exposed by services.
- Vertical Pod Autoscaler (VPA): Review recommended resource requests/limits periodically.
- Replicas: Adjust deployment replicas per service workload characteristics.
- Stateful components: Ensure Redis sizing and persistence align with expected load.
- **Database Scaling**: Monitor PostgreSQL StatefulSet performance and consider read replicas for high-volume audit scenarios.
- **Observability Scaling**: Scale OpenObserve instances based on telemetry volume and query patterns.
- **Model Catalog Scaling**: Monitor model discovery refresh rates and cache hit ratios for optimal performance.
- **Version 0.5.0 Considerations**: All services optimized for consistent scaling behavior across the platform.

Guidelines:
- Set resource requests and limits conservatively; monitor actual usage.
- Use separate HPA targets for stateless services (agent-platform, identity-broker, tool-gateway, platform-gateway, audit-service, skills-hub, incident-service).
- Monitor autoscaling events and adjust thresholds to avoid flapping.
- Size PostgreSQL volumes appropriately for audit data retention requirements.
- Plan OpenObserve capacity based on telemetry ingestion rates and retention policies.
- Configure model discovery refresh intervals based on provider API rate limits and change frequency.
- Ensure consistent scaling across all version 0.5.0 services for optimal performance.

**Section sources**
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/api-gateway-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml)

### Monitoring Setup: Prometheus Metrics, Structured Logging, Health Checks, OpenTelemetry
- Each service exposes metrics and observability hooks through dedicated modules.
- Structured logging should be enabled via environment configuration.
- Health check endpoints are defined for readiness/liveness probes.
- **Audit Service Monitoring**: Prometheus scraping configured with specific metrics endpoint and port configuration.
- **OpenTelemetry Integration**: Unified telemetry pipeline with automated credential provisioning and centralized collection.
- **Model Catalog Monitoring**: Metrics for model discovery refresh rates, cache hit ratios, and model counts per provider.
- **Version 0.5.0 Monitoring**: All services emit consistent version metadata for accurate monitoring and alerting.

Implementation notes:
- Integrate Prometheus scraping via ServiceMonitors or scrape configs targeting service ports.
- Ensure metrics endpoints are reachable and not blocked by network policies.
- Configure log levels and output formats consistently across services.
- Monitor audit event ingestion rates and database performance metrics.
- Configure OpenTelemetry exporters with proper authentication and endpoint configuration.
- Monitor telemetry export success rates and error patterns.
- Track version consistency across all monitored services.
- Monitor model discovery performance and provider API response times.
- Track model selection patterns and pinning effectiveness.

```mermaid
graph TB
Services["Agent Platform / Identity Broker / Tool Gateway / Platform Gateway / Audit Service / Incident Service / Skills Hub"]
Metrics["Metrics Endpoint"]
Logs["Structured Logs"]
Health["Health Endpoints"]
OTel["OpenTelemetry Exporters"]
ModelMetrics["Model Catalog Metrics"]
Prometheus["Prometheus"]
Grafana["Grafana Dashboards"]
OpenObserve["OpenObserve Backend"]
VersionMonitor["Version Consistency Monitor"]
Services --> Metrics
Services --> Logs
Services --> Health
Services --> OTel
Services --> ModelMetrics
Prometheus --> Metrics
Prometheus --> ModelMetrics
Grafana --> Prometheus
OTel --> OpenObserve
VersionMonitor --> Services
```

**Section sources**
- [products/agent-platform/src/agent_service/core/metrics.py](file://products/agent-platform/src/agent_service/core/metrics.py)
- [products/agent-platform/src/agent_service/core/observability.py](file://products/agent-platform/src/agent_service/core/observability.py)
- [products/agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)
- [products/identity-broker/src/identity_service/core/metrics.py](file://products/identity-broker/src/identity_service/core/metrics.py)
- [products/identity-broker/src/identity_service/core/observability.py](file://products/identity-broker/src/identity_service/core/observability.py)
- [products/identity-broker/src/identity_service/core/telemetry.py](file://products/identity-broker/src/identity_service/core/telemetry.py)
- [products/tool-gateway/src/api_gateway/core/metrics.py](file://products/tool-gateway/src/api_gateway/core/metrics.py)
- [products/tool-gateway/src/api_gateway/core/observability.py](file://products/tool-gateway/src/api_gateway/core/observability.py)
- [products/tool-gateway/src/tool_gateway/core/telemetry.py](file://products/tool-gateway/src/tool_gateway/core/telemetry.py)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)

### Operational Procedures: Updates, Rollbacks, Disaster Recovery, Capacity Planning
- Updates:
  - Build new images and update overlay tags.
  - Apply overlay changes; verify rollout status.
  - Validate health endpoints and metrics.
  - Re-provision delegation secrets if service credentials change.
  - Re-provision audit secrets if audit ingestion credentials change.
  - Re-provision OpenTelemetry credentials if OpenObserve authentication changes.
  - **Version Validation**: Ensure all services maintain version 0.5.0 consistency.
  - **Model Catalog Updates**: Refresh model discovery if provider model lineups change significantly.
- Rollbacks:
  - Revert overlay commits to previous known-good tags.
  - Apply reverted overlay; confirm rollback success.
  - Restore delegation secrets if needed.
  - Restore audit secrets if needed.
  - Restore OpenTelemetry credentials if needed.
  - **Version Rollback**: Ensure all services revert to consistent previous version.
  - **Model Catalog Rollback**: Revert to curated series if live discovery causes issues.
- Disaster Recovery:
  - Back up persistent data (e.g., Redis volumes, PostgreSQL data).
  - Restore from backups and reapply overlays.
  - Re-provision delegation secrets and validate service connectivity.
  - Re-provision audit secrets and validate audit ingestion.
  - Re-provision OpenTelemetry credentials and validate telemetry flow.
  - Confirm data integrity and service functionality.
  - **Version Verification**: Validate all services restored to consistent version 0.5.0.
  - **Model Catalog Recovery**: Rebuild model catalog from curated series if discovery cache is corrupted.
- Capacity Planning:
  - Analyze metrics trends and resource utilization.
  - Scale horizontally or vertically based on observed demand.
  - Plan node pool sizing and cluster upgrades.
  - Monitor PostgreSQL storage growth for audit data retention.
  - Monitor OpenObserve storage and query performance for telemetry data.
  - **Version 0.5.0 Optimization**: Leverage consistent service versions for predictable scaling behavior.
  - **Model Catalog Capacity**: Plan for increased model discovery traffic and provider API rate limits.

**Section sources**
- [shared/platform-ops/gitops/dev-k8s/deploy.sh](file://shared/platform-ops/gitops/dev-k8s/deploy.sh)
- [shared/platform-ops/gitops/deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

## Dependency Analysis
The platform's dependencies span build tools, container images, Kubernetes resources, runtime profiles, delegation secret management, audit secret management, OpenTelemetry credential provisioning, centralized version management, and advanced model catalog management.

```mermaid
graph LR
MakefileRoot["Makefile"] --> MkImage["mk/image.mk"]
MakefileRoot --> MkPython["mk/python.mk"]
APMake["products/agent-platform/Makefile"] --> APDocker["products/agent-platform/Dockerfile"]
IBMake["products/identity-broker/Makefile"] --> IBDocker["products/identity-broker/Dockerfile"]
TGMake["products/tool-gateway/Makefile"] --> TGDocker["products/tool-gateway/Dockerfile"]
PGMake["products/platform-gateway/Makefile"] --> PGDocker["products/platform-gateway/Dockerfile"]
ASMake["products/audit-service/Makefile"] --> ASDocker["products/audit-service/Dockerfile"]
ISMake["products/incident-service/Makefile"] --> ISDocker["products/incident-service/Dockerfile"]
BaseKust["base/kustomization.yaml"] --> Infra["infra/*"]
BaseKust --> APRes["agent-platform/*"]
BaseKust --> IBRes["identity-broker/*"]
BaseKust --> TGRes["tool-gateway/*"]
BaseKust --> OPRes["operator-portal/*"]
BaseKust --> PGRes["platform-gateway/*"]
BaseKust --> ASRes["audit-service/*"]
BaseKust --> ISRes["incident-service/*"]
OverlayKust["dev-k8s/kustomization.yaml"] --> BaseKust
OverlayKust --> Profiles["runtime-profiles/*"]
OverlayKust --> Delegation["sync-delegation-secrets.sh"]
OverlayKust --> AuditSecrets["sync-audit-secrets.sh"]
OverlayKust --> OTelSecrets["sync-otel-secrets.sh"]
OverlayKust --> VersionValidation["validate_version.py"]
OverlayKust --> ModelCatalog["model_catalog.py"]
VersionValidation --> VERSION["VERSION"]
ModelCatalog --> Providers["provider adapters"]
```

**Diagram sources**
- [Makefile](file://Makefile)
- [mk/image.mk](file://mk/image.mk)
- [mk/python.mk](file://mk/python.mk)
- [products/agent-platform/Makefile](file://products/agent-platform/Makefile)
- [products/identity-broker/Makefile](file://products/identity-broker/Makefile)
- [products/tool-gateway/Makefile](file://products/tool-gateway/Makefile)
- [products/audit-service/Dockerfile](file://products/audit-service/Dockerfile)
- [products/incident-service/Dockerfile](file://products/incident-service/Dockerfile)
- [shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)
- [products/agent-platform/src/agent_service/services/model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [VERSION](file://VERSION)

**Section sources**
- [Makefile](file://Makefile)
- [mk/image.mk](file://mk/image.mk)
- [mk/python.mk](file://mk/python.mk)
- [shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml)
- [shared/platform-ops/gitops/dev-k8s/kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)
- [VERSION](file://VERSION)

## Performance Considerations
- Resource Requests/Limits:
  - Set realistic CPU/memory requests and limits based on profiling.
  - Avoid over-provisioning; use VPA recommendations cautiously.
- Concurrency and Timeouts:
  - Tune HTTP timeouts and concurrency settings per service workload.
- Caching:
  - Leverage Redis for session/state caching where applicable.
  - Utilize delegated token caching in platform-gateway to reduce identity broker calls.
  - **Model Catalog Caching**: Enable model discovery caching to reduce provider API calls and improve response times.
- Garbage Collection:
  - For Python-based services, configure GC flags if needed to reduce latency spikes.
- Network Policies:
  - Minimize unnecessary egress/ingress to reduce overhead.
- Token Delegation Performance:
  - Monitor delegation cache hit rates to optimize token refresh intervals.
  - Consider workload identity for reduced authentication overhead in production.
- **Audit Service Performance**:
  - Monitor PostgreSQL query performance and connection pooling.
  - Tune audit event batch sizes and eviction intervals based on ingestion volume.
  - Consider read replicas for high-volume audit query scenarios.
- **OpenTelemetry Performance**:
  - Monitor telemetry export success rates and latency.
  - Configure appropriate batch sizes and timeout settings for OTel exporters.
  - Monitor OpenObserve ingestion performance and storage utilization.
  - Consider sampling strategies for high-volume telemetry data.
- **Model Catalog Performance**:
  - Monitor model discovery refresh rates and provider API response times.
  - Configure appropriate discovery refresh intervals to balance freshness with API rate limits.
  - Monitor cache hit ratios and fallback chain effectiveness.
  - Consider disabling discovery for stable model lineups to reduce overhead.
- **Version 0.5.0 Optimizations**:
  - All services benefit from consistent version optimizations and performance improvements.
  - Leverage synchronized service versions for predictable performance characteristics.
  - Monitor version-specific performance metrics across all platform components.

## Troubleshooting Guide
Common issues and resolutions:
- Deployment failures:
  - Validate Kustomize rendering; check for missing fields or invalid references.
  - Inspect pod logs and events for errors.
- Secrets not applied:
  - Ensure secret sync script runs successfully and secrets exist in the target namespace.
  - Verify delegation secrets are properly provisioned for cross-service authentication.
  - Verify audit secrets are properly provisioned for audit event ingestion.
  - Verify OpenTelemetry credentials are properly provisioned for telemetry authentication.
- Health checks failing:
  - Confirm health endpoints are reachable and returning expected responses.
- Metrics not scraped:
  - Verify ServiceMonitors or scrape configs target correct ports and paths.
- Runtime profile mismatch:
  - Use verification script to ensure selected profile matches expectations.
- Token delegation failures:
  - Check delegation secret consistency between platform-gateway and identity-broker.
  - Verify workload identity configuration if using projected tokens.
  - Monitor delegation exchange metrics for failure patterns.
- **Audit ingestion failures**:
  - Check audit secret consistency between emitters and audit-service.
  - Verify PostgreSQL connectivity and database availability.
  - Monitor audit event ingestion metrics and error rates.
  - Check audit service health endpoints and database connection status.
- **OpenTelemetry issues**:
  - Verify `OTEL_ENABLED` is set correctly for each service.
  - Check OpenObserve endpoint configuration and network connectivity.
  - Verify Basic auth headers are properly provisioned via `sync-otel-secrets.sh`.
  - Monitor telemetry export success rates and authentication errors.
  - Check OpenObserve ingestion logs for 401 unauthorized responses.
  - **CI/CD Issues**: If running in CI/CD, ensure `SKIP_OTEL_SECRETS=true` is set when secrets are injected externally.
  - **Missing Local Files**: When runtime-secrets.env files are missing locally, the script will automatically patch existing cluster secrets instead of failing.
  - **Durable Merging Issues**: If OTLP headers are being wiped, verify that sibling scripts are preserving existing headers during their env-file rewrites.
  - **kubectl Patch Failures**: Check cluster permissions for patch operations and verify secret existence before patching.
- **Model Catalog Issues**:
  - Verify model discovery is enabled and configured correctly.
  - Check provider API connectivity and rate limit compliance.
  - Monitor model discovery refresh metrics and cache hit ratios.
  - Verify fixed-point model IDs are used for better audit attribution.
  - Check curated series alignment with provider current offerings.
  - Validate model resolution precedence (request > pinned > default).
- **Version Consistency Issues**:
  - Use `validate_version.py` to check version drift across all services.
  - Ensure all services maintain version 0.5.0 consistency.
  - Check SERVICE_VERSION constants in metadata.py files.
  - Verify __version__ attributes in package __init__.py files.
  - Validate VERSION file matches expected platform version.

Operational commands:
- Use deploy scripts to apply overlays and reconcile resources.
- Use verification scripts to validate runtime profiles and health.
- Use delegation secret provisioning script to ensure consistent service credentials.
- Use audit secret provisioning script to ensure consistent audit ingestion credentials.
- Use OpenTelemetry secret provisioning script to ensure consistent telemetry authentication.
- Use version validation script to ensure consistent service versions.
- Use model catalog metrics to monitor discovery performance and cache effectiveness.

**Section sources**
- [shared/platform-ops/gitops/dev-k8s/deploy.sh](file://shared/platform-ops/gitops/dev-k8s/deploy.sh)
- [shared/platform-ops/gitops/deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [shared/platform-ops/gitops/sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

## Conclusion
This guide outlines the end-to-end deployment and operations for the Luban AIOps Platform using GitOps and Kustomize. By following the documented processes for building images, managing overlays, configuring environments, provisioning delegation secrets, synchronizing audit secrets, provisioning OpenTelemetry credentials, and setting up monitoring, teams can reliably operate the platform at scale. The enhanced delegation secret auto-provisioning ensures secure cross-service authentication while maintaining operational simplicity. The new audit service provides durable audit trail storage with PostgreSQL persistence, enabling comprehensive compliance and security monitoring. The integrated OpenTelemetry pipeline with automated credential provisioning delivers centralized observability with fail-safe design and enhanced CI/CD support. The centralized version management system ensures all services operate at version 0.5.0 with consistent behavior across the platform. The advanced model catalog system with live discovery and enhanced model pinning best practices provides robust LLM model management with fixed-point model IDs for better audit attribution and traceability. Continuous validation, robust secret management, proactive capacity planning, careful monitoring of token delegation flows, audit ingestion, telemetry export, model catalog performance, and version consistency are essential for maintaining stability and performance.

## Appendices

### Appendix A: Key Scripts and Their Roles
- deploy-overlay.sh: Builds and applies Kustomize overlays to the cluster.
- select-runtime-profile.sh: Chooses the appropriate runtime profile for model providers.
- sync-runtime-secret.sh: Synchronizes runtime secrets into the cluster securely.
- sync-delegation-secrets.sh: Automatically provisions delegation secrets for cross-service authentication between platform-gateway and identity-broker.
- sync-audit-secrets.sh: Automatically provisions audit secrets for audit event ingestion across all platform components.
- **sync-otel-secrets.sh**: Automatically provisions OpenTelemetry credentials for centralized observability via OpenObserve with enhanced CI/CD support and durable cluster-side merging using kubectl patch.
- verify-runtime-profile.sh: Validates that the active runtime profile matches expectations.
- reconcile-portal-oidc-client.sh: Ensures OIDC client configuration remains consistent with Keycloak.
- **validate_version.py**: Validates version consistency across all platform services and ensures version 0.5.0 synchronization.

**Section sources**
- [shared/platform-ops/gitops/deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [shared/platform-ops/gitops/select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [shared/platform-ops/gitops/sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh](file://shared/platform-ops/gitops/dev-k8s/reconcile-portal-oidc-client.sh)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

### Appendix B: Environment Variables and Configurations
- Observability settings centralized in a shared env file.
- Per-service runtime configs mounted via env files.
- **Delegation configuration**: PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET and IDENTITY_SERVICE_CLIENTS must match for secure token delegation.
- **Audit configuration**: AUDIT_STORE_BACKEND=postgres, AUDIT_DB_URL for PostgreSQL connection, AUDIT_RETENTION_DAYS for data retention policy.
- **OpenTelemetry configuration**: OTEL_ENABLED for pipeline activation, OTEL_EXPORTER_OTLP_ENDPOINT for OpenObserve URL, OTEL_EXPORTER_OTLP_HEADERS for authentication (provisioned by sync-otel-secrets.sh).
- **Workload identity**: PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH for production deployments preferring projected tokens over static secrets.
- **CI/CD Integration**: SKIP_OTEL_SECRETS=true to skip OpenTelemetry secret provisioning in environments where secrets are injected externally.
- **Version Management**: All services configured with version 0.5.0 metadata and consistent versioning enforced by validate_version.py.
- **Model Catalog Configuration**: AGENT_MODEL_DISCOVERY_ENABLED for live discovery, AGENT_MODEL_DISCOVERY_REFRESH_SECONDS for refresh intervals, AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS for API timeouts.
- **Model Pinning Best Practices**: Use fixed-point model IDs (e.g., qwen3.8-max) over rolling tier aliases (e.g., qwen-plus) for better audit attribution and traceability.
- Ensure consistency across environments by pinning versions and tags.

**Section sources**
- [shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)

### Appendix C: Delegation Secret Management
**New Section** Enhanced delegation secret management for secure cross-service authentication.

The delegation secret system ensures secure communication between platform-gateway and identity-broker:

- **Automatic Secret Generation**: The sync-delegation-secrets.sh script generates a shared secret used by both services
- **Consistent Configuration**: The same secret is configured in both platform-gateway (PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET) and identity-broker (IDENTITY_SERVICE_CLIENTS)
- **Automated Deployment**: The script creates Kubernetes secrets and restarts affected deployments
- **Security Best Practices**: Secrets are never committed to version control; generated dynamically during deployment
- **Version 0.5.0 Integration**: All services operate with consistent delegation secret handling

Usage:
```bash
# Generate and provision delegation secrets
./shared/platform-ops/gitops/sync-delegation-secrets.sh dev-luban-aiops

# Override with specific secret
DELEGATION_CLIENT_SECRET=my-secret ./shared/platform-ops/gitops/sync-delegation-secrets.sh dev-luban-aiops

# Skip in CI when secrets are injected externally
SKIP_DELEGATION_SECRETS=true make deploy
```

**Section sources**
- [shared/platform-ops/gitops/sync-delegation-secrets.sh](file://shared/platform-ops/gitops/sync-delegation-secrets.sh)
- [shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env)
- [shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env)

### Appendix D: Audit Secret Management
**New Section** Comprehensive audit secret management for secure audit event ingestion.

The audit secret system ensures secure audit event ingestion from all platform components:

- **Centralized Secret Generation**: The sync-audit-secrets.sh script generates a single shared secret for all audit emitters
- **Multi-Component Integration**: Supports tool-gateway, platform-gateway, and identity-broker as audit event emitters
- **Static Client Registry**: Audit-service maintains a registry of authorized clients with their corresponding secrets
- **Automatic Workload Restart**: Script automatically restarts affected deployments after secret updates
- **Version 0.5.0 Compatibility**: Full integration with platform version synchronization

Usage:
```bash
# Generate and provision audit secrets
./shared/platform-ops/gitops/sync-audit-secrets.sh dev-luban-aiops

# Override with specific secret
AUDIT_INGEST_SECRET=my-audit-secret ./shared/platform-ops/gitops/sync-audit-secrets.sh dev-luban-aiops

# Skip in CI when secrets are injected externally
SKIP_AUDIT_SECRETS=true make deploy
```

Configuration details:
- **AUDIT_INGEST_CLIENTS**: Comma-separated list of client_id=secret pairs for authorized emitters
- **Per-emitter secrets**: GATEWAY_AUDIT_CLIENT_SECRET, PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET, IDENTITY_AUDIT_CLIENT_SECRET
- **PostgreSQL backend**: AUDIT_STORE_BACKEND=postgres with connection string in AUDIT_DB_URL
- **Retention policy**: AUDIT_RETENTION_DAYS controls how long audit events are stored

**Section sources**
- [shared/platform-ops/gitops/sync-audit-secrets.sh](file://shared/platform-ops/gitops/sync-audit-secrets.sh)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-secrets.example.env)
- [products/audit-service/src/audit_service/core/config.py](file://products/audit-service/src/audit_service/core/config.py)

### Appendix E: OpenTelemetry Secret Management
**Updated Section** Comprehensive OpenTelemetry credential management for centralized observability with enhanced CI/CD support and durable cluster-side merging.

The OpenTelemetry secret system ensures secure telemetry ingestion via OpenObserve:

- **Centralized Credential Generation**: The sync-otel-secrets.sh script generates Basic auth headers from OpenObserve root credentials
- **Multi-Service Integration**: Applies authentication headers to all platform services (agent-platform, identity-broker, tool-gateway, platform-gateway, audit-service, skills-hub, incident-service)
- **ConfigMap-Based Endpoint**: Shared OTLP endpoint configuration via ConfigMap with per-service secret headers
- **Fail-Open Design**: Missing credentials result in anonymous push attempts that fail gracefully without impacting services
- **Enhanced CI/CD Support**: Intelligent handling of externally provisioned secrets with skip mechanisms
- **Robust Fallback**: Uses `kubectl patch --type merge` for atomic header updates instead of wholesale file rewrites, preserving other secret keys
- **Sibling Script Synchronization**: All sibling scripts (delegation, audit, skills) preserve existing OTLP headers during their env-file rewrites
- **Version 0.5.0 Metadata**: All telemetry includes consistent version information for accurate tracking

Usage:
```bash
# Generate and provision OpenTelemetry credentials
export OO_ROOT_USER_EMAIL=admin@example.com
export OO_ROOT_USER_PASSWORD=password
./shared/platform-ops/gitops/sync-otel-secrets.sh dev-luban-aiops

# Skip in CI when secrets are injected externally
SKIP_OTEL_SECRETS=true make deploy
```

Configuration details:
- **OTEL_ENABLED**: Master switch for telemetry pipeline (default false)
- **OTEL_EXPORTER_OTLP_ENDPOINT**: OpenObserve OTLP HTTP endpoint (configured in shared runtime.env)
- **OTEL_EXPORTER_OTLP_HEADERS**: Basic auth header for OpenObserve ingestion (provisioned by sync-otel-secrets.sh)
- **Authentication**: Basic auth with base64-encoded email:password combination
- **Backend**: OpenObserve with organization prefix (/api/default)
- **CI/CD Integration**: Set `SKIP_OTEL_SECRETS=true` in CI environments where secrets are injected externally

**Section sources**
- [shared/platform-ops/gitops/sync-otel-secrets.sh](file://shared/platform-ops/gitops/sync-otel-secrets.sh)
- [shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env](file://shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env)
- [shared/shared-contracts/observability-conventions.md](file://shared/shared-contracts/observability-conventions.md)
- [products/agent-platform/src/agent_service/core/telemetry.py](file://products/agent-platform/src/agent_service/core/telemetry.py)

### Appendix F: PostgreSQL Infrastructure
**New Section** PostgreSQL StatefulSet configuration for audit service persistence.

The audit service requires PostgreSQL for durable audit trail storage:

- **StatefulSet Configuration**: Single replica with persistent volume claim for data durability
- **Headless Service**: Enables stable DNS names for StatefulSet pod discovery
- **Development Credentials**: Pre-configured with development database, user, and password
- **Volume Management**: Persistent volume with 1Gi storage allocation for audit data
- **Version 0.5.0 Optimization**: Enhanced performance and reliability improvements

Production considerations:
- Replace development credentials with proper secrets management
- Configure appropriate storage classes and backup strategies
- Monitor database performance and scale storage as needed
- Consider read replicas for high-volume audit query scenarios
- Implement version-consistent database migrations

**Section sources**
- [shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-statefulset.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/infra/postgres-service.yaml](file://shared/platform-ops/gitops/dev-k8s/base/infra/postgres-service.yaml)
- [shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env)

### Appendix G: Version Management and Synchronization
**New Section** Comprehensive version management system ensuring all platform services operate at version 0.5.0.

The platform implements a centralized version management system that enforces version consistency across all components:

- **Single Source of Truth**: The root VERSION file contains the authoritative platform version (0.5.0)
- **Automated Validation**: The validate_version.py script checks version consistency across all services
- **Metadata Synchronization**: All services maintain consistent SERVICE_VERSION constants in metadata.py files
- **Package Versioning**: Package __init__.py files contain matching __version__ attributes
- **Build Integration**: Version validation is integrated into the build and deployment pipeline
- **Drift Detection**: Automatic detection and reporting of version inconsistencies

Key version locations:
- Root VERSION file: Contains platform version 0.5.0
- Service metadata: SERVICE_VERSION = "0.5.0" in all metadata.py files
- Package versions: __version__ = "0.5.0" in package __init__.py files
- Pyproject.toml: [project] version set to 0.5.0 for all products

Usage:
```bash
# Validate version consistency across all services
python shared/shared-contracts/scripts/validate_version.py

# Check current platform version
cat VERSION

# Update version across all services
echo "0.5.0" > VERSION
# Then run validation to ensure consistency
python shared/shared-contracts/scripts/validate_version.py
```

Benefits:
- Prevents version drift between services
- Ensures compatible service interactions
- Simplifies debugging and troubleshooting
- Enables reliable rolling updates
- Supports consistent monitoring and alerting

**Section sources**
- [VERSION](file://VERSION)
- [shared/shared-contracts/scripts/validate_version.py](file://shared/shared-contracts/scripts/validate_version.py)
- [products/audit-service/src/audit_service/metadata.py](file://products/audit-service/src/audit_service/metadata.py)
- [products/incident-service/src/incident_service/metadata.py](file://products/incident-service/src/incident_service/metadata.py)
- [products/audit-service/src/audit_service/__init__.py](file://products/audit-service/src/audit_service/__init__.py)
- [products/incident-service/src/incident_service/__init__.py](file://products/incident-service/src/incident_service/__init__.py)

### Appendix H: Model Catalog Configuration and Best Practices
**New Section** Comprehensive model catalog configuration with enhanced model pinning best practices.

The model catalog system provides advanced LLM model management with live discovery and credential gating:

- **Multi-Provider Support**: DeepSeek, DashScope, and OpenAI provider integration with curated model series
- **Live Model Discovery**: Periodic queries to provider `/models` endpoints with fail-soft fallback mechanisms
- **Credential Gating**: Only providers with resolvable API keys contribute to the catalog
- **Model Resolution**: Request > pinned > default precedence with strict validation
- **Enhanced Model Pinning**: Fixed-point model IDs recommended over rolling tier aliases for better audit attribution

Key configuration options:
- **AGENT_MODEL_DISCOVERY_ENABLED**: Enable/disable live model discovery (default: true)
- **AGENT_MODEL_DISCOVERY_REFRESH_SECONDS**: Refresh interval for model discovery (default: 1800)
- **AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS**: Timeout for provider API calls (default: 5)
- **<PROVIDER>_MODELS**: Override curated series with specific model list
- **<PROVIDER>_MODEL_NAME**: Set default model for provider
- **<PROVIDER>_API_KEY**: Provider API key for authentication

Best practices:
- **Use Fixed-Point Model IDs**: Prefer specific model IDs like `qwen3.8-max` over rolling aliases like `qwen-plus` for precise audit attribution
- **Configure Provider Overrides**: Use `<PROVIDER>_MODELS` to restrict available models to approved lineups
- **Enable Discovery for Flexibility**: Allow live discovery to automatically pick up new provider models
- **Monitor Discovery Performance**: Track refresh rates and cache hit ratios for optimal performance
- **Validate Model Selection**: Ensure model resolution follows expected precedence rules

Usage examples:
```bash
# Enable live model discovery with custom refresh interval
export AGENT_MODEL_DISCOVERY_ENABLED=true
export AGENT_MODEL_DISCOVERY_REFRESH_SECONDS=3600

# Restrict DashScope to specific models
export DASHSCOPE_MODELS=qwen3.8-max,qwen3.7-plus,qwen-turbo

# Set default model for provider
export DASHSCOPE_MODEL_NAME=qwen3.8-max

# Disable discovery for stable model lineup
export AGENT_MODEL_DISCOVERY_ENABLED=false
```

**Section sources**
- [products/agent-platform/src/agent_service/services/model_catalog.py](file://products/agent-platform/src/agent_service/services/model_catalog.py)
- [products/agent-platform/src/agent_service/providers/deepseek.py](file://products/agent-platform/src/agent_service/providers/deepseek.py)
- [products/agent-platform/src/agent_service/providers/dashscope.py](file://products/agent-platform/src/agent_service/providers/dashscope.py)
- [shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env](file://shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env)
- [shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [shared/platform-ops/gitops/runtime-profiles/README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)