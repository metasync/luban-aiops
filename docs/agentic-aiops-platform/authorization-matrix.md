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
- `developer`
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

### developer

The platform's read-mostly technical identity — a system integrator, QA
engineer, or service account that builds and tests against the platform. It
is **not** a skill-authoring persona: authoring (drafting and graduating
skills, creating documents) stays an operational power held by `operator`,
`approver`, and `platform-admin`. `developer` is also the platform's non-SSO
identity: the synthetic dev identity platform-gateway mints when auth is
disabled (`subject="dev"`, tagged `authenticated=false`) and the default role
of the identity-broker dev token.

Primary use:

- sign in, chat, and query services
- view incidents and act as first responder (`incident:triage`,
  `incident:act`)
- invoke read-class tools (`tools:invoke`), read the policy matrix
  (`policy:read`), and confirm low-risk `tier_1` tool cards in-session
  (`chat:confirm`)

Restrictions:

- denied every mutating and governance action: `tools:mutate`,
  `documents:*`, `session:skill_draft`, `incident:skill_draft`,
  `session:skill_graduate`, and `audit:read`
- not a `tier_2` designated approver (`approvals:list` denied)

Example group mapping:

- `ops-developers` -> `developer`

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

## Agent-Role Axis (SPEC-074, phase 3)

The six roles above are **human platform roles** carried in the delegated
token's `roles`. Orthogonal to them is a closed **agent-role** vocabulary that
narrows authority *within* a single delegated turn when it is decomposed across
sub-agents ([ADR-0017](../adr/0017-bounded-read-only-multi-agent-orchestration.md)).
An agent-role is never a human role, never a JWT claim or wire field, and never
an approver — it is an authority-narrowing label on the **same** token.

| Agent-role | Posture | Sees mutating tools | Approves |
|---|---|---|---|
| `diagnostician` | read-level tools, autonomous | no | never |
| `orchestrator` | decomposes / delegates / synthesizes; holds **no** direct gateway tools | no | never |
| `executor` | may see mutating tools | yes — still parks on HITL | never |

- **Subtractive only.** The axis composes **conjunctively** with the human
  `roles_any` matrix dimension and can only *remove* authority the token
  already grants: an agent-role-scoped grant never widens a human role the
  token does not hold and never overrides an explicit `deny`.
- **Fail-closed.** A rule scoped to an agent-role **never matches an unscoped
  (`None`) call**, and an unknown or absent role falls back to the most
  restrictive posture.
- **`executor` → human approver.** An `executor`-staged mutation still requires
  an approval decided by a **distinct human** role (`decided_by_roles`); no
  agent-role is ever an approver decider. This invariant is encoded as policy
  and guarded by test.
- **Inert in phase 3.** The axis is a *model* dimension only — an optional,
  additive `agent_roles_any` field in `policy-rule.schema.json` (v2→v3). The
  canonical `policy-default.yaml` carries no such rule and every deployed
  evaluation forwards `agent_role=None`, so all outcomes are byte-identical
  (reachability and no-diff guards enforce this). A producer first binding a
  role, and the canonical rule landing, are deferred to **phase 5**.

## Agent-Role Attribution in the Audit Trail (SPEC-075, phase 4)

The agent-role axis above is **prescriptive** — it narrows authority (SPEC-074).
Phase 4 adds a **descriptive** sibling: the durable audit trail can record *which
role acted*, completing the attribution triple beside the two legs that already
existed as top-level audit-event fields.

| Attribution leg | Audit-event field | Answers | Landed |
|---|---|---|---|
| on whose behalf | `subject` / `username` | which human the action is attributed to | SPEC-013 |
| under which delegation | `delegation_mode` | how outbound authority was acquired | SPEC-070 |
| which role acted | `agent_role` | which sub-agent role performed the turn | **SPEC-075** |

- **Descriptive, never prescriptive.** `agent_role` records provenance only; it
  narrows no authority and grants nothing. The prescriptive axis is the SPEC-074
  policy `agent_roles_any` dimension above — the two are orthogonal and share one
  closed vocabulary (`diagnostician` / `orchestrator` / `executor`), so attribution
  can never drift from the identity/policy vocabulary.
- **One vocabulary, three contracts.** The same closed enum is pinned across
  `audit-event.schema.json`, `session-evidence.schema.json`, and the
  `evidence_turns` item of `agent-session.schema.json`, and equals the SPEC-073
  producer vocabulary — an enum-lockstep guard fails the build on any drift.
