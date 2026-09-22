# Runtime Profiles

<cite>
**Referenced Files in This Document**
- [README.md](file://shared/platform-ops/gitops/runtime-profiles/README.md)
- [select-runtime-profile.sh](file://shared/platform-ops/gitops/select-runtime-profile.sh)
- [verify-runtime-profile.sh](file://shared/platform-ops/gitops/verify-runtime-profile.sh)
- [kustomization.yaml (default)](file://shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml)
- [configmap.yaml (default)](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml)
- [kustomization.yaml (browser-dev)](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml)
- [browser.env (browser-dev)](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env)
- [tool-gateway-browser-sidecar.yaml](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml)
- [browser-sidecar-network-policy.yaml](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml)
- [kustomization.yaml (mutating-dev)](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml)
- [mutating.env (mutating-dev)](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env)
- [tool-gateway-pod-delete.yaml](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml)
- [secrets.env (secrets-dev)](file://shared/platform-ops/gitops/runtime-profiles/secrets-dev/secrets.env)
- [kustomization.yaml (dev-k8s)](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml)
- [config.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/core/config.py)
- [app.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/app.py)
- [password-policy.yaml (contract)](file://shared/shared-contracts/policies/password-policy.yaml)
</cite>

## Update Summary
**Changes Made**
- Added secrets-dev runtime profile section documenting development-time password generation capabilities without email delivery
- Updated dev-k8s overlay configuration to include the new secrets-dev posture overlay
- Enhanced architecture diagrams to show the fourth posture layer for secret generation
- Updated troubleshooting guidance to cover secrets-enabled scenarios and password policy validation
- Added security considerations for the secrets-dev profile's read-tier-only posture

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
This document explains the runtime profiles system that customizes platform behavior for different operational scenarios. It covers:
- The default profile for standard deployments, which sets a generic agent profile and provider configuration.
- The browser-dev profile for web automation testing with a Playwright-compatible sidecar and posture configuration only (sample targets are deployed out-of-band).
- The mutating-dev profile for testing write operations with elevated permissions scoped to bounded actions.
- **New**: The secrets-dev profile for enabling development-time password generation capabilities without email delivery, providing secure credential generation through the portal-copy handoff mechanism.

It also documents how each profile configures security policies, network policies, resource allocations, and service integrations; how tool execution policies and approval workflows are affected; and how to use the select and verify scripts to switch and validate profiles. Finally, it provides guidance for creating custom profiles and understanding their security implications.

## Project Structure
Runtime profiles are implemented as Kustomize overlays under shared/platform-ops/gitops/runtime-profiles. Each profile directory contributes resources and environment variables that the dev-k8s overlay merges into the running platform. Three "posture" profiles (mutating-dev, browser-dev, and secrets-dev) are always wired into dev-k8s alongside the active LLM provider profile. A fourth profile (default) is the current LLM provider profile used by dev-k8s.

```mermaid
graph TB
subgraph "dev-k8s overlay"
D["dev-k8s/kustomization.yaml"]
end
subgraph "runtime-profiles"
DEF["default/"]
BR["browser-dev/"]
MUT["mutating-dev/"]
SEC["secrets-dev/"]
end
D --> DEF
D --> BR
D --> MUT
D --> SEC
```

**Diagram sources**
- [kustomization.yaml (dev-k8s):5-15](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml#L5-L15)
- [kustomization.yaml (browser-dev):22-28](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml#L22-L28)
- [kustomization.yaml (mutating-dev):18-21](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml#L18-L21)
- [kustomization.yaml (default):1-5](file://shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml#L1-L5)

**Section sources**
- [README.md:1-18](file://shared/platform-ops/gitops/runtime-profiles/README.md#L1-L18)
- [select-runtime-profile.sh:14-55](file://shared/platform-ops/gitops/select-runtime-profile.sh#L14-L55)

## Core Components
- Default profile: Provides a ConfigMap that labels the deployment with a generic profile and selects an LLM provider and model.
- Browser-dev posture: Adds a headless browser sidecar to the tool-gateway Deployment, mounts credential sets, and restricts network access to the CDP port. Sample target applications are deployed out-of-band via `make deploy-sample-app`.
- Mutating-dev posture: Grants a minimal RBAC Role/RoleBinding for deleting pods in the dev namespace and enables mutating tools via a ConfigMap flag.
- **New**: Secrets-dev posture: Enables secure password generation through the `secrets.generate_password` tool with one-time portal-copy handoff, without email delivery capabilities.

These components affect:
- Security policies: Deny-by-default posture unless explicitly enabled by a profile.
- Network policies: Restrict cross-pod access to the browser's debugging port.
- Resource allocations: Sidecar CPU/memory requests and limits.
- Service integrations: Tool-gateway integration with the browser sidecar, optional credentials, and secret delivery buffer.

**Section sources**
- [configmap.yaml (default):1-11](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml#L1-L11)
- [browser.env (browser-dev):1-11](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env#L1-L11)
- [tool-gateway-browser-sidecar.yaml:1-67](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml#L1-L67)
- [browser-sidecar-network-policy.yaml:1-31](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml#L1-L31)
- [mutating.env (mutating-dev):1-4](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env#L1-L4)
- [tool-gateway-pod-delete.yaml:1-48](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml#L1-L48)
- [secrets.env (secrets-dev):1-15](file://shared/platform-ops/gitops/runtime-profiles/secrets-dev/secrets.env#L1-L15)

## Architecture Overview
The dev-k8s overlay composes four layers at build time:
- Base platform manifests.
- One active LLM provider profile (currently default).
- Always-on posture overlays: mutating-dev, browser-dev, and secrets-dev.

The select script writes a new dev-k8s/kustomization.yaml that includes the chosen profile while preserving all posture overlays. The verify script reports the active profile and validates that kustomize can render the overlay without errors.

```mermaid
sequenceDiagram
participant Dev as "Developer"
participant Sel as "select-runtime-profile.sh"
participant Kum as "dev-k8s/kustomization.yaml"
participant Prof as "runtime-profiles/<profile>"
participant PostM as "runtime-profiles/mutating-dev"
participant PostB as "runtime-profiles/browser-dev"
participant PostS as "runtime-profiles/secrets-dev"
Dev->>Sel : Run with <profile>
Sel->>Kum : Write resources list
Note over Sel,Kum : Always include mutating-dev, browser-dev, and secrets-dev
Sel->>Prof : Include selected profile
Sel->>PostM : Include posture overlay
Sel->>PostB : Include posture overlay
Sel->>PostS : Include posture overlay
Dev->>Sel : Verify
Sel->>Kum : Render with kubectl kustomize
Kum-->>Dev : Success or error
```

**Diagram sources**
- [select-runtime-profile.sh:30-52](file://shared/platform-ops/gitops/select-runtime-profile.sh#L30-L52)
- [verify-runtime-profile.sh:8-23](file://shared/platform-ops/gitops/verify-runtime-profile.sh#L8-L23)
- [kustomization.yaml (dev-k8s):5-15](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml#L5-L15)

**Section sources**
- [select-runtime-profile.sh:14-55](file://shared/platform-ops/gitops/select-runtime-profile.sh#L14-L55)
- [verify-runtime-profile.sh:1-24](file://shared/platform-ops/gitops/verify-runtime-profile.sh#L1-L24)

## Detailed Component Analysis

### Default Profile
Purpose:
- Declares a generic deploy-time profile label and selects an LLM provider and model through a ConfigMap consumed by the agent platform.

Configuration highlights:
- Sets AGENTSCOPE_PROFILE, AGENTSCOPE_PROVIDER, AGENTSCOPE_MODEL_NAME, and base URL.
- Is included as one of exactly one LLM provider profile at a time in dev-k8s.

Security and policy impact:
- Does not enable mutating tools, browser features, or secret generation by itself.
- Provider selection is decoupled from the profile label, allowing any provider mix within the same profile.

**Section sources**
- [README.md:5-18](file://shared/platform-ops/gitops/runtime-profiles/README.md#L5-L18)
- [configmap.yaml (default):1-11](file://shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml#L1-L11)
- [kustomization.yaml (default):1-5](file://shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml#L1-L5)

### Browser-Dev Profile (Web Automation Testing)
**Updated** The browser-dev profile now functions purely as a posture configuration without shipping sample target applications. Sample targets like `acme-admin` are deployed out-of-band using `make deploy-sample-app`.

Purpose:
- Enables browser-based web checks in dev by adding a headless browser sidecar to the tool-gateway pod and providing posture configuration for secure browser automation.

Key configurations:
- Environment variables merged into platform-runtime-config:
  - Enable browser connector (`GATEWAY_BROWSER_ENABLED=true`).
  - Define CDP endpoint on loopback (`ws://localhost:9222`).
  - Allow only the `acme-admin` origin (`http://acme-admin:8080`).
  - Mount named credential sets for web logins.
- Strategic merge patch adds:
  - Chromium headless sidecar bound to loopback on a fixed port.
  - Credential secret volume mount on the gateway container.
  - Resource requests/limits for the sidecar.
- Network policy:
  - Explicitly allows HTTP ingress to the gateway.
  - Denies ingress to the CDP port from other pods (defense-in-depth).

Sample targets:
- Deployed out-of-band via `make deploy-sample-app` (SPEC-059).
- The `acme-admin` application serves as the primary test target.
- No longer ships static mock applications like `browser-check-target` (retired by SPEC-061).

Tool execution and approvals:
- Browser tools are gated by feature enablement and allowlist.
- Named credential sets are mounted but optional; missing credentials fail closed at call time.
- Only configured origins (currently just `acme-admin`) are allowed for navigation.

Security boundaries:
- CDP is bound to loopback and protected by a NetworkPolicy.
- Only configured origins are allowed for navigation.
- Sample targets must be deployed separately and are not part of the profile's scope.

```mermaid
flowchart TD
Start(["Browser tool invoked"]) --> CheckEnv["Check GATEWAY_BROWSER_ENABLED"]
CheckEnv --> |False| Deny["Deny invocation"]
CheckEnv --> |True| CheckOrigin["Validate target origin against allowlist"]
CheckOrigin --> |Denied| Deny
CheckOrigin --> |Allowed| ConnectCDP["Connect to CDP on loopback:9222"]
ConnectCDP --> Credentials{"Credential set available?"}
Credentials --> |No| FailClosed["Fail closed at call time"]
Credentials --> |Yes| Navigate["Navigate to acme-admin or configured origin"]
Navigate --> End(["Result returned"])
Deny --> End
FailClosed --> End
```

**Diagram sources**
- [browser.env (browser-dev):1-11](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env#L1-L11)
- [tool-gateway-browser-sidecar.yaml:1-67](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml#L1-L67)
- [browser-sidecar-network-policy.yaml:1-31](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml#L1-L31)

**Section sources**
- [README.md:41-56](file://shared/platform-ops/gitops/runtime-profiles/README.md#L41-L56)
- [kustomization.yaml (browser-dev):1-29](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml#L1-L29)
- [browser.env (browser-dev):1-11](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env#L1-L11)
- [tool-gateway-browser-sidecar.yaml:1-67](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml#L1-L67)
- [browser-sidecar-network-policy.yaml:1-31](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml#L1-L31)

### Mutating-Dev Profile (Write Operations)
Purpose:
- Enables bounded mutating tools in dev by granting minimal RBAC and enabling the mutating tools flag.

Key configurations:
- Environment variable merged into platform-runtime-config to enable mutating tools.
- Role/RoleBinding limited to delete verb on pods in the dev namespace, scoped to the tool-gateway ServiceAccount.

Tool execution and approvals:
- Mutating invokes remain triple-gated: risk-tier admission, policy grant, and HITL confirmation.
- Activation requires the profile's environment variable, policy grants, RBAC applied, and HITL timeout configured.

Security boundaries:
- Minimal surface: only delete on pods in the dev namespace.
- No create/update/patch or access to other resources/namespaces.

```mermaid
flowchart TD
Start(["Mutating tool invoked"]) --> Flag{"GATEWAY_MUTATING_TOOLS_ENABLED?"}
Flag --> |False| Deny["Deny invocation"]
Flag --> |True| PolicyGrant{"tools:mutate granted?"}
PolicyGrant --> |No| Deny
PolicyGrant --> |Yes| RBAC{"RBAC permits delete pod?"}
RBAC --> |No| Deny
RBAC --> |Yes| HITL{"HITL confirmation required?"}
HITL --> |Required| Confirm["Await confirmation"]
Confirm --> Execute["Execute bounded mutation"]
HITL --> |Not required| Execute
Execute --> End(["Result returned"])
Deny --> End
```

**Diagram sources**
- [mutating.env (mutating-dev):1-4](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env#L1-L4)
- [tool-gateway-pod-delete.yaml:1-48](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml#L1-L48)
- [kustomization.yaml (mutating-dev):1-22](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml#L1-L22)

**Section sources**
- [README.md:29-39](file://shared/platform-ops/gitops/runtime-profiles/README.md#L29-L39)
- [kustomization.yaml (mutating-dev):1-22](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml#L1-L22)
- [mutating.env (mutating-dev):1-4](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env#L1-L4)
- [tool-gateway-pod-delete.yaml:1-48](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml#L1-L48)

### Secrets-Dev Profile (Secure Password Generation)
**New** The secrets-dev profile enables development-time password generation capabilities without email delivery, providing secure credential generation through the portal-copy handoff mechanism.

Purpose:
- Enables secure password generation in development environments through the `secrets.generate_password` tool, with values delivered via one-time portal-copy handoff rather than email.

Key configurations:
- Environment variable merged into platform-runtime-config:
  - Enable secrets connector (`GATEWAY_SECRETS_ENABLED=true`).
  - Password policy contract is already mounted via base platform-policy ConfigMap.
  - Email delivery remains disabled (no SMTP configuration).

Tool execution and approvals:
- Password generation is read-tier and does not require HITL confirmation.
- Generated passwords are stored in an ephemeral, single-use buffer with TTL expiration.
- Portal-copy handoff provides authenticated, one-time redemption without value exposure in transcripts.
- Email delivery fails closed with `EMAIL_NOT_CONFIGURED` until SMTP is provisioned out-of-band.

Security boundaries:
- Password policy enforcement ensures cryptographically secure generation meeting minimum requirements.
- One-time delivery prevents value persistence in conversation history or logs.
- Email channel remains disabled by default, requiring explicit SMTP configuration for delivery.
- Secret delivery buffer uses memory backend by default (single-replica, ephemeral).

```mermaid
flowchart TD
Start(["Password generation requested"]) --> CheckEnabled{"GATEWAY_SECRETS_ENABLED?"}
CheckEnabled --> |False| Deny["Deny invocation"]
CheckEnabled --> |True| Generate["Generate password per policy"]
Generate --> Validate["Validate against password-policy.yaml"]
Validate --> Buffer["Store in ephemeral delivery buffer"]
Buffer --> ReturnId["Return delivery_id to caller"]
ReturnId --> PortalCopy["Portal renders Copy password button"]
PortalCopy --> Redeem["Authenticated one-time redemption"]
Redeem --> Clipboard["Copy to clipboard"]
Clipboard --> Invalidate["Invalidate delivery handle"]
Invalidate --> End(["Password copied once"])
Deny --> End
```

**Diagram sources**
- [secrets.env (secrets-dev):1-15](file://shared/platform-ops/gitops/runtime-profiles/secrets-dev/secrets.env#L1-L15)
- [config.py (tool-gateway):118-136](file://products/tool-gateway/src/tool_gateway/core/config.py#L118-L136)
- [app.py (tool-gateway):119-164](file://products/tool-gateway/src/tool_gateway/app.py#L119-L164)
- [password-policy.yaml (contract):1-48](file://shared/shared-contracts/policies/password-policy.yaml#L1-L48)

**Section sources**
- [secrets.env (secrets-dev):1-15](file://shared/platform-ops/gitops/runtime-profiles/secrets-dev/secrets.env#L1-L15)
- [kustomization.yaml (dev-k8s):15](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml#L15)
- [config.py (tool-gateway):118-136](file://products/tool-gateway/src/tool_gateway/core/config.py#L118-L136)
- [app.py (tool-gateway):119-164](file://products/tool-gateway/src/tool_gateway/app.py#L119-L164)
- [password-policy.yaml (contract):1-48](file://shared/shared-contracts/policies/password-policy.yaml#L1-L48)

### Select and Verify Scripts
- select-runtime-profile.sh:
  - Validates input and rejects mutating-dev, browser-dev, and secrets-dev as switchable LLM profiles.
  - Writes dev-k8s/kustomization.yaml to include the selected profile plus all three posture overlays.
  - Merges environment files from all posture overlays into the runtime ConfigMap.
  - Applies the browser sidecar strategic merge patch to the tool-gateway Deployment.
- verify-runtime-profile.sh:
  - Extracts the currently active LLM profile from dev-k8s/kustomization.yaml.
  - Renders the overlay with kustomize to validate integrity.

```mermaid
sequenceDiagram
participant U as "User"
participant S as "select-runtime-profile.sh"
participant V as "verify-runtime-profile.sh"
participant K as "dev-k8s/kustomization.yaml"
U->>S : ./select-runtime-profile.sh <profile>
S->>S : Validate profile name
S->>K : Write resources + env merges + patches
U->>V : ./verify-runtime-profile.sh
V->>K : Read active profile
V->>K : kubectl kustomize render
K-->>V : Success or error
V-->>U : Report active profile and result
```

**Diagram sources**
- [select-runtime-profile.sh:1-55](file://shared/platform-ops/gitops/select-runtime-profile.sh#L1-L55)
- [verify-runtime-profile.sh:1-24](file://shared/platform-ops/gitops/verify-runtime-profile.sh#L1-L24)

**Section sources**
- [select-runtime-profile.sh:1-55](file://shared/platform-ops/gitops/select-runtime-profile.sh#L1-L55)
- [verify-runtime-profile.sh:1-24](file://shared/platform-ops/gitops/verify-runtime-profile.sh#L1-L24)

## Dependency Analysis
Profiles compose through Kustomize:
- dev-k8s includes the active LLM profile and all three posture overlays.
- browser-dev depends on:
  - tool-gateway Deployment (patched by dev-k8s).
  - NetworkPolicy restricting CDP ingress.
  - Out-of-band sample applications (deployed via `make deploy-sample-app`).
- mutating-dev depends on:
  - tool-gateway ServiceAccount in the dev namespace.
  - RBAC Role/RoleBinding for bounded pod deletion.
- **New**: secrets-dev depends on:
  - tool-gateway ServiceAccount in the dev namespace.
  - Password policy contract mounted via base platform-policy ConfigMap.
  - Ephemeral secret delivery buffer (memory backend by default).

```mermaid
graph LR
DevK8s["dev-k8s/kustomization.yaml"]
Def["default/"]
Br["browser-dev/"]
Mut["mutating-dev/"]
Sec["secrets-dev/"]
TG["tool-gateway Deployment"]
NP["NetworkPolicy"]
RB["Role/RoleBinding"]
SA["ServiceAccount"]
PP["Password Policy Contract"]
DB["Secret Delivery Buffer"]
DevK8s --> Def
DevK8s --> Br
DevK8s --> Mut
DevK8s --> Sec
Br --> TG
Br --> NP
Mut --> RB
Mut --> SA
Sec --> PP
Sec --> DB
```

**Diagram sources**
- [kustomization.yaml (dev-k8s):5-15](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml#L5-L15)
- [kustomization.yaml (browser-dev):22-28](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml#L22-L28)
- [kustomization.yaml (mutating-dev):18-21](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml#L18-L21)
- [secrets.env (secrets-dev):1-15](file://shared/platform-ops/gitops/runtime-profiles/secrets-dev/secrets.env#L1-L15)
- [tool-gateway-browser-sidecar.yaml:1-67](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml#L1-L67)
- [browser-sidecar-network-policy.yaml:1-31](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml#L1-L31)
- [tool-gateway-pod-delete.yaml:1-48](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml#L1-L48)

**Section sources**
- [kustomization.yaml (dev-k8s):5-15](file://shared/platform-ops/gitops/dev-k8s/kustomization.yaml#L5-L15)
- [kustomization.yaml (browser-dev):1-29](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml#L1-L29)
- [kustomization.yaml (mutating-dev):1-22](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml#L1-L22)
- [secrets.env (secrets-dev):1-15](file://shared/platform-ops/gitops/runtime-profiles/secrets-dev/secrets.env#L1-L15)

## Performance Considerations
- Browser sidecar resources:
  - Requests and limits are defined to prevent unbounded CPU/memory usage.
  - Shared memory volume is mounted for browser stability.
- Network policy:
  - Limits exposure of the CDP port to loopback and denies cross-pod access.
- Mutating tools:
  - Keep scope minimal (delete pods only in dev namespace) to reduce blast radius.
- **New**: Secret delivery buffer:
  - Memory backend provides single-replica ephemeral storage with TTL expiration.
  - Redis backend available for multi-replica deployments with proper TTL support.
  - Password generation follows cryptographic standards with entropy floor validation.

[No sources needed since this section provides general guidance derived from the referenced files]

## Troubleshooting Guide
Common issues and resolutions:
- Wrong profile selected:
  - Use verify-runtime-profile.sh to confirm the active LLM profile and ensure kustomize renders successfully.
- Browser tools failing:
  - Ensure GATEWAY_BROWSER_ENABLED is true and the allowlist includes the target origin.
  - Confirm the sidecar is running and reachable on loopback.
  - Check that credential sets are synced to the expected secret and mounted.
  - Verify that sample applications (like `acme-admin`) are deployed out-of-band using `make deploy-sample-app`.
- Mutating tools denied:
  - Verify GATEWAY_MUTATING_TOOLS_ENABLED is true.
  - Confirm RBAC Role/RoleBinding exists and matches the tool-gateway ServiceAccount.
  - Ensure policy grants and HITL configuration are in place.
- **New**: Secret generation failing:
  - Verify GATEWAY_SECRETS_ENABLED is true in the secrets-dev profile.
  - Check that password policy contract is properly mounted and readable.
  - Ensure secret delivery buffer is initialized and accessible.
  - For email delivery failures, confirm SMTP configuration is provisioned via sync-email-secrets.sh.
  - Validate password policy compliance if generation requests are rejected.

Operational steps:
- Re-run select-runtime-profile.sh with the desired profile.
- Re-run verify-runtime-profile.sh to validate overlay rendering.
- Deploy sample applications using `make deploy-sample-app` if browser tools cannot connect to targets.
- Inspect logs of tool-gateway and browser sidecar if connectivity issues persist.
- **New**: Check tool-gateway logs for secret delivery buffer initialization and password policy validation errors.

**Section sources**
- [verify-runtime-profile.sh:8-23](file://shared/platform-ops/gitops/verify-runtime-profile.sh#L8-L23)
- [browser.env (browser-dev):1-11](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env#L1-L11)
- [tool-gateway-browser-sidecar.yaml:1-67](file://shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml#L1-L67)
- [mutating.env (mutating-dev):1-4](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env#L1-L4)
- [tool-gateway-pod-delete.yaml:1-48](file://shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml#L1-L48)
- [secrets.env (secrets-dev):1-15](file://shared/platform-ops/gitops/runtime-profiles/secrets-dev/secrets.env#L1-L15)
- [config.py (tool-gateway):118-136](file://products/tool-gateway/src/tool_gateway/core/config.py#L118-L136)

## Conclusion
Runtime profiles provide a layered, deny-by-default approach to configuring platform behavior:
- The default profile sets a generic agent profile and provider selection.
- The browser-dev posture enables safe, scoped browser automation with strict network and credential controls, relying on out-of-band sample applications.
- The mutating-dev posture enables bounded write operations with minimal RBAC and enforced approvals.
- **New**: The secrets-dev posture enables secure password generation with one-time portal-copy handoff, maintaining strong security boundaries while providing development-time credential generation capabilities.

Use the select script to switch the active LLM profile while keeping all posture overlays permanently enabled. Use the verify script to validate the overlay before deploying. Follow the security boundaries and approval workflows described above to maintain safe operations across environments. Remember that sample applications must be deployed separately using `make deploy-sample-app` when testing browser functionality, and email delivery requires additional SMTP configuration beyond the secrets-dev profile scope.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Creating Custom Profiles
Guidance:
- Create a new directory under runtime-profiles with a kustomization.yaml listing resources to include.
- If you need environment variables, add an env file and merge it via the dev-k8s overlay's configMapGenerator.
- For posture-like features (sidecars, network policies, RBAC), follow the patterns in browser-dev, mutating-dev, and secrets-dev.
- Keep defaults deny-by-default; only enable capabilities explicitly through your profile.
- Update dev-k8s to include your profile if it replaces the active LLM profile, or keep it as an additional posture overlay if appropriate.

Security considerations:
- Scope RBAC to the minimum necessary resources and verbs.
- Bind sensitive services (like CDP) to loopback and protect with NetworkPolicy.
- Use allowlists for external access (origins, endpoints).
- Ensure secrets are provisioned out-of-band and mounted as optional where possible to avoid blocking startup.
- For browser-related profiles, remember that sample applications should be deployed out-of-band rather than included in the profile resources.
- **New**: For secret-related profiles, ensure password policy compliance and consider whether email delivery capabilities should be enabled based on security requirements.

[No sources needed since this section provides general guidance]