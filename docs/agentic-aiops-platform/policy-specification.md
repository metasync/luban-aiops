# Policy Specification

## Objective

Define a machine-oriented policy specification for the enterprise-grade agentic AIOps platform so the authorization matrix can be implemented consistently by platform services.

This document turns the design intent from:

- [identity-and-authorization-design.md](identity-and-authorization-design.md)
- [authorization-matrix.md](authorization-matrix.md)

into enforceable policy objects, evaluation flow, and concrete decision outputs.

## Goals

- define the policy evaluation model
- define a reusable rule schema
- define decision outcomes and approval triggers
- provide sample policy objects
- support MVP-first implementation while allowing future expansion

## Policy Scope

The policy engine should govern:

- portal feature access
- tool invocation authorization
- environment targeting
- approval requirements
- separation of duties
- execution gating

The policy engine should not be responsible for:

- authenticating users
- storing raw IdP credentials
- rendering UI logic

## Policy Principles

### 1. Deny by default

If no rule matches a request, the result should be `deny`.

### 2. Evaluate normalized identity only

The policy engine should consume normalized identity attributes produced after authentication and group mapping.

### 3. Keep route, feature, and action policies separate

Separate policy domains make policies easier to reason about and audit.

### 4. Approval is a policy outcome, not a UI feature

The policy engine should return `require_approval` as a first-class decision outcome.

### 5. Execution should only occur from approved policy decisions

Workers should execute only after the control plane records an allowed or approved decision.

## Policy Decision Outcomes

The policy engine should support these outcomes:

- `allow`
- `deny`
- `require_approval`
- `allow_with_conditions`

### Outcome Meaning

- `allow`
  - the request may proceed immediately
- `deny`
  - the request must not proceed
- `require_approval`
  - the request may proceed only after an approval workflow succeeds
- `allow_with_conditions`
  - the request may proceed if all returned conditions are satisfied

Examples of conditions:

- change window is open
- incident reference is present
- target environment is non-production
- self-approval is not used

## Policy Evaluation Inputs

Every request should be normalized into a policy input object.

### Required Inputs

- `request_id`
- `session_id`
- `principal.user_id`
- `principal.platform_roles`
- `principal.source_groups`
- `principal.environment_scopes`
- `principal.approval_scopes`
- `request.feature`
- `request.action`
- `request.target_type`
- `request.target_id`
- `request.environment`
- `request.risk_tier`
- `request.ticket_reference`
- `request.incident_reference`
- `request.change_window`
- `request.is_self_approval`

### Optional Inputs

- `principal.tenant_id`
- `principal.team_id`
- `request.service_criticality`
- `request.tool_name`
- `request.connector_name`
- `request.execution_mode`

## Policy Domains

### 1. Feature Access Policy

Controls:

- portal screens
- admin screens
- approval queue visibility
- audit UI access

### 2. Action Authorization Policy

Controls:

- whether a user may request an action
- whether the action is environment-allowed
- whether the action is denied outright

### 3. Approval Policy

Controls:

- whether approval is required
- what approval tier applies
- who may approve
- whether self-approval is allowed
- whether two-person approval is required

### 4. Execution Gate Policy

Controls:

- whether execution may proceed after decision
- whether conditions have been satisfied
- whether the execution request is properly signed and scoped

## Rule Schema

### Recommended Logical Shape

Each rule should contain:

- `id`
- `domain`
- `description`
- `priority`
- `enabled`
- `match`
- `decision`
- `conditions`
- `metadata`

### Field Definitions

- `id`
  - unique policy rule identifier
- `domain`
  - one of `feature_access`, `action_authz`, `approval`, `execution_gate`
- `description`
  - short human-readable explanation
- `priority`
  - numeric precedence
- `enabled`
  - whether the rule is active
- `match`
  - criteria that determine whether the rule applies
- `decision`
  - one of the supported outcomes
- `conditions`
  - additional constraints that must be satisfied
- `metadata`
  - ownership, audit tags, change ticket, or rollout info

## Match Schema

### Recommended Match Fields