- **Additive and inert.** The field is optional and **omitted when absent** (never
  null, never an empty string), exactly like `delegation_mode`, so every event from
  today's unscoped single-agent path audits **byte-identically** and a legacy row
  reads back `agent_role is None`. The agent-platform emitter seam is wired to
  SPEC-073's `current_agent_role_value()`, which returns `None` on every deployed
  turn — no producer binds a role until phase 5 (reachability and no-diff guards
  enforce this). It is a plain string enum on the v2 contract: no agentscope type
  leaks and no new principal, claim, or identity edge. Four-point gate: audit
  **strengthened**; identity, read-only posture, and no-agentscope **unchanged**.
- **Evidence-turn attribution.** The same optional `agent_role` rides a persisted
  `session_evidence` turn, so a scoped turn records which role produced its
  evidence and a legacy turn replays with no empty artifact.
- **Deferred (no consumer yet).** Per OQ-4 there is **no portal filter or column**
  (`delegation_mode` has none either) and per OQ-5 **no summary facet** — both are
  consumerless until a producer binds roles in phase 5. Per OQ-6 the field is
  additive **within audit-event v1** (no title bump, no new ADR), the
  `delegation_mode` precedent. Per OQ-3 the transcript-turn projection and any
  concurrent-multi-agent transcript re-modelling stay deferred to phase 5/6.

## Agent-Role Binding (SPEC-076, phase 5) — live in-process, policy axis ready-but-inert

Phase 3 modelled the agent-role axis and phase 4 attributed it; **phase 5 binds the
role in-process and populates the attribution**, while the **gateway policy axis stays
ready-but-inert**. A producer — the bounded read-only orchestration loop
([ADR-0017](../adr/0017-bounded-read-only-multi-agent-orchestration.md) Decision 3's
controlled relaxation) — brackets each turn in `agent_role_scope()`, so the closed
vocabulary is **bound** and the attribution dimension is **populated**; but SPEC-073 R-3
keeps the role **off every wire field**, so it never reaches the separate-process
gateway `evaluate()`.

- **The in-process postures are live.** An `orchestrator` fans out read-only
  `diagnostician` members and holds **no** direct gateway tools itself; a
  `diagnostician` reads **autonomously — no human approves any read**, its toolkit
  narrowed at the `_ensure_toolkit` seam by **risk tier + token `roles`** (not by
  runbook family — `read_families` is declarative documentation only); an `executor`
  *would* see mutating tools but only to **stage** a proposal onto the existing HITL
  card (which still dispatches solely through the signed worker with a **distinct
  human** approver) — and in phase 5 the executor-staging mechanism is delivered +
  unit-proven but **not wired to a trigger** (`FU-076-b` — **wired by
  [SPEC-077](../specs/SPEC-077-operator-diagnose-to-act-bridge/spec.md), v0.58.0; see
  below**). No agent-role ever approves.
- **The live read-only control is in-process narrowing, not the gateway axis.** A
  `diagnostician` cannot reach a mutating grant because `_narrow_for_role` gives it no
  mutating tool (risk tier) and the loop admits only `read_only=True` turns — non-spoofable,
  since the role never crosses the wire (R-3). The **minimal** canonical `agent_roles_any`
  rule pair (a `diagnostician` read posture + an `executor`→`require_approval` encoding)
  landed in `policy-default.yaml`, synced byte-identically across all four replicas, and its
  **engine** semantics are proven — but the rules stay **inert in deployment** (no deployed
  caller threads a non-`None` role) until the phase-6 wire contract, or the `FU-076-c`
  in-process evaluation point, threads one. The tool-name/family axis stays deferred (OQ-4:
  narrowing already suffices).
- **Subtractive-only and fail-closed are preserved.** The axis still composes
  conjunctively with the human `roles_any` matrix, never widens a human role, never
  overrides a `deny`, and never matches an unscoped (`None`) call.
- **The unscoped path is byte-identical.** Only the orchestration frame binds a role;
  the deployed single-agent turn forwards `agent_role=None` and every outcome audits and
  authorizes exactly as before (the reachability guards now read “**only** the
  orchestration frame binds a role”).
- **Bounded and read-only by construction.** The loop is capped by
  `AGENT_ORCHESTRATION_MAX_STEPS` (default `20`, `>= 1`) and fails closed to a partial
  diagnosis; the operator-invoked trigger (`POST /api/v2/diagnose`, gateway
  `/api/v1/diagnose`, gated by the existing `chat` action) never dispatches a mutation.
  Unattended machine-trigger ingestion is the named follow-up **`FU-076`**.

