# SPEC-074: Policy Role Axis (Agent-Role Dimension in Deny-by-Default Authorization)

## Status

- status: `delivered`
- owner: chi
- created: 2026-11-04
- approved: 2026-11-04 (all seven Open Questions ratified by the operator **exactly as
  recommended** — an inert model axis; an optional `agent_roles_any` in `match`; agent-role ×
  action only; the canonical bundle byte-unchanged; no decision/matrix projection; a v3
  `policy-rule.schema.json` with no new ADR; unit + contract + scenario evidence. See
  `## Open Questions — resolved`.)
- delivered: 2026-11-05 as **v0.55.0** — R-1…R-6 implemented as an **inert model axis**: an
  optional `agent_roles_any` in `policy-rule.schema.json` (v2 → v3, additive; absent =
  unconstrained) and an optional `agent_role: str | None = None` input on **both** gateway
  `evaluate()` engines, composing conjunctively with the human `roles_any` axis (a scoped rule
  never matches an unscoped call — fail-closed) and encoding the `executor`→**human**-approver
  disjointness invariant. No deployed caller threads a non-`None` agent-role, the canonical
  `policy-default.yaml` is byte-unchanged, and every live evaluation is byte-identical; no
  contract field beyond the additive v3 schema revision changed (`agent-stream-event` /
  `execution-request` byte-unchanged). Both policy suites green (**platform-gateway 55**,
  **tool-gateway 47**, incl. five SPEC-074 test classes mirrored across both engines plus a
  reachability guard), the full gateway suites unchanged (**500** + **1085**), all-product
  `make test` **4028**, and root `make verify` green end-to-end (portal **546**; the SPEC-063
  `execution-failure-test` campaign **795 passed, exit 0** in 0:37:24; total 42m02s, exit 0).
- release slice: the **multi-agent / bounded-autonomy program** — phase 3 of the phased SPEC
  series [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md) gates
  ([memo](../../workspace/multi-agent-orchestration-spike.md) §7, §4.2). Slotted at delivery as
  **v0.55.0** (a minor bump over v0.54.0, per the SPEC-070/071/072/073 pattern).
- related ADRs: [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md)
  (`accepted` 2026-11-03 — **Decision 4**: role-scoped agents on the *same* delegated token
  narrowed per role "at the toolkit **+ policy** layer"; SPEC-073 realized the toolkit half, this
  spec realizes the policy half);
  [ADR-0004](../../adr/0004-broker-mediated-token-delegation.md) (the *one* identity edge — the
  agent-role is a label beside the token, never a new principal or claim);
  [ADR-0007](../../adr/0007-browser-flow-single-hitl-gate.md) (one HITL gate per mutating flow —
  the `executor`→human-approver invariant this spec encodes in policy);
  [ADR-0010](../../adr/0010-signed-execution-envelopes-declare-authority-provenance.md)
  (provenance rides the fact). **No new ADR is expected**: ADR-0017 Decision 4 already authorizes
  the policy-layer role axis; this spec makes it concrete and additive (see OQ-6 on the schema
  revision).
- extends: [SPEC-004](../SPEC-004-deny-by-default-policy-enforcement/spec.md) (deny-by-default
  evaluation), [SPEC-030](../SPEC-030-tiered-mutating-action-approval/spec.md) (the
  `require_approval` outcome + tiers + the v1→v2 `policy-rule.schema.json` revision precedent),
  [SPEC-019](../SPEC-019-portal-transparency-navigation/spec.md) (the live permission matrix),
  [SPEC-048](../SPEC-048-policy-testing-rollout-controls/spec.md) (the scenario-expectation
  harness + bundle content-hash provenance), and
  [SPEC-073](../SPEC-073-role-scoped-agent-identity/spec.md) (the closed agent-role vocabulary
  this axis evaluates).

> SDD note: `spec.md` was drafted first and carried **seven Open Questions**, all ratified by the
> operator **2026-11-04** exactly as recommended (see `## Open Questions — resolved`). Approval
> authorizes the [plan](plan.md) / [tasks](tasks.md) — now written and **binding** (provisional
> banners lifted) — and lets implementation **begin**. It does **not** authorize a merge,
> commit/push, deployment, or a version bump; those stay separate boundaries, and the standing
> "review before any merge/deploy" constraint governs. This is phase 3 of the series: **audit &
> attribution** (memo §4.3), **bounded autonomous diagnosis** (§5, the loop that first *binds*
> roles), and the **v2 multi-agent contract** (§4.5) are separate later specs and are explicitly
> out of scope here.

