# SPEC-030 Plan: Require-Approval Policy Semantics

## Approach

Contract-first: the two shared policy schemas grow the reserved
`require_approval` outcome (additive v1 → v2 revision) with explicit
approval tiers — `tier_1` (session operator self-confirmation,
destructive-but-routine) and `tier_2` (designated approver distinct from
the requester, critical destructive), mirroring the authorization
matrix's existing tier vocabulary. Both policy engines learn identical
three-outcome semantics, and enforcement rides the already-delivered
SPEC-020 confirmation substrate instead of any new queue machinery.
Stages: contracts → engines → confirm-route bridging → bundle posture →
transparency/audit → docs.

## Design Per Requirement

### R-1: Contract revision

- affected files: `shared/shared-contracts/schemas/policy-rule.schema.json`,
  `policy-decision.schema.json`, contract validation scripts/tests
- chosen approach: additive enum extension plus an optional `approval`
  object on both rule decisions and the decision payload — `tier`
  (required, `tier_1` / `tier_2`), `decided_by_roles`, and optional
  `allow_self_approval` (unset means the tier default: tier_1 allows,
  tier_2 forbids); the previously reserved decision-side `approval_tier`
  field is activated. v1 bundles stay valid.
- alternatives: separate `approval` policy domain per the Tier-1 spec —
  rejected for this slice (the action_authz subset is the delivered
  engine shape; a new domain implies the policy-center service, which is
  the R5 remainder).

### R-2: Evaluation semantics

- affected files: `products/platform-gateway/src/platform_gateway/services/policy_engine.py`,
  `products/tool-gateway/src/tool_gateway/services/policy_engine.py`,
  both test suites
- chosen approach: extend `PolicyDecision` with an optional approval
  block (tier + deciders); evaluation order deny > require_approval >
  allow; highest priority wins within require_approval matches; bundle
  load validation raises `PolicyLoadError` for require_approval rules on
  unbridged actions and for `tier_2` rules with explicit
  `allow_self_approval: true` (platform-gateway bridge set
  `{tools:mutate}`, tool-gateway empty this slice). Engines stay
  deliberately non-parity (different action vocabularies) — semantics
  tests mirror each other instead.
- alternatives: 403-only blocking semantics (spike option A) — rejected
  as operator-invisible; the confirm bridge makes the outcome decidable.

### R-3: Tiered enforcement bridge on `chat:confirm`

- affected files: `products/platform-gateway/src/platform_gateway/api/routes/chat.py`,
  `services/gateway_service.py` (`chat_confirm` proxy path),
  `products/agent-platform/src/agent_service/services/hitl_confirmations.py`
  (parked-call metadata: which tool action is parked),
  `products/agent-platform/src/agent_service/api/v2/routes.py`
- chosen approach: the confirm path resolves the parked call's tool
  action, evaluates it against the platform-gateway bundle, and on
  `require_approval` checks the confirmer's roles against
  `decided_by_roles` before forwarding to agent-platform; `tier_1`
  accepts the session owner as confirmer (self-confirmation), `tier_2`
  rejects when the confirmer subject equals the session owner subject
  (the tier forbids self-approval). Rejections are structured 403s in
  the existing policy-denial detail shape; the parked call stays parked
  (no state mutation on rejection). The agent registry already fails
  closed on concurrent claims — untouched.
- alternatives: enforcing decider roles kernel-side — rejected (kernel
  confirmation is the operator-inline layer per the two-layer model;
  policy decisions belong at the platform edge).

### R-4: Default bundle posture

- affected files: `shared/shared-contracts/policies/policy-default.yaml`,
  packaged copies, both dev-k8s overlay copies (`make sync-policy`),
  `shared/platform-ops/e2e/mutating-demo.sh`
- chosen approach: one `tier_2` `require_approval` rule on
  `tools:mutate` (`decided_by_roles: [approver, platform-admin]`);
  the existing allow rule stays so admission is unchanged. A bundle
  comment documents the `tier_1` authoring pattern for
  destructive-but-routine actions added later. Demo script switches to a
  two-identity flow (operator requests, approver confirms). Synthetic
  identities excluded by bundle authoring, documented in a bundle
  comment.
