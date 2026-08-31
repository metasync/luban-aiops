# Authorization Matrix

## Objective

Define a concrete authorization matrix for the enterprise-grade agentic AIOps platform so implementation teams can consistently enforce:

- portal access
- feature access
- request permissions
- approval permissions
- environment scope
- action restrictions

This document builds on [identity-and-authorization-design.md](identity-and-authorization-design.md).

## Scope

This matrix covers the initial platform roles defined in the identity design:

- `read-only-observer`
- `operator`
- `senior-operator`
- `approver`
- `auditor`
- `platform-admin`

Environment scopes:

- `dev`
- `test`
- `staging`
- `prod`

Action tiers:

- `tier 0`: read-only
- `tier 1`: low-risk non-production action
- `tier 2`: low-risk production action
- `tier 3`: high-risk production action

## Decision Model

### Decision Outcomes

Use the following authorization outcomes:

- `allow`
- `deny`
- `request-only`
- `approve-only`
- `request-and-approve`

### Core Rules

- all users must authenticate through `SSO`
- all decisions must use normalized roles and environment scopes
- destructive actions are denied by default
- production approvals should be separated from normal request permissions
- high-risk production actions should not allow self-approval

## Role Definitions

### read-only-observer

Primary use:

- view operational state
- consume evidence and incident summaries

Restrictions:

- cannot request actions
- cannot approve actions
- cannot manage policy or admin settings

### operator

Primary use:

- perform day-to-day operational investigation
- request low-risk actions within assigned scope

Restrictions:

- cannot approve production high-risk actions
- cannot manage policy or platform-wide authorization mappings

### senior-operator

Primary use:

- handle more advanced operational actions
- request broader actions across assigned environments

Restrictions:

- should still not self-approve high-risk production actions

### approver

Primary use:

- approve bounded actions within assigned environments
- review action evidence and policy requirements

Restrictions:

- approval scope must still be environment-bound
- should not automatically gain full admin authority

### auditor

Primary use:

- view audit trails
- inspect approvals and execution attribution

Restrictions:

- cannot request or execute actions
- cannot change policy or mappings

### platform-admin

Primary use:

- manage platform configuration
- manage identity mappings and policy settings

Restrictions:

- should not automatically bypass operational approval controls
- should use a separate operational role if they also act as an operator

## Feature Access Matrix

| Feature | read-only-observer | operator | senior-operator | approver | auditor | platform-admin |
|---|---|---|---|---|---|---|
| Portal login | allow | allow | allow | allow | allow | allow |
| Chat and service query | allow | allow | allow | allow | allow | allow |
| Incident view | allow | allow | allow | allow | allow | allow |
| Evidence and tool result view | allow | allow | allow | allow | allow | allow |
| Approval queue view | deny | allow | allow | allow | allow | allow |
| Approval action buttons | deny | deny | deny | allow | deny | allow by policy only |
| Audit history view | deny | limited | limited | limited | allow | allow |
| Skill management UI | deny | limited | limited | limited | deny | allow |
| Policy admin UI | deny | deny | deny | deny | deny | allow |
| Identity mapping admin UI | deny | deny | deny | deny | deny | allow |

## Environment Scope Matrix

This matrix shows default environment eligibility. Actual access still depends on mapped entitlements from `AD` or `Keycloak`.

| Role | dev | test | staging | prod |
|---|---|---|---|---|
| read-only-observer | allow | allow | allow | allow |
| operator | allow | allow | allow | request-only |
| senior-operator | allow | allow | allow | request-only |
| approver | allow | allow | allow | approve-only |
| auditor | allow | allow | allow | allow |
| platform-admin | allow | allow | allow | allow |

## Action Authorization Matrix

### Action Categories

Initial action categories for the platform:

- `read-status`
- `read-logs`
- `read-metrics`
- `collect-diagnostics`
- `ticket-update`
- `restart-service`
- `scale-service`
- `change-configuration`
- `delete-or-destructive`

### Default Role vs Action Matrix

