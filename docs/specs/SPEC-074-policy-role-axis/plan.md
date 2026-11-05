# SPEC-074 Plan: Policy Role Axis (Agent-Role Dimension in Deny-by-Default Authorization)

> **BINDING** — approved 2026-11-04. The operator ratified all seven Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the resolutions assumed below are binding:
> an inert model axis; an optional `agent_roles_any` in `match`; agent-role × action only; the
> canonical `policy-default.yaml` byte-unchanged; no decision/matrix projection; a v3
> `policy-rule.schema.json` with no new ADR; unit + contract + scenario evidence. Implementation is
> authorized to *begin* — not to merge, commit/push, deploy, or version-bump (separate gates).

## Approach

Phase 3 generalizes the *shipped* `action_authz` slice from one identity axis (the human token's
`roles`) to two conjunctive axes (human `roles_any` **and** an optional agent-role
`agent_roles_any`), exactly as SPEC-030 generalized the outcome set from two to three. The change
is **additive and inert**: the new match key is optional and absent-means-unconstrained, the new
`evaluate()` parameter defaults to `None`, and no deployed caller threads a role — so every live
decision is byte-identical. Both gateway engines share the near-identical `evaluate()` /
`_parse_rules()` / `PolicyRule` code, so the axis lands once per engine with identical semantics
(the tool-gateway keeps skipping `require_approval` at load per SPEC-030). The work groups into six
stages mirroring R-1…R-6.

## Design Per Requirement

### R-1: Additive agent-role dimension in `policy-rule.schema.json` (v2 → v3)

- affected files: `shared/shared-contracts/schemas/policy-rule.schema.json`.
- chosen approach: add an optional `agent_roles_any: {"type":"array","items":{"enum":
  ["diagnostician","orchestrator","executor"]}}` to the `match` object's `properties`, leaving it
  out of `match.required` (so absent = unconstrained) and keeping `additionalProperties: false`.
  Bump the title/description to v3 with a revision note (the SPEC-030 v1→v2 precedent). The closed
  `enum` enforces the SPEC-073 vocabulary at validation time.
- alternatives rejected: a free-form `string[]` (loses the closed-vocabulary guarantee SPEC-073
  R-1 established); a separate `agent_role_authz` domain schema (splits the model — OQ-2).

### R-2: Optional `agent_role` input on both engines

