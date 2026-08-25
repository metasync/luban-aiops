# SPEC-030: Require-Approval Policy Semantics

## Status

- status: `delivered`
- owner: chi
- created: 2026-08-25
- release slice: 0.12.0
- related ADRs: `docs/adr/0006-contract-purpose-invariant-enforcement.md`
- extends: `docs/specs/SPEC-004-policy-enforcement/spec.md`,
  `docs/specs/SPEC-019-portal-transparency-navigation/spec.md`,
  `docs/specs/SPEC-020-hitl-confirmation-bridging/spec.md`, and
  `docs/specs/SPEC-021-bounded-mutating-actions/spec.md`
- spike memo: `docs/workspace/policy-require-approval-spike.md`

## Summary

SPEC-021 triple-gates the first mutating tool, but who may confirm a
mutating run is fixed by bundle grants — the requesting operator can
self-confirm their own destructive action. SPEC-030 makes approval a
first-class, data-driven policy outcome with explicit levels: the shared
policy contracts gain the `require_approval` decision (reserved since
SPEC-004) carrying an approval tier — `tier_1` keeps confirmation with
the session operator themself (destructive-but-routine actions),
`tier_2` requires a designated approver distinct from the requester
(critical destructive actions). Both policy engines evaluate it with
deny > require_approval > allow precedence, and the SPEC-020
confirmation flow enforces the tier when the parked call's action
carries a `require_approval` rule; the requirement renders in the live
permission matrix and the durable audit trail. No approval-queue
service: enforcement rides the delivered confirmation substrate.

## Motivation

- The authorization matrix promises an `approver` role that "may approve
  those actions within assigned environments" with no self-approval, but
  today `approver` holds the same grants as `operator` and any
  `chat:confirm` holder can confirm any parked mutating call, including
  their own. The governance story is currently documentation, not
  behavior.
- Operators need two distinct approval levels, and both must be policy
  data, not code: (1) destructive-but-routine actions (e.g. a service
  restart) where the operator working with the agent confirming their
  own HITL card is sufficient, and (2) critical destructive actions where
  only admin/approver personnel **other than** the requesting operator
  may decide. The authorization matrix already names these as tier 1
  ("request-and-approve if policy allows") and tier 2 ("request-only" +
  "approve-only"); this spec makes them enforceable.
- The Tier-1 policy specification names the fix — "approval is a policy
  outcome, not a UI feature" — and both shared policy schemas have
  reserved `require_approval` since SPEC-004. The delivery-roadmap marks
  these semantics as the next R4 slice.
- Every enforcement substrate already exists (park/resume, confirm route,
  confirmation cards, `confirmation_decided` audit, live permission
  matrix), so the slice is contract + semantics + bridging, not new
  machinery — and the spike memo fixed the two-layer model (kernel HITL
  confirmation vs platform approval) this spec completes.

## Requirements

### R-1: Contract revision — `require_approval` with approval tiers

The shared policy schemas grow the reserved outcome into a real one with
an explicit tier; rule bundles and decision objects stay the single
contract both engines consume.

Acceptance criteria:

- `shared/shared-contracts/schemas/policy-rule.schema.json` (v2):
  `decision.outcome` enum gains `require_approval`; `decision` gains an
  optional `approval` object with `tier` (required, enum
  `["tier_1", "tier_2"]`), `decided_by_roles` (non-empty string array,
  required), and `allow_self_approval` (optional boolean; unset means
  the tier default — `tier_1` allows self-approval, `tier_2` forbids
  it); `allow_with_conditions` stays reserved in the description. Tier
  semantics mirror the authorization matrix: `tier_1` = the session
  operator may decide their own confirmation (destructive-but-routine);
  `tier_2` = a designated approver distinct from the requester decides
  (critical destructive).
- `shared/shared-contracts/schemas/policy-decision.schema.json` (v2):
  `decision` enum gains `require_approval`; the previously reserved
  `approval_tier` field is activated and carries the winning rule's
  tier; an optional `approval` object mirrors the winning rule's
  approval block so callers never re-read the bundle; `conditions`
  stays reserved.
