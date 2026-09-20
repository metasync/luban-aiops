# Skill Composition Runbooks

- Date: 2026-09-20
- Version: v0.40.0
- Specs: [SPEC-057](../../specs/SPEC-057-skill-composition-runbooks/spec.md)

## Summary

This release delivers SPEC-057 — a third, additive skill `kind: composition`:
an ordered `sub_skills[]` list of existing published single-target skills that
reaches the agent as grounded guidance for a multi-target runbook. It is roadmap
row 346's item **(b)**; the **(a)** Chat→Studio spawn bridge and **(c)** assisted
trace-extraction stay deferred to a later Phase 2 spec as authoring ergonomics
that change no gate semantics.

A composition carries **no authority** (ADR-0011). It never mints tokens, unlocks
flows, or auto-approves a gate, and each named sub-skill keeps its own
human-in-the-loop gate through the shipped `FlowContext.identity() ==
(skill_id, origin)` guard plus ADR-0007 re-park-on-rebind — so multi-binding
re-park needed **no new enforcement machinery** and adds no kernel trust state.
Skill Format goes **v2 → v3** additively: a v2 consumer ignores `sub_skills` and
is unaffected. There is **no new policy action, no new audit event type, no
stream-contract change, and no database migration** beyond one idempotent
`ADD COLUMN IF NOT EXISTS sub_skills JSONB` on the skills store; the tool-gateway
deviation guard and both gateways' skill passthrough are untouched.

## Delivered capabilities

- **`kind: composition`** on the shared contract
  (`shared/shared-contracts/schemas/skill.schema.json`, retitled `"Skill (v2)"` →
  `"Skill (v3)"`), carrying an optional top-level `sub_skills[]` array whose items
  are `{ skill_id (required), note (optional ≤ 200 chars) }` with
  `additionalProperties: false`. A composition declares **no** `web_target`,
  **no** `steps`, and **no** `risk_class` of its own.
- **No control flow.** A `sub_skills` item carries no branch, loop, conditional,
  retry, or early-exit key, and a `note` is a string, never interpreted — an
  interpreter would need loops, and a loop defeats `GATEWAY_BROWSER_FLOW_MAX_STEPS`,
  the only bound on an unlocked browser flow. The list is ordered **guidance**, and
  the platform never pre-binds a sub-skill, never issues `web.navigate` on the
  model's behalf, and never enforces the declared order.
- **`SKILLS_COMPOSITION_MAX_SUB_SKILLS`** (default `8`) — the composite-wide cap
  that bounds the inherited per-bound-flow step budget: 8 × 20 = 160 worst-case
  unlocked browser writes per run, each still individually gated, signed, audited
  and receipted. A value below 1 fails fast with a `SettingsError`.
- **Two-layer fail-closed validation.** A pure structural `_validate_composition`
  in ingestion (shared by the `/skills/validate` route and the
  `python -m skills_hub.validate` CLI) rejects a malformed list, a duplicate
  `skill_id`, an over-cap list, a `kind: composition` with no `sub_skills`, a
  composition declaring its own `web_target`/`steps`/`risk_class`, a `note > 200`,
  or any unrecognized sequencing key. A store-consulting `_resolve_compositions`
  pass in `SyncManager.sync_once` then drops a record on an **unresolved**
  sub-skill or a **nested** composition reference (single-target needs no active
  check — a sub-skill's `web_target` is a scalar, so a resolved skill is
  single-target by construction), appending a `Rejection` to the existing
  `skills_synced` rejected count.
  Cross-source compositions are **eventually consistent** — rejected on the cycle
  before a sub-skill's own source syncs, accepted after.
- **Derived, persisted `risk_class`.** A composition's display badge is `write`
  when any resolved sub-skill is `write`, else `read` — computed in the resolution
  pass and stored (reusing the existing top-level field, no new column), so
  `summary()` carries it to the list badge without a per-read computation.
- **Resolved-sub-skill read path.** skills-hub's `get_skill` projects each stored
  `{ skill_id, note }` to a display view adding `resolved_title` and
  `resolved_web_target` looked up from the store (the `search_skills`
  `score`/`excerpt` projection precedent); read-path only, nothing resolved is
  persisted. Both gateways forward the record verbatim through the existing
  SPEC-014 grounded-guidance path.
- **Not a transaction.** On a sub-skill failure the runbook reports which
  sub-skill failed and stops — no rollback or compensation. The completed prefix
  for re-entry derives from `execution_records` signed receipts, swept at **30
  days** (`execution_records.py:31`); outside that window the operator restarts
  from the beginning. No composite-progress store is introduced.
