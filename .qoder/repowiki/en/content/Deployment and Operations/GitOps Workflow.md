# GitOps Workflow

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [dev-k8s README.md](file://shared/platform-ops/gitops/dev-k8s/README.md)
- [runtime profiles README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)
- [openai kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/openai/kustomization.yaml)
- [dashscope kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/dashscope/kustomization.yaml)
- [deepseek kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/deepseek/kustomization.yaml)
- [agent-platform deployment](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [identity-broker deployment](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [tool-gateway deployment](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [platform-gateway deployment](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [web-ui deployment](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)
- [audit-service deployment](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [incident-service deployment](file://shared/platform-ops/gitops/dev-k8s/base/incident-service/incident-service-deployment.yaml)
- [skills-hub deployment](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [infra redis deployment](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml)
- [namespace manifest](file://shared/platform-ops/gitops/dev-k8s/base/shared/namespace.yaml)
- [policy manifest](file://shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml)
</cite>

## Update Summary
**Changes Made**
- Enhanced deployment convergence behavior section with automatic ConfigMap change detection
- Updated rolling restart mechanism for all application deployments when runtime configuration changes
- Added detailed explanation of platform-runtime-config and platform-policy ConfigMap handling
- Expanded troubleshooting guide with ConfigMap-related issues

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
This document explains the GitOps workflow for the Luban AIOps Platform, focusing on a Git-based deployment pipeline using Kustomize overlays and runtime profiles. It covers how to manage different deployment environments through Git branches and overlays, configure AI providers at runtime (OpenAI, DashScope, DeepSeek), manage secrets with GitOps practices, automate synchronization, and verify deployments. The system now includes enhanced deployment convergence behavior that automatically detects runtime configuration changes and triggers rolling restarts to ensure proper configuration propagation across all services.

## Project Structure
The GitOps assets are organized under shared/platform-ops/gitops:
- dev-k8s: Base Kubernetes manifests and environment-specific overlays for local or development clusters.
- runtime-profiles: Provider-specific configurations for OpenAI, DashScope, and DeepSeek.
- Scripts: Utilities to select profiles, apply overlays, sync secrets, and verify profiles.

```mermaid
graph TB
subgraph "GitOps Assets"
A["dev-k8s<br/>base + overlay"] --> B["Kustomize build"]
C["runtime-profiles<br/>openai/dashscope/deepseek"] --> B
D["Scripts<br/>deploy-overlay.sh<br/>select-runtime-profile.sh<br/>sync-runtime-secret.sh<br/>verify-runtime-profile.sh"] --> B
end
B --> E["Cluster State<br/>Namespace + Services + Deployments"]
F["ConfigMaps<br/>platform-runtime-config<br/>platform-policy"] --> G["Rolling Restarts<br/>All Deployments"]
G --> E
```

**Diagram sources**
- [kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)

**Section sources**
- [dev-k8s README.md](file://shared/platform-ops/gitops/dev-k8s/README.md)
- [runtime profiles README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)

## Core Components
- Kustomize base and overlays: The base defines common resources (namespaces, services, deployments). Overlays enable per-environment customizations.
- Runtime profiles: Provider-specific ConfigMaps and example secret files that inject runtime configuration into applications.
- Automation scripts:
  - deploy-overlay.sh: Applies Kustomize overlays to the cluster with enhanced convergence behavior.
  - select-runtime-profile.sh: Selects and applies a runtime profile.
  - sync-runtime-secret.sh: Syncs provider secrets into the cluster securely.
  - verify-runtime-profile.sh: Validates that the active profile is correctly applied.

Key responsibilities:
- Environment isolation via Git branches and overlays.
- Provider selection via runtime profiles.
- Secret injection without committing sensitive values.
- Automated sync and verification to ensure desired state.
- **Enhanced**: Automatic detection of runtime configuration changes and coordinated rolling restarts across all services.

**Section sources**
- [kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)

## Architecture Overview
The GitOps flow uses Git as the source of truth. Changes pushed to specific branches trigger builds that render Kustomize templates and apply them to target clusters. Runtime profiles allow switching AI providers without changing application code. The enhanced deployment convergence ensures that when runtime configuration changes are detected, all dependent services are automatically restarted to pick up new settings.

```mermaid
sequenceDiagram
participant Dev as "Developer"
participant Git as "Git Repository"
participant CI as "CI/CD Pipeline"
participant Kust as "Kustomize"
participant Script as "deploy-overlay.sh"
participant Cluster as "Kubernetes Cluster"
Dev->>Git : Push changes to branch (env/profile)
Git-->>CI : Webhook / Poll
CI->>Kust : Build overlays + runtime profile
Kust-->>CI : Rendered manifests
CI->>Script : Apply with convergence detection
Script->>Cluster : Apply manifests
Cluster-->>Script : Apply status
Script->>Script : Detect ConfigMap changes
alt ConfigMap changed
Script->>Cluster : Rolling restart all deployments
else No changes
Script->>Cluster : Status check only
end
Cluster-->>CI : Status and health checks
CI-->>Dev : Deployment result and verification report
```

[No sources needed since this diagram shows conceptual workflow, not actual code structure]

## Detailed Component Analysis

### Kustomize Base and Overlay Strategy
- Base manifests define core platform components:
  - Agent Platform service and deployment
  - Identity Broker service and deployment
  - Tool Gateway service and deployment
  - Platform Gateway service and deployment
  - Audit Service service and deployment
  - Incident Service service and deployment
  - Skills Hub service and deployment
  - Web UI service and deployment
  - Shared infrastructure (e.g., Redis)
  - Namespace and shared configuration
- Overlays customize resources per environment (e.g., replicas, image tags, config mounts).

```mermaid
flowchart TD
Start(["Start"]) --> ReadBase["Read base manifests"]
ReadBase --> ReadOverlay["Read overlay patches"]
ReadOverlay --> Merge["Merge and resolve references"]
Merge --> Validate{"Validation passed?"}
Validate --> |No| Fix["Fix errors and re-run"]
Validate --> |Yes| Apply["Apply to cluster"]
Apply --> CheckCM{"ConfigMap changes?"}
CheckCM --> |Yes| Restart["Rolling restart all deployments"]
CheckCM --> |No| Verify["Verify resources"]
Restart --> Verify
Verify --> End(["Done"])
```

**Diagram sources**
- [kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)

**Section sources**
- [agent-platform deployment](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml)
- [identity-broker deployment](file://shared/platform-ops/gitops/dev-k8s/base/identity-broker/identity-service-deployment.yaml)
- [tool-gateway deployment](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
- [platform-gateway deployment](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml)
- [audit-service deployment](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml)
- [incident-service deployment](file://shared/platform-ops/gitops/dev-k8s/base/incident-service/incident-service-deployment.yaml)
- [skills-hub deployment](file://shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml)
- [web-ui deployment](file://shared/platform-ops/gitops/dev-k8s/base/operator-portal/web-ui-deployment.yaml)
- [infra redis deployment](file://shared/platform-ops/gitops/dev-k8s/base/infra/redis-deployment.yaml)
- [namespace manifest](file://shared/platform-ops/gitops/dev-k8s/base/shared/namespace.yaml)

### Runtime Profiles for AI Providers
Runtime profiles encapsulate provider-specific configuration and secrets:
- openai: Configuration and example secrets for OpenAI integration.
- dashscope: Configuration and example secrets for DashScope integration.
- deepseek: Configuration and example secrets for DeepSeek integration.

Each profile contains:
- A Kustomization file to patch ConfigMaps and environment variables.
- A ConfigMap defining runtime settings.
- An example secrets file template for secure secret management.

```mermaid
classDiagram
class Profile {
+name string
+configmap ConfigMap
+secrets_example env_file
}
class OpenAI {
+provider string
+api_key_ref string
}
class DashScope {
+provider string
+api_key_ref string
}
class DeepSeek {
+provider string
+api_key_ref string
}
Profile <|-- OpenAI
Profile <|-- DashScope
Profile <|-- DeepSeek
```

**Diagram sources**
- [openai kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/openai/kustomization.yaml)
- [dashscope kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/dashscope/kustomization.yaml)
- [deepseek kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/deepseek/kustomization.yaml)

**Section sources**
- [runtime profiles README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)
- [openai kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/openai/kustomization.yaml)
- [dashscope kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/dashscope/kustomization.yaml)
- [deepseek kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/deepseek/kustomization.yaml)

### Enhanced Deployment Convergence Behavior

**Updated** The deploy-overlay.sh script now includes intelligent deployment convergence that automatically detects when runtime configuration changes occur and coordinates rolling restarts across all application deployments.

#### ConfigMap Change Detection
The script monitors Kustomize apply output for changes to two critical ConfigMaps:
- `platform-runtime-config`: Contains runtime configuration parameters consumed by services via envFrom
- `platform-policy`: Contains authorization policies mounted as volumes to gateway services

When either ConfigMap is updated, the script triggers coordinated rolling restarts of all eight application deployments to ensure consistent configuration propagation:

```mermaid
sequenceDiagram
participant Script as "deploy-overlay.sh"
participant Kubectl as "kubectl"
participant Deployments as "Application Deployments"
Script->>Kubectl : Apply Kustomize manifests
Kubectl-->>Script : Return apply status
Script->>Script : Parse output for ConfigMap changes
alt platform-runtime-config or platform-policy changed
Script->>Deployments : Rollout restart web-ui
Script->>Deployments : Rollout restart platform-gateway
Script->>Deployments : Rollout restart tool-gateway
Script->>Deployments : Rollout restart agent-service
Script->>Deployments : Rollout restart identity-service
Script->>Deployments : Rollout restart audit-service
Script->>Deployments : Rollout restart skills-hub
Script->>Deployments : Rollout restart incident-service
else No ConfigMap changes
Script->>Script : Skip restart phase
end
```

**Diagram sources**
- [deploy-overlay.sh:66-73](file://shared/platform-ops/gitops/deploy-overlay.sh#L66-L73)

#### Affected Deployments and Configuration Consumption
Each deployment consumes runtime configuration differently:

- **Services using envFrom with platform-runtime-config**:
  - agent-service: Consumes runtime parameters via environment variables
  - platform-gateway: Uses runtime config for gateway behavior
  - tool-gateway: Applies runtime settings for tool execution
  - audit-service: Reads audit configuration from runtime config
  - identity-service: Uses runtime settings for authentication
  - incident-service: Consumes incident processing parameters
  - skills-hub: Reads skill processing configuration

- **Services mounting platform-policy as volume**:
  - platform-gateway: Mounts policy file at /etc/luban/policy
  - tool-gateway: Mounts policy file at /etc/luban/policy

- **Services requiring restart for configuration updates**:
  - web-ui: Frontend portal that may need restart for configuration changes
  - All other services: Require restart to pick up new ConfigMap values

**Section sources**
- [deploy-overlay.sh:66-73](file://shared/platform-ops/gitops/deploy-overlay.sh#L66-L73)
- [agent-platform deployment:32-39](file://shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml#L32-L39)
- [platform-gateway deployment:33-48](file://shared/platform-ops/gitops/dev-k8s/base/platform-gateway/platform-gateway-deployment.yaml#L33-L48)
- [tool-gateway deployment:33-48](file://shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml#L33-L48)
- [audit-service deployment:32-37](file://shared/platform-ops/gitops/dev-k8s/base/audit-service/audit-service-deployment.yaml#L32-L37)

### Secret Management with GitOps
Secrets should never be committed directly. Use one of these approaches:
- External secret stores (e.g., Kubernetes Secrets Manager, Vault) synced by operators.
- Sealed Secrets or SOPS encrypted files stored in Git; decrypted at deploy time.
- Local-only secret files referenced by sync scripts but excluded from version control.

Recommended practice:
- Store only example templates in Git (e.g., runtime-secrets.example.env).
- Maintain real secrets outside Git and sync them via CI/CD or a dedicated operator.
- Use namespace-scoped secrets aligned with platform components.

**Section sources**
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [runtime profiles README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)

### Automated Sync and Verification Workflows
- deploy-overlay.sh: Builds and applies Kustomize overlays for the selected environment with enhanced convergence detection.
- select-runtime-profile.sh: Switches the active runtime profile and updates ConfigMaps/env.
- sync-runtime-secret.sh: Ensures provider secrets exist in the target namespace.
- verify-runtime-profile.sh: Checks that the correct profile is applied and resources are healthy.

```mermaid
sequenceDiagram
participant Dev as "Developer"
participant Script as "deploy-overlay.sh"
participant Kust as "Kustomize"
participant Cluster as "Kubernetes Cluster"
Dev->>Script : Run with env and profile flags
Script->>Kust : Build overlays + profile
Kust-->>Script : Rendered manifests
Script->>Cluster : Apply manifests
Cluster-->>Script : Apply status
Script->>Script : Check for ConfigMap changes
alt ConfigMap changed
Script->>Cluster : Trigger rolling restarts
end
Cluster-->>Script : Rollout status
Script-->>Dev : Success/failure output
```

**Diagram sources**
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)

**Section sources**
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)

## Dependency Analysis
The GitOps layer depends on:
- Kustomize for templating and patching.
- Kubernetes API for applying manifests.
- CI/CD system for automation and validation.
- External secret managers for secure secret handling.
- **Enhanced**: Coordinated rollout management for configuration convergence.

```mermaid
graph TB
Git["Git Repo"] --> CI["CI/CD"]
CI --> Kust["Kustomize"]
Kust --> K8s["Kubernetes API"]
CI --> Secrets["Secret Manager"]
Secrets --> K8s
K8s --> Apps["Platform Services"]
K8s --> CM["ConfigMaps"]
CM --> Rollout["Rollout Controller"]
Rollout --> Apps
```

[No sources needed since this diagram shows conceptual dependencies, not direct code mapping]

**Section sources**
- [kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)

## Performance Considerations
- Keep base manifests minimal and reusable; use overlays for targeted changes.
- Avoid large diffs across overlays; prefer small, focused commits.
- Cache Kustomize builds in CI to speed up pipelines.
- Limit secret sync operations to necessary namespaces and resources.
- Use readiness/liveness probes in deployments to accelerate health checks.
- **Enhanced**: Rolling restarts are coordinated to minimize downtime during configuration updates.
- **Enhanced**: ConfigMap change detection prevents unnecessary restarts when no runtime configuration has changed.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Profile mismatch: Ensure the selected runtime profile matches the intended provider. Use verify-runtime-profile.sh to validate.
- Missing secrets: Confirm secrets are synced to the correct namespace before applying overlays.
- Overlay conflicts: Review Kustomize patches for overlapping changes; resolve naming or selector mismatches.
- Health check failures: Inspect pod logs and events after apply; confirm external dependencies (e.g., Redis) are reachable.
- **New**: Configuration not taking effect: If runtime configuration changes don't appear to take effect, check if rolling restarts were triggered by examining deploy-overlay.sh output for ConfigMap change detection messages.
- **New**: Stale configuration in pods: Verify that platform-runtime-config and platform-policy ConfigMaps were properly updated and that all deployments received rolling restart signals.
- **New**: Partial rollout failures: Monitor rollout status for each deployment individually using kubectl rollout status commands if the automated status checks fail.

Useful commands:
- Rebuild and preview manifests locally before pushing.
- Run verification script to assert profile and resource states.
- Check namespace and resource existence post-apply.
- **New**: Check ConfigMap contents: `kubectl get configmap platform-runtime-config -o yaml`
- **New**: Verify rollout status: `kubectl rollout status deployment/<service-name>`
- **New**: Force restart if needed: `kubectl rollout restart deployment/<service-name>`

**Section sources**
- [verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [deploy-overlay.sh:66-73](file://shared/platform-ops/gitops/deploy-overlay.sh#L66-L73)

## Conclusion
The Luban AIOps Platform's GitOps workflow leverages Kustomize overlays and runtime profiles to deliver consistent, secure, and provider-flexible deployments across environments. The enhanced deployment convergence behavior ensures that runtime configuration changes are automatically detected and propagated across all services through coordinated rolling restarts. By separating base manifests from overlays and isolating provider configuration into profiles, teams can collaborate effectively while maintaining strong security practices around secrets. Automation scripts streamline the process, enabling reliable synchronization, verification, and configuration convergence.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Best Practices for Version Control and Change Management
- Branch strategy:
  - main: Stable baseline with validated overlays.
  - feature/*: Experimental changes and new overlays.
  - release/*: Tagged releases with pinned images and profiles.
- Commit hygiene:
  - Small, atomic commits with clear messages.
  - Separate changes to overlays, profiles, and scripts.
- Review process:
  - Require PR reviews for overlay and profile changes.
  - Enforce automated checks (lint, test, verify).
- Collaboration:
  - Use issue templates and PR templates for consistency.
  - Document environment-specific decisions in overlay comments.
- **Enhanced**: Configuration change management:
  - Test runtime configuration changes in development before production deployment.
  - Monitor rollout status after configuration updates to ensure successful convergence.
  - Document significant runtime configuration changes in commit messages for traceability.

**Section sources**
- [README.md](file://README.md)

### Runtime Configuration Reference
The following ConfigMaps are managed by the GitOps workflow:

- **platform-runtime-config**: Contains runtime parameters consumed by services via environment variables
- **platform-policy**: Authorization policy bundle mounted as a file to gateway services
- **agent-platform-runtime-profile**: Provider-specific configuration for agent platform services

**Section sources**
- [policy manifest:1-177](file://shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml#L1-L177)
- [openai configmap:1-10](file://shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml#L1-L10)