| Action | Tier | read-only-observer | operator | senior-operator | approver | auditor | platform-admin |
|---|---|---|---|---|---|---|---|
| read-status | tier 0 | allow | allow | allow | allow | allow | allow |
| read-logs | tier 0 | allow | allow | allow | allow | allow | allow |
| read-metrics | tier 0 | allow | allow | allow | allow | allow | allow |
| collect-diagnostics | tier 1 | deny | request-only | request-only | request-only | deny | request-only |
| ticket-update | tier 1 | deny | request-only | request-only | request-only | deny | request-only |
| restart-service | tier 1 or 2 | deny | request-only | request-only | request-only | deny | request-only |
| scale-service | tier 2 or 3 | deny | deny | request-only | request-only | deny | request-only |
| change-configuration | tier 3 | deny | deny | deny | request-only | deny | request-only |
| delete-or-destructive | tier 3 | deny | deny | deny | deny | deny | deny by default |

## Environment-Specific Action Matrix

### dev and test

| Action Tier | operator | senior-operator | approver | platform-admin |
|---|---|---|---|---|
| tier 0 | allow | allow | allow | allow |
| tier 1 | request-and-approve if policy allows | request-and-approve if policy allows | request-and-approve | request-and-approve by policy only |
| tier 2 | request-only | request-only | approve-only | request-and-approve by policy only |
| tier 3 | deny | deny | approve-only if explicitly enabled | deny by default |

### staging

| Action Tier | operator | senior-operator | approver | platform-admin |
|---|---|---|---|---|
| tier 0 | allow | allow | allow | allow |
| tier 1 | request-only | request-only | approve-only | request-and-approve by policy only |
| tier 2 | request-only | request-only | approve-only | request-and-approve by policy only |
| tier 3 | deny | deny | approve-only if explicitly enabled | deny by default |

### prod

| Action Tier | operator | senior-operator | approver | platform-admin |
|---|---|---|---|---|
| tier 0 | allow | allow | allow | allow |
| tier 1 | request-only | request-only | approve-only | request-only unless separately authorized |
| tier 2 | deny | request-only | approve-only | request-only unless separately authorized |
| tier 3 | deny | deny | approve-only with strong controls | deny by default |

## Approval Matrix

### Who May Request

| Role | tier 0 | tier 1 | tier 2 | tier 3 |
|---|---|---|---|---|
| read-only-observer | allow | deny | deny | deny |
| operator | allow | allow | allow in assigned scope | deny |
| senior-operator | allow | allow | allow in assigned scope | request-only in exceptional cases |
| approver | allow | allow | allow | allow if policy permits |
| auditor | allow | deny | deny | deny |
| platform-admin | allow | allow by policy | allow by policy | request-only in exceptional cases |

### Who May Approve

| Role | dev/test tier 1 | staging tier 1 | prod tier 1 | prod tier 2 | prod tier 3 |
|---|---|---|---|---|---|
| read-only-observer | deny | deny | deny | deny | deny |
| operator | optional if self-approval is enabled | deny | deny | deny | deny |
| senior-operator | optional if self-approval is enabled | deny | deny | deny | deny |
| approver | allow | allow | allow | allow | allow only if explicitly enabled |
| auditor | deny | deny | deny | deny | deny |
| platform-admin | allow by policy only | allow by policy only | allow by policy only | allow by policy only | deny by default |

## Separation of Duties Rules

### Required Defaults

- `prod tier 2` and `prod tier 3` actions must not allow self-approval
- `delete-or-destructive` actions are denied by default for all roles
- `platform-admin` should not automatically gain operational approval bypass
- `auditor` must be read-only

### Recommended Stronger Controls

- require two-person approval for `prod tier 3` actions
- require change-window validation for risky production actions
- require explicit incident or ticket reference for production restarts
- require evidence package review before approval

## MVP Authorization Matrix

The MVP should implement a reduced version of the full matrix.

### MVP Roles

- `operator`
- `approver`
- `platform-admin`
- `auditor`

### MVP Action Coverage

| Action | dev/test | staging | prod |
|---|---|---|---|
| read-status | allow | allow | allow |
| read-logs | allow | allow | allow |
| read-metrics | allow | allow | allow |
| collect-diagnostics | request-only | request-only | request-only |
| ticket-update | request-only | request-only | request-only |
| restart-service | request-only | request-only | request-only |
| scale-service | deny | deny | deny |
| change-configuration | deny | deny | deny |
| delete-or-destructive | deny | deny | deny |