## Operator Diagnose→Act Bridge (SPEC-077, v0.58.0) — the executor-staging trigger is wired

Phase 5 delivered the `executor`-scoped `stage_remediation(...)` mechanism unit-proven
but **not wired to a production trigger** (`FU-076-b`). **SPEC-077 closes `FU-076-b`**
and supplies **only the trigger** — an explicit, human-initiated `POST /api/v2/remediate`
(gateway `POST /api/v1/remediate` proxy) that reaches the delivered mechanism
**unchanged**. **Zero new mutation-path machinery**, no new wire frame; the
diagnose-before-act ceiling (ADR-0017 Decision 2) is unchanged and autonomous resolve
stays deferred.

- **A new deny-by-default action gates the trigger.** `remediate:stage` is granted to
  `platform-admin` + `operator` and **denied** to `developer`, `read-only-observer`, and
  `auditor` — added to the canonical `policy-default.yaml`, synced byte-identically
  across all four bundle replicas, and registered in `PROTECTED_ACTIONS` + the action
  vocabulary of **both** gateway `evaluate()` engines. A token without `remediate:stage`
  is refused **403** at the gateway before any proxy or model call. (The sibling
  `/api/v1/diagnose` trigger reuses the existing `chat` action; the mutating-proposal
  trigger gets its **own** action because it reaches an `executor` staging turn.)
- **The `executor` → distinct-human invariant is the mutation ceiling.** The trigger
  binds `AgentRole.EXECUTOR` for **exactly one** `read_only=False` staging turn on the
  derived `{session_id}::orch::staging` session, over the **same** gateway-forwarded
  delegated token. The executor's full toolkit may *propose* the single mutating call,
  which the kernel **parks** as the **existing** SPEC-020/030/031 confirmation card
  carrying `staged_by_role="executor"` provenance. It dispatches **only** through the
  signed at-most-one-dispatch worker (SPEC-037/038/063) after a **distinct human**
  approver decides — the SPEC-030 self-approval block is unchanged, so the stager can
  never be the approver. The trigger itself dispatches **nothing** and never auto-approves.
- **Fail-closed on a non-stageable profile.** Only the two stageable profiles
  (`post-deploy-verify`, `k8s-pod-degradation`) can stage; a diagnosis-only profile
  (`servicenow-incident`, `observability-alert` — `remediation_shape is None`) or an
  unknown profile is refused **4xx before any executor turn**, never coerced to a wider
  runbook.
- **Role off the wire, no new frame, audit enum closed.** `RemediateRequest` is
  `extra="forbid"` and carries **no** `agent_role`; the response rides the existing
  `AgentChatResponse` + SPEC-031 card, `agent-stream-event.schema.json` /
  `execution-request.schema.json` stay **byte-unchanged**, and no `agent_role` crosses any
  wire field (SPEC-073 R-3) — so the SPEC-074 gateway policy axis stays **ready-but-inert**
  on this path (making it live is `FU-076-c`). The wired executor turn audits the SPEC-075
  `agent_role="executor"` dimension through the delivered emitter seam with **no new
  `event_type`** (the gateway reuses `chat_completed`; the enum stays closed).
- **Portal entry deferred (`FU-077-agentic-remediation`, a SPEC-078 candidate).** The R-4
  portal **Stage remediation** button was **deferred post-approval (2026-11-11, operator
  re-scope)**: the portal has no completed-diagnosis surface to attach it to (SPEC-076
  shipped diagnose backend-only; the portal was last touched by SPEC-072 / v0.53.0), and the
  operator's direction is an **agentic / multi-agent** remediation — human-requested,
  agent-team-carried, surfacing through the existing conversational portal surface (no card,
  no discrete button) or graduated autonomy — rather than a button on a card. The backend
  trigger is UX-agnostic and ships regardless, and is that follow-up's prerequisite (any
  entry shape reaches the same wired `stage_remediation`).

## Feature Access Matrix

| Feature | read-only-observer | operator | developer | approver | auditor | platform-admin |
|---|---|---|---|---|---|---|
| Portal login | allow | allow | allow | allow | allow | allow |
| Chat and service query | allow | allow | allow | allow | allow | allow |
| Incident view | allow | allow | allow | allow | allow | allow |
| Evidence and tool result view | allow | allow | allow | allow | allow | allow |
| Approval queue view | deny | allow | deny | allow | allow | allow |
| Approval action buttons | deny | deny | deny | allow | deny | allow by policy only |
| Audit history view | deny | limited | deny | limited | allow | allow |
| Skill management UI | deny | limited | deny | limited | deny | allow |
| Policy admin UI | deny | deny | deny | deny | deny | allow |
| Identity mapping admin UI | deny | deny | deny | deny | deny | allow |

## Environment Scope Matrix

This matrix shows default environment eligibility. Actual access still depends on mapped entitlements from `AD` or `Keycloak`.

| Role | dev | test | staging | prod |
|---|---|---|---|---|
| read-only-observer | allow | allow | allow | allow |
| operator | allow | allow | allow | request-only |
| developer | allow | allow | allow | allow |
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

| Action | Tier | read-only-observer | operator | developer | approver | auditor | platform-admin |
|---|---|---|---|---|---|---|---|
| read-status | tier 0 | allow | allow | allow | allow | allow | allow |
| read-logs | tier 0 | allow | allow | allow | allow | allow | allow |
| read-metrics | tier 0 | allow | allow | allow | allow | allow | allow |
| collect-diagnostics | tier 1 | deny | request-only | deny | request-only | deny | request-only |
| ticket-update | tier 1 | deny | request-only | deny | request-only | deny | request-only |
| restart-service | tier 1 or 2 | deny | request-only | deny | request-only | deny | request-only |
| scale-service | tier 2 or 3 | deny | deny | deny | request-only | deny | request-only |
| change-configuration | tier 3 | deny | deny | deny | request-only | deny | request-only |
| delete-or-destructive | tier 3 | deny | deny | deny | deny | deny | deny by default |

## Environment-Specific Action Matrix

### dev and test

| Action Tier | operator | developer | approver | platform-admin |
|---|---|---|---|---|
| tier 0 | allow | allow | allow | allow |
| tier 1 | request-and-approve if policy allows | deny | request-and-approve | request-and-approve by policy only |
| tier 2 | request-only | deny | approve-only | request-and-approve by policy only |
| tier 3 | deny | deny | approve-only if explicitly enabled | deny by default |

### staging

| Action Tier | operator | developer | approver | platform-admin |
|---|---|---|---|---|
| tier 0 | allow | allow | allow | allow |
| tier 1 | request-only | deny | approve-only | request-and-approve by policy only |
| tier 2 | request-only | deny | approve-only | request-and-approve by policy only |
| tier 3 | deny | deny | approve-only if explicitly enabled | deny by default |

### prod

| Action Tier | operator | developer | approver | platform-admin |
|---|---|---|---|---|
| tier 0 | allow | allow | allow | allow |
| tier 1 | request-only | deny | approve-only | request-only unless separately authorized |
| tier 2 | deny | deny | approve-only | request-only unless separately authorized |
| tier 3 | deny | deny | approve-only with strong controls | deny by default |

## Approval Matrix

### Who May Request

| Role | tier 0 | tier 1 | tier 2 | tier 3 |
|---|---|---|---|---|
| read-only-observer | allow | deny | deny | deny |
| operator | allow | allow | allow in assigned scope | deny |
| developer | allow | deny | deny | deny |
| approver | allow | allow | allow | allow if policy permits |
| auditor | allow | deny | deny | deny |
| platform-admin | allow | allow by policy | allow by policy | request-only in exceptional cases |

### Who May Approve

