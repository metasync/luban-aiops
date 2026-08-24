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
- [default configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [default kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml)
- [default runtime-secrets.example.env](file://shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env)
- [mutating-dev kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml)
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
- Updated runtime profiles section to reflect simplified structure from per-provider directories to single generic default profile
- Revised provider configuration approach from directory-based selection to ConfigMap-based multi-provider setup
- Updated script references and workflows to match current implementation
- Enhanced multi-model catalog documentation for SPEC-026 support
- Clarified mutating-dev profile separation from LLM provider profiles

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
This document explains the GitOps workflow for the Luban AIOps Platform, focusing on a Git-based deployment pipeline using Kustomize overlays and runtime profiles. It covers how to manage different deployment environments through Git branches and overlays, configure AI providers at runtime using a unified profile system, manage secrets with GitOps practices, automate synchronization, and verify deployments. The system uses a simplified runtime profile structure where a single generic profile manages multiple AI providers (OpenAI, DashScope, DeepSeek) through ConfigMap configuration rather than separate provider-specific directories.

## Project Structure
The GitOps assets are organized under shared/platform-ops/gitops:
- dev-k8s: Base Kubernetes manifests and environment-specific overlays for local or development clusters.
- runtime-profiles: Unified runtime profile configuration with a single default profile supporting multiple AI providers, plus a mutating-dev profile for development tooling.
- Scripts: Utilities to select profiles, apply overlays, sync secrets, and verify profiles.

```mermaid
graph TB
subgraph "GitOps Assets"
A["dev-k8s<br/>base + overlay"] --> B["Kustomize build"]
C["runtime-profiles<br/>default + mutating-dev"] --> B
D["Scripts<br/>deploy-overlay.sh<br/>select-runtime-profile.sh<br/>sync-runtime-secret.sh<br/>verify-runtime-profile.sh"] --> B
end
B --> E["Cluster State<br/>Namespace + Services + Deployments"]
F["ConfigMaps<br/>platform-runtime-config<br/>platform-policy<br/>agent-platform-runtime-profile"] --> G["Rolling Restarts<br/>All Deployments"]
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
- Runtime profiles: A unified profile system with a single default profile that manages multiple AI providers through ConfigMap configuration, plus a separate mutating-dev profile for development tooling.
- Automation scripts:
  - deploy-overlay.sh: Applies Kustomize overlays to the cluster with enhanced convergence behavior.
  - select-runtime-profile.sh: Selects and applies a runtime profile.
  - sync-runtime-secret.sh: Syncs provider secrets into the cluster securely.
  - verify-runtime-profile.sh: Validates that the active profile is correctly applied.

Key responsibilities:
- Environment isolation via Git branches and overlays.
- Multi-provider configuration via unified runtime profiles with ConfigMap-based provider selection.
- Secret injection without committing sensitive values.
- Automated sync and verification to ensure desired state.
- Automatic detection of runtime configuration changes and coordinated rolling restarts across all services.

**Section sources**
- [kustomization.yaml](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [deploy-overlay.sh](file://shared/platform-ops/gitops/deploy-overlay.sh)
- [select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)

## Architecture Overview
The GitOps flow uses Git as the source of truth. Changes pushed to specific branches trigger builds that render Kustomize templates and apply them to target clusters. The unified runtime profile system allows configuring multiple AI providers within a single deployment through ConfigMap settings, eliminating the need for separate provider-specific directories. Enhanced deployment convergence ensures that when runtime configuration changes are detected, all dependent services are automatically restarted to pick up new settings.

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
CI->>Kust : Build overlays + unified profile
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

### Unified Runtime Profiles for Multiple AI Providers

**Updated** The runtime profile system has been simplified from per-provider directories to a unified approach where a single default profile manages multiple AI providers through ConfigMap configuration.

#### Profile Structure
The current runtime profile structure consists of:
- **default**: A generic profile that supports multiple AI providers through ConfigMap settings
- **mutating-dev**: A separate profile for development tooling (not an LLM provider profile)

Each profile contains:
- A Kustomization file to include ConfigMaps and other resources
- A ConfigMap defining runtime settings including provider configuration
- Example secret files for secure secret management

```mermaid
classDiagram
class Profile {
+name string
+configmap ConfigMap
+secrets_example env_file
+supports_multiple_providers boolean
}
class DefaultProfile {
+provider_selection ConfigMap_based
+multi_model_catalog true
+supported_providers dashscope, deepseek, openai
}
class MutatingDevProfile {
+purpose development_tooling
+llm_provider false
+tools_enabled true
}
Profile <|-- DefaultProfile
Profile <|-- MutatingDevProfile
```

**Diagram sources**
- [default configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [default kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml)
- [mutating-dev kustomization.yaml](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml)

#### Multi-Provider Configuration
The unified profile system enables configuring multiple AI providers within a single deployment:

- **ConfigMap-based Provider Selection**: Provider selection is controlled through `AGENTSCOPE_PROVIDER` in the `agent-platform-runtime-profile` ConfigMap
- **Multi-Model Catalog**: Each supported provider with API keys joins the model catalog with curated model series
- **Credential-Gated Access**: Providers without resolvable API keys are dropped (fail-closed)
- **Flexible Model Selection**: Per-provider model restrictions via `<PROVIDER>_MODELS` environment variables

**Section sources**
- [runtime profiles README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)
- [default configmap.yaml](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [default runtime-secrets.example.env](file://shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env)

### Enhanced Deployment Convergence Behavior

**Updated** The deploy-overlay.sh script includes intelligent deployment convergence that automatically detects when runtime configuration changes occur and coordinates rolling restarts across all application deployments.

#### ConfigMap Change Detection
The script monitors Kustomize apply output for changes to three critical ConfigMaps:
- `platform-runtime-config`: Contains runtime configuration parameters consumed by services via envFrom
- `platform-policy`: Contains authorization policies mounted as volumes to gateway services
- `agent-platform-runtime-profile`: Contains AI provider configuration (new addition)

When any of these ConfigMaps are updated, the script triggers coordinated rolling restarts of all eight application deployments to ensure consistent configuration propagation:

```mermaid
sequenceDiagram
participant Script as "deploy-overlay.sh"
participant Kubectl as "kubectl"
participant Deployments as "Application Deployments"
Script->>Kubectl : Apply Kustomize manifests
Kubectl-->>Script : Return apply status
Script->>Script : Parse output for ConfigMap changes
alt platform-runtime-config, platform-policy, or agent-platform-runtime-profile changed
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

- **Services consuming agent-platform-runtime-profile**:
  - agent-service: Reads AI provider configuration from the profile ConfigMap

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
- Configure multiple provider credentials in a single secrets file for multi-provider deployments.

**Section sources**
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [runtime profiles README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)
- [default runtime-secrets.example.env](file://shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env)

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
Script->>Kust : Build overlays + unified profile
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
- Coordinated rollout management for configuration convergence.

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
- Rolling restarts are coordinated to minimize downtime during configuration updates.
- ConfigMap change detection prevents unnecessary restarts when no runtime configuration has changed.
- Multi-provider configuration reduces deployment complexity compared to separate provider-specific deployments.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- Profile mismatch: Ensure the selected runtime profile matches the intended provider configuration. Use verify-runtime-profile.sh to validate.
- Missing secrets: Confirm secrets are synced to the correct namespace before applying overlays.
- Overlay conflicts: Review Kustomize patches for overlapping changes; resolve naming or selector mismatches.
- Health check failures: Inspect pod logs and events after apply; confirm external dependencies (e.g., Redis) are reachable.
- Configuration not taking effect: If runtime configuration changes don't appear to take effect, check if rolling restarts were triggered by examining deploy-overlay.sh output for ConfigMap change detection messages.
- Stale configuration in pods: Verify that platform-runtime-config, platform-policy, and agent-platform-runtime-profile ConfigMaps were properly updated and that all deployments received rolling restart signals.
- Partial rollout failures: Monitor rollout status for each deployment individually using kubectl rollout status commands if the automated status checks fail.
- Multi-provider issues: When configuring multiple AI providers, verify that each provider has proper API keys configured and that the AGENTSCOPE_PROVIDER setting points to the intended active provider.

Useful commands:
- Rebuild and preview manifests locally before pushing.
- Run verification script to assert profile and resource states.
- Check namespace and resource existence post-apply.
- Check ConfigMap contents: `kubectl get configmap platform-runtime-config -o yaml`
- Check runtime profile ConfigMap: `kubectl get configmap agent-platform-runtime-profile -o yaml`
- Verify rollout status: `kubectl rollout status deployment/<service-name>`
- Force restart if needed: `kubectl rollout restart deployment/<service-name>`

**Section sources**
- [verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [sync-runtime-secret.sh](file://shared/platform-ops/gitops/sync-runtime-secret.sh)
- [deploy-overlay.sh:66-73](file://shared/platform-ops/gitops/deploy-overlay.sh#L66-L73)

## Conclusion
The Luban AIOps Platform's GitOps workflow leverages Kustomize overlays and a unified runtime profile system to deliver consistent, secure, and multi-provider-flexible deployments across environments. The simplified profile structure eliminates the complexity of managing separate provider-specific directories while enabling powerful multi-provider configurations through ConfigMap settings. Enhanced deployment convergence behavior ensures that runtime configuration changes are automatically detected and propagated across all services through coordinated rolling restarts. By separating base manifests from overlays and centralizing provider configuration into a unified profile system, teams can collaborate effectively while maintaining strong security practices around secrets. Automation scripts streamline the process, enabling reliable synchronization, verification, and configuration convergence.

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
- Configuration change management:
  - Test runtime configuration changes in development before production deployment.
  - Monitor rollout status after configuration updates to ensure successful convergence.
  - Document significant runtime configuration changes in commit messages for traceability.
  - For multi-provider setups, document which providers are enabled and their purposes.

**Section sources**
- [README.md](file://README.md)

### Runtime Configuration Reference
The following ConfigMaps are managed by the GitOps workflow:

- **platform-runtime-config**: Contains runtime parameters consumed by services via environment variables
- **platform-policy**: Authorization policy bundle mounted as a file to gateway services
- **agent-platform-runtime-profile**: Unified profile containing AI provider configuration including provider selection, model settings, and base URLs

**Section sources**
- [policy manifest:1-177](file://shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml#L1-L177)
- [default configmap.yaml:1-11](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml#L1-L11)

### Multi-Provider Configuration Examples
The unified runtime profile supports configuring multiple AI providers simultaneously:

```bash
# Example runtime-secrets.env for multiple providers
AGENTSCOPE_API_KEY=your-default-provider-key
DASHSCOPE_API_KEY=your-dashscope-key
OPENAI_API_KEY=your-openai-key
DEEPSEEK_API_KEY=your-deepseek-key

# Optional per-provider model restrictions
DASHSCOPE_MODELS=qwen-plus,qwen-max
DEEPSEEK_MODELS=deepseek-chat,deepseek-reasoner
OPENAI_MODELS=gpt-4,gpt-3.5-turbo
```

**Section sources**
- [default runtime-secrets.example.env:1-23](file://shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env#L1-L23)