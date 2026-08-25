# SPEC-030: Require Approval Policy Semantics

<cite>
**Referenced Files in This Document**
- [spec.md](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md)
- [plan.md](file://docs/specs/SPEC-030-require-approval-policy-semantics/plan.md)
- [tasks.md](file://docs/specs/SPEC-030-require-approval-policy-semantics/tasks.md)
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [policy_engine.py (platform-gateway)](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy_engine.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [hitl_confirmations.py](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [chat.py](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py)
- [gateway_service.py](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py)
- [ConfirmationCard.test.tsx](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx)
- [approval-and-hitl.md](file://docs/guides/approval-and-hitl.md)
- [triage.py](file://products/incident-service/src/incident_service/services/triage.py)
- [runtime_kernel.py](file://products/agent-platform/src/agent_service/runtime_kernel.py)
- [kernel_middleware.py](file://products/agent-platform/src/agent_service/services/kernel_middleware.py)
</cite>

## Update Summary
**Changes Made**
- Enhanced Core Components section with triage service read-only enforcement and runtime kernel enhancements
- Updated Architecture Overview with per-turn read_only agent cache keys and toolkit scoping
- Added Critical Remediations section covering GenerateStructuredOutput allow-list additions and approver role permissions
- Expanded Default Bundle Posture with approver role tool access grants
- Updated Troubleshooting Guide with triage-specific scenarios and structured output handling
- Added comprehensive source tracking for all applied changes including runtime kernel modifications

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Critical Remediations](#critical-remediations)
6. [Detailed Component Analysis](#detailed-component-analysis)
7. [Dependency Analysis](#dependency-analysis)
8. [Performance Considerations](#performance-considerations)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Conclusion](#conclusion)
11. [Appendices](#appendices)

## Introduction
SPEC-030 introduces require-approval policy semantics as a first-class, data-driven outcome for mutating actions. It upgrades the existing allow/deny-only policy model to include require_approval with explicit approval tiers:
- **tier_1**: session operator may confirm their own parked call (destructive-but-routine).
- **tier_2**: a designated approver distinct from the requester must decide (critical destructive).

The enforcement rides the already-delivered HITL confirmation substrate (park/resume and chat:confirm), so no new queue service is required in this slice. The default bundle ships a tier_2 requirement on tools:mutate, making the governance promise enforceable by default.

Key outcomes:
- Contract revision adds require_approval with an approval block to both rule and decision schemas.
- Both gateway engines evaluate deny > require_approval > allow with priority-based selection among approvals.
- Platform-gateway enforces tiered approval on the chat:confirm path; tool-gateway keeps admission unchanged.
- Transparency surfaces (permission matrix, portal cards, audit events) render approval requirements consistently.

**Updated** Live cluster validation during delivery surfaced critical issues that were immediately remediated: incident-service triage turns now run with `read_only=True` to prevent mutating tools from executing in background triage operations, `GenerateStructuredOutput` was added to the kernel's local-tool allow-list to prevent parking structured-output calls, and approver roles received necessary tool access permissions (`tools:list`, `tools:invoke`, `tools:mutate`) to support tier_2-approved execution flows.

**Section sources**
- [spec.md:16-31](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L16-L31)
- [approval-and-hitl.md:170-208](file://docs/guides/approval-and-hitl.md#L170-L208)
- [spec.md:337-352](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L337-L352)

## Project Structure
This spec spans shared contracts, two gateway services, agent-platform HITL storage, incident-service triage, and the operator portal. The most relevant files are:
- Shared contracts: policy-rule.schema.json, policy-decision.schema.json, policy-default.yaml
- Platform-gateway: policy engine, policy matrix, confirm bridge (routes referenced in plan)
- Tool-gateway: policy engine (require_approval rules skipped at load)
- Agent-platform: HITL confirmation registry exposing risk-level mapping to policy actions, runtime kernel with per-turn toolkit scoping
- Incident-service: triage service with read-only enforcement
- Portal: permission view and confirmation card rendering (referenced in plan)

```mermaid
graph TB
subgraph "Shared Contracts"
A["policy-rule.schema.json"]
B["policy-decision.schema.json"]
C["policy-default.yaml"]
end
subgraph "Platform Gateway"
D["policy_engine.py"]
E["policy_matrix.py"]
F["chat routes (plan reference)"]
G["gateway_service.py"]
end
subgraph "Tool Gateway"
H["policy_engine.py"]
end
subgraph "Agent Platform"
I["hitl_confirmations.py"]
J["runtime_kernel.py<br/>per-turn toolkit scoping"]
K["kernel_middleware.py<br/>GenerateStructuredOutput allow-list"]
end
subgraph "Incident Service"
L["triage.py<br/>read_only enforcement"]
end
subgraph "Portal"
M["PermissionsView.tsx (plan reference)"]
N["Confirmation Card (plan reference)"]
end
A --> D
B --> D
C --> D
C --> H
D --> E
F --> G
G --> I
E --> M
G --> N
J --> K
L --> J
```

**Diagram sources**
- [policy-engine.py (platform-gateway):1-12](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L12)
- [policy-engine.py (tool-gateway):1-14](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L1-L14)
- [policy_matrix.py:1-9](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L1-L9)
- [hitl_confirmations.py:34-42](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L34-L42)
- [runtime_kernel.py:277-389](file://products/agent-platform/src/agent_service/runtime_kernel.py#L277-L389)
- [kernel_middleware.py:55-60](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L55-L60)
- [triage.py:250-263](file://products/incident-service/src/incident_service/services/triage.py#L250-L263)
- [policy-default.yaml:113-135](file://shared/shared-contracts/policies/policy-default.yaml#L113-L135)

**Section sources**
- [plan.md:16-15](file://docs/specs/SPEC-030-require-approval-policy-semantics/plan.md#L16-L15)
- [spec.md:257-262](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L257-L262)

## Core Components
- **Policy schemas (v2)**:
  - policy-rule.schema.json: Adds require_approval outcome and an approval object with tier, decided_by_roles, and optional allow_self_approval.
  - policy-decision.schema.json: Activates require_approval outcome and approval_tier; includes an optional approval mirror for callers.
- **Policy engines**:
  - platform-gateway: Evaluates deny > require_approval > allow; validates require_approval rules only on bridged actions; returns approval metadata.
  - tool-gateway: Validates approval blocks loudly but skips require_approval rules at load because there is no pre-approval substrate; admission remains allow/deny.
- **HITL confirmation registry**:
  - Maps tool risk levels to policy actions (tools:invoke or tools:mutate) and exposes highest action for policy evaluation during confirm.
- **Permission matrix**:
  - Derives role × action cells via evaluate(); will gain a third cell state requires_approval when the caller's role evaluates to require_approval.
- **Default bundle**:
  - Ships a tier_2 require_approval rule on tools:mutate with deciders approver and platform-admin, blocking self-approval by default.
- **Runtime kernel enhancements**:
  - Per-turn read_only agent cache keys ensure toolkit scoping isolation between interactive and automated diagnostic turns.
  - GenerateStructuredOutput tool added to kernel local-tool allow-list to prevent parking structured-output calls.
- **Triage service read-only enforcement**:
  - Incident-service triage runs with `read_only=True` flag to structurally restrict toolkit to read-level tools, preventing any mutating tool execution or parking in background triage operations.

Acceptance highlights:
- Precedence and priority semantics implemented in both engines.
- Confirm path enforces tiered approval; structured 403 on non-deciders and self-approval where forbidden.
- Transparency and audit enriched with approval details.
- Runtime kernel provides structural protection against mutating tool execution in automated contexts.

**Section sources**
- [policy-rule.schema.json:47-100](file://shared/shared-contracts/schemas/policy-rule.schema.json#L47-L100)
- [policy-decision.schema.json:8-56](file://shared/shared-contracts/schemas/policy-decision.schema.json#L8-L56)
- [policy_engine.py (platform-gateway):335-389](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L335-L389)
- [policy_engine.py (tool-gateway):187-246](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L187-L246)
- [hitl_confirmations.py:34-104](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L34-L104)
- [policy_matrix.py:25-62](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L25-L62)
- [policy-default.yaml:113-135](file://shared/shared-contracts/policies/policy-default.yaml#L113-L135)
- [runtime_kernel.py:277-389](file://products/agent-platform/src/agent_service/runtime_kernel.py#L277-L389)
- [kernel_middleware.py:55-60](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L55-L60)
- [triage.py:250-263](file://products/incident-service/src/incident_service/services/triage.py#L250-L263)

## Architecture Overview
The require-approval flow integrates into the existing HITL confirmation path with enhanced runtime protections:
- A mutating tool run parks a reply requiring user confirmation.
- The platform-gateway chat:confirm route resolves the parked call's effective action (from risk level) and evaluates it against the bundle.
- If require_approval is returned, the confirmer must hold one of the approved roles; tier_2 rejects self-approval unless explicitly allowed.
- On success, the confirmed call proceeds through tool-gateway admission using the confirmer's delegated token (unchanged).
- Triage operations run with read_only enforcement to prevent any mutating tool execution in background diagnostic turns.
- Structured output generation bypasses the approval gate as it's a kernel-local operation.
- Transparency surfaces reflect the approval requirement and decisions.

```mermaid
sequenceDiagram
participant Client as "Operator / Approver"
participant PG as "Platform Gateway<br/>chat : confirm route"
participant PE as "Policy Engine (PG)"
participant AP as "Agent Platform<br/>HITL Registry"
participant RK as "Runtime Kernel<br/>Per-turn Toolkit Scoping"
participant TG as "Tool Gateway"
participant IS as "Incident Service<br/>Triage"
Client->>PG : POST /api/v1/chat/confirm
PG->>AP : Resolve parked call and read risk levels
AP-->>PG : Highest action (e.g., tools : mutate)
PG->>PE : Evaluate(action, roles)
PE-->>PG : {decision : require_approval, approval}
alt Tier 1 or Tier 2 with decider role
PG->>PG : Enforce tier rules (self-approval check)
alt Allowed
PG->>TG : Forward confirmed execution (delegated token)
TG-->>PG : Admission result
PG-->>Client : Success
else Blocked (non-decider or self-approval)
PG-->>Client : 403 {require_approval, reason}
end
else No require_approval
PG->>TG : Forward confirmed execution
TG-->>PG : Admission result
PG-->>Client : Success
end
Note over IS,RK : Triage Operations
IS->>RK : Chat request with read_only=True
RK->>RK : Filter toolkit to read-level tools only
RK-->>IS : Execute with restricted toolkit
```

**Diagram sources**
- [policy_engine.py (platform-gateway):335-389](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L335-L389)
- [hitl_confirmations.py:34-104](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L34-L104)
- [policy-default.yaml:113-135](file://shared/shared-contracts/policies/policy-default.yaml#L113-L135)
- [runtime_kernel.py:277-389](file://products/agent-platform/src/agent_service/runtime_kernel.py#L277-L389)
- [triage.py:250-263](file://products/incident-service/src/incident_service/services/triage.py#L250-L263)

## Critical Remediations
During live cluster validation, three critical issues were identified and immediately remediated:

### Triage Service Read-Only Enforcement
Incident-service triage turns now execute with `read_only=True` flag passed to agent-platform `/api/v2/chat`. This ensures that automated diagnostic turns never invoke — or park on — mutating tools, regardless of what the model decides. The runtime kernel filters the toolkit to read-level tools only for these turns, providing structural protection beyond prompt discipline alone.

### GenerateStructuredOutput Allow-List Addition
The kernel's built-in `GenerateStructuredOutput` tool (used for response_schema structured output) was added to the kernel local-tool allow-list. This prevents structured-output calls from being parked as if they were gateway actions, which would wedge every structured turn (including incident triage) on a headless stream. The tool is considered kernel-local and always allowed since it only shapes the final reply into the caller-provided schema without touching external systems.

### Approver Role Permission Grants
Approver roles received necessary tool access permissions (`tools:list`, `tools:invoke`, `tools:mutate`) to support tier_2-approved execution flows. When a tier_2-approved call resumes under the confirmer's delegated token, the approver needs these permissions to successfully execute the approved action. Two-person control is preserved — an approver's own parked call still requires a distinct designated approver due to tier_2 self-approval blocking.

```mermaid
flowchart TD
Start(["Triage Request"]) --> ReadOnly["Set read_only=True"]
ReadOnly --> FilterToolkit["Filter toolkit to read-level tools only"]
FilterToolkit --> Execute["Execute with restricted toolkit"]
Execute --> CheckMutating{"Any mutating tools?"}
CheckMutating --> |Yes| Block["Block execution - structural protection"]
CheckMutating --> |No| Proceed["Proceed with read-only tools"]
Proceed --> StructuredOutput["GenerateStructuredOutput<br/>Always ALLOWED"]
StructuredOutput --> Complete["Complete triage"]
Block --> Complete
```

**Diagram sources**
- [triage.py:250-263](file://products/incident-service/src/incident_service/services/triage.py#L250-L263)
- [runtime_kernel.py:356-376](file://products/agent-platform/src/agent_service/runtime_kernel.py#L356-L376)
- [kernel_middleware.py:55-60](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L55-L60)
- [policy-default.yaml:81-119](file://shared/shared-contracts/policies/policy-default.yaml#L81-L119)

**Section sources**
- [triage.py:250-263](file://products/incident-service/src/incident_service/services/triage.py#L250-L263)
- [runtime_kernel.py:356-376](file://products/agent-platform/src/agent_service/runtime_kernel.py#L356-L376)
- [kernel_middleware.py:55-60](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L55-L60)
- [policy-default.yaml:81-119](file://shared/shared-contracts/policies/policy-default.yaml#L81-L119)
- [spec.md:337-352](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L337-L352)

## Detailed Component Analysis

### Policy Schemas (v2)
- Rule schema adds require_approval outcome and an approval block:
  - tier: enum ["tier_1", "tier_2"]
  - decided_by_roles: non-empty array
  - allow_self_approval: optional boolean overriding tier defaults
- Decision schema activates require_approval and approval_tier; includes an optional approval mirror for callers.

These changes are additive v1 → v2 and preserve backward compatibility for v1 bundles.

**Section sources**
- [policy-rule.schema.json:47-100](file://shared/shared-contracts/schemas/policy-rule.schema.json#L47-L100)
- [policy-decision.schema.json:8-56](file://shared/shared-contracts/schemas/policy-decision.schema.json#L8-L56)

### Policy Engines
- Evaluation precedence: deny > require_approval > allow.
- Among require_approval matches, highest priority wins; its approval block rides the decision.
- Platform-gateway validation:
  - require_approval rules must target bridged actions (currently tools:mutate).
  - tier_2 with allow_self_approval:true is rejected at load.
- Tool-gateway behavior:
  - Validates approval blocks loudly, then skips require_approval rules at load (logged warning) because there is no pre-approval substrate; admission stays allow/deny.

```mermaid
flowchart TD
Start(["evaluate()"]) --> Load["Load bundle"]
Load --> Match["Find enabled rules matching action + roles"]
Match --> AnyDeny{"Any deny?"}
AnyDeny --> |Yes| Deny["Return deny with matched ids"]
AnyDeny --> |No| Approvals["Collect require_approval matches"]
Approvals --> HasApproval{"Any approvals?"}
HasApproval --> |Yes| BestApproval["Pick highest priority approval"]
BestApproval --> ReturnApproval["Return require_approval with approval block"]
HasApproval --> |No| Allows["Collect allow matches"]
Allows --> HasAllow{"Any allows?"}
HasAllow --> |Yes| BestAllow["Pick highest priority allow"]
BestAllow --> ReturnAllow["Return allow"]
HasAllow --> |No| DefaultDeny["Return deny (no match)"]
```

**Diagram sources**
- [policy_engine.py (platform-gateway):335-389](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L335-L389)
- [policy_engine.py (tool-gateway):279-335](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L279-L335)

**Section sources**
- [policy_engine.py (platform-gateway):97-164](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L97-L164)
- [policy_engine.py (platform-gateway):183-285](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L183-L285)
- [policy_engine.py (tool-gateway):62-129](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L62-L129)
- [policy_engine.py (tool-gateway):147-246](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L147-L246)

### HITL Confirmation Bridge
- PendingConfirmation tracks risk_levels per tool and maps them to policy actions:
  - read → tools:invoke
  - write/admin → tools:mutate
- highest_action selects the strictest action in a batch (mutate over invoke).
- The confirm bridge uses this action to evaluate require_approval and enforce tier rules before forwarding to tool-gateway.

```mermaid
classDiagram
class PendingConfirmation {
+string confirm_id
+string session_id
+string user_id
+string reply_id
+list tool_calls
+dict risk_levels
+float created_at
+bool resolved
+bool claimed
+is_expired(timeout) bool
+pending_calls_payload() list
+highest_action() string?
+tool_names() list
}
```

**Diagram sources**
- [hitl_confirmations.py:45-111](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L45-L111)

**Section sources**
- [hitl_confirmations.py:34-104](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L34-L104)

### Runtime Kernel Enhancements
The runtime kernel provides critical structural protections through per-turn toolkit scoping:

- **Per-turn read_only cache keys**: Each turn creates a separate toolkit cache entry based on bearer token and read_only flag, ensuring read-only turns never leak mutating tools to interactive turns and vice versa.
- **Read-only toolkit filtering**: For read_only turns, the kernel filters the toolkit to only include tools with risk_level="read", logging excluded mutating tools.
- **Kernel local-tool allow-list**: GenerateStructuredOutput and task tools are always allowed as they operate on session-local state only.

```mermaid
flowchart TD
Request["Chat Request"] --> CheckReadOnly{"read_only flag?"}
CheckReadOnly --> |Yes| CreateROKey["Create read-only cache key"]
CheckReadOnly --> |No| CreateIKKey["Create interactive cache key"]
CreateROKey --> BuildROToolkit["Build read-only toolkit"]
CreateIKKey --> BuildIKToolkit["Build full toolkit"]
BuildROToolkit --> FilterTools["Filter to risk_level='read' only"]
BuildIKToolkit --> UseFullToolkit["Use complete toolkit"]
FilterTools --> Execute["Execute with restricted toolkit"]
UseFullToolkit --> Execute
Execute --> CacheResult["Cache toolkit by key"]
```

**Diagram sources**
- [runtime_kernel.py:277-389](file://products/agent-platform/src/agent_service/runtime_kernel.py#L277-L389)
- [kernel_middleware.py:44-60](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L44-L60)

**Section sources**
- [runtime_kernel.py:277-389](file://products/agent-platform/src/agent_service/runtime_kernel.py#L277-L389)
- [kernel_middleware.py:44-60](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L44-L60)

### Gateway Enforcement Implementation
The platform-gateway implements tiered approval enforcement in the chat:confirm flow:
- `_enforce_approval_tier()` evaluates the parked batch's policy action against the bundle
- For approve decisions, checks if confirmer holds required decider roles
- Enforces self-approval restrictions based on tier configuration
- Returns structured 403 responses with detailed rejection reasons
- Emits audit events for blocked attempts while keeping parked calls active

```mermaid
flowchart TD
Confirm["POST /api/v1/chat/confirm"] --> FetchParked["Fetch parked confirmation"]
FetchParked --> CheckDecision{"Decision = 'approve'?"}
CheckDecision --> |No| Proxy["Proxy to agent-service"]
CheckDecision --> |Yes| Evaluate["Evaluate policy action"]
Evaluate --> RequireApproval{"require_approval?"}
RequireApproval --> |No| Proxy
RequireApproval --> |Yes| CheckDecider{"Has decider role?"}
CheckDecider --> |No| Block403["403 not_a_designated_approver"]
CheckDecider --> |Yes| CheckSelf{"Self-approval allowed?"}
CheckSelf --> |No| BlockSelf["403 self_approval"]
CheckSelf --> |Yes| Proxy
Proxy --> Stream["Stream response"]
Block403 --> Audit["Audit blocked attempt"]
BlockSelf --> Audit
```

**Diagram sources**
- [gateway_service.py:610-684](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L610-L684)
- [chat.py:158-199](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L158-L199)

**Section sources**
- [gateway_service.py:527-700](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L527-L700)
- [chat.py:158-199](file://products/platform-gateway/src/platform_gateway/api/routes/chat.py#L158-L199)

### Permission Matrix and Portal Rendering
- build_policy_matrix evaluates each role × action via evaluate(), inheriting precedence and disabled-rule semantics.
- For SPEC-030, the matrix gains a third cell state requires_approval carrying tier and decider roles; consumers render it distinctly from allow/deny.
- Portal confirmation card shows tier badge ("operator confirmation" vs "approver required") and read-only mode for non-deciders.

**Section sources**
- [policy_matrix.py:25-62](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L25-L62)
- [ConfirmationCard.test.tsx:80-103](file://products/operator-portal/web-ui/app/src/chat/__tests__/ConfirmationCard.test.tsx#L80-L103)

### Default Bundle Posture
- policy-default.yaml includes a tier_2 require_approval rule on tools:mutate with decided_by_roles [approver, platform-admin].
- Self-approval is blocked by default for tier_2; developer identity excluded by authoring.
- Existing allow rules remain; precedence ensures require_approval overrides allow for mutating runs.
- **Updated** Approver roles now have tools:list, tools:invoke, and tools:mutate permissions to support tier_2-approved execution flows under the confirmer's delegated token.

**Section sources**
- [policy-default.yaml:113-135](file://shared/shared-contracts/policies/policy-default.yaml#L113-L135)
- [policy-default.yaml:81-119](file://shared/shared-contracts/policies/policy-default.yaml#L81-L119)
- [spec.md:154-179](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L154-L179)

## Dependency Analysis
- Contracts drive both engines and transparency surfaces.
- Platform-gateway depends on:
  - policy_engine for evaluation and validation
  - hitl_confirmations for parked-call action resolution
  - policy_matrix for live permissions
- Tool-gateway depends on policy_engine for admission (allow/deny); require_approval rules are skipped at load.
- Portal depends on matrix and confirmation card components to render approval states.
- **Updated** Incident-service depends on runtime kernel's read_only enforcement for safe triage operations.
- **Updated** Runtime kernel provides structural toolkit scoping independent of policy decisions.

```mermaid
graph LR
Contracts["Shared Contracts"] --> PGEngine["Platform Gateway Engine"]
Contracts --> TGEngine["Tool Gateway Engine"]
PGEngine --> PGMatrix["Platform Gateway Matrix"]
HITL["Agent Platform HITL"] --> PGConfirm["Platform Gateway Confirm Bridge"]
PGConfirm --> PGEngine
PGMatrix --> Portal["Portal UI"]
RuntimeKernel["Runtime Kernel<br/>Per-turn Toolkit Scoping"] --> KernelMiddleware["Kernel Middleware"]
IncidentService["Incident Service<br/>Triage"] --> RuntimeKernel
KernelMiddleware --> Portal
```

**Diagram sources**
- [policy_engine.py (platform-gateway):1-12](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L12)
- [policy_engine.py (tool-gateway):1-14](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L1-L14)
- [policy_matrix.py:1-9](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L1-L9)
- [hitl_confirmations.py:34-42](file://products/agent-platform/src/agent_service/services/hitl_confirmations.py#L34-L42)
- [runtime_kernel.py:277-389](file://products/agent-platform/src/agent_service/runtime_kernel.py#L277-L389)
- [kernel_middleware.py:129-210](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L129-L210)
- [triage.py:250-263](file://products/incident-service/src/incident_service/services/triage.py#L250-L263)

**Section sources**
- [spec.md:257-262](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L257-L262)

## Performance Considerations
- Policy evaluation is O(n) over enabled rules per request; typical bundles are small and cached.
- require_approval adds minimal overhead: an extra branch and approval block serialization.
- Tool-gateway skips require_approval rules at load, avoiding runtime cost for unenforced paths.
- Matrix computation iterates all visible roles × actions; caching and scope filtering mitigate cost.
- **Updated** Per-turn toolkit scoping adds minimal overhead through cache key differentiation and selective toolkit filtering for read-only turns.
- **Updated** Read-only toolkit filtering excludes mutating tools early in the pipeline, preventing unnecessary policy evaluation downstream.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- **Bundle load errors**:
  - Unknown outcome or malformed approval block raises PolicyLoadError; fix rule schema or remove invalid require_approval rules.
  - tier_2 with allow_self_approval:true is rejected; adjust to tier_1 or remove allow_self_approval.
- **Unexpected 403 on confirm**:
  - Confirmer lacks a decider role; ensure they hold one of decided_by_roles.
  - Self-approval blocked for tier_2; use a different approver identity.
  - Non-decider attempting approval; grant appropriate role or switch to approver identity.
- **Matrix not showing approval requirement**:
  - Ensure the caller's role evaluates to require_approval for the action; verify bundle and role membership.
- **Portal card not actionable**:
  - Non-deciders see read-only card; grant appropriate role or switch to an approver identity.
  - Observer without chat:confirm role sees read-only regardless of tier.
- **Triage operations failing**:
  - Verify triage requests include `read_only=True` flag to ensure read-only toolkit execution.
  - Check that triage sessions are properly scoped to incident IDs.
  - Validate structured output schema compliance when using response_schema parameter.
- **Structured output not working**:
  - Ensure GenerateStructuredOutput is available in the kernel's local-tool allow-list.
  - Verify response_schema parameter is properly formatted JSON schema.
  - Check that structured output validation passes against the provided schema.
- **Approver execution failures**:
  - Confirm approver has tools:list, tools:invoke, and tools:mutate permissions in the policy bundle.
  - Verify tier_2-approved calls execute under the confirmer's delegated token.
  - Check that approver roles are included in the allow rules for tool execution.

**Section sources**
- [policy_engine.py (platform-gateway):183-285](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L183-L285)
- [policy_engine.py (tool-gateway):147-246](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L147-L246)
- [test_policy_engine.py:446-502](file://products/platform-gateway/tests/test_policy_engine.py#L446-L502)
- [gateway_service.py:610-684](file://products/platform-gateway/src/platform_gateway/services/gateway_service.py#L610-L684)
- [triage.py:250-263](file://products/incident-service/src/incident_service/services/triage.py#L250-L263)
- [runtime_kernel.py:356-376](file://products/agent-platform/src/agent_service/runtime_kernel.py#L356-L376)
- [kernel_middleware.py:55-60](file://products/agent-platform/src/agent_service/services/kernel_middleware.py#L55-L60)
- [policy-default.yaml:81-119](file://shared/shared-contracts/policies/policy-default.yaml#L81-L119)

## Conclusion
SPEC-030 makes approval a first-class, data-driven policy outcome with explicit tiers, enforced on the existing HITL confirmation path. It tightens security by default (tier_2 on mutating actions), preserves backward compatibility (v1 bundles), and improves transparency (matrix, portal, audit). The critical remediations during live validation — triage read-only enforcement, GenerateStructuredOutput allow-list addition, and approver role permissions — ensure robust operation across all usage patterns. Future slices can extend to policy-center and additional tiers without breaking this enforcement contract.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Requirements Summary
- R-1: Contract revision with require_approval and approval block.
- R-2: Evaluation semantics in both engines (deny > require_approval > allow; priority; validation).
- R-3: Tiered enforcement bridge on chat:confirm (decider roles, self-approval checks).
- R-4: Default bundle posture (tier_2 on tools:mutate; demo updates; approver role permissions).
- R-5: Transparency and audit consistency (matrix third state, portal badges, audit enrichment).
- R-6: Settings panel restoration (portal-only, read-only panes).
- **Updated** R-7: Runtime kernel enhancements (per-turn read_only toolkit scoping, GenerateStructuredOutput allow-list).
- **Updated** R-8: Triage service read-only enforcement (structural protection against mutating tools).

**Section sources**
- [spec.md:59-226](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L59-L226)
- [plan.md:16-139](file://docs/specs/SPEC-030-require-approval-policy-semantics/plan.md#L16-L139)
- [tasks.md:5-50](file://docs/specs/SPEC-030-require-approval-policy-semantics/tasks.md#L5-L50)
- [spec.md:337-352](file://docs/specs/SPEC-030-require-approval-policy-semantics/spec.md#L337-L352)

### Related Specifications and Guidance
- Policy specification defines minimum decision response and recommended tier behavior.
- Spike memo documents findings, options, and recommended shape leading to SPEC-030.
- **Updated** Incident triage specifications define read-only operational boundaries for automated diagnostic turns.

**Section sources**
- [policy-specification.md:223-295](file://docs/agentic-aiops-platform/policy-specification.md#L223-L295)
- [policy-require-approval-spike.md:21-142](file://docs/workspace/policy-require-approval-spike.md#L21-L142)
- [triage.py:1-14](file://products/incident-service/src/incident_service/services/triage.py#L1-L14)