# Policy Rules and Schema

<cite>
**Referenced Files in This Document**
- [policy-rule.schema.json](file://shared/shared-contracts/schemas/policy-rule.schema.json)
- [policy-decision.schema.json](file://shared/shared-contracts/schemas/policy-decision.schema.json)
- [policy-matrix.schema.json](file://shared/shared-contracts/schemas/policy-matrix.schema.json)
- [policy-default.yaml](file://shared/shared-contracts/policies/policy-default.yaml)
- [password-policy.yaml](file://shared/shared-contracts/policies/password-policy.yaml)
- [password_policy.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/tools/password_policy.py)
- [secrets_connector.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py)
- [validate_password_policy.py](file://shared/shared-contracts/scripts/validate_password_policy.py)
- [policy_engine.py (platform-gateway)](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py)
- [policy_engine.py (tool-gateway)](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py)
- [test_policy_engine.py (platform-gateway)](file://products/platform-gateway/tests/test_policy_engine.py)
- [test_policy_engine.py (tool-gateway)](file://products/tool-gateway/tests/test_policy_engine.py)
- [test_secrets_connector.py (tool-gateway)](file://products/tool-gateway/tests/test_secrets_connector.py)
- [policy_diff.py](file://shared/shared-contracts/scripts/policy_diff.py)
- [policy-specification.md](file://docs/agentic-aiops-platform/policy-specification.md)
- [authorization-matrix.md](file://docs/agentic-aiops-platform/authorization-matrix.md)
- [SPEC-074-policy-role-axis/spec.md](file://docs/specs/SPEC-074-policy-role-axis/spec.md)
</cite>

## Update Summary
**Changes Made**
- Updated policy rule schema documentation from v2 to v3 with new `agent_roles_any` field
- Added comprehensive documentation for agent role axis supporting diagnostician, orchestrator, and executor roles
- Enhanced match field documentation with agent role composition semantics
- Updated evaluation flow to include agent role filtering
- Added fail-closed behavior documentation for agent role scoping
- Updated examples to demonstrate agent role scoping patterns

## Table of Contents
1. Introduction
2. Project Structure
3. Core Components
4. Architecture Overview
5. Detailed Component Analysis
6. Agent Role Axis (v3 Enhancement)
7. Password Policy Engine
8. Dependency Analysis
9. Performance Considerations
10. Troubleshooting Guide
11. Conclusion
12. Appendices

## Introduction
This document explains the policy rule schema and structure used by the Luban AIOPS platform to authorize actions, gate approvals, and control execution. It covers the complete rule object shape, match fields, decision outcomes, approval tiers, and metadata. It also documents the four policy domains defined by the specification and clarifies which are enforced today versus those reserved for future expansion. Concrete YAML examples illustrate read-only access, production restart approvals, destructive action denials, and approver permissions. Guidance on rule ordering, priority conflicts, and best practices is included to help author maintainable policies.

**Updated** The platform now includes a comprehensive password policy engine that enforces fail-closed security policies for generated passwords, including minimum length requirements, entropy thresholds, and character class validation. **Updated** The policy rule schema has been extended from v2 to v3 with an optional `agent_roles_any` field that supports closed vocabulary of diagnostician, orchestrator, and executor roles for fine-grained agent authorization.

## Project Structure
Policy artifacts are split between shared contracts (schemas and default bundle) and gateway implementations that enforce them:
- Shared contracts define the canonical shapes for rules, decisions, and the live matrix.
- The default policy bundle defines concrete authorization behavior for the current surface.
- Platform-gateway enforces action authorization and bridges tiered approvals for mutating tool calls.
- Tool-gateway enforces admission for tool invocation and intentionally skips require_approval enforcement because it has no approval substrate.
- **New**: Password policy contract provides centralized enforcement for generated password strength.

```mermaid
graph TB
subgraph "Shared Contracts"
S1["policy-rule.schema.json<br/>(v3)"]
S2["policy-decision.schema.json"]
S3["policy-matrix.schema.json"]
S4["policy-default.yaml"]
S5["password-policy.yaml"]
end
subgraph "Platform Gateway"
P1["policy_engine.py"]
T1["tests/test_policy_engine.py"]
end
subgraph "Tool Gateway"
G1["policy_engine.py"]
G2["password_policy.py"]
G3["secrets_connector.py"]
T2["tests/test_policy_engine.py"]
T3["tests/test_secrets_connector.py"]
end
subgraph "Validation"
V1["validate_password_policy.py"]
end
S1 --> P1
S2 --> P1
S3 --> P1
S4 --> P1
S5 --> G2
S5 --> G3
S1 --> G1
S2 --> G1
S3 --> G1
S4 --> G1
V1 --> S5
V1 --> G2
P1 --> T1
G1 --> T2
G2 --> T3
G3 --> T3
```

**Diagram sources**
- [policy-rule.schema.json:1-110](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L110)
- [policy-decision.schema.json:1-60](file://shared/shared-contracts/schemas/policy-decision.schema.json#L1-L60)
- [policy-matrix.schema.json:1-85](file://shared/shared-contracts/schemas/policy-matrix.schema.json#L1-L85)
- [policy-default.yaml:1-326](file://shared/shared-contracts/policies/policy-default.yaml#L1-L326)
- [password-policy.yaml:1-48](file://shared/shared-contracts/policies/password-policy.yaml#L1-L48)
- [password_policy.py:1-346](file://products/tool-gateway/src/tool_gateway/tools/password_policy.py#L1-L346)
- [secrets_connector.py:1-654](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L1-L654)
- [validate_password_policy.py:1-261](file://shared/shared-contracts/scripts/validate_password_policy.py#L1-L261)

**Section sources**
- [policy-rule.schema.json:1-110](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L110)
- [policy-default.yaml:1-326](file://shared/shared-contracts/policies/policy-default.yaml#L1-L326)
- [password-policy.yaml:1-48](file://shared/shared-contracts/policies/password-policy.yaml#L1-L48)
- [policy_engine.py (platform-gateway):1-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L499)
- [policy_engine.py (tool-gateway):1-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L1-L419)

## Core Components
- Rule schema: Defines id, domain, description, priority, enabled, match, and decision with required and conditional fields.
- Decision schema: Defines the engine's output including decision, matched_rule_ids, reason, optional subject/action, and approval details when applicable.
- Matrix schema: Exposes a read-only view of effective role × action permissions and approval requirements derived from the loaded bundle.
- Default bundle: Concrete rules implementing deny-by-default semantics, explicit allow/deny grants, and tiered approval for mutating tool execution.
- **New**: Password policy contract: Centralized enforcement for generated password strength with fail-closed guarantees.

Key behaviors enforced by the engines:
- Deny by default when no rule matches.
- Explicit deny overrides require_approval and allow.
- require_approval overrides allow within matching rules.
- Higher priority wins among rules of the same outcome class.
- Disabled rules are ignored.
- **New**: Password generation fails closed when policy is unavailable or invalid.
- **New**: Agent role scoping is fail-closed - rules with `agent_roles_any` never match unscoped calls.

**Section sources**
- [policy-rule.schema.json:1-110](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L110)
- [policy-decision.schema.json:1-60](file://shared/shared-contracts/schemas/policy-decision.schema.json#L1-L60)
- [policy-matrix.schema.json:1-85](file://shared/shared-contracts/schemas/policy-matrix.schema.json#L1-L85)
- [policy-default.yaml:1-326](file://shared/shared-contracts/policies/policy-default.yaml#L1-L326)
- [password-policy.yaml:1-48](file://shared/shared-contracts/policies/password-policy.yaml#L1-L48)
- [policy_engine.py (platform-gateway):428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)
- [policy_engine.py (tool-gateway):348-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L348-L419)

## Architecture Overview
The platform uses a layered policy model across four domains. Today, the implementation enforces action_authz with allow/deny/require_approval outcomes; feature_access, approval, and execution_gate are specified for broader governance and future use.

```mermaid
sequenceDiagram
participant Client as "Client"
participant PG as "Platform Gateway<br/>policy_engine.evaluate()"
participant TG as "Tool Gateway<br/>policy_engine.evaluate()"
participant Bundle as "policy-default.yaml"
participant PolicyStore as "PasswordPolicyStore"
participant Decision as "PolicyDecision"
Client->>PG : Evaluate roles + action [+ agent_role]
PG->>Bundle : Load rules (deny-by-default)
PG->>PG : Match enabled rules by roles_any + actions_any [+ agent_roles_any]
alt Any deny matches
PG-->>Decision : decision=deny
else Require approval matches
PG-->>Decision : decision=require_approval<br/>approval=tier_1|tier_2
else Allow matches
PG-->>Decision : decision=allow
else No match
PG-->>Decision : decision=deny
end
Note over TG,Bundle : Tool-gateway skips require_approval enforcement<br/>and only evaluates allow/deny for tools : invoke/tools : mutate
Note over PolicyStore : Password generation requires valid policy<br/>or fails closed with INVALID_PARAMETERS
```

**Diagram sources**
- [policy_engine.py (platform-gateway):428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)
- [policy_engine.py (tool-gateway):348-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L348-L419)
- [password_policy.py:238-346](file://products/tool-gateway/src/tool_gateway/tools/password_policy.py#L238-L346)
- [policy-default.yaml:1-326](file://shared/shared-contracts/policies/policy-default.yaml#L1-L326)

**Section sources**
- [policy-specification.md:121-157](file://docs/agentic-aiops-platform/policy-specification.md#L121-L157)
- [policy_engine.py (platform-gateway):1-127](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L127)
- [policy_engine.py (tool-gateway):1-52](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L1-L52)

## Detailed Component Analysis

### Rule Object Schema
A policy rule contains:
- id: Unique identifier.
- domain: One of feature_access, action_authz, approval, execution_gate.
- description: Human-readable explanation.
- priority: Numeric precedence.
- enabled: Whether the rule participates.
- match: Criteria that determine applicability.
- decision: Outcome and optional approval block.
- conditions: Additional constraints (reserved for future use).
- metadata: Ownership, audit tags, rollout info (reserved for future use).

Current enforcement scope:
- The shipped engine implements action_authz with allowed outcomes allow, deny, require_approval.
- require_approval requires an approval block with tier and decided_by_roles.
- allow_with_conditions and conditions/metadata are reserved for future revisions.

Match fields:
- roles_any: Principal must hold at least one listed role.
- roles_all: All listed roles must be held (recommended field; not currently enforced in the minimal engine).
- environments_any: Target environment filter (recommended; not enforced in MVP).
- features_any: Feature flag or UI feature filter (recommended; not enforced in MVP).
- actions_any: Requested action must be in this list (required in current engine).
- target_types_any: Resource type filter (recommended; not enforced in MVP).
- risk_tiers_any: Risk tier filter (recommended; not enforced in MVP).
- approval_tiers_any: Approval tier filter (recommended; not enforced in MVP).
- service_criticality_any: Service criticality filter (recommended; not enforced in MVP).
- **agent_roles_any**: Optional agent-role axis (v3 enhancement) - rule matches only if the call carries one of these SPEC-073 agent-roles (diagnostician, orchestrator, executor); absent means unconstrained.

Examples of combining match fields:
- Read-only access: roles_any includes observers/operators; actions_any lists read actions; environments_any spans all environments; risk_tiers_any targets tier_0.
- Production restart approval: roles_any includes operators/approvers; actions_any includes restart-service; environments_any restricts to prod; risk_tiers_any targets tier_2; decision requires tier_2 approval.
- Destructive denial: actions_any includes delete-or-destructive; environments_any spans all; decision denies explicitly.
- Approver permissions: roles_any includes approver; approval_tiers_any targets tier_2; environments_any restricts to prod; decision may allow_with_conditions requiring non-self-approval and environment scope.
- **Agent role scoping**: agent_roles_any restricts rules to specific agent types (diagnostician, orchestrator, executor) while composing conjunctively with human roles_any.

**Section sources**
- [policy-rule.schema.json:1-110](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L110)
- [policy-specification.md:158-210](file://docs/agentic-aiops-platform/policy-specification.md#L158-L210)
- [policy-default.yaml:53-152](file://shared/shared-contracts/policies/policy-default.yaml#L53-L152)

### Decision Outcomes and Approval Tiers
Outcomes:
- allow: Proceed immediately.
- deny: Do not proceed.
- require_approval: Proceed only after successful tiered confirmation.

Approval tiers:
- tier_1: Session operator self-confirmation allowed by default; suitable for routine destructive-but-low-risk actions.
- tier_2: Requires a designated approver distinct from requester; self-approval forbidden by default.

Decision payload:
- decision, matched_rule_ids, reason are always present.
- action and subject are optional context.
- approval_tier and approval are present when decision is require_approval.

**Section sources**
- [policy-decision.schema.json:1-60](file://shared/shared-contracts/schemas/policy-decision.schema.json#L1-L60)
- [policy_engine.py (platform-gateway):142-194](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L142-L194)
- [policy_engine.py (platform-gateway):408-426](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L408-L426)

### Four Policy Domains
- feature_access: Controls portal screens, admin screens, approval queue visibility, and audit UI access. Not enforced by the current engine; used for UI gating and future policy surfaces.
- action_authz: Controls whether a user may request an action and whether it is denied outright. Enforced today with allow/deny/require_approval.
- approval: Controls whether approval is required, its tier, who may approve, and self-approval rules. Enforced via require_approval bridging on the platform-gateway confirm path.
- execution_gate: Controls whether execution may proceed after decision, condition satisfaction, and signed/scoped execution requests. Lightweight execution gate is part of the MVP profile; full enforcement is gated by additional workflow steps.

**Section sources**
- [policy-specification.md:121-157](file://docs/agentic-aiops-platform/policy-specification.md#L121-L157)
- [policy_engine.py (platform-gateway):119-127](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L119-L127)

### Concrete YAML Examples
Below are conceptual examples aligned with the specification and default bundle patterns. Refer to the cited files for exact structures and current enforcement.

- Read-only access rule:
  - Domain: action_authz
  - Match: roles_any includes observer/operator/developer/approver/auditor/platform-admin; actions_any includes read-status/read-logs/read-metrics; environments_any spans dev/test/staging/prod; risk_tiers_any targets tier_0
  - Decision: allow
  - See example pattern in specification sample rules.

- Production restart approval:
  - Domain: approval
  - Match: roles_any includes operator/approver/platform-admin; actions_any includes restart-service; environments_any targets prod; risk_tiers_any targets tier_2
  - Decision: require_approval with tier_2
  - Conditions: must_have_ticket_reference, must_not_be_self_approval
  - See example pattern in specification sample rules.

- Destructive action denial:
  - Domain: action_authz
  - Match: actions_any includes delete-or-destructive; environments_any spans all
  - Decision: deny
  - See example pattern in specification sample rules.

- Approver permissions:
  - Domain: approval
  - Match: roles_any includes approver; approval_tiers_any targets tier_2; environments_any targets prod
  - Decision: allow_with_conditions
  - Conditions: must_have_environment_scope, must_not_be_self_approval
  - See example pattern in specification sample rules.

- **Agent role scoped rule**:
  - Domain: action_authz
  - Match: roles_any includes operator; actions_any includes tools:read; agent_roles_any includes diagnostician
  - Decision: allow
  - Effect: Only diagnostician agents can perform this action, regardless of human roles

For reference to the shipped defaults:
- Mutating tool execution requires tier_2 approval by approver or platform-admin distinct from requester.
- Read-only tool invocation is allowed for operational roles and observers.
- Audit read is restricted to auditor and platform-admin.

**Section sources**
- [policy-specification.md:297-407](file://docs/agentic-aiops-platform/policy-specification.md#L297-L407)
- [policy-default.yaml:90-152](file://shared/shared-contracts/policies/policy-default.yaml#L90-L152)

### Evaluation Flow and Precedence
Evaluation order and precedence:
1. Validate request shape and identity context.
2. Evaluate feature_access policies (UI gating).
3. Evaluate action_authz policies (enforced).
4. Evaluate approval policies (bridged on confirm path).
5. Evaluate execution_gate policies if execution is requested.
6. Return final decision with matched rules and conditions.

Precedence:
- Explicit deny overrides require_approval and allow.
- More specific rules override broader rules.
- Higher priority wins when specificity is equal.
- If no rule matches, return deny.

Within the engine:
- Match enabled rules by roles_any and actions_any.
- **Agent role filtering**: Rules with agent_roles_any only match when the call carries a compatible agent_role.
- If any deny matches, return deny.
- Else if require_approval matches, pick highest priority and return require_approval with approval block.
- Else if allow matches, pick highest priority and return allow.
- Else return deny with "no matching policy rule".

**Section sources**
- [policy-specification.md:256-273](file://docs/agentic-aiops-platform/policy-specification.md#L256-L273)
- [policy_engine.py (platform-gateway):428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)
- [policy_engine.py (tool-gateway):348-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L348-L419)

### Class Model of Engine Types
```mermaid
classDiagram
class ApprovalSpec {
+string tier
+tuple~string~ decided_by_roles
+bool|None allow_self_approval
+effective_self_approval() bool
+to_dict() dict
}
class PolicyRule {
+string id
+int priority
+bool enabled
+tuple~string~ roles_any
+tuple~string~ actions_any
+tuple~string~ agent_roles_any
+string outcome
+ApprovalSpec|None approval
}
class PolicyDecision {
+string decision
+string[] matched_rule_ids
+string reason
+string|None action
+string|None subject
+ApprovalSpec|None approval
+approval_tier() string|None
+to_dict() dict
}
PolicyDecision --> ApprovalSpec : "carries"
PolicyRule --> ApprovalSpec : "optional"
```

**Diagram sources**
- [policy_engine.py (platform-gateway):142-194](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L142-L194)
- [policy_engine.py (tool-gateway):66-133](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L66-L133)

### API Workflow: Action Authorization
```mermaid
sequenceDiagram
participant Caller as "Caller"
participant Engine as "policy_engine.evaluate()"
participant Bundle as "Loaded Rules"
participant Result as "PolicyDecision"
Caller->>Engine : evaluate(roles, action, agent_role?)
Engine->>Bundle : load_bundle()
Engine->>Engine : filter enabled rules by roles_any ∩ actions_any ∩ agent_roles_any?
alt any deny
Engine-->>Result : decision=deny
else require_approval exists
Engine-->>Result : decision=require_approval<br/>approval=best.priority
else allow exists
Engine-->>Result : decision=allow
else none
Engine-->>Result : decision=deny
end
Caller-->>Result : inspect decision, matched_rule_ids, reason
```

**Diagram sources**
- [policy_engine.py (platform-gateway):428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)
- [policy_engine.py (tool-gateway):348-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L348-L419)

## Agent Role Axis (v3 Enhancement)

**New Section** The Luban AIOPS platform extends the policy rule schema from v2 to v3 with an optional `agent_roles_any` field that enables fine-grained authorization based on agent roles. This enhancement supports the closed vocabulary of diagnostician, orchestrator, and executor roles established by SPEC-073.

### Schema Evolution (v2 → v3)
The policy rule schema has been updated to version 3 with additive changes:
- **Title**: Changed from "Policy Rule (v2)" to "Policy Rule (v3)"
- **Description**: Updated to document the new agent-role axis
- **New Field**: `agent_roles_any` added to the match block properties
- **Backward Compatibility**: The change is fully additive - existing v2 rules validate unchanged against v3

### Agent Role Vocabulary
The system supports three closed agent roles:
- **diagnostician**: Read-level tools only, reuses read-only filtering
- **orchestrator**: No direct gateway tools - delegates rather than executing directly  
- **executor**: Full discovered set - can propose mutations that still require human approval

### Agent Role Matching Semantics
The agent role axis composes conjunctively with human roles:
- A rule matches only if the principal holds a `roles_any` human role AND (the rule has no `agent_roles_any`, or the call's `agent_role` is in it)
- Rules with `agent_roles_any` never match unscoped calls (`agent_role=None`) - fail-closed behavior
- The axis narrows only - it can never widen what the human token roles already permit
- Absent `agent_roles_any` means unconstrained (matches regardless of agent-role)

### Fail-Closed Enforcement
The agent role axis implements fail-closed security:
- **Unscoped calls**: Rules with `agent_roles_any` never match when `agent_role=None`
- **Unknown roles**: Invalid agent-role values fail schema validation
- **Subtractive only**: Agent roles can only remove authority, never add it
- **Inert deployment**: Phase 3 ships without live producer threading agent roles

### Implementation Details
Both gateway engines implement the agent role axis:
- **Platform Gateway**: `evaluate(settings, roles, action, agent_role=None)` with full approval support
- **Tool Gateway**: `evaluate(settings, roles, action, agent_role=None)` with allow/deny only (no approval substrate)
- **Schema Validation**: Closed vocabulary enforced at both schema and runtime levels
- **Bundle Loading**: Optional `agent_roles_any` parsed during rule loading

### Security Invariants
The agent role axis enforces critical security properties:
- **Executor→Human Approver Disjointness**: Agent roles can never appear as approver deciders
- **No Agent Self-Approval**: An agent-role is never a human role nor an approver decider
- **Role Vocabulary Guard**: Tests ensure no overlap between agent roles and human platform roles
- **Reachability Guard**: Phase 3 proves no deployed caller threads a non-None agent_role

**Section sources**
- [policy-rule.schema.json:1-110](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L110)
- [policy_engine.py (platform-gateway):138-143](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L138-L143)
- [policy_engine.py (platform-gateway):428-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L428-L499)
- [policy_engine.py (tool-gateway):74-79](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L74-L79)
- [policy_engine.py (tool-gateway):348-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L348-L419)
- [SPEC-074-policy-role-axis/spec.md:108-145](file://docs/specs/SPEC-074-policy-role-axis/spec.md#L108-L145)

## Password Policy Engine

**Existing Section** The Luban AIOPS platform includes a comprehensive password policy engine that enforces fail-closed security policies for generated passwords. This system ensures that all generated passwords meet minimum security standards through centralized policy enforcement.

### Password Policy Contract
The password policy contract (`password-policy.yaml`) serves as the single source of truth for generated password strength. It defines:

- **min_length**: The minimum length a generated password must have (default: 16 characters)
- **hard_floor**: Absolute minimum length that cannot be bypassed (default: 12 characters)  
- **required_classes**: Character classes that must be present (upper, lower, digit, symbol)
- **entropy_floor_bits**: Minimum entropy requirement (default: 64 bits)
- **exclude_ambiguous**: Option to exclude visually ambiguous characters (I/l/1/O/0)

### Fail-Closed Enforcement
The password policy engine implements fail-closed security:

- **Unavailable policy**: Generation refuses with `INVALID_PARAMETERS` error
- **Invalid policy**: Generation refuses without falling back to defaults
- **Weak policy**: Environment overrides can only tighten, never weaken the contract
- **Missing contract**: System refuses generation rather than using built-in defaults

### Policy Store Implementation
The `PasswordPolicyStore` provides lazy-loading with automatic refresh:

- **Mtime-based reloading**: Detects policy file changes without restart
- **Fail-closed loading**: Invalid or unreadable policies clear active state
- **No content logging**: Policy contents are never logged for security
- **Packaged fallback**: Uses embedded policy when no custom path is configured

### Password Generation Algorithm
The generation algorithm ensures cryptographic security:

- **CSPRNG source**: Uses Python's `secrets` module for cryptographically secure randomness
- **Class seeding**: Guarantees at least one character from each required class
- **Entropy validation**: Verifies generated passwords meet entropy floor requirements
- **Fisher-Yates shuffle**: Ensures unbiased character distribution

### Configuration and Overrides
Environment variables provide controlled tightening:

- **GATEWAY_PASSWORD_MIN_LENGTH**: Raises minimum length (cannot weaken below contract)
- **GATEWAY_PASSWORD_REQUIRED_CLASSES**: Adds required character classes (must include contract classes)
- **GATEWAY_PASSWORD_EXCLUDE_AMBIGUOUS**: Enables ambiguous character exclusion

### Validation and Testing
Comprehensive validation ensures policy integrity:

- **Contract validation**: Verifies YAML structure and field types
- **Connector pinning**: Ensures hardcoded values match contract specifications
- **Integration testing**: Tests fail-closed behavior and policy enforcement
- **Security mutation checks**: Validates no plaintext leakage in projections

**Section sources**
- [password-policy.yaml:1-48](file://shared/shared-contracts/policies/password-policy.yaml#L1-L48)
- [password_policy.py:1-346](file://products/tool-gateway/src/tool_gateway/tools/password_policy.py#L1-L346)
- [secrets_connector.py:1-654](file://products/tool-gateway/src/tool_gateway/tools/secrets_connector.py#L1-L654)
- [validate_password_policy.py:1-261](file://shared/shared-contracts/scripts/validate_password_policy.py#L1-L261)
- [test_secrets_connector.py:135-213](file://products/tool-gateway/tests/test_secrets_connector.py#L135-L213)

## Dependency Analysis
- Schemas define the contract consumed by both gateways.
- Default bundle provides the authoritative policy set.
- Platform-gateway enforces action_authz and bridges require_approval for tools:mutate.
- Tool-gateway enforces allow/deny for tools:invoke and tools:mutate; require_approval rules are skipped at load because there is no approval substrate.
- **New**: Password policy contract provides centralized enforcement for generated password strength.
- Tests validate deny-by-default, higher-priority wins, and role/action matching.

```mermaid
graph LR
Schema["Schemas<br/>(v3)"] --> PG["Platform Gateway Engine"]
Schema --> TG["Tool Gateway Engine"]
Bundle["Default Bundle"] --> PG
Bundle --> TG
PasswordPolicy["Password Policy Contract"] --> TG
PG --> TestsPG["Platform Gateway Tests"]
TG --> TestsTG["Tool Gateway Tests"]
PasswordPolicyValidator["Password Policy Validator"] --> PasswordPolicy
PasswordPolicyValidator --> TG
```

**Diagram sources**
- [policy-rule.schema.json:1-110](file://shared/shared-contracts/schemas/policy-rule.schema.json#L1-L110)
- [policy-default.yaml:1-326](file://shared/shared-contracts/policies/policy-default.yaml#L1-L326)
- [password-policy.yaml:1-48](file://shared/shared-contracts/policies/password-policy.yaml#L1-L48)
- [password_policy.py:1-346](file://products/tool-gateway/src/tool_gateway/tools/password_policy.py#L1-L346)
- [validate_password_policy.py:1-261](file://shared/shared-contracts/scripts/validate_password_policy.py#L1-L261)
- [policy_engine.py (platform-gateway):1-499](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L499)
- [policy_engine.py (tool-gateway):1-419](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L1-L419)
- [test_policy_engine.py (platform-gateway):39-66](file://products/platform-gateway/tests/test_policy_engine.py#L39-L66)
- [test_policy_engine.py (tool-gateway):127-152](file://products/tool-gateway/tests/test_policy_engine.py#L127-L152)

**Section sources**
- [policy_engine.py (platform-gateway):1-127](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L1-L127)
- [policy_engine.py (tool-gateway):1-52](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L1-L52)
- [test_policy_engine.py (platform-gateway):39-66](file://products/platform-gateway/tests/test_policy_engine.py#L39-L66)
- [test_policy_engine.py (tool-gateway):127-152](file://products/tool-gateway/tests/test_policy_engine.py#L127-L152)

## Performance Considerations
- Rule evaluation is O(n) over enabled rules per request; keep bundles concise and well-scoped.
- Use precise actions_any and roles_any to minimize matches.
- Prefer explicit deny rules for high-risk actions to short-circuit further checks.
- Avoid overly broad roles_any unless necessary; combine with actions_any and other recommended match fields when supported.
- Leverage priority to resolve conflicts deterministically without duplicating logic.
- **New**: Password policy store uses lazy loading with mtime-based refresh to avoid unnecessary reloads.
- **New**: Password generation uses efficient CSPRNG operations with bounded alphabet sizes.
- **New**: Agent role filtering adds minimal overhead - simple tuple membership check.

## Troubleshooting Guide
Common issues and how to diagnose them:
- Unexpected deny:
  - Verify the action is protected and present in the bundle's vocabulary.
  - Confirm the caller's roles intersect with roles_any in a matching rule.
  - Check for explicit deny rules that override allow or require_approval.
  - See tests asserting deny-by-default for unknown actions or ungranted roles.

- Approval not triggered:
  - Ensure the action is in the bridged set for the gateway (tools:mutate on platform-gateway).
  - Confirm the rule outcome is require_approval and includes a valid approval block.
  - Validate tier and decided_by_roles; ensure self-approval settings align with tier defaults.

- Priority conflicts:
  - When multiple rules match, the highest priority within the same outcome class wins.
  - Use clear priorities and narrow scopes to avoid ambiguity.

- Bundle loading errors:
  - Invalid YAML or malformed rule structure raises load errors.
  - require_approval on non-bridged actions is rejected at load time in platform-gateway.
  - Tool-gateway logs warnings and skips require_approval rules due to lack of enforcement substrate.

- **Agent role issues**:
  - **Unexpected rule non-match**: Check if rule has `agent_roles_any` but call has `agent_role=None`
  - **Schema validation errors**: Verify agent-role values are from closed vocabulary (diagnostician, orchestrator, executor)
  - **Deployment concerns**: Phase 3 ships inert - no live producer threads agent roles yet

- **New**: Password policy issues:
  - **Policy unavailable**: Check that password-policy.yaml is readable and properly formatted
  - **Generation failures**: Verify policy meets minimum requirements (length ≥ 16, entropy ≥ 64 bits)
  - **Override conflicts**: Ensure environment variables don't weaken the base policy
  - **Validation errors**: Run `make validate-password-policy` to check contract consistency

Useful references:
- Default bundle comments explain precedence, tiers, and authoring conventions.
- Tests demonstrate expected behaviors for deny-by-default and priority resolution.
- Policy diff script can compute outcomes across role/action pairs and report bundle SHA-256.
- **New**: Password policy validator ensures contract and connector consistency.

**Section sources**
- [policy_default.yaml:1-39](file://shared/shared-contracts/policies/policy-default.yaml#L1-L39)
- [policy_engine.py (platform-gateway):229-331](file://products/platform-gateway/src/platform_gateway/services/policy_engine.py#L229-L331)
- [policy_engine.py (tool-gateway):152-251](file://products/tool-gateway/src/tool_gateway/services/policy_engine.py#L152-L251)
- [test_policy_engine.py (platform-gateway):55-66](file://products/platform-gateway/tests/test_policy_engine.py#L55-L66)
- [policy_diff.py:68-84](file://shared/shared-contracts/scripts/policy_diff.py#L68-L84)
- [validate_password_policy.py:223-261](file://shared/shared-contracts/scripts/validate_password_policy.py#L223-L261)

## Conclusion
The Luban AIOPS platform enforces a deny-by-default policy model with explicit allow/deny and tiered approval for risky actions. The current implementation focuses on action_authz with allow/deny/require_approval outcomes, while feature_access, approval, and execution_gate remain part of the broader specification for future expansion. By using precise match fields, clear priorities, and structured approval blocks, teams can author maintainable policies that scale safely across environments and roles.

**Updated** The platform now includes a comprehensive password policy engine that enforces fail-closed security policies for generated passwords, ensuring cryptographic strength through minimum length requirements, entropy thresholds, and character class validation. **Updated** The policy rule schema has been enhanced from v2 to v3 with an optional agent role axis that supports diagnostician, orchestrator, and executor roles for fine-grained agent authorization with fail-closed semantics. This addition strengthens the platform's security posture by centralizing password generation policies and providing robust validation against policy drift, while enabling future multi-agent orchestration scenarios.

## Appendices

### Best Practices for Authoring Policies
- Be explicit: prefer narrow roles_any and actions_any combinations.
- Use priority to express intent clearly; document rationale in description.
- For destructive or production actions, prefer require_approval with tier_2 and exclude self-approval.
- Keep rules focused on one concern; split complex logic into multiple rules.
- Validate bundles before deployment; use policy-diff to review changes.
- Audit and review changes through Git; version bumps signal policy drift.
- **New**: For agent role scoping, use `agent_roles_any` judiciously - remember it's subtractive-only and fail-closed.
- **New**: Test agent role policies thoroughly using the validation suite before deployment.
- **New**: For password policies, ensure generated passwords meet organizational security requirements through appropriate min_length and entropy settings.
- **New**: Test password policy changes thoroughly using the validation suite before deployment.

### Agent Role Security Guidelines
- **Closed Vocabulary**: Only use diagnostician, orchestrator, and executor roles
- **Fail-Closed Design**: Rules with `agent_roles_any` never match unscoped calls
- **Subtractive Only**: Agent roles can only narrow authority, never expand it
- **Disjoint Roles**: Agent roles are separate from human platform roles
- **No Agent Approval**: Agent roles can never be approver deciders
- **Phase 3 Inert**: Current deployment doesn't thread agent roles - axis is ready for future use

### Password Policy Security Guidelines
- **Minimum Length**: Set min_length to at least 16 characters for strong security
- **Character Classes**: Require all four classes (upper, lower, digit, symbol) for maximum entropy
- **Entropy Thresholds**: Ensure entropy_floor_bits meets organizational requirements (64+ bits recommended)
- **Ambiguous Characters**: Consider enabling exclude_ambiguous for manual entry scenarios
- **Environment Overrides**: Use environment variables to tighten policies without weakening the base contract
- **Policy Validation**: Regularly run validation checks to ensure policy consistency across deployments

[No sources needed since this section provides general guidance]