### MVP Approval Rules

- `operator` may request `collect-diagnostics`, `ticket-update`, and `restart-service`
- `approver` may approve those actions within assigned environments
- `prod` restart requires approver review
- self-approval is disabled in `prod`
- `platform-admin` manages mappings and policy but does not automatically bypass production approval

## Policy Engine Inputs

The policy engine should evaluate at least:

- authenticated user ID
- normalized platform role
- environment scope
- requested action
- target system
- risk tier
- approval status
- whether requester and approver are the same user

## Implementation Notes

### Recommended Enforcement Order

1. authenticate through `SSO`
2. validate token at the gateway
3. normalize groups and roles
4. evaluate route and feature access
5. evaluate action and environment access
6. require approval if needed
7. block execution if policy conditions are not satisfied

### Recommended Storage

Store the matrix in a versioned policy configuration so it can be:

- reviewed
- audited
- changed through controlled pull requests
- tested before rollout

### Live Matrix Transparency

The enforced implementation of this matrix lives in the policy bundle
(`shared/shared-contracts/policies/policy-default.yaml`) and is exposed live
by platform-gateway at `GET /api/v1/policy/matrix` (SPEC-019), evaluated from
the loaded bundle rather than hand-maintained. The operator portal's
Permissions view renders it, so the granted role × action surface is
self-service and always reflects what the gateway actually enforces.
Transparency actions `policy:read` and `skills:read` (read-only workspace
inventory) are granted to all operational roles; deny-by-default semantics
are unchanged. SPEC-020 adds `chat:confirm` (approve or deny a parked HITL
tool confirmation), granted to `platform-admin`, `approver`, `operator`, and
`developer`; `read-only-observer` is excluded because confirming a parked
tool call is an act-on-the-system action, not observation. Every decision is
recorded as a durable `confirmation_decided` audit event by platform-gateway.
SPEC-021 adds `tools:mutate` (execute mutating — write/admin risk — tools at
the tool-gateway), granted only to `platform-admin` and `operator`, matching
this matrix's `restart-service` example; `developer`, `approver`, `auditor`,
and `read-only-observer` are denied by default, and `approver` stays
approve-only (`chat:confirm` without execution). SPEC-022 completes the
session workspace lifecycle with `session:list` and `session:delete`,
granted exactly where `session:create` is granted: both operations are
scoped server-side to the caller's own sessions (anti-enumeration 404 for
foreign sessions, 409 while a session holds a parked HITL confirmation), so
the lifecycle actions share one posture across all chat-capable roles and
`auditor` holds none of them. SPEC-024 adds `models:list` (discover the
credential-gated LLM model catalog), granted exactly where `chat` is
granted — including `read-only-observer` — because discovery is safe by
construction: the payload carries only id/label/provider/default and never
credentials or base URLs. SPEC-030 activates this matrix's approval tiers as
policy data: `require_approval` is a first-class bundle outcome with `tier_1`
(session-operator self-confirmation, this matrix's `request-and-approve`)
and `tier_2` (designated-approver with self-approval blocked, this matrix's
`request-only` + `approve-only` separation), enforced by platform-gateway on
the `chat:confirm` path — the shipped default bundle puts `tools:mutate`
under a `tier_2` rule decided by `approver` and `platform-admin`. The live
matrix exposes the requirement as an additive third cell state
(`approval_requirements`, with the tier and decider roles) alongside the
boolean cells, and blocked approval attempts are recorded as
`confirmation_decided` audit events. Live validation surfaced one bundle
consequence of the tier_2 resume semantics: the approved call executes
under the confirmer's delegated token, so the shipped bundle grants
`approver` the tool execution actions (`tools:list`/`tools:invoke`/
`tools:mutate`) — separation of duties stays enforced at the approval
gate, where tier_2 self-approval is blocked. SPEC-031 adds `approvals:list`
(list the cross-session confirmation inbox: pending items plus 30 days of
decision history, metadata only), granted exactly to the tier_2 decider
roles `approver` and `platform-admin`; every other role receives the
standard audited policy 403, mirroring who may decide tier_2 approvals.
SPEC-039 adds the operations document repository actions: `documents:create`
(create, publish, and delete one's own documents) and `documents:read`
(read drafts — own only — and published documents), both granted to
`platform-admin`, `approver`, and `operator`; `developer`,
`read-only-observer`, and `auditor` receive the standard audited policy
403. Access is role-based with no per-document grants — publishing moves a
document into the role-visible space — and foreign-session coverage inside
a document digest is capped at the inbox's metadata-only posture by gating
on the caller's own `approvals:list` grant. Cross-owner document reads are
recorded as `document_read` audit events (own reads stay unaudited);
since v0.21.1 document listings are envelope-only, so the audited single
fetch is the only path to a document's content. Since v0.22.0 (SPEC-040)
shift-summary digests additionally carry a deterministic `handover`
section and the generated narrative defaults on under a digest-anchoring
prompt contract; the portal's Markdown export serializes the document
already fetched through that audited surface, so it introduces no new
policy action and no new audit event type. That audit sits
alongside `document_created` / `document_published`. Since v0.25.0
(SPEC-043) `incident_report` documents pass a dual-action gate at
creation: the caller must hold `documents:create` **and**
`incident:read` — two existing actions combined, no new policy
vocabulary — so the document surface never bypasses the incident
visibility matrix; a denial reports the first failing action in the
standard structured shape. The incident's linked triage session rides
the digest under the same `approvals:list`-derived foreign-coverage
posture, the covered incident id rides `document_created` as
provenance, and creation answers the dependency postures (503 not
configured, 502 transport, 404 unknown incident id) without new audit
event types. SPEC-039 also adds
`session:update` (rename one's own session titles), granted exactly where
`session:list` is granted — every chat-capable role — with server-side
ownership scoping (anti-enumeration 404 for foreign sessions) and no new
audit event; `auditor` holds none of the session actions. Since v0.26.0
(SPEC-044) `session:skill_draft` gates the skill-draft export — one
bounded generation over the caller's own session record, validated on
skills-hub's ingestion code path before it is returned and handed over
client-side (nothing persisted). The action follows the documents-create
grant pattern: `platform-admin`, `approver`, and `operator` hold it;
`developer`, `read-only-observer`, and `auditor` receive the standard
audited policy 403. Ownership stays enforced by the anti-enumeration
404, and each successful draft is recorded as a
`skill_draft_generated` audit event carrying the session, the covered
incident id when present, the mode (generated/skeleton), and the
validation outcome. Since v0.27.0 (SPEC-045) the incident detail gains
the companion entry point: `incident:skill_draft` gates drafting a skill
from an incident's **validated triage report**, dual-gated with
`incident:read` at the same route (the SPEC-043 pattern; a denial
reports the first failing action) and granted to the same operational
roles — a triaged incident is team property, so the drafter need not
own the triage session. The bundle is the incident envelope (minus the
raw failed-triage output) plus the validated report only — never
anyone's session; an incident without a validated report (new,
triaging, `triage_failed`) answers a deterministic 409 instead of a
thin guess. Both entry points open the validated draft in a read-only
preview modal before the client-side download, and each incident
generation is recorded once as `incident_skill_draft_generated`
carrying the incident id, mode, and validation outcome — emitted
regardless of whether the operator downloads or discards. Since v0.28.0
(SPEC-046) the audit trail gains two read-only reporting surfaces — the
summary aggregate (`GET /api/v1/audit/summary`) and the bounded CSV
export (`GET /api/v1/audit/export`) — both riding the existing
`audit:read` grant (auditors and platform admins; operator and
read-only-observer receive the standard audited policy 403). No new
policy action and no new event type are introduced, and the auditor
read-only invariant is unchanged: both surfaces query envelope columns
only and never aggregate over event payloads. The full approval model —
policy actions, risk-tier admission, the agent auto-allow list, and HITL
confirmation — is documented in the
[Approval and HITL Governance Guide](../guides/approval-and-hitl.md).

## Final Recommendation

Use this matrix as the default enterprise baseline for the platform:

- broad read access for authenticated operational users
- narrow request rights for actions
- stronger approval boundaries in `prod`
- explicit separation of duties for risky changes
- deny destructive actions by default

This gives the platform a practical starting point for enterprise-grade operations while keeping the first implementation safe and auditable.