- `roles_any`
- `roles_all`
- `environments_any`
- `features_any`
- `actions_any`
- `target_types_any`
- `risk_tiers_any`
- `approval_tiers_any`
- `service_criticality_any`

All match fields are optional, but a rule should include enough specificity to be safe and understandable.

## Condition Schema

### Recommended Condition Types

- `must_have_ticket_reference`
- `must_have_incident_reference`
- `must_be_within_change_window`
- `must_not_be_self_approval`
- `must_have_approver_role`
- `must_have_environment_scope`
- `must_have_signed_execution_request`

## Decision Object Schema

### Minimum Decision Response

The policy engine should return:

```json
{
  "decision": "require_approval",
  "matched_rule_ids": ["approval-prod-restart-tier2"],
  "approval_tier": "tier_2",
  "conditions": [
    "must_not_be_self_approval",
    "must_have_ticket_reference"
  ],
  "reason": "Production restart requires approver review and traceable ticket context."
}
```

### Required Decision Fields

- `decision`
- `matched_rule_ids`
- `reason`

### Optional Decision Fields

- `approval_tier`
- `conditions`
- `required_roles`
- `required_groups`
- `execution_constraints`

## Evaluation Order

### Recommended Flow

1. validate the request shape
2. verify normalized identity context is present
3. evaluate `feature_access` policies
4. evaluate `action_authz` policies
5. evaluate `approval` policies
6. evaluate `execution_gate` policies if execution is requested
7. return final decision with matched rules and conditions

### Precedence Rules

- explicit `deny` should override `allow`
- more specific rules should override broader rules
- higher `priority` should win when specificity is equal
- if no rule matches, return `deny`

## Approval Tiers

### Tier Definitions

- `tier_0`
  - read-only, no approval
- `tier_1`
  - low-risk non-production action
- `tier_2`
  - low-risk production action
- `tier_3`
  - high-risk production action

### Recommended Tier Behavior

| Tier | Default Decision | Typical Conditions |
|---|---|---|
| `tier_0` | `allow` | none |
| `tier_1` | `allow` or `require_approval` | may allow self-approval in non-production |
| `tier_2` | `require_approval` | ticket reference, no self-approval |
| `tier_3` | `require_approval` or `deny` | approver role, no self-approval, strong controls |

## Example Policy Object Shape

### YAML Example

```yaml
version: 1
rules:
  - id: feature-approval-queue-approver
    domain: feature_access
    description: Allow approvers to access approval queue
    priority: 200
    enabled: true
    match:
      roles_any: ["approver", "platform-admin"]
      features_any: ["approval_queue"]
    decision:
      outcome: allow
    metadata:
      owner: platform-security
      scope: global
```

## Sample Rules

### 1. Read-Only Service Status

```yaml
- id: action-read-status-all-authenticated
  domain: action_authz
  description: Allow authenticated operational users to query service status
  priority: 100
  enabled: true
  match:
    roles_any: ["read-only-observer", "operator", "senior-operator", "approver", "auditor", "platform-admin"]
    actions_any: ["read-status", "read-logs", "read-metrics"]
    environments_any: ["dev", "test", "staging", "prod"]
    risk_tiers_any: ["tier_0"]
  decision:
    outcome: allow
```

### 2. Production Restart Requires Approval

```yaml
- id: approval-prod-restart-tier2
  domain: approval
  description: Production restart requires approver review
  priority: 300
  enabled: true
  match:
    roles_any: ["operator", "senior-operator", "approver", "platform-admin"]
    actions_any: ["restart-service"]
    environments_any: ["prod"]
    risk_tiers_any: ["tier_2"]
  decision:
    outcome: require_approval
    approval_tier: tier_2
  conditions:
    - must_have_ticket_reference
    - must_not_be_self_approval
```

### 3. Deny Destructive Actions By Default

```yaml
- id: deny-destructive-default
  domain: action_authz
  description: Deny destructive actions for all roles unless explicitly enabled later
  priority: 1000
  enabled: true
  match:
    actions_any: ["delete-or-destructive"]
    environments_any: ["dev", "test", "staging", "prod"]
  decision:
    outcome: deny
```