- alternatives: shipping the rule disabled by default — rejected (the
  whole slice is invisible unless the default posture uses it; mutating
  execution is already opt-in via `GATEWAY_MUTATING_TOOLS_ENABLED`).

### R-5: Transparency and audit consistency

- affected files: `products/platform-gateway/src/platform_gateway/services/policy_matrix.py`,
  `api/routes/policy.py`, `products/operator-portal/web-ui/app/src/views/control/PermissionsView.tsx`,
  `chat/` confirmation-card component, audit event schema details
  description, `confirmation_decided` enrichment at the audit tee point
- chosen approach: third matrix cell state `requires_approval` carrying
  the tier and decider roles (additive response field); portal renders
  it distinctly; confirmation cards gain a tier badge ("operator
  confirmation" vs "approver required") and read-only mode for
  non-deciders; `confirmation_decided` details gain `approval_rule_id`,
  the tier, and a blocked-self-approval outcome value at the existing
  tee (only applied/rejected decisions reach the trail, per the SPEC-020
  pattern).
- alternatives: endpoint version bump for the matrix — rejected; the
  cell value is additive and the portal is the only consumer (Q-2 must
  still verify).

### R-6: Settings view restored as a read-only panel (add-on)

- affected files: new `products/operator-portal/web-ui/app/src/views/SettingsView.tsx`
  (wired into `App.tsx` replacing `ViewPlaceholder` for settings),
  `src/api/client.ts` (remember last generated `x-request-id`),
  vitest coverage
- chosen approach: read-only panes built from state that already
  exists client-side — `AuthContext` (username/roles/sign-in state), the
  session workspace's selected session id, `PLATFORM_VERSION`, and the
  current gateway origin. Ant Design `Descriptions`/`Card` styling on
  the dark theme tokens; no new API calls, no mutable controls (the
  obsolete pre-OIDC debug inputs are not restored). The view is a
  tabbed/sectioned container whose panes are self-contained components,
  so future settings functions (display preferences, default model
  selection, notification defaults) can be added as new panes without
  restructuring — owner direction, not committed scope.
- alternatives: restoring the vanilla debug inputs (gateway override,
  manual user id, non-stream send) — rejected as obsolete post-OIDC;
  shipping them would contradict the bearer-overrides-manual posture.

## Sequencing And Dependencies

1. Contract revision (R-1) — depends on nothing; everything else
   consumes the v2 schemas.
2. Engine semantics (R-2) — depends on 1; independent between the two
   gateways.
3. Confirm-route bridging (R-3) — depends on 2 (platform-gateway).
4. Bundle posture + demo script (R-4) — depends on 2 (validation) and
   3 (enforcement must exist before the rule ships active).
5. Transparency and audit (R-5) — depends on 2 for the matrix; the card
   and audit enrichment depend on 3.
6. Settings panel (R-6) — depends on nothing in R-1…R-5; independent
   portal-only work that can land whenever convenient in the train.
7. Docs + delivery gate — depends on all above.

## Test Strategy

- unit tests: engine semantics (mixed matches, precedence, priority,
  disabled rules, load validation) in both gateway suites; confirm-route
  decider/self-approval cases in platform-gateway route tests; matrix
  third-state cases in `test_policy_matrix.py`; portal card rendering
  tests (vitest) for badge and read-only modes; Settings panel vitest
  renders (signed-in, signed-out, no-session states).
- contract tests: v2 schema validation of v1 bundles (backward compat),
  new-rule validation, audit-event details parity with audit-service.
- integration / overlay validation: `make sync-policy` +
  `make validate-policy` across the four bundle copies; kustomize render
  of both dev-k8s bases; `mutating-demo.sh` two-identity e2e as the
  live validation path (requires the Q-3 approver test user).

## Rollout And Migration

- deployment: bundle ConfigMap updates propagate via the existing
  `sync-policy`/deploy flow; no new services, no new secrets.
- backward compatibility: v1 bundles evaluate identically (no
  require_approval rules → identical decisions); matrix consumers see a
  new optional cell value only.
- rollback: revert the bundle rule (redeploy ConfigMap) to restore
  today's operator-self-confirm behavior instantly; code paths stay
  inert without require_approval rules in the bundle.
