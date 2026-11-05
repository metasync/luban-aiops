# SPEC-074 Tasks: Policy Role Axis (Agent-Role Dimension in Deny-by-Default Authorization)

> **BINDING** — approved 2026-11-04; all seven Open Questions in [`spec.md`](spec.md) ratified by
> the operator exactly as recommended, provisional banner lifted.
> Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs. Phase 3 is
> an **inert model axis** — every task is provable by unit/contract/scenario tests with no caller
> threading a role and no change to any deployed (unscoped) evaluation.

## R-1: Additive agent-role dimension in the policy rule schema (v2 → v3)

- [x] Add an optional `agent_roles_any` array to the `match` block of
      `policy-rule.schema.json`, items `enum`-closed to `diagnostician`/`orchestrator`/`executor`,
      not in `match.required`, `additionalProperties` still `false`; bump the title/description to
      v3 with a revision note (`shared/shared-contracts/schemas/policy-rule.schema.json`)
- [x] Contract test: the v2→v3 diff is additive only, and every canonical `policy-default.yaml`
      rule validates byte-unchanged against v3 (`shared/shared-contracts` validation)

## R-2: Optional agent-role input on both gateway policy engines

- [x] Add `agent_roles_any: tuple[str, ...] = ()` to `PolicyRule` and parse it in `_parse_rules`
      (reject an out-of-vocabulary value with `PolicyLoadError`)
      (`products/platform-gateway/src/platform_gateway/services/policy_engine.py`)
- [x] Add `agent_role: str | None = None` to `evaluate()` and extend the match to compose
      conjunctively: a rule with `agent_roles_any` never matches an unscoped (`None`) call
      (`.../platform-gateway/.../policy_engine.py`)
- [x] Mirror both changes with identical semantics in the tool-gateway engine (which keeps skipping
      `require_approval` at load per SPEC-030)
      (`products/tool-gateway/src/tool_gateway/services/policy_engine.py`)
- [x] Thread the optional `agent_role=None` default through the `enforce_policy` / admission call
      sites' signatures only — no route passes a non-`None` value
      (`.../platform-gateway/services/gateway_service.py`, tool-gateway admission)
- [x] Test: `evaluate(settings, roles, action)` (no agent_role) is byte-identical to today over the
      canonical bundle; a scoped rule matches only the right role; conjunctive with the human axis;
      both engines agree (`products/*/tests/test_policy_engine.py`)

## R-3: The `executor`→human-approver invariant encoded as policy

- [x] Guard test: the agent-role vocabulary is disjoint from every `decided_by_roles` and
      `roles_any` value in the canonical bundle — an agent-role is never an approver decider nor a
      human platform role (`products/*/tests/...`)
- [x] Scenario: an `executor`-scoped `tools:mutate` rule → `require_approval` with a human decider,
      and a `diagnostician`/`orchestrator` context that cannot reach a mutating grant
      (`shared/shared-contracts/policies/policy-scenarios.yaml`)
- [x] Confirm the canonical `policy-default.yaml` stays byte-unchanged (OQ-4 recommendation); the
      rule is demonstrated in scenarios + unit fixtures, landing canonically at phase 5

## R-4: The agent-role axis in the authorization model documentation

- [x] Add an "Agent-Role Axis (SPEC-074, phase 3)" section to the authorization matrix beside the
      six human roles: the three agent-roles, their default posture, the subtractive-only
      relationship, and the `executor`→human-approver invariant
      (`docs/agentic-aiops-platform/authorization-matrix.md`)
- [x] Add the agent-role to the policy-input object and the rule-match model in the Tier-1 policy
      specification, within the reserved "future expansion," plus a v3 revision-history line
      (`docs/agentic-aiops-platform/policy-specification.md`)
- [x] Update the phase-boundary note to record phase 3 delivered
      (`docs/agentic-aiops-platform/identity-and-authorization-design.md`)

## R-5: Fail-closed invariants, inertness, and four-point-gate parity

- [x] Reachability guard: no code path reachable from the deployed gateway routes / `enforce_policy`
      call sites passes a non-`None` `agent_role` (the SPEC-073 R-5 guard, policy-side)
      (`products/*/tests/...`)
- [x] No-diff test: the full platform-gateway and tool-gateway policy suites pass unchanged with the
      axis present but unexercised
- [x] Subtractive-only test: an agent-role-scoped rule never overrides a human-role deny; the axis
      can only remove authority the token already grants
- [x] Root `make verify` green (incl. `validate-policy`, `validate-policy-scenarios`, bundle parity,
      `validate-version`)

## R-6: Scenario-expectation coverage and contract reconciliation

- [x] `policy-scenarios.yaml` agent-role expectations pin the matching semantics;
      `make validate-policy-scenarios` green
- [x] Reconcile `policy-decision.schema.json` / `policy-matrix.schema.json` per OQ-5 (expected
      unchanged — human-role-only; record the reason); confirm `agent-stream-event.schema.json` and
      `execution-request.schema.json` stay byte-unchanged
- [x] Record the v3 schema revision in the Tier-1 policy specification's revision history

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (R-1…R-6)
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing SPEC-074
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
- [x] confirm no caller threads a non-`None` agent-role, the canonical bundle is byte-unchanged
      (OQ-4), every deployed evaluation is byte-identical, and no contract field beyond the additive
      v3 `policy-rule.schema.json` revision changed (phase-3 inertness)