## Summary

Land the **agent-role** as an explicit, first-class **axis in the deny-by-default authorization
model** — the policy half of ADR-0017 Decision 4 that SPEC-073 deliberately deferred. Today the
gateway policy engines evaluate `evaluate(settings, roles, action)` keyed only on the *human*
token's `roles`; the SPEC-073 agent-role (`diagnostician`, `orchestrator`, `executor`) is a
process-local label in `agent-platform` that never reaches the gateway. Phase 3 adds an **additive,
inert** agent-role dimension to the policy *model* — the `policy-rule.schema.json` `match` block,
both gateway `evaluate()` engines, the authorization-matrix documentation, the Tier-1 policy
specification, and the scenario-expectation harness — so a rule *may* be scoped to agent-roles and
the `executor`→**human**-approver invariant is encoded as policy, not prose. Like SPEC-070 and
SPEC-073, it ships **inert**: no deployed caller threads a non-`None` agent-role across the process
boundary yet (that wiring is phase 5/6), so every live evaluation passes `agent_role=None` and is
**byte-identical** to today.

## Motivation

- **ADR-0017 Decision 4 names two narrowing layers; only one is built.** Decision 4 fixed the
  model as role-scoped agents "narrowed per role at the **toolkit + policy** layer." SPEC-073 built
  the *toolkit* half (what an agent sees) and explicitly left the *policy* half to phase 3
  (SPEC-073 Non-Goals: "the policy role axis is phase 3"; OQ-3: "a family allowlist is a *policy*
  concern for phase 3's role axis … no gateway-side role check lands in phase 2"). The program is
  not decision-complete downstream until the policy model can express an agent-role.
- **The memo requires an explicit axis, not ad-hoc rules.** memo §4.2: "Multi-agent adds an
  **agent-role** dimension: the same tool may be allowed for the `diagnostician` and denied for a
  `summarizer`, and a mutation proposed by an `executor` must still require a *human* approver
  (never another agent). This **must land in the authorization matrix and the policy-center model
  as an explicit role axis, not as per-agent ad-hoc rules**."
- **The model already reserves room for it.** The Tier-1
  [policy-specification.md](../../agentic-aiops-platform/policy-specification.md) states a goal to
  "support MVP-first implementation while allowing **future expansion**," defines a rich policy
  input object (with `request.tool_name`, `request.execution_mode`, …) and reserves
  `allow_with_conditions`. The *shipped* slice is a strict `action_authz` subset
  (`match: {roles_any, actions_any}`). An additive agent-role match dimension is the natural next
  axis, exactly as SPEC-030 added `require_approval` via a v1→v2 schema revision.
- **Why now.** SPEC-073 (the identity/authority substrate) is delivered (v0.54.0). Sequencing the
  policy axis immediately after identity is the memo's own order (§7): phase 4 (audit attribution)
  and phase 5 (bounded diagnosis, which first *binds* roles) both need the policy model to already
  understand an agent-role, or they would build on an unmapped edge.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.
Phase 3 delivers an **inert model axis**: every requirement is provable by unit/contract/scenario
tests over the policy model with **no orchestration caller threading a role** and **no change to
any deployed (unscoped) evaluation** — mirroring SPEC-070/073's inert-substrate acceptance.

### R-1: An additive agent-role dimension in the policy rule schema

Extend `policy-rule.schema.json` (v2 → v3) with an **optional** `agent_roles_any` array in the
`match` block — items drawn from the closed SPEC-073 vocabulary (`diagnostician`, `orchestrator`,
`executor`). **Absent = unconstrained** (the rule matches regardless of the call's agent-role), so
every existing rule is byte-identical and still evaluates exactly as today. The revision is
additive and backward-compatible: a v2 bundle validates against v3 unchanged.

Acceptance criteria:

- The schema `match` block accepts an optional `agent_roles_any: string[]`; `additionalProperties`
  stays `false` for every other key; the closed vocabulary is enforced (an out-of-set value fails
  validation).
- Every rule in the canonical `policy-default.yaml` (which carries no `agent_roles_any`) validates
  byte-unchanged against the v3 schema.
- A contract test asserts the v2→v3 diff is additive only (no required key added, no existing
  semantics changed).

### R-2: An optional agent-role input on both gateway policy engines

Add an optional `agent_role: str | None = None` parameter to `evaluate()` in **both**
`platform-gateway` and `tool-gateway` `policy_engine.py`, and an `agent_roles_any` field to the
parsed `PolicyRule`. Matching composes the two axes **conjunctively within a rule**: a rule matches
only if the principal holds a `roles_any` human role **and** (the rule has no `agent_roles_any`, or
the call's `agent_role` is in it). Precedence is unchanged (`deny > require_approval > allow`).

Acceptance criteria:

- `evaluate(settings, roles, action)` (no `agent_role`) is **byte-identical** to today for every
  rule in the canonical bundle — the default `None` path never consults the new axis.
- A rule with `agent_roles_any` **never matches** an unscoped (`agent_role=None`) call — an
  agent-role-scoped grant cannot be satisfied by a turn that carries no role (**fail-closed**,
  mirroring SPEC-073 R-5).
- A rule with `agent_roles_any` matches only when the call's `agent_role` is in the set; the
  human-role axis still applies conjunctively.
- Both engines share the semantics; the tool-gateway continues to skip `require_approval` at load
  (SPEC-030), the platform-gateway continues to honor it.

### R-3: The `executor`→human-approver invariant encoded as policy

Encode memo §4.2's segregation-of-duty invariant in the policy model: an `executor`-scoped
mutation stays on the **human** approval path, and **no agent-role is ever a decider**. Concretely
— a guard proves the SPEC-073 agent-role vocabulary and the human `decided_by_roles` /
`roles_any` vocabularies are **disjoint** (an agent-role can never appear as an approver decider or
be confused with a human platform role), and the canonical encoding of "`executor` mutation ⇒
`require_approval` by a distinct human" is documented and scenario-covered.

Acceptance criteria:

- A guard test asserts no value in `{diagnostician, orchestrator, executor}` appears in any
  `decided_by_roles` (an agent never approves) — the SPEC-030 "synthetic/workload identities are
  excluded by authoring" rule extended to agent-roles, now enforced by a test rather than prose.
- A scenario in `policy-scenarios.yaml` exercises an `executor`-scoped `tools:mutate` rule
  evaluating to `require_approval` with a human `decided_by_roles`, and a `diagnostician`/
  `orchestrator` context that cannot reach a mutating grant.
- The invariant is documented in the authorization matrix and the Tier-1 policy specification.

### R-4: The agent-role axis in the authorization model documentation

Document the agent-role axis as a first-class dimension in
[authorization-matrix.md](../../agentic-aiops-platform/authorization-matrix.md) (a new agent-role ×
capability section beside the six human platform roles, stating the subtractive-only relationship
to the human-role axis and the `executor`→human-approver invariant) and in
[policy-specification.md](../../agentic-aiops-platform/policy-specification.md) (the agent-role as
a policy-input dimension and a rule-match axis, within the reserved "future expansion").

Acceptance criteria:

- The matrix names the three agent-roles, their default posture (diagnostician read-only,
  orchestrator no direct gateway tools, executor may propose mutations that still park on human
  approval), and states that the axis **narrows only** (an agent-role can never widen what the
  human token's `roles` already permit).
- The policy specification adds the agent-role to the policy-input object and the rule-match model
  as an optional, additive dimension.
- Both docs cross-reference SPEC-073 (vocabulary) and ADR-0017 Decision 4.

### R-5: Fail-closed invariants, inertness, and four-point-gate parity

The axis is **subtractive-only** and **inert** on every deployed path. An unscoped evaluation
(`agent_role=None`) is byte-identical to today; an agent-role-scoped rule can only ever *remove*
authority the human token already grants, never add it; and no deployed caller threads a role.

Acceptance criteria:

- Guard test: no code path reachable from the deployed gateway routes
  (`platform-gateway` `enforce_policy` call sites, `tool-gateway` admission) passes a non-`None`
  `agent_role` in phase 3 — the axis has no live producer (the SPEC-073 R-5 reachability guard,
  policy-side).
- No-diff test: the full platform-gateway and tool-gateway policy suites pass unchanged with the
  axis present but unexercised; the canonical bundle hash is unchanged unless OQ-4 lands a rule
  (in which case the four replicas stay byte-identical via `make sync-policy`).
- An agent-role-scoped rule evaluated against a token whose human `roles` already deny the action
  still denies (subtractive-only: the axis never overrides a human-role deny).
- Root `make verify` green (incl. `validate-policy`, `validate-policy-scenarios`, the bundle-parity
  check, and `validate-version`).

### R-6: Scenario-expectation coverage and contract reconciliation

Extend the SPEC-048 scenario harness with agent-role expectations and reconcile the contract
surfaces: the `policy-decision.schema.json` (does the decision object surface the evaluated
agent-role? — OQ-5), the live `policy-matrix` surface (does it render the axis? — OQ-5), and the
`policy-rule.schema.json` v3 revision note.

Acceptance criteria:

- `policy-scenarios.yaml` gains expectations that pin the agent-role matching semantics (scoped
  rule matches the right role, never matches unscoped, composes conjunctively with the human axis);
  `make validate-policy-scenarios` green.
- The `policy-decision` / `policy-matrix` contract surfaces are reconciled per OQ-5 (additive only,
  or explicitly unchanged with the reason recorded).
- The schema revision is recorded in the Tier-1 policy specification's revision history.

## Non-Goals

- **Binding a role at a live caller** — no orchestration/diagnosis loop threads an agent-role into
  `evaluate()` in phase 3. The producer is phase 5 (bounded autonomous diagnosis). Phase 3 is the
  inert model axis only.
- **Crossing the process boundary with the role** — the agent-role stays out of every wire field,
  JWT claim, and forwarded header in phase 3 (SPEC-073's invariant). Projecting role provenance
  onto the wire/audit is phase 4 (audit & attribution) and phase 6 (the v2 multi-agent contract).
- **A tool-name / tool-family allowlist axis** — memo §4.2's "the same tool allowed for X, denied
  for Y" at *tool-name* granularity. The shipped bundle is action-based (`tools:invoke` /
  `tools:mutate`) and names no tool; adding a tool-name match dimension is a larger axis deferred
  unless OQ-3 pulls it in. Phase 3's axis is the agent-role, composing with the existing action
  axis.
- **`allow_with_conditions` / the full Tier-1 input object** — the reserved rich outcome and the
  full `principal.*` / `request.*` input set stay unimplemented; phase 3 adds only the agent-role
  axis to the shipped `action_authz` slice.
- **Any change to the toolkit narrowing** — SPEC-073's `_narrow_for_role` / `_ensure_toolkit` seam
  is unchanged; phase 3 is the *gateway policy* layer, not the agent-platform toolkit layer.
- **Policy-center as a service** — `evaluate()` stays an in-process function (the schema's
  "when policy-center becomes a service" note is a separate future move).

## Impact

- products touched: `products/platform-gateway` (`services/policy_engine.py`,
  `services/policy_matrix.py` per OQ-5, `services/gateway_service.py` signature only),
  `products/tool-gateway` (`services/policy_engine.py`, admission path signature only).
  **No** `agent-platform`, `identity-broker`, `audit-service`, `execution-runtime`, or portal
  change in phase 3 (the toolkit axis is SPEC-073; the audit projection is phase 4; the contract
  field is phase 6). Documentation: `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/agentic-aiops-platform/policy-specification.md`,
  `docs/agentic-aiops-platform/identity-and-authorization-design.md` (phase-boundary note).
- contracts touched: `shared/shared-contracts/schemas/policy-rule.schema.json` (v2 → v3, additive
  `agent_roles_any`); `shared/shared-contracts/policies/policy-default.yaml` (+ its three
  byte-identical replicas) **only if** OQ-4 lands a canonical rule;
  `shared/shared-contracts/policies/policy-scenarios.yaml` (new expectations);
  `shared/shared-contracts/schemas/policy-decision.schema.json` /
  `policy-matrix.schema.json` **only if** OQ-5 projects the axis. `agent-stream-event.schema.json`
  and `execution-request.schema.json` stay **byte-unchanged**.
- identity / policy / audit / execution safety impact: **policy** — adds an inert, subtractive-only
  agent-role axis to deny-by-default evaluation; the human-role axis and precedence are unchanged;
  an unscoped evaluation is byte-identical. **identity** — none (the role stays a label beside the
  one delegated token; no new principal, claim, or edge). **audit** — none in phase 3 (the role
  projection is phase 4). **execution safety** — the `executor`→human-approver invariant is
  reinforced (an agent-role can never be an approver decider); the governed mutation path
  (SPEC-037/038/063) is unchanged.
- living state docs to update on delivery: `docs/specs/README.md` (index row),
  `docs/agentic-aiops-platform/delivery-roadmap.md` (the multi-agent program row, phase 3),
  `CHANGELOG.md`, and the phase-boundary note in `identity-and-authorization-design.md`.

## Open Questions — resolved

All seven Open Questions were ratified by the operator **2026-11-04** exactly as recommended (the
SPEC-072/073 pattern). Each resolution is binding on the [plan](plan.md) / [tasks](tasks.md).

- **OQ-1 — Phase-3 posture. RESOLVED: an inert model axis.** Phase 3 lands the agent-role as an
  additive, inert policy-model dimension (schema + engine signature + matrix + scenarios + docs)
  with **no** caller threading a role, so every deployed evaluation is byte-identical. Live gateway
  enforcement is deferred to phase 5, when a producer exists; the role crosses no wire field in
  phase 3 (SPEC-073's invariant; the contract field is phase 6).
- **OQ-2 — Match shape. RESOLVED: an optional `agent_roles_any` array in the existing `match`
  block.** Mirrors `roles_any` / `actions_any`, keeps one rule shape, and is the smallest additive
  v3 revision. A separate `agent_role_authz` domain and a top-level axis outside `match` are
  rejected as larger and less faithful to the memo's "explicit role axis … not per-agent ad-hoc
  rules."
- **OQ-3 — Axis granularity. RESOLVED: agent-role × action only.** The shipped bundle is
  action-based and names no tool; SPEC-073 already does read/write-tier *toolkit* narrowing
  in-process. A tool-name/tool-family match dimension stays deferred (revisit at phase 5 when a
  real diagnosis loop names the first concrete tool families — memo §8 Q5).
- **OQ-4 — Canonical bundle. RESOLVED: `policy-default.yaml` stays byte-unchanged.** With no caller
  threading a role, any `agent_roles_any` rule would be inert anyway, and adding one forces a
  bundle-hash change + four-replica re-sync for zero deployed effect. The `executor`→human-approver
  encoding (R-3) is demonstrated in `policy-scenarios.yaml` and unit fixtures (synthetic bundles);
  the canonical rule lands at phase 5 when a producer exists.
- **OQ-5 — Decision/matrix projection. RESOLVED: no contract projection in phase 3.** The
  `policy-decision` object and the live `policy-matrix` stay human-role-only; the agent-role axis is
  documented (R-4) but not rendered live, because there is no producer and projecting an
  always-`None` axis adds a consumerless contract surface. Additive projection is deferred to phase
  4 (audit attribution) / phase 5, following the SPEC-073 OQ-4 "add the field when a real consumer
  exists" pattern.
- **OQ-6 — Schema version / ADR. RESOLVED: a v3 `policy-rule.schema.json` with a recorded revision
  note; no new ADR.** The v2→v3 bump is additive (the SPEC-030 v1→v2 precedent), so it is a contract
  decision within this spec, not an architecture decision — ADR-0017 Decision 4 already authorizes
  the policy-layer role axis.
- **OQ-7 — Acceptance evidence. RESOLVED: unit + contract + scenario tests, green `make verify`,
  and a policy-side reachability/no-diff guard; no live/browser evidence.** Mirrors SPEC-073 OQ-5.
  The reachability guard (R-5) proves no deployed gateway route threads a non-`None` agent-role;
  the no-diff test proves the unscoped evaluation is byte-identical.

## Changelog

- 2026-11-04: created as `draft` with seven Open Questions; phase 3 of the ADR-0017 series,
  realizing the policy-layer half of Decision 4 that SPEC-073 (v0.54.0) deferred.
- 2026-11-04: **approved** — all seven Open Questions ratified by the operator exactly as
  recommended; [plan](plan.md) / [tasks](tasks.md) provisional banners lifted and now binding;
  implementation authorized to *begin* (not to merge, commit/push, deploy, or version-bump).
