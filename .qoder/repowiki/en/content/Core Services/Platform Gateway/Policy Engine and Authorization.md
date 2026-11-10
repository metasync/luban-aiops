# Policy Engine and Authorization

<cite>
**Referenced Files in This Document**
- [policy_engine.py](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy_matrix.py](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py)
- [policy-default.yaml](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml)
- [policy_engine.py](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [policy-default.yaml](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml)
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-matrix.schema.json](file://shared/shared-contracts/schemas/policy-matrix.schema.json)
- [authorization-matrix.md](file://docs/agentic-aiops-platform/authorization-matrix.md)
- [policy-specification.md](file://docs/agentic-aiops-platform/policy-specification.md)
- [authorization_transactions.py](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py)
- [authorization.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py)
- [authorization.py (platform-gateway)](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py)
- [test_authorization_contracts.py (tool-gateway)](file://products/tool-gateway/tests/test_authorization_contracts.py)
- [test_authorization_contracts.py (platform-gateway)](file://products/platform-gateway/tests/test_authorization_contracts.py)
- [oq7-first-use-handoff-contract.md](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md)
- [spec.md (SPEC-070)](file://docs/specs/SPEC-070-outbound-user-delegated-identity/spec.md)
- [plan.md (SPEC-070)](file://docs/specs/SPEC-070-outbound-user-delegated-identity/plan.md)
- [agent_role.py](file://products/agent-platform/src/agent_service/services/agent_role.py)
- [validate_policy_scenarios.py](file://shared/shared-contracts/scripts/validate_policy_scenarios.py)
- [test_policy_engine.py](file://products/platform-gateway/tests/test_policy_engine.py)
- [spec.md (SPEC-074)](file://docs/specs/SPEC-074-policy-role-axis/spec.md)
- [plan.md (SPEC-074)](file://docs/specs/SPEC-074-policy-role-axis/plan.md)
- [tasks.md (SPEC-074)](file://docs/specs/SPEC-074-policy-role-axis/tasks.md)
- [spec.md (SPEC-076)](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/spec.md)
- [plan.md (SPEC-076)](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/plan.md)
- [tasks.md (SPEC-076)](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/tasks.md)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive documentation for SPEC-076 bounded autonomous diagnosis policy enforcement, including the two canonical agent-role rules: `deny-diagnostician-tools-mutate` and `require-approval-executor-tools-mutate`.
- Updated policy rule sections to document the ready-but-inert deployment status where no deployed caller threads non-None agent-role values.
- Enhanced examples to show how the diagnostician deny rule overrides mutating grants and how executor staging requires tier_2 approval.
- Added detailed coverage of the phase-5 delivery resolution where in-process SPEC-073 toolkit narrowing provides live read-only control while policy axis remains unit-proven but inert.
- Updated authorization matrix and policy specification sections to document the canonical bundle changes and their byte-identical synchronization across all four replicas.

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Authorization Contract Integration](#authorization-contract-integration)
6. [Agent Role Axis Implementation](#agent-role-axis-implementation)
7. [SPEC-076 Bounded Autonomous Diagnosis Policy Enforcement](#spec-076-bounded-autonomous-diagnosis-policy-enforcement)
8. [Detailed Component Analysis](#detailed-component-analysis)
9. [Dependency Analysis](#dependency-analysis)
10. [Performance Considerations](#performance-considerations)
11. [Troubleshooting Guide](#troubleshooting-guide)
12. [Conclusion](#conclusion)
13. [Appendices](#appendices)

## Introduction
This document explains the Platform Gateway's policy engine and authorization system. It covers how incoming requests are evaluated against policy rules, how role-based permissions are enforced across endpoints and operations, how approval workflows integrate with policy decisions, and how policies are loaded and cached. It also documents the policy rule format, risk-tier evaluation, tool permission checks, the live policy matrix, conflict resolution, and audit logging. Finally, it describes integration points with the Identity Broker for user context and how decisions are recorded for auditing.

**Updated** This document now includes the OQ-7 authorization contract integration, the SPEC-074 policy role axis implementation, and the SPEC-076 bounded autonomous diagnosis policy enforcement. The policy role axis adds an optional `agent_roles_any` field to the v3 schema, enabling agent-role-scoped authorization rules while maintaining backward compatibility. The SPEC-076 implementation introduces two canonical rules that remain ready-but-inert since no deployed caller threads non-None agent-role values, with in-process SPEC-073 toolkit narrowing providing the live read-only control.

## Project Structure
The policy system spans two gateways:
- Platform Gateway: enforces route-level and action-level authorization, bridges HITL confirmations, and exposes a live policy matrix.
- Tool Gateway: enforces tool invocation admission (read vs write/admin tools) and delegates approval enforcement to the platform gateway.
- Authorization Contracts: define the OQ-7 handoff protocol shapes and transaction store interface without implementing OAuth flows.
- Agent Role Axis: implements the SPEC-074 policy role dimension with closed vocabulary enforcement.
- SPEC-076 Canonical Rules: implement bounded autonomous diagnosis policy enforcement with ready-but-inert deployment semantics.

```mermaid
graph TB
subgraph "Platform Gateway"
PGE["Policy Engine<br/>evaluate()"]
PMX["Policy Matrix<br/>build_policy_matrix()"]
POLY["Default Bundle<br/>policy-default.yaml"]
PGW_AUTH["Authorization Schemas<br/>portal wire shapes"]
end
subgraph "Tool Gateway"
TGE["Policy Engine<br/>evaluate()"]
TOLY["Default Bundle<br/>policy-default.yaml"]
AUTH_TX["Authorization Transaction Store<br/>Protocol + Models"]
AUTH_SCHEMA["Authorization Schemas<br/>wire models"]
end
subgraph "Shared Contracts"
SCHEMA_RULE["policy-rule.schema.json<br/>v3 with agent_roles_any"]
SCHEMA_MATRIX["policy-matrix.schema.json"]
TOOL_RESULT["tool-result.schema.json"]
end
subgraph "Design Docs"
AUTHZ["authorization-matrix.md"]
POLSPEC["policy-specification.md"]
OQ7["OQ-7 Handoff Contract"]
SPEC074["SPEC-074 Policy Role Axis"]
SPEC076["SPEC-076 Bounded Autonomy"]
end
POLY --> PGE
TOLY --> TGE
PGE --> PMX
PGE --> SCHEMA_MATRIX
TGE --> SCHEMA_MATRIX
AUTH_TX --> AUTH_SCHEMA
AUTH_SCHEMA --> TOOL_RESULT
PGW_AUTH --> OQ7
PGE -.-> AUTHZ
TGE -.-> AUTHZ
PGE -.-> POLSPEC
TGE -.-> POLSPEC
PGE -.-> SPEC074
TGE -.-> SPEC074
PGE -.-> SPEC076
TGE -.-> SPEC076
```

**Diagram sources**
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [policy_matrix.py:31-88](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L88)
- [authorization_transactions.py:65-122](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L65-L122)
- [authorization.py (tool-gateway):1-74](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L74)
- [authorization.py (platform-gateway):1-47](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py#L1-L47)

**Section sources**
- [policy_engine.py:1-136](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L136)
- [policy_engine.py:1-60](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L1-L60)
- [authorization_transactions.py:1-122](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L1-L122)
- [authorization.py (tool-gateway):1-74](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L74)
- [authorization.py (platform-gateway):1-47](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py#L1-L47)

## Core Components
- Policy bundle loader: loads YAML bundles from a configured path or packaged defaults; caches them per process; computes a SHA-256 fingerprint at load time.
- Rule parser and validator: validates schema, outcomes, and approval blocks; enforces that require_approval is only valid on bridged actions in the platform gateway; validates agent_roles_any against closed vocabulary.
- Evaluator: matches enabled rules by roles and actions, applies precedence deny > require_approval > allow, selects highest priority within an outcome class, and returns a structured decision. Now supports agent-role scoping.
- Live matrix builder: derives a role × action boolean matrix plus an additive approval_requirements structure from the same evaluate() path used for enforcement.
- Default bundles: define the canonical set of actions and grants for both gateways, including SPEC-076 canonical rules.
- Authorization transaction store: defines the Protocol interface for OQ-7 handoff state management without implementing storage backends.
- Agent role vocabulary: closed set of diagnostician/orchestrator/executor roles with fail-closed validation.

Key behaviors:
- Deny-by-default when no rule matches.
- Explicit deny overrides require_approval and allow.
- require_approval overrides allow.
- Higher priority wins within an outcome class.
- Disabled rules are ignored.
- Agent-role scoping composes conjunctively with human roles.
- Authorization contracts are inert - they define shapes but don't register routes or enable OAuth flows.
- SPEC-076 canonical rules remain ready-but-inert since no deployed caller threads non-None agent-role values.

**Section sources**
- [policy_engine.py:334-371](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L334-L371)
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [policy_matrix.py:31-88](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L88)
- [authorization_transactions.py:65-122](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L65-L122)
- [test_authorization_contracts.py (tool-gateway):96-117](file://products/tool-gateway/tests/test_authorization_contracts.py#L96-L117)

## Architecture Overview
The platform gateway evaluates every protected action through the policy engine using normalized roles provided by the identity layer. The tool gateway enforces tool invocation admission based on the same rule vocabulary but does not enforce approvals itself; approvals are enforced on the platform gateway's confirmation path.

**Updated** The OQ-7 authorization contract adds a separate flow for first-use target authorization. When tool execution requires user delegation, the system emits an authorization_required signal rather than executing the tool. This signal carries routing metadata that the portal uses to guide users through browser-based authorization without exposing secrets or enabling direct OAuth flows. The SPEC-074 policy role axis adds agent-role scoping that composes conjunctively with human roles. The SPEC-076 bounded autonomy policy enforcement adds canonical rules that remain ready-but-inert in deployment.

```mermaid
sequenceDiagram
participant Client as "Client"
participant PGW as "Platform Gateway"
participant PE as "Policy Engine"
participant TM as "Tool Gateway"
participant TE as "Tool Gateway Policy Engine"
participant ATX as "Authorization Transaction Store"
Client->>PGW : Request with normalized roles
PGW->>PE : evaluate(roles, action, agent_role=None)
PE-->>PGW : {decision, matched_rule_ids, reason[, approval]}
alt Action requires approval
PGW->>Client : Park confirmation / require approval
Note over PGW : Approval workflow resolves tier_1/tier_2
else Immediate allow/deny
PGW-->>Client : Allow or Deny
end
Client->>TM : Tool invocation request
TM->>TE : evaluate(roles, action, agent_role=None)
TE-->>TM : {decision}
alt Tool requires user delegation
TM->>ATX : Create authorization transaction
ATX-->>TM : Challenge ID
TM-->>Client : authorization_required signal
else Normal tool execution
TM-->>Client : Allow or Deny (no approval enforcement here)
end
```

**Diagram sources**
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [policy_engine.py:299-355](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L299-L355)
- [authorization_transactions.py:85-117](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L85-L117)

**Section sources**
- [policy_engine.py:92-127](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L92-L127)
- [policy_engine.py:32-52](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L32-L52)
- [oq7-first-use-handoff-contract.md:85-141](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md#L85-L141)

## Authorization Contract Integration

### OQ-7 Contract Architecture
The OQ-7 authorization contract defines the protocol for first-use target authorization handoffs. It establishes the contract boundary between components without implementing the actual OAuth flow. The contract includes:

- **Wire Models**: Pydantic models defining request/response shapes for authorization challenges and status queries
- **Transaction Store Protocol**: Interface definition for state persistence without backend implementation
- **Signal Flow**: Tool-result error signaling that triggers the authorization workflow
- **Stream Projection**: SSE frame format for communicating authorization requirements to the portal

```mermaid
flowchart TD
A["Tool Execution"] --> B{"User delegation required?"}
B --> |Yes| C["Return TARGET_AUTHORIZATION_REQUIRED error"]
C --> D["Emit authorization_required stream frame"]
D --> E["Portal displays authorization prompt"]
E --> F["User completes browser authorization"]
F --> G["Callback updates transaction status"]
G --> H["Resume original tool execution"]
B --> |No| I["Execute tool normally"]
```

**Diagram sources**
- [oq7-first-use-handoff-contract.md:85-141](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md#L85-L141)
- [authorization_transactions.py:34-63](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L34-L63)

### Authorization Transaction Store Interface
The `AuthorizationTransactionStore` Protocol defines the required behavior for storing and managing authorization transactions. Key characteristics:

- **Owner-scoped access**: All operations bind namespace AND subject to prevent cross-owner access
- **Atomic operations**: Callback claims and finalization must coordinate with encrypted state/custody
- **Inert implementation**: No backend is registered; future implementations must refuse multi-replica setups without shared Postgres
- **Security boundaries**: Secret values (codes, states, tokens) are never persisted in plain text

```mermaid
classDiagram
class AuthorizationTransactionStore {
+backend_name : str
+shared : bool
+initialize() : None
+create(transaction) : None
+get(challenge_id, owner_namespace, owner_sub, now) : AuthorizationTransaction | None
+claim_callback(challenge_id, owner_namespace, owner_sub, config_generation, now) : AuthorizationTransaction | None
+finish(challenge_id, owner_namespace, owner_sub, config_generation, status, now) : bool
+cancel(challenge_id, owner_namespace, owner_sub, now) : None
+expire(now, limit) : int
+ready() : None
+close() : None
}
class AuthorizationTransaction {
+challenge_id : ChallengeId
+owner_namespace : str
+owner_sub : str
+target : DisplayLabel
+credential_set_id : str
+config_generation : str
+session_id : str
+call_id : str
+return_url : LocalReturnPath
+status : AuthorizationStatus
+created_at : AwareDatetime
+updated_at : AwareDatetime
+expires_at : AwareDatetime
+consumed : bool
}
AuthorizationTransactionStore --> AuthorizationTransaction : manages
```

**Diagram sources**
- [authorization_transactions.py:65-122](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L65-L122)
- [authorization_transactions.py:34-63](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L34-L63)

**Section sources**
- [authorization_transactions.py:1-122](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L1-L122)
- [test_authorization_contracts.py (tool-gateway):96-117](file://products/tool-gateway/tests/test_authorization_contracts.py#L96-L117)
- [oq7-first-use-handoff-contract.md:72-84](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md#L72-L84)

### Contract Validation and Security Boundaries
The authorization contracts enforce strict validation and security boundaries:

- **Field validation**: All models use frozen configuration with forbidden extra fields
- **Secret redaction**: Internal values like codes, states, and provider URLs are redacted in representations
- **Route omission**: No authorization routes are registered in the OpenAPI specification
- **Capability validation**: Start URLs are restricted to specific patterns preventing arbitrary redirects
- **State binding**: Challenge IDs are UUID4 patterns bound to owner namespaces and subjects

```mermaid
flowchart TD
Start(["Contract Validation"]) --> Parse["Parse request/response"]
Parse --> ValidateFields{"All fields valid?"}
ValidateFields --> |No| Reject["Reject with ValidationError"]
ValidateFields --> |Yes| CheckSecrets{"Contains secrets?"}
CheckSecrets --> |Yes| Redact["Redact sensitive fields"]
CheckSecrets --> |No| CheckRoutes{"Routes registered?"}
Redact --> CheckRoutes
CheckRoutes --> |Yes| Error["Security violation - routes should not be registered"]
CheckRoutes --> |No| Accept["Accept validated model"]
```

**Diagram sources**
- [authorization.py (tool-gateway):20-22](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L20-L22)
- [authorization.py (platform-gateway):26-27](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py#L26-L27)
- [test_authorization_contracts.py (platform-gateway):44-46](file://products/platform-gateway/tests/test_authorization_contracts.py#L44-L46)

**Section sources**
- [authorization.py (tool-gateway):1-74](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L74)
- [authorization.py (platform-gateway):1-47](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py#L1-L47)
- [test_authorization_contracts.py (tool-gateway):31-84](file://products/tool-gateway/tests/test_authorization_contracts.py#L31-L84)
- [test_authorization_contracts.py (platform-gateway):17-46](file://products/platform-gateway/tests/test_authorization_contracts.py#L17-L46)

## Agent Role Axis Implementation

### SPEC-074 Policy Role Axis Overview
The SPEC-074 policy role axis introduces an optional `agent_roles_any` field to the v3 policy rule schema, enabling agent-role-scoped authorization rules. This implementation is additive and inert in phase 3, meaning:

- The schema extension is backward-compatible (v2→v3)
- No deployed caller threads a non-None agent-role
- Every live evaluation remains byte-identical to pre-SPEC-074 behavior
- The closed vocabulary includes diagnostician, orchestrator, and executor roles

```mermaid
flowchart TD
A["Policy Rule Schema v3"] --> B{"Has agent_roles_any?"}
B --> |No| C["Unconstrained - matches any agent-role"]
B --> |Yes| D{"Call has agent_role?"}
D --> |No| E["Fail-closed - no match"]
D --> |Yes| F{"agent_role in agent_roles_any?"}
F --> |Yes| G["Rule matches"]
F --> |No| H["Rule doesn't match"]
```

**Diagram sources**
- [policy-rule.schema.json:44-48](file://shared/shared-contracts/schemas/policy-rule.schema.json#L44-L48)
- [policy_engine.py:443-459](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L443-L459)

### Agent Role Vocabulary and Semantics
The agent-role vocabulary mirrors the SPEC-073 `AgentRole` enum with three closed values:

- **diagnostician**: Read-only diagnostic capabilities, no mutation authority
- **orchestrator**: Planning and coordination capabilities, no direct tool access  
- **executor**: May propose mutations but still requires human approval

The vocabulary is enforced at multiple levels:
- JSON Schema validation (enum constraint)
- Policy engine load-time validation
- Runtime matching validation
- Disjointness from human roles and approver deciders

```mermaid
classDiagram
class AgentRoleVocabulary {
+diagnostician : str
+orchestrator : str
+executor : str
+AGENT_ROLES : frozenset
}
class PolicyRule {
+agent_roles_any : tuple[str, ...]
+roles_any : tuple[str, ...]
+actions_any : tuple[str, ...]
}
class EvaluationContext {
+agent_role : str | None
+roles : list[str]
+action : str
}
AgentRoleVocabulary --> PolicyRule : constrains
EvaluationContext --> PolicyRule : composes conjunctively
```

**Diagram sources**
- [agent_role.py:30-61](file://products/agent-platform/src/agent_service/services/agent_role.py#L30-L61)
- [policy_engine.py:138-143](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L138-L143)
- [policy_engine.py:186-197](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L186-L197)

**Section sources**
- [agent_role.py:30-61](file://products/agent-platform/src/agent_service/services/agent_role.py#L30-L61)
- [policy-engine.py:138-143](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L138-L143)
- [policy-engine.py:186-197](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L186-L197)

### Conjunctive Role Composition
The agent-role axis composes conjunctively with human roles, meaning both conditions must be satisfied:

- A rule with `agent_roles_any` only matches when the call's `agent_role` is in the specified set
- The human token must still hold one of the `roles_any` values
- An unscoped call (`agent_role=None`) never matches a scoped rule (fail-closed)
- The axis can only narrow authority, never widen it beyond what human roles permit

```mermaid
flowchart TD
A["Human roles: operator"] --> C{"Match roles_any?"}
B["Agent role: executor"] --> D{"Match agent_roles_any?"}
C --> |Yes| E{"Both axes match?"}
C --> |No| F["No match"]
D --> |Yes| E
D --> |No| F
E --> |Yes| G["Rule matches"]
E --> |No| F
```

**Diagram sources**
- [policy_engine.py:458-459](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L458-L459)
- [test_policy_engine.py:684-696](file://products/platform-gateway/tests/test_policy_engine.py#L684-L696)

**Section sources**
- [policy_engine.py:458-459](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L458-L459)
- [test_policy_engine.py:684-696](file://products/platform-gateway/tests/test_policy_engine.py#L684-L696)

### Invariant Enforcement and Safety Guarantees
The implementation enforces several critical invariants:

- **Subtractive-only**: Agent-role scoping can only remove authority the token already grants
- **Fail-closed**: Unknown or absent agent-roles result in most restrictive posture
- **Executor→human approver**: Executor-staged mutations require human approval, never agent approval
- **Disjoint vocabularies**: Agent roles never appear in human `roles_any` or approver `decided_by_roles`
- **Reachability guard**: No deployed code threads non-None agent-role values

```mermaid
flowchart TD
A["Agent Role Invariants"] --> B["Subtractive-only"]
A --> C["Fail-closed"]
A --> D["Executor→human approver"]
A --> E["Disjoint vocabularies"]
A --> F["Reachability guard"]
B --> G["Never widens human authority"]
C --> H["Unknown roles = deny"]
D --> I["Agents never approve"]
E --> J["No role confusion"]
F --> K["Phase 3 inertness"]
```

**Diagram sources**
- [test_policy_engine.py:698-725](file://products/platform-gateway/tests/test_policy_engine.py#L698-L725)
- [test_policy_engine.py:842-861](file://products/platform-gateway/tests/test_policy_engine.py#L842-L861)
- [test_policy_engine.py:863-890](file://products/platform-gateway/tests/test_policy_engine.py#L863-890)

**Section sources**
- [test_policy_engine.py:698-725](file://products/platform-gateway/tests/test_policy_engine.py#L698-L725)
- [test_policy_engine.py:842-861](file://products/platform-gateway/tests/test_policy_engine.py#L842-L861)
- [test_policy_engine.py:863-890](file://products/platform-gateway/tests/test_policy_engine.py#L863-890)

## SPEC-076 Bounded Autonomous Diagnosis Policy Enforcement

### Canonical Agent-Role Rules
SPEC-076 introduces two canonical `agent_roles_any` rules that encode the bounded autonomous diagnosis policy:

- **deny-diagnostician-tools-mutate**: Prevents diagnostician agent-roles from executing mutating tools (priority 300)
- **require-approval-executor-tools-mutate**: Requires tier_2 approval for executor agent-roles staging mutations (priority 200)

These rules are implemented as the minimal canonical encoding per OQ-4 resolution, keeping the existing action-based axis rather than adding a tool-family dimension.

```mermaid
flowchart TD
A["tools:mutate request"] --> B{"agent_role == 'diagnostician'?"}
B --> |Yes| C["deny-diagnostician-tools-mutate<br/>Priority 300 → DENY"]
B --> |No| D{"agent_role == 'executor'?"}
D --> |Yes| E["require-approval-executor-tools-mutate<br/>Priority 200 → require_approval"]
D --> |No| F["Continue normal evaluation"]
```

**Diagram sources**
- [policy-default.yaml:214-251](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L214-L251)
- [policy-default.yaml:214-251](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml#L214-L251)

### Ready-But-Inert Deployment Status
The SPEC-076 canonical rules remain ready-but-inert in deployment because:

- SPEC-073 R-3 keeps the bound `agent_role` off every wire field
- No deployed gateway `evaluate()` calls thread a non-None `agent_role`
- The live read-only control is provided by in-process SPEC-073 toolkit narrowing
- The loop's `read_only=True` admission provides additional safety
- Making the policy axis itself live is deferred to follow-up `FU-076-c`

```mermaid
flowchart TD
A["Deployed System"] --> B{"agent_role threaded?"}
B --> |No| C["Rules ready but inert<br/>Byte-identical to pre-SPEC-076"]
B --> |Yes| D["Rules would fire<br/>Future: FU-076-c or phase-6 wire"]
C --> E["Live control via:<br/>- SPEC-073 toolkit narrowing<br/>- Loop read_only=True admission"]
D --> F["Phase-6 wire contract<br/>or in-process evaluation point"]
```

**Diagram sources**
- [spec.md (SPEC-076):263-276](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/spec.md#L263-L276)
- [plan.md (SPEC-076):14-24](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/plan.md#L14-L24)

### Diagnostician Deny Rule Behavior
The `deny-diagnostician-tools-mutate` rule ensures that diagnostician agent-roles can never execute mutating tools:

- Matches all operational human roles (platform-admin, approver, operator, developer, read-only-observer)
- Applies specifically to `tools:mutate` action
- Targets only `diagnostician` agent-role
- Has highest priority (300) among the canonical rules
- Overrides any other allow rules for diagnostician mutations

```mermaid
flowchart TD
A["Diagnostician mutation attempt"] --> B["Match roles_any: operational roles"]
B --> C["Match actions_any: tools:mutate"]
C --> D["Match agent_roles_any: diagnostician"]
D --> E["Priority 300 → DENY"]
```

**Diagram sources**
- [policy-default.yaml:214-225](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L214-L225)
- [test_policy_engine.py:675-685](file://products/platform-gateway/tests/test_policy_engine.py#L675-L685)

### Executor Require-Approval Rule Behavior
The `require-approval-executor-tools-mutate` rule encodes the diagnose-before-act ceiling:

- Matches mutating-capable human roles (platform-admin, approver, operator, developer)
- Applies to `tools:mutate` action
- Targets only `executor` agent-role
- Requires tier_2 approval by distinct humans (approver, platform-admin)
- Is deliberately redundant with human-axis rules for identical outcomes

```mermaid
flowchart TD
A["Executor mutation staging"] --> B["Match roles_any: mutating-capable roles"]
B --> C["Match actions_any: tools:mutate"]
C --> D["Match agent_roles_any: executor"]
D --> E["Priority 200 → require_approval"]
E --> F["Tier 2 approval by approver/platform-admin"]
```

**Diagram sources**
- [policy-default.yaml:238-251](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L238-L251)
- [test_policy_engine.py:689-694](file://products/platform-gateway/tests/test_policy_engine.py#L689-L694)

### Byte-Identical Bundle Synchronization
The canonical rules are synchronized byte-identically across all four bundle replicas:

- `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`
- `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`
- `shared/shared-contracts/policies/policy-default.yaml`
- `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`

The synchronization is enforced via `make sync-policy`, and bundle parity is verified by tests.

```mermaid
flowchart TD
A["Canonical Rules"] --> B["Platform Gateway Bundle"]
A --> C["Tool Gateway Bundle"]
A --> D["Shared Contracts Bundle"]
A --> E["GitOps Dev Bundle"]
B --> F["make sync-policy"]
C --> F
D --> F
E --> F
F --> G["Bundle Parity Verification"]
```

**Diagram sources**
- [tasks.md (SPEC-076):75-78](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/tasks.md#L75-L78)
- [test_policy_engine.py:843-862](file://products/platform-gateway/tests/test_policy_engine.py#L843-L862)

**Section sources**
- [policy-default.yaml:200-251](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L200-L251)
- [policy-default.yaml:200-251](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml#L200-L251)
- [spec.md (SPEC-076):243-276](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/spec.md#L243-L276)
- [plan.md (SPEC-076):110-123](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/plan.md#L110-L123)
- [tasks.md (SPEC-076):69-88](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/tasks.md#L69-L88)

## Detailed Component Analysis

### Policy Rule Format and Validation
- Rules are defined in YAML bundles under each gateway's policies directory.
- Each rule includes id, domain, description, priority, enabled, match (roles_any, actions_any), and decision (outcome, optional approval).
- The shared JSON Schema defines the contract for rules and decisions.
- The platform gateway enforces that require_approval rules apply only to bridged actions (currently tools:mutate). The tool gateway skips require_approval rules entirely because it has no approval substrate.
- **Updated** The v3 schema now supports optional `agent_roles_any` field with closed vocabulary validation. The SPEC-076 canonical rules demonstrate the proper usage pattern for agent-role scoping.

```mermaid
flowchart TD
Start(["Load Bundle"]) --> Parse["Parse YAML into rules"]
Parse --> Validate{"Outcome valid?"}
Validate --> |No| Error["PolicyLoadError"]
Validate --> |Yes| CheckApproval{"require_approval?"}
CheckApproval --> |Yes| BridgeCheck{"Bridged action?"}
BridgeCheck --> |No| Error
BridgeCheck --> |Yes| BuildApproval["Build ApprovalSpec"]
CheckApproval --> |No| SkipApproval["No approval block"]
BuildApproval --> CheckAgentRoles{"Has agent_roles_any?"}
SkipApproval --> CheckAgentRoles
CheckAgentRoles --> |Yes| ValidateVocab{"Valid vocabulary?"}
CheckAgentRoles --> |No| Cache["Cache rules + SHA-256"]
ValidateVocab --> |Yes| Cache
ValidateVocab --> |No| Error
Cache --> End(["Ready for evaluate()"])
```

**Diagram sources**
- [policy_engine.py:269-331](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L269-L331)
- [policy_engine.py:192-251](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L192-L251)
- [policy-rule.schema.json:1-105](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L105)

**Section sources**
- [policy_engine.py:229-331](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L229-L331)
- [policy_engine.py:152-251](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L152-L251)
- [policy-rule.schema.json:1-105](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L105)

### Risk Tier Evaluation and Tool Permission Checks
- Risk tiers are part of the broader authorization model and influence default behavior and approval requirements.
- In the platform gateway, mutating tool execution is gated via the tools:mutate action and requires tier_2 approval by designated approvers distinct from the requester.
- In the tool gateway, read-only tool execution requires tools:invoke; write/admin tools additionally require tools:mutate. The tool gateway performs allow/deny admission only; approvals are enforced upstream.
- **Updated** Tool execution may now trigger the OQ-7 authorization flow instead of immediate allow/deny. When a tool requires user delegation, the system returns an authorization_required signal rather than executing the tool directly. The SPEC-076 canonical rules provide additional agent-role-based restrictions on top of these existing mechanisms.

```mermaid
flowchart TD
A["Incoming tool call"] --> B{"Action type?"}
B --> |Read-only| C["Evaluate tools:list/tools:invoke"]
B --> |Write/Admin| D["Evaluate tools:mutate"]
C --> E{"Allow?"}
D --> F{"Require approval?"}
E --> |Yes| G{"User delegation needed?"}
G --> |Yes| H["Emit authorization_required signal"]
G --> |No| I["Proceed to tool execution"]
F --> |Yes| J["Park confirmation for tier_2 approval"]
F --> |No| K{"Allow?"}
K --> |Yes| L{"User delegation needed?"}
L --> |Yes| H
L --> |No| I
K --> |No| M["Deny"]
```

**Diagram sources**
- [policy-default.yaml:90-151](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L90-L151)
- [policy-default.yaml:90-151](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml#L90-L151)
- [oq7-first-use-handoff-contract.md:85-141](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md#L85-L141)

**Section sources**
- [policy-default.yaml:90-151](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L90-L151)
- [policy-default.yaml:90-151](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml#L90-L151)
- [policy_engine.py:32-52](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L32-L52)
- [oq7-first-use-handoff-contract.md:85-141](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md#L85-L141)

### Policy Matrix Structure and Live Transparency
- The live matrix is derived by evaluating every role × action pair through the same evaluate() function used for enforcement.
- For platform-admin, the matrix shows all roles; for other identities, only their granted roles are shown.
- Cells evaluating to require_approval appear as false in the boolean matrix and additionally include approval_requirements with tier and decider roles.
- **Updated** The matrix currently remains human-role-only per OQ-5 resolution, with agent-role projection deferred to later phases. The SPEC-076 canonical rules are included in the matrix evaluation but remain inert since no agent-role is threaded.

```mermaid
classDiagram
class PolicyMatrix {
+version
+source
+sha256
+scope
+roles
+actions
+matrix
+approval_requirements
}
class PolicyEngine {
+evaluate(roles, action, agent_role=None) PolicyDecision
+bundle_metadata() dict
}
PolicyMatrix --> PolicyEngine : "uses evaluate()"
```

**Diagram sources**
- [policy_matrix.py:31-88](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L88)
- [policy_engine.py:374-387](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L374-L387)
- [policy-matrix.schema.json:1-85](file://shared/shared-contracts/schemas/policy-matrix.schema.json#L1-L85)

**Section sources**
- [policy_matrix.py:31-88](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L88)
- [policy-matrix.schema.json:1-85](file://shared/shared-contracts/schemas/policy-matrix.schema.json#L1-L85)

### Integration with Identity Broker and User Context
- The policy engine consumes normalized roles supplied by the identity layer. The platform gateway uses these roles to evaluate protected actions.
- The tool gateway similarly uses normalized roles for tool invocation admission.
- The design documentation outlines normalization and environment scoping expectations consumed by the policy engine.
- **Updated** The authorization contract integration extends this pattern by adding owner-scoped identity binding for authorization transactions. Owner namespace and subject are recovered from authenticated server context, never from callback input. The SPEC-076 bounded autonomy maintains the same-token identity preservation across fan-out without introducing new identity edges.

```mermaid
sequenceDiagram
participant IdP as "Identity Broker"
participant PGW as "Platform Gateway"
participant PE as "Policy Engine"
participant ATX as "Authorization Transaction Store"
IdP-->>PGW : Normalized roles and identity context
PGW->>PE : evaluate(roles, action, agent_role=None)
PE-->>PGW : Decision
PGW-->>IdP : Audit events (via audit emitter)
Note over ATX : Owner namespace + subject binding
```

**Diagram sources**
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [policy_engine.py:299-355](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L299-L355)
- [authorization_transactions.py:34-63](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L34-L63)

**Section sources**
- [policy-specification.md:88-120](file://docs/agentic-aiops-platform/policy-specification.md#L88-L120)
- [authorization_transactions.py:34-63](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L34-L63)

### Approval Workflows and HITL Bridging
- Mutating tool execution triggers a require_approval decision with tier_2 approval by designated approvers distinct from the requester.
- The platform gateway parks the confirmation and coordinates approval; the tool gateway does not enforce approvals.
- The authorization matrix documents the separation of duties and approval boundaries.
- **Updated** The authorization contract provides an alternative flow for user delegation that doesn't involve traditional approval workflows. Instead, it guides users through browser-based authorization to obtain delegated credentials. The SPEC-076 executor staging mechanism reuses the existing HITL infrastructure for proposed remediations.

```mermaid
sequenceDiagram
participant Client as "Operator"
participant PGW as "Platform Gateway"
participant PE as "Policy Engine"
participant Approver as "Approver"
participant TM as "Tool Gateway"
participant Portal as "Portal UI"
Client->>PGW : chat : confirm (parked call)
PGW->>PE : evaluate("chat : confirm")
PE-->>PGW : allow
PGW->>PE : evaluate("tools : mutate")
PE-->>PGW : require_approval (tier_2)
PGW->>Approver : Present approval card
Approver-->>PGW : Approve
PGW->>TM : Execute with delegated token
TM-->>PGW : Result
PGW-->>Client : Final result
Note over Portal : Alternative flow for user delegation
```

**Diagram sources**
- [policy-default.yaml:130-151](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L130-L151)
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [authorization-matrix.md:378-397](file://docs/agentic-aiops-platform/authorization-matrix.md#L378-L397)

**Section sources**
- [policy-default.yaml:130-151](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L130-L151)
- [authorization-matrix.md:378-397](file://docs/agentic-aiops-platform/authorization-matrix.md#L378-L397)
- [oq7-first-use-handoff-contract.md:346-382](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md#L346-L382)

### Policy Conflicts and Overrides
- Precedence: explicit deny > require_approval > allow.
- Within the same outcome class, higher priority wins.
- Disabled rules are ignored.
- These semantics are enforced in the evaluator and documented in the policy specification.
- **Updated** Agent-role scoping composes conjunctively with human roles and cannot override explicit denies. The SPEC-076 canonical rules demonstrate this with the diagnostician deny rule having priority 300 (highest) and the executor require_approval rule having priority 200.

```mermaid
flowchart TD
M["Matched rules"] --> D{"Any deny?"}
D --> |Yes| DENY["Return deny"]
D --> |No| RA{"Any require_approval?"}
RA --> |Yes| BEST_RA["Pick highest priority require_approval"]
RA --> |No| AL{"Any allow?"}
AL --> |Yes| BEST_AL["Pick highest priority allow"]
AL --> |No| DEFAULT_DENY["Deny by default"]
```

**Diagram sources**
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [policy-specification.md:256-274](file://docs/agentic-aiops-platform/policy-specification.md#L256-L274)

**Section sources**
- [policy_engine.py:390-444](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L390-L444)
- [policy-specification.md:256-274](file://docs/agentic-aiops-platform/policy-specification.md#L256-L274)

### Examples of Policy Rules and Decision Outcomes
- Read access: roles holding chat/session actions may use chat and manage sessions.
- Observer access: read-only observers may query via chat and view sessions.
- Tool invocation: operational, developer, approver, and observer roles may invoke read-only tools.
- Mutating tools: require tier_2 approval by approver or platform-admin distinct from requester.
- Audit and transparency: auditors and platform admins may read audit trails; all roles may read policy and skills inventory.
- **Updated** New authorization-related outcomes may include authorization_required signals that trigger the OQ-7 handoff flow instead of traditional allow/deny decisions. The SPEC-076 canonical rules provide concrete examples of agent-role-scoped policy enforcement.

These examples are defined in the default bundles and validated by the schemas.

**Section sources**
- [policy-default.yaml:54-151](file://products/platform-gateway/src/platform_gateway/policies/policy-default.yaml#L54-L151)
- [policy-default.yaml:54-151](file://products/tool-gateway/src/tool_gateway/policies/policy-default.yaml#L54-L151)
- [policy-rule.schema.json:1-105](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L105)
- [oq7-first-use-handoff-contract.md:85-141](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md#L85-L141)

## Dependency Analysis
- Platform Gateway depends on:
  - Its own policy engine for evaluation and matrix derivation.
  - The default bundle for canonical rules.
  - Shared schemas for validation and transparency surfaces.
  - Authorization schemas for portal wire shapes.
- Tool Gateway depends on:
  - Its own policy engine for admission control.
  - The default bundle for tool-related actions.
  - Shared schemas for validation.
  - Authorization transaction store interface for OQ-7 support.
- **Updated** Both gateways now depend on the authorization contract definitions, the SPEC-074 agent-role vocabulary, and the SPEC-076 canonical rules. Only the tool gateway implements the transaction store interface. The canonical rules are synchronized across all four bundle replicas.

```mermaid
graph LR
PGW_PE["Platform Gateway Policy Engine"] --> PGW_BUNDLE["Platform Default Bundle"]
PGW_PE --> SCHEMA_R["policy-rule.schema.json v3"]
PGW_PE --> SCHEMA_M["policy-matrix.schema.json"]
PGW_AUTH["Platform Authorization Schemas"] --> OQ7_CONTRACT["OQ-7 Contract"]
TGW_PE["Tool Gateway Policy Engine"] --> TGW_BUNDLE["Tool Default Bundle"]
TGW_PE --> SCHEMA_R
TGW_PE --> SCHEMA_M
AUTH_TX["Authorization Transaction Store"] --> AUTH_SCHEMA["Authorization Schemas"]
AUTH_SCHEMA --> TOOL_RESULT["tool-result.schema.json"]
AGENT_ROLE["Agent Role Vocabulary"] --> PGW_PE
AGENT_ROLE --> TGW_PE
SPEC076_RULES["SPEC-076 Canonical Rules"] --> PGW_BUNDLE
SPEC076_RULES --> TGW_BUNDLE
```

**Diagram sources**
- [policy_engine.py:334-371](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L334-L371)
- [policy_engine.py:254-287](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L287)
- [authorization_transactions.py:1-122](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L1-L122)
- [authorization.py (tool-gateway):1-74](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L1-L74)
- [authorization.py (platform-gateway):1-47](file://products/platform-gateway/src/platform_gateway/schemas/authorization.py#L1-L47)

**Section sources**
- [policy_engine.py:334-371](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L334-L371)
- [policy_engine.py:254-287](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L254-L287)
- [authorization_transactions.py:1-122](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L1-L122)

## Performance Considerations
- Bundles are parsed once and cached per process; subsequent evaluations reuse the in-memory rule list.
- Evaluations scan enabled rules matching the requested action and intersecting caller roles; complexity is linear in the number of enabled rules.
- The live matrix builds rows by evaluating each role × action pair; this is intentionally read-only and can be cached at the API layer if needed.
- Authorization transactions are designed for bounded lifetimes (60 seconds start TTL, 600 seconds transaction TTL) to minimize storage overhead.
- **Updated** Agent-role scoping adds minimal overhead since it's a simple tuple membership check that composes with existing role matching logic. The SPEC-076 canonical rules add two additional rules to evaluate but maintain the same linear complexity profile.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and diagnostics:
- PolicyLoadError during bundle load indicates invalid YAML, missing required fields, unknown outcomes, or invalid approval blocks.
- require_approval on non-bridged actions fails at load time in the platform gateway.
- Missing policy path raises a clear error rather than silently falling back.
- Use the live policy matrix endpoint to verify effective permissions and approval requirements for the current bundle.
- Compare bundle SHA-256 fingerprints to confirm the enforced bundle matches the intended commit.
- **Updated** Authorization contract issues:
  - Authorization models reject secret fields in public responses
  - No authorization routes are registered (by design)
  - Transaction store Protocol methods require owner namespace and subject binding
  - Invalid challenge IDs or expired transactions return None without revealing failure details
- **Updated** Agent-role axis issues:
  - Out-of-vocabulary agent_roles_any values cause PolicyLoadError during bundle load
  - Non-list agent_roles_any values are rejected at load time
  - Reachability guard tests detect unauthorized threading of agent-role literals
  - Disjointness guard tests ensure agent roles don't appear in human roles or approver deciders
- **Updated** SPEC-076 canonical rule issues:
  - Bundle synchronization failures indicate non-byte-identical replicas
  - Canonical rule validation failures suggest incorrect agent_roles_any values
  - Ready-but-inert deployment is expected - rules won't match without agent-role threading

**Section sources**
- [policy_engine.py:229-331](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L229-L331)
- [policy_engine.py:334-371](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L334-L371)
- [policy_matrix.py:31-88](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L88)
- [test_authorization_contracts.py (tool-gateway):31-84](file://products/tool-gateway/tests/test_authorization_contracts.py#L31-L84)
- [test_authorization_contracts.py (platform-gateway):17-46](file://products/platform-gateway/tests/test_authorization_contracts.py#L17-L46)
- [test_policy_engine.py:760-781](file://products/platform-gateway/tests/test_policy_engine.py#L760-L781)
- [test_policy_engine.py:842-890](file://products/platform-gateway/tests/test_policy_engine.py#L842-L890)

## Conclusion
The Platform Gateway's policy engine implements a compact, deterministic authorization model grounded in versioned YAML bundles, strict schema validation, and clear precedence rules. It integrates with the Identity Broker via normalized roles, enforces tool permissions at both gateways, and bridges approval workflows where necessary. The live policy matrix provides transparent, authoritative visibility into effective permissions and approval requirements, while bundle provenance ensures deploy-time verification.

**Updated** The OQ-7 authorization contract integration extends this foundation with a protocol for first-use target authorization handoffs. The SPEC-074 policy role axis adds an optional, additive agent-role dimension that composes conjunctively with human roles while maintaining backward compatibility. The SPEC-076 bounded autonomous diagnosis policy enforcement introduces two canonical rules (`deny-diagnostician-tools-mutate` and `require-approval-executor-tools-mutate`) that remain ready-but-inert in deployment since no deployed caller threads non-None agent-role values. The axis is implemented as an inert model dimension in phase 3, with comprehensive test coverage ensuring fail-closed behavior, subtractive-only semantics, and disjoint vocabularies. Future phases will introduce live producer wiring and canonical rule deployment.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Policy Rule Fields and Semantics
- id: unique stable identifier.
- domain: action_authz for this slice.
- description: human-readable explanation.
- priority: numeric precedence within an outcome class.
- enabled: whether the rule participates in evaluation.
- match.roles_any: principal must hold at least one listed role.
- match.actions_any: rule applies to listed actions.
- match.agent_roles_any: optional agent-role axis (SPEC-074, v3), closed to diagnostician/orchestrator/executor.
- decision.outcome: allow, deny, or require_approval.
- decision.approval: required for require_approval; includes tier and decided_by_roles; optional allow_self_approval override.

**Section sources**
- [policy-rule.schema.json:1-105](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L105)

### Live Matrix Fields and Semantics
- version, source, sha256: provenance of the loaded bundle.
- scope: full for platform-admin; own for others.
- roles, actions: sorted sets used to render the matrix.
- matrix: boolean cells indicating immediate allow.
- approval_requirements: additive third state for require_approval cells.

**Section sources**
- [policy-matrix.schema.json:1-85](file://shared/shared-contracts/schemas/policy-matrix.schema.json#L1-L85)
- [policy_matrix.py:31-88](file://products/platform-gateway/src/platform_gateway/services/policy_matrix.py#L31-L88)

### Authorization Contract Models
- AuthorizationRequired: Public challenge metadata with challenge_id, target, and expires_at fields
- AuthorizationStatusResponse: Status query response with exact field vocabulary
- AuthorizationTransaction: Routing state with owner binding and lifecycle management
- AuthorizationTransactionStore: Protocol interface for transaction persistence

**Section sources**
- [authorization.py (tool-gateway):24-74](file://products/tool-gateway/src/tool_gateway/schemas/authorization.py#L24-L74)
- [authorization_transactions.py:23-122](file://products/tool-gateway/src/tool_gateway/services/authorization_transactions.py#L23-L122)

### OQ-7 Contract Status
- Ratified 2026-10-19, closing pre-runtime gate
- Additive contract increment implemented 2026-10-23
- No usable OAuth flow enabled
- Contract-only v0.50.0 release approved
- AAP compatibility unverified
- DI-070 deployment integration remains pending

**Section sources**
- [spec.md (SPEC-070):1-95](file://docs/specs/SPEC-070-outbound-user-delegated-identity/spec.md#L1-L95)
- [plan.md (SPEC-070):46-80](file://docs/specs/SPEC-070-outbound-user-delegated-identity/plan.md#L46-L80)
- [oq7-first-use-handoff-contract.md:481-504](file://docs/specs/SPEC-070-outbound-user-delegated-identity/oq7-first-use-handoff-contract.md#L481-L504)

### SPEC-074 Policy Role Axis Status
- Delivered 2026-11-05 as v0.55.0
- Phase 3 inert model axis implementation complete
- Optional agent_roles_any field added to v3 schema
- Comprehensive test coverage for diagnostician/orchestrator/executor roles
- Reachability and disjointness guards verified
- Canonical bundle remains byte-unchanged
- No live producer threads agent-role values yet

**Section sources**
- [spec.md (SPEC-074):1-315](file://docs/specs/SPEC-074-policy-role-axis/spec.md#L1-L315)
- [plan.md (SPEC-074):1-40](file://docs/specs/SPEC-074-policy-role-axis/plan.md#L1-L40)
- [tasks.md (SPEC-074):1-90](file://docs/specs/SPEC-074-policy-role-axis/tasks.md#L1-L90)

### SPEC-076 Bounded Autonomous Diagnosis Status
- Approved 2026-11-06, targeting v0.57.0
- Two canonical agent_roles_any rules delivered: deny-diagnostician-tools-mutate and require-approval-executor-tools-mutate
- Rules remain ready-but-inert since no deployed caller threads non-None agent-role values
- In-process SPEC-073 toolkit narrowing provides live read-only control
- Byte-identical synchronization across all four bundle replicas
- Follow-ups recorded: FU-076 (unattended machine-trigger ingestion), FU-076-b (diagnose→act bridge), FU-076-c (live policy axis)

**Section sources**
- [spec.md (SPEC-076):1-531](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/spec.md#L1-L531)
- [plan.md (SPEC-076):1-233](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/plan.md#L1-L233)
- [tasks.md (SPEC-076):1-157](file://docs/specs/SPEC-076-bounded-autonomous-diagnosis/tasks.md#L1-L157)