| Role | dev/test tier 1 | staging tier 1 | prod tier 1 | prod tier 2 | prod tier 3 |
|---|---|---|---|---|---|
| read-only-observer | deny | deny | deny | deny | deny |
| operator | optional if self-approval is enabled | deny | deny | deny | deny |
| developer | deny | deny | deny | deny | deny |
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
only and never aggregate over event payloads. Since v0.36.0 (SPEC-055) one
new action gates skill graduation: `session:skill_graduate` authorizes
turning a session's captured authoring trace into an executable-flow draft,
and it is deliberately **not** folded into `session:skill_draft` — the
artifact declares `risk_class: write` and a machine-readable replay step list
rather than knowledge prose, so it is a higher trust level and is separately
authorized (SPEC-055 OQ-3). It follows the same operational-role grant
pattern as its authoring siblings: `platform-admin`, `approver`, and
`operator` hold it; `developer`, `read-only-observer`, and `auditor` receive
the standard audited policy 403. One grant covers both graduated-session
entry points — the chat header's **Graduate as skill** and the mid-session
**Declare target** route — while declaring a target at session *birth* rides
`session:create`, so any role that may open a session may scope it but only a
graduation-capable one may ever export it. Ownership stays enforced by the
anti-enumeration 404, and graduation never auto-publishes: the draft *is* the
ephemeral response, for a human to review and merge into their own skills
repo, with nothing persisted server-side. Each export is recorded once as a
`skill_graduated` audit event whose `details` carry the session, the mode, the
step count, the `web_target` scope in force and the declaration-ordering
verdict — the declare-target route is deliberately unaudited at the gateway
(a declaration is a scope, not an operational act) and `session_created`
records only a boolean `skill_target_declared` flag rather than the URL, so
that event is where a reviewer learns which origin a graduated flow is bound
to. Since v0.37.0 (SPEC-056) the portal splits its one **Chat** entry into
**Chat** (*operation* sessions) and a new **Studio** (*development* sessions)
over one shared chat core, told apart by an additive `session_type`
discriminator that is fixed at birth and immutable — and it adds **no** new
policy action, **no** bundle change, and **no** new audit event type. Opening a
`development` session dual-gates at the gateway create route: always
`session:create`, **plus** the existing `session:skill_graduate` when
`session_type == "development"` (the SPEC-043/045 route-level dual-gate
pattern; a denial reports the first failing action in the standard structured
shape). The rationale is the tightening R-6 names: a session whose only
distinguishing power is graduation should require the graduation grant to open,
so a non-authoring role (`developer`, `read-only-observer`, `auditor`) that
holds `session:create` but not `session:skill_graduate` can no longer open a
dead-end Studio session it could never graduate, while the graduation-capable
roles (`platform-admin`, `approver`, `operator` — exactly the portal's
`STUDIO_ROLES`, defined equal to its `SKILL_GRADUATE_ROLES` so the two cannot
drift) may. An *operation* create still needs only `session:create` for every
role that holds it, so Chat's broad gating is unchanged. The session list gains
an optional server-side `session_type` scope (Chat lists `operation`, Studio
lists `development`, and the shift-summary picker consumes the `operation`
scope so a development session is never offered as shift material); the scope
is enforced in the agent's list query, never a client hide. The SPEC-055
declare-target and graduate pass-through routes are unchanged — declare-target
still rides `session:skill_graduate`, still first-declaration-wins, still names
a scope and never writes `session_type`. `make policy-diff` reports **zero**
new grants, the assertion this no-new-vocabulary decision leaves behind. The
full approval model —
policy actions, risk-tier admission, the agent auto-allow list, and HITL
confirmation — is documented in the
[Approval and HITL Governance Guide](../guides/approval-and-hitl.md).

Since v0.53.0 (SPEC-072) one new action gates platform-configuration
transparency: `runtime:flags` authorizes an authenticated read of the runtime's
curated feature-flag inventory — each entry a stable `name`, an optional human
`label`, and an on/off `enabled` boolean, **never a secret value** — served by
`GET /api/v1/runtime/flags` (proxying the agent's `GET /api/v2/runtime/flags`)
and rendered read-only in the portal's Settings ▸ Platform pane. It follows the
operational-trio grant pattern (`documents:read`, `session:skill_graduate`):
`platform-admin`, `approver`, and `operator` hold it; `developer`,
`read-only-observer`, and `auditor` receive the standard audited policy 403, for
which the pane degrades just that section to “unavailable” while the
unauthenticated component-health rows persist for every role. This is
deliberately narrower than `models:list` — a chat-surface read granted wherever
`chat` is (including `read-only-observer`) because discovery is safe by
construction — since the flag inventory describes *how the platform is
deployed*, an operational concern rather than a chat input. The unauthenticated
`/api/v1/runtime` probe stays flag-free, and the same spec's composer **“Auto
(routed)”** selector introduces **no** new action: it rides the existing
`chat`/`models:list` surface plus an additive `routing_available` catalog
boolean, so SPEC-072 adds exactly one new policy action (`runtime:flags`) to the
bundle.

## Final Recommendation

Use this matrix as the default enterprise baseline for the platform:

- broad read access for authenticated operational users
- narrow request rights for actions
- stronger approval boundaries in `prod`
- explicit separation of duties for risky changes
- deny destructive actions by default

This gives the platform a practical starting point for enterprise-grade operations while keeping the first implementation safe and auditable.
