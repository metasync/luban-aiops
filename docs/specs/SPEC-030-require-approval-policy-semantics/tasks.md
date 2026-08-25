# SPEC-030 Tasks: Require-Approval Policy Semantics

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Contract revision

- [ ] `policy-rule.schema.json` v2: `require_approval` outcome + optional `approval` block (`tier` enum tier_1/tier_2 required, `decided_by_roles`, optional `allow_self_approval` with tier defaults) (`shared/shared-contracts/schemas/`)
- [ ] `policy-decision.schema.json` v2: `require_approval` outcome, activated `approval_tier`, optional `approval` block (`shared/shared-contracts/schemas/`)
- [ ] contract tests: v1 bundles validate unchanged; new rules validate; reserved fields stay documented (`shared/shared-contracts/`)

## R-2: Evaluation semantics

- [ ] platform-gateway `evaluate()`: deny > require_approval > allow, priority within approvals, `PolicyDecision.approval` with tier (`products/platform-gateway/src/platform_gateway/services/policy_engine.py`)
- [ ] platform-gateway bundle validation: reject `require_approval` rules outside the bridged action set and `tier_2` + `allow_self_approval: true` with `PolicyLoadError` (same file)
- [ ] platform-gateway engine tests: mixed-match, precedence, priority, disabled-rule, load-validation cases (`products/platform-gateway/tests/test_policy_engine.py`)
- [ ] tool-gateway `evaluate()`: identical semantics; load validation rejects all `require_approval` rules this slice (`products/tool-gateway/src/tool_gateway/services/policy_engine.py`)
- [ ] tool-gateway engine tests mirroring the platform-gateway semantics cases (`products/tool-gateway/tests/`)

## R-3: Tiered enforcement bridge on `chat:confirm`

- [ ] agent-platform: expose the parked call's tool action in the pending-confirmation payload (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`, schemas)
- [ ] platform-gateway confirm route: evaluate parked action, decider-role check, structured 403 on non-deciders (`products/platform-gateway/src/platform_gateway/api/routes/chat.py`)
- [ ] platform-gateway confirm route: `tier_1` accepts session-owner self-confirmation; `tier_2` rejects self-approval (confirmer subject vs session owner subject) with `self_approval` reason (same file)
- [ ] route tests: decider allowed, non-decider 403, tier_1 owner self-confirm allowed, tier_2 self-approval blocked, non-mutating parks unchanged (`products/platform-gateway/tests/`)
- [ ] regression: confirmed mutating call still passes tool-gateway `tools:mutate` admission on the delegated token unchanged (`products/tool-gateway/tests/`)

## R-4: Default bundle posture

- [ ] `policy-default.yaml`: `tier_2` `require_approval` rule on `tools:mutate` (`decided_by_roles: [approver, platform-admin]`) + `tier_1` authoring-pattern comment + synthetic-identity exclusion comment (`shared/shared-contracts/policies/`)
- [ ] `make sync-policy` + `make validate-policy` across packaged and overlay copies
- [ ] `mutating-demo.sh`: two-identity flow (operator requests, approver confirms) + doc header update (`shared/platform-ops/e2e/`)
- [ ] dev-k8s: confirm/provision the `approver`-role test user needed by the demo (resolves spec Q-3)

## R-5: Transparency and audit consistency

- [ ] `policy_matrix.py`: third cell state `requires_approval` with tier and decider roles, additive response shape (`products/platform-gateway/src/platform_gateway/services/policy_matrix.py`)
- [ ] matrix tests incl. caller-scoped rendering of the new state (`products/platform-gateway/tests/test_policy_matrix.py`)
- [ ] portal permissions view: render the third state distinctly (`products/operator-portal/web-ui/app/src/views/control/PermissionsView.tsx`)
- [ ] portal confirmation card: tier badge ("operator confirmation" / "approver required") + read-only mode for non-deciders, with vitest coverage (`products/operator-portal/web-ui/app/src/chat/`)
- [ ] `confirmation_decided` enrichment: `approval_rule_id` + tier + blocked-self-approval outcome at the existing audit tee; audit-event schema details description updated (`products/platform-gateway/`, `shared/shared-contracts/schemas/audit-event.schema.json`)
- [ ] resolve spec Q-1: observer read-only card rendering against SPEC-022 session-scoping code
- [ ] resolve spec Q-2: confirm no external matrix consumer parses boolean-only cells

## R-6: Settings view restored as a read-only Session & Identity panel (add-on)

- [ ] `client.ts`: remember the last generated `x-request-id` with a read accessor (`products/operator-portal/web-ui/app/src/api/client.ts`)
- [ ] new `SettingsView.tsx`: extensible tabbed container; Identity / Session / Platform read-only panes from `AuthContext`, session workspace, version, gateway origin (`products/operator-portal/web-ui/app/src/views/`)
- [ ] wire the view into `App.tsx`, replacing the settings `ViewPlaceholder` (`products/operator-portal/web-ui/app/src/App.tsx`)
- [ ] vitest: signed-in, signed-out, and no-session-selected renders (`products/operator-portal/web-ui/app/src/views/__tests__/`)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