- affected files: `products/platform-gateway/src/platform_gateway/services/policy_engine.py`,
  `products/tool-gateway/src/tool_gateway/services/policy_engine.py` (and the `enforce_policy` /
  admission call sites' signatures, default `None`).
- chosen approach: add `agent_roles_any: tuple[str, ...] = ()` to `PolicyRule`; parse it in
  `_parse_rules` (validating against the closed vocabulary, raising `PolicyLoadError` on an
  out-of-set value); add `agent_role: str | None = None` to `evaluate()`; extend the match
  comprehension to `and (not rule.agent_roles_any or (agent_role is not None and agent_role in
  rule.agent_roles_any))`. Precedence and the deny-by-default tail are untouched.
- alternatives rejected: threading the role through `IdentityContext` (it is not an identity
  attribute and would imply it rides the token — SPEC-073 forbids); evaluating the axis only in one
  engine (the memo wants one model, and both share the bundle).

### R-3: `executor`→human-approver invariant as policy

- affected files: `shared/shared-contracts/policies/policy-scenarios.yaml`, engine guard tests.
- chosen approach: a guard test asserts the agent-role vocabulary is disjoint from every
  `decided_by_roles` and `roles_any` value in the canonical bundle (an agent-role is never an
  approver decider nor mistaken for a human role). A scenario pins an `executor`-scoped
  `tools:mutate` rule → `require_approval` with a human decider, and a `diagnostician`/
  `orchestrator` context that cannot reach a mutating grant. Per OQ-4 the canonical
  `policy-default.yaml` stays byte-unchanged; the rule is demonstrated in the scenario harness and
  unit fixtures (a synthetic bundle), landing canonically at phase 5.
- alternatives rejected: landing an inert canonical rule now (a bundle-hash change + four-replica
  re-sync for zero deployed effect — OQ-4).

### R-4: Authorization-model documentation

- affected files: `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/agentic-aiops-platform/policy-specification.md`,
  `docs/agentic-aiops-platform/identity-and-authorization-design.md` (phase-boundary note).
- chosen approach: a new "Agent-Role Axis (SPEC-074, phase 3)" section in the matrix beside the six
  human roles — the three agent-roles, their default posture, the subtractive-only relationship to
  the human axis, and the `executor`→human-approver invariant; the policy specification adds the
  agent-role to the policy-input object and the rule-match model within the reserved "future
  expansion," plus a v3 revision-history line.
- alternatives rejected: documenting only in the spec (the memo explicitly requires the matrix and
  policy-center model to carry the axis).

### R-5: Fail-closed invariants, inertness, four-point-gate parity

- affected files: engine tests, a new reachability guard test.
- chosen approach: a reachability guard scans the deployed gateway routes / `enforce_policy` call
  sites asserting none passes a non-`None` `agent_role` (the SPEC-073 R-5 guard, policy-side); a
  no-diff test runs the existing policy suites unchanged; a subtractive-only test proves an
  agent-role-scoped rule never overrides a human-role deny.
- alternatives rejected: a live end-to-end enforcement test (no producer exists until phase 5).

### R-6: Scenario coverage and contract reconciliation

- affected files: `shared/shared-contracts/policies/policy-scenarios.yaml`,
  `shared/shared-contracts/schemas/policy-decision.schema.json` /
  `policy-matrix.schema.json` (per OQ-5, expected unchanged), the Tier-1 spec revision history.
- chosen approach: scenario expectations pin the matching semantics; the decision/matrix schemas
  stay human-role-only per OQ-5 (recorded with the reason); the schema revision is noted in the
  Tier-1 spec.
- alternatives rejected: an additive `agent_role` on the decision object now (a consumerless
  contract surface — OQ-5).

## Sequencing And Dependencies

1. **Stage 1 — schema (R-1)** — depends on nothing; the additive v3 revision is the contract anchor.
2. **Stage 2 — engines (R-2)** — depends on Stage 1; lands `agent_roles_any` parsing + the
   `evaluate()` axis in both gateways with identical semantics.
3. **Stage 3 — invariant + scenarios (R-3, R-6)** — depends on Stage 2; the disjointness guard and
   the scenario expectations exercise the axis.
4. **Stage 4 — inertness + reachability guards (R-5)** — depends on Stage 2; proves byte-identical
   unscoped evaluation and no live producer.
5. **Stage 5 — documentation (R-4)** — depends on Stages 1–2; the matrix + Tier-1 spec + design
   phase-boundary note.
6. **Stage 6 — verify + reconcile (R-6)** — depends on all; `make verify` (incl. `validate-policy`,
   `validate-policy-scenarios`, bundle parity, `validate-version`), contract reconciliation, index /
   roadmap / CHANGELOG on delivery.

## Test Strategy

- unit tests: `evaluate()` with and without `agent_role` over synthetic bundles (scoped rule matches
  the right role, never matches unscoped, composes conjunctively with the human axis, never
  overrides a human deny); `_parse_rules` rejects an out-of-vocabulary `agent_roles_any`; both
  engines assert identical semantics.
- contract tests: the v2→v3 `policy-rule.schema.json` diff is additive; every canonical bundle rule
  validates byte-unchanged against v3; `agent-stream-event.schema.json` and
  `execution-request.schema.json` stay byte-unchanged; the decision/matrix schemas unchanged (OQ-5).
- scenario tests: `policy-scenarios.yaml` agent-role expectations via `make validate-policy-scenarios`.
- guard tests: the reachability scan (no deployed route threads a non-`None` agent-role) and the
  agent-role/human-role vocabulary disjointness (no agent-role is an approver decider).
- integration / overlay validation: `make sync-policy` keeps the four bundle replicas byte-identical
  (unchanged unless OQ-4 lands a rule); root `make verify` green.

## Rollout And Migration

- deployment or configuration changes: **none** in phase 3 — the axis is inert (no producer), the
  canonical bundle is byte-unchanged (OQ-4 recommendation), and no env/flag is added. A pod restart
  picks up the new engine code but changes no decision.
- backward compatibility: a v2 bundle validates and evaluates identically under v3; the default
  `agent_role=None` path is byte-identical. The schema revision is additive.
- rollback approach: revert the engine/schema/doc commits; with no bundle or contract-field change
  and no producer, rollback has no runtime effect beyond removing the inert capability.