### 4. Approver May Approve Tier 2 In Production

```yaml
- id: approver-prod-tier2-approval
  domain: approval
  description: Approver role may approve production tier 2 actions
  priority: 400
  enabled: true
  match:
    roles_any: ["approver"]
    approval_tiers_any: ["tier_2"]
    environments_any: ["prod"]
  decision:
    outcome: allow_with_conditions
  conditions:
    - must_have_environment_scope
    - must_not_be_self_approval
```

### 5. Execution Requires Signed Approval Context

```yaml
- id: execution-requires-signed-approved-request
  domain: execution_gate
  description: Execution workers accept only approved signed execution requests
  priority: 500
  enabled: true
  match:
    actions_any: ["collect-diagnostics", "ticket-update", "restart-service", "scale-service", "change-configuration"]
  decision:
    outcome: allow_with_conditions
  conditions:
    - must_have_signed_execution_request
```

## MVP Policy Profile

The MVP should implement a reduced policy profile.

### Included Domains

- `feature_access`
- `action_authz`
- `approval`
- lightweight `execution_gate`

### Included Actions

- `read-status`
- `read-logs`
- `read-metrics`
- `collect-diagnostics`
- `ticket-update`
- `restart-service`

### MVP Defaults

- allow `tier_0` reads for authenticated users in scope
- require approval for `restart-service` in `prod`
- deny `scale-service`, `change-configuration`, and `delete-or-destructive`
- deny self-approval in `prod`

## Policy Storage and Change Control

### Recommended Storage Format

Use versioned policy files in Git, such as:

- `yaml`
- `json`

### Recommended Governance

- changes require pull request review
- policy files are versioned and auditable
- policy bundles are promoted through environments
- policy tests run before deployment

## Policy Testing Strategy

### Required Test Types

- unit tests for rule matching
- precedence tests for conflicting rules
- regression tests for known approval paths
- deny-by-default tests

### Example Test Cases

- operator requests `read-status` in `prod` -> `allow`
- operator requests `restart-service` in `prod` -> `require_approval`
- operator attempts self-approval for `prod tier_2` restart -> `deny`
- approver approves `prod tier_2` restart with ticket reference -> `allow_with_conditions` or final approval success
- any role requests `delete-or-destructive` -> `deny`

## Service Integration Model

### API Gateway

The gateway should:

- authenticate requests
- forward trusted identity context
- not make detailed action authorization decisions

### Agent Service

The agent service should:

- call the policy engine before tool invocation
- pass normalized identity and request metadata
- honor returned policy conditions

### Approval Service

The approval service should:

- consume `require_approval` decisions
- resolve approver eligibility
- submit final approval context back to the control plane

### Execution Workers

Workers should:

- verify the request came from the control plane
- verify the decision state is executable
- reject unsigned or out-of-scope execution requests

## Recommended Initial APIs

### Policy Evaluation API

```json
POST /policy/evaluate
{
  "principal": {
    "user_id": "u123",
    "platform_roles": ["operator"],
    "environment_scopes": ["prod"]
  },
  "request": {
    "action": "restart-service",
    "environment": "prod",
    "risk_tier": "tier_2",
    "target_type": "kubernetes_deployment",
    "target_id": "payments-api",
    "ticket_reference": "INC-1042"
  }
}
```

### Example Response

```json
{
  "decision": "require_approval",
  "approval_tier": "tier_2",
  "matched_rule_ids": ["approval-prod-restart-tier2"],
  "conditions": [
    "must_have_ticket_reference",
    "must_not_be_self_approval"
  ],
  "reason": "Production restart requires approval."
}
```

## Final Recommendation

Implement the policy engine around a small, explicit rule model with:

- clear policy domains
- deny-by-default behavior
- approval as a first-class decision
- versioned policy files
- testable rule precedence

This provides a practical bridge from architecture documents to an enforceable enterprise control plane for the agentic AIOps platform.