- The schema parity/validation tests in
  `shared/shared-contracts/scripts` (or the audit/contract test that
  binds packaged copies to shared-contracts) pass with the v2 schemas.
- `allow`/`deny`-only v1 bundles validate unchanged against the v2
  schema (strictly additive revision).

### R-2: Evaluation semantics in both policy engines

Both `policy_engine.py` copies learn the third outcome with identical
semantics; their deliberately different action vocabularies are
untouched.

Acceptance criteria:

- Precedence: explicit `deny` > `require_approval` > `allow`; a request
  matching both an allow and a require_approval rule answers
  `require_approval` (safe default), with the matched rule ids reported.
- Between multiple `require_approval` matches, highest `priority` wins
  and its `approval` block (tier + deciders) rides the `PolicyDecision`
  (mirrors the allow path); disabled rules are skipped as today.
- Bundle load validation rejects malformed approval rules with
  `PolicyLoadError` (loud failure at load, never silent 403-only
  semantics): a `tier_2` rule with explicit `allow_self_approval: true`
  is invalid, and a `require_approval` rule whose `match` names actions
  outside the engine's bridged action set is invalid. platform-gateway's
  bridged set is `{tools:mutate}` for this slice; tool-gateway accepts
  no `require_approval` rules in this slice (its invocation path has no
  pre-approval substrate). Implementation note: because `make sync-policy`
  ships the same bundle to both gateways, tool-gateway validates approval
  blocks loudly and then skips the rule with a warning instead of failing
  the load — rejecting would break startup on the synced default bundle
  and evaluating would break SPEC-021 admission (both forbidden by R-3/R-4).

- platform-gateway `evaluate()` and tool-gateway `evaluate()` implement
  the identical semantics; each service's test suite covers mixed-match,
  priority, and disabled-rule cases.

### R-3: Tiered enforcement bridge on the `chat:confirm` path

When a parked mutating call's action evaluates to `require_approval`,
the confirm path enforces the tier: `tier_1` keeps the decision with the
session operator (self-confirmation allowed), `tier_2` restricts it to
policy-named deciders other than the requester.

Acceptance criteria:

- `POST /api/v1/chat/confirm` evaluates the parked call's tool action
  against the bundle; on `require_approval` it requires the confirmer to
  hold at least one `decided_by_roles` role and returns structured 403
  `{detail, action, reason, requirement: "require_approval"}` otherwise,
  for both tiers. The decider-role check applies to `approve` decisions
  only; `deny` stays open to any `chat:confirm` holder so the requester
  can always cancel their own parked call.
- `tier_1`: a confirmer who is the session owner and holds a decider
  role may approve their own parked call — destructive-but-routine
  actions stay a one-person flow.
- `tier_2` self-approval: when the effective self-approval rule is
  `false` (the tier default, or any `tier_2` rule) and the confirmer is
  the session owner, the confirm route rejects
  with the same structured 403 naming `self_approval`; the rejection is
  audited (R-5) and the parked call stays parked. Implementation note:
  agent-platform parks and identifies users by username (`X-User-ID`),
  so the owner comparison runs on usernames carried by the auth session,
  not keycloak subjects.
- Non-mutating parked calls (read-only tools that ASK because they left
  the auto-allow list) evaluate `allow` for `chat:confirm` holders and
  keep today's operator-confirm behavior byte-for-byte; actions with no
  `require_approval` rule likewise keep today's behavior (the implicit
  scenario-1 path).