- **Portal read/viewer surface.** A derived **risk** badge column on the Skills
  catalog (`SkillsView`) and an ordered, read-only **Runbook** sub-skill list
  (title · declared target · note) above the body in `SkillContentViewer`. Phase 1
  ships **no** bespoke composition editor: a composition is authored by hand (in a
  development session or directly) and merged to a skill source through Git like
  any other skill, and it reads under the existing `skills:read` with no new
  policy action.

The sample composition demonstrates the mixed-surface gate count:

| Composition | Sub-skills | Surface | Cards |
|---|---|---|---|
| `RecoverAcmeAccount` | `password-reset` | bound browser (write) | 1 flow |
| | `lock-unlock-user` | `http.post` (write) | 1 action |
| | **total on one session** | mixed browser + infra | **2** |

See the [sample README](../../../samples/acme-admin/composition/README.md) and its
[WALKTHROUGH](../../../samples/acme-admin/composition/WALKTHROUGH.md) for the
two-card recovery of a locked-out account, and the
[demo](../../../samples/acme-admin/composition/demo/demo.sh) for the deterministic
and opt-in live legs.

## Validation

- `make verify`: green — **2,738** backend product tests across all eight
  products (agent-platform 1,327; tool-gateway 398; platform-gateway 376;
  skills-hub 229; audit-service 138; incident-service 137; execution-runtime 73;
  identity-broker 60), four kustomize overlay renders, 18 policy rules validated,
  137 API and 19 tool-policy scenarios, version lockstep at 0.40.0, and all three
  secret-vocabulary checks unchanged (`VERIFY_EXIT=0`).
- `make policy-diff` against the deployed gitops bundle: **zero** outcome
  transitions across all **138** (role, action) pairs on both engines against an
  identical bundle hash (`ee1f6c5f…`) — the assertion the "no new policy
  vocabulary" decision leaves behind.
- Portal `npm test`: green (**408** tests / 32 files) with `npm run build`
  (`tsc --noEmit` + vite) clean (`BUILD_EXIT=0`).
- The composition contract, ingestion, resolution, read-path, purity, and viewer
  assertions each map to a named test in the spec's Delivery Gate (ADR-0008):
  `test_contracts.py`, `test_skill_store.py`, `test_ingestion.py`,
  `test_config.py`, `test_sync.py`, `test_routes.py`,
  `test_skill_composition_purity.py`, `test_flow_approvals.py`,
  `SkillContentViewer.test.tsx`, and `SkillsView.test.tsx`.
- The `samples/acme-admin/composition/demo.sh` deterministic legs assert the
  catalog-facing behavior (the composition resolves; a nested reference passes
  structure and is owned by resolution; the cap, an authored `risk_class` and a
  smuggled sequencing key each reject; the derived `risk_class` is `write`; the
  two sub-skill ids are the mounted ids). These ran **green on the deployed dev-k8s
  cluster**: `make build` (all 9 images under one coordinated tag), `make deploy`
  (every luban deployment `1/1 READY` at `RESTARTS=0`, 8 secret bundles re-synced,
  Keycloak realm + portal OIDC client reconciled), `make deploy-sample-app`, and
  `make deploy-samples` (6 sample skills mounted; the composition **resolved in the
  live Postgres `skills` store** at `kind=composition`, derived `risk_class=write`,
  both ordered sub-skill refs persisted), then `make e2e` → `E2E_OK: all demos
  passed`, the composition rung clearing all five legs via `acme-admin/demo-suite.sh`.
  The opt-in `RUN_CHAT_LEG=true` live leg (the **2**-card multi-binding gate count
  on one session) is model-dependent and is not set by the `make e2e` gate, so it
  skipped; that 2-card count is asserted deterministically at the unit level
  (`test_flow_approvals.py` rebind re-park + the mixed browser+infra gate-count test).

## Deploy and live-test notes

```sh
make build
make deploy
make deploy-sample-app
make deploy-samples
```

`make deploy-samples` discovers the composition by its `skill/` directory and
mounts it as `samples/composition-recoveracmeaccount` in the **same** `samples`
source as its two sub-skills, so resolution is deterministic within one sync
cycle. The `browser-dev` runtime profile enables the HTTP connector and
allowlists the sample origin; the chat leg additionally needs the platform-gateway
and identity-service port-forwards named by `make e2e`.

The two cards a composition parks are **correct, not a transaction**: approving
the first does not commit the second, and a `409 NO_OP` from the sample app is a
real state fact, not a demo failure. The declared sub-skill order is guidance the
agent may follow, never a platform-enforced sequence. The sample uses one replica
with `Recreate`, so restarting it resets its in-memory data; do not use it as a
production administration service.