- The tool-gateway admission path is unchanged: a confirmed mutating
  call still passes `tools:mutate` allow/deny evaluation on the
  delegated (confirmer's) token exactly as delivered in SPEC-021.

### R-4: Default bundle posture

The shipped bundle makes the governance promise real for the dev-k8s
mutating demo.

Acceptance criteria:

- `shared/shared-contracts/policies/policy-default.yaml` gains one
  `tier_2` `require_approval` rule on `tools:mutate` with
  `decided_by_roles: [approver, platform-admin]`; `make sync-policy`
  propagates it to every packaged and overlay copy and
  `make validate-policy` passes.
- A bundle comment documents the `tier_1` authoring pattern for
  scenario-1 actions (destructive-but-routine: `decided_by_roles`
  includes `operator`, self-approval allowed) so lighter mutating tools
  added later declare their level explicitly instead of relying on the
  implicit no-rule path.
- The existing `tools:mutate` allow rule stays (admission unchanged);
  precedence means an operator requesting a mutating run can no longer
  confirm it themselves — the demo script
  (`shared/platform-ops/e2e/mutating-demo.sh`) updates to use a second
  approver identity for the confirm step and documents the new flow.
- Synthetic identities (`developer` role) are excluded by bundle
  authoring (`decided_by_roles` omits them), documented in the bundle
  comment — not coded as a special case.

### R-5: Transparency and audit consistency

Approval requirements render consistently across the live permission
matrix, the confirmation cards, and the durable audit trail.

Acceptance criteria:

- `policy_matrix.py` emits a third cell state `requires_approval` (with
  the tier and decider roles) wherever the caller's role x action
  evaluation answers `require_approval`; `GET /api/v1/policy/matrix`
  stays additive (no endpoint version bump); the portal permissions view
  renders the new state distinctly from allow/deny.
- The portal confirmation card shows a tier badge — "operator
  confirmation" for `tier_1`, "approver required" naming the decider
  roles for `tier_2`; users without a decider role see a read-only card
  (no approve/deny buttons). `read-only-observer` sees parked cards
  read-only per the existing SPEC-022 session-visibility rules.
- `confirmation_decided` audit events carry the matched approval rule id
  and its tier (empty for non-approval confirmations) and a distinct
  outcome value for blocked self-approval attempts; the audit-event
  schema enum and audit-service parity test stay bound.

### R-6: Settings view restored as a read-only Session & Identity panel (add-on)

The SPEC-023 placeholder in the Settings view is replaced by a read-only
information panel so the shipped portal has no half-baked view; it is
portal-only work with no backend changes.

Acceptance criteria:

- The Settings view renders three read-only sections from existing
  client-side state: **Identity** (sign-in state, username, roles, and
  the identity claims carried by the auth session — from `AuthContext`;
  signed-out state shows a sign-in prompt instead of stale data), **Session** (the currently selected session id
  from the session workspace, or an explicit "no session selected"
  state), and **Platform** (platform version chip value, API origin /
  gateway base, and the most recent request id — `client.ts` remembers
  the last generated `x-request-id` for correlation when reporting
  issues).
- No mutable controls ship in this slice: the obsolete pre-OIDC debug
  inputs (gateway URL override, manual user ID, non-stream send) from
  the vanilla portal are deliberately not restored — bearer identity
  overrides manual user ids platform-wide now.
- The panel works signed-out (identity section degrades gracefully) and
  adds no new backend endpoints; vitest coverage renders all three
  sections plus the signed-out state.
- The sidebar entry keeps its role-agnostic visibility (settings is
  visible to everyone, as today).
- The view is built as an extensible container, not a one-shot page:
  Identity / Session / Platform are its first panes (antd `Tabs` or
  equivalent sectioned layout), structured so future settings functions
  can be added as new panes without restructuring the view. Candidate
  future panes are recorded but NOT committed in this slice: display
  preferences, per-user default model selection, confirmation /
  notification defaults.

## Non-Goals

- No policy-center service and no approval queue — evaluation stays in
  the two gateway engines; the queue, persistence, and notification
  surfaces are the R5 remainder (policy-center placeholder keeps its
  boundary README).
- No approval tiers beyond `tier_1` / `tier_2` (the matrix's tier 3
  actions stay deny-by-default with no bridged path), no approval queue
  or persistence — evaluation stays in the two gateway engines; the
  queue, notification surfaces, and tier 3 governance are the R5
  remainder (policy-center placeholder keeps its boundary README).
- No `require_approval` enforcement in tool-gateway's invocation path
  (R-2) and no new confirmation TTL — parked calls keep
  `AGENT_HITL_CONFIRM_TIMEOUT` expiry semantics from SPEC-020.
- The Settings panel (R-6) is deliberately an additive portal-only slice
  with no coupling to R-1…R-5: it restores the SPEC-023 placeholder but
  adds no backend surface, no new API calls beyond existing identity
  introspection, and no mutable configuration.

## Impact

- products touched: `products/platform-gateway` (policy engine,
  enforce/confirm bridging, matrix, tests), `products/tool-gateway`
  (policy engine semantics, bundle validation, tests),
  `products/operator-portal` (confirmation card + permissions view),
  `shared/shared-contracts` (both policy schemas, default bundle),
  `shared/platform-ops` (overlay bundles, e2e demo script)
- contracts touched: `policy-rule.schema.json`,
  `policy-decision.schema.json` (additive v1 → v2 revision),
  `audit-event.schema.json` (details description enrichment only)
- identity / policy / audit / execution safety impact: strictly tighter
  — one action family gains a decider-restriction; no grant is widened;
  self-approval becomes impossible by default on mutating runs
- living state docs to update on delivery: authorization-matrix,
  approval-and-hitl guide, configuration-reference, policy-center README
  (deferred remainder), portal-user-guide Settings & Debug section
  (re-describe the restored panel), CHANGELOG, delivery-roadmap, spec index

## Open Questions

Carried from the spike memo; all resolved during delivery:

- Q-1 (observer visibility) — resolved: session list/get/delete are
  scoped server-side to the caller's own sessions (SPEC-022 R-1), so a
  parked card only ever renders inside its owner's own transcript; a
  `read-only-observer` sees only their own parked cards, and without a
  `chat:confirm` grant those render read-only (no approve/deny
  buttons). No cross-user transcript exposure exists.
- Q-2 (matrix consumer compatibility) — resolved: the only consumers of
  `GET /api/v1/policy/matrix` are the portal permissions view (updated
  in R-5) and one `jq` snippet in the troubleshooting guide (updated in
  the docs pass); the boolean cells stay fail-safe (`require_approval`
  reads `false`) and the third state rides the additive
  `approval_requirements` structure.
- Q-3 (dev-k8s identity availability) — resolved:
  `reconcile-luban-realm.sh` already provisions `luban-approver` in
  `ops-approvers`, so the two-identity demo needs no realm change.

## Changelog

- 2026-08-25: created as `draft` from the completed spike memo
  (`docs/workspace/policy-require-approval-spike.md`), promoted from the
  delivery-roadmap's "next R4 slice" marker on the bounded-mutating-
  actions row.
- 2026-08-25: draft revised after owner review — explicit approval tiers
  (`tier_1` session-operator self-confirmation for destructive-but-
  routine actions, `tier_2` designated-approver with self-approval
  blocked for critical destructive actions) cover both approval
  scenarios; the previously reserved `approval_tier` decision field is
  activated in this slice.
- 2026-08-25: R-6 add-on added at owner request — the Settings view is
  restored as a read-only Session & Identity panel in this slice (moved
  forward from the future portal-enhancement slice recorded in the D6
  memo addendum) so the shell ships without a placeholder view.
- 2026-08-25: R-6 framed as an extensible container at owner direction —
  more settings functions are expected down the road, so the panel's
  panes must be addable without restructuring the view.
- 2026-08-25: R-2 implementation note added during delivery — tool-gateway
  validates approval blocks loudly then skips require_approval rules at
  load (warning-logged), because the synced default bundle must stay
  loadable there and SPEC-021 admission must stay allow/deny (R-3/R-4).
- 2026-08-25: R-3 clarified during delivery — the decider-role check
  applies to approvals only (deny stays open so a requester can cancel
  their own parked call), and the self-approval comparison runs on
  usernames because agent-platform identifies users by `X-User-ID`;
  agent-platform's confirmer-must-own-session restriction was relaxed
  accordingly (approval authorization now lives in the gateway bridge).
- 2026-08-25: open questions Q-1/Q-2/Q-3 resolved during delivery —
  observer cards stay read-only inside owner-scoped transcripts, the
  matrix's only consumers are the portal view and one guide snippet,
  and `luban-approver` already exists in the dev realm.
- 2026-08-25: delivered in the 0.12.0 train — R-1…R-6 complete with
  full test suites green (agent-platform, platform-gateway, tool-gateway,
  portal vitest); living docs updated (approval-and-hitl, troubleshooting,
  portal-user-guide, configuration-reference, authorization-matrix,
  policy-center boundary README).
