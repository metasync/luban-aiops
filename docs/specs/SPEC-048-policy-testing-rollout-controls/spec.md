# SPEC-048: Policy Testing and Rollout Controls

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-01
- approved: 2026-09-01
- delivered: 2026-09-02
- release slice: R5 — Hardening and External Consumption (tenth R5
  slice, target v0.30.0)
- related ADRs: none (lineage: promotes the R5 "better policy
  testing and rollout controls" deliverable — integration point
  `policy repo <-> CI/CD` — from the 2026-09-01 spike memo
  `docs/workspace/policy-rollout-controls-spike.md` under the
  memo-first rule; extends SPEC-004 deny-by-default enforcement,
  SPEC-030 require-approval semantics, SPEC-019 policy transparency)

## Summary

The policy engine cluster is the platform's most live-validated
surface, but the change workflow around the bundle is bare: an edit
to the canonical bundle reaches both running gatekeepers through one
`make sync-policy` + deploy with no rehearsal step, no impact
report, no regression guard on granted access, and no way for an
operator to verify which bundle a running gateway actually enforces.
The spike memo verified the gaps: one canonical bundle copied into
four locations, schema + duplicate-id validation only (no scenario
testing), a `version` field that is parsed and surfaced but never
bumped and carries no content hash, path-keyed bundle caching with
no hot reload, 17 bundle edits since inception, and no bundle
lifecycle audit.

This slice closes the R5 deliverable with four repo-native,
CI-runnable controls: a content-hash provenance field on the live
transparency and readiness surfaces, a scenario-expectation harness
pinned into `make verify`, a review-time impact report
(`make policy-diff`), and a documented rollout runbook. It adds
**no new policy actions, no new audit event types, and no bundle
schema changes**; evaluation semantics are untouched — the slice
tests, fingerprints, and documents the existing enforcement, it does
not extend it.

## Requirements

### R-1: Bundle provenance on the live surfaces

Both policy engines expose a content fingerprint of the bundle they
actually enforce:

- `bundle_metadata()` in each engine gains the loaded bundle's
  SHA-256 content hash (hex digest of the exact loaded text) beside
  the existing `version` and `source` fields. The hash is computed
  at load time — never authored in the bundle — and the bundle YAML
  schema is unchanged.
- Platform-gateway's `GET /api/v1/policy/matrix` payload carries the
  provenance block (version, source, hash) under its existing
  `policy:read` gate; both gateways' readiness/health surfaces carry
  the same block so a deploy can be confirmed from outside the pod.
- The bundle header documents the version-bump discipline: bump
  `version` on every rule change; enforcement is review discipline
  (Git history is the authority — no cross-commit monotonicity
  machinery).

### R-2: Scenario-expectation harness in `make verify`

No rule edit may silently flip an operator-visible grant:

- A curated scenario table (`policy-scenarios.yaml`, beside the
  canonical bundle in `shared/shared-contracts/policies/`) names the
  expected outcome for sentinel (role, action) pairs: **every grant
  in the canonical bundle** (each rule's roles × actions covered by
  at least one expectation) **plus the deliberate denials** —
  auditor gets nothing, observer denied the mutating / documents /
  skill-draft / approvals surfaces, developer excluded from tier_2
  decision-making, and the deny-by-default floor for ungranted
  pairs.
- A new script (`shared/shared-contracts/scripts/validate_policy_scenarios.py`)
  evaluates the canonical bundle against the table using the exact
  engine semantics — it imports the platform-gateway engine for the
  API vocabulary and the tool-gateway engine for the tool
  vocabulary (the engines are the contract; no re-implementation),
  with one table section per engine honoring the deliberate
  non-parity.
- Wired into `make verify` beside `validate-policy`: a rule edit
  that flips an expectation fails the gate until the author edits
  the expectation in the same commit, making the intent change
  explicit and reviewable. This is the policy analog of the portal's
  vitest vocabulary drift guard (SPEC-046).

### R-3: `policy-diff` impact report

Reviewers see what a candidate bundle changes before merge:

- `make policy-diff CANDIDATE=<path>` compares the canonical bundle
  against a candidate file and reports every per-(role, action)
  outcome transition across both vocabularies (allow→deny,
  allow→require_approval, new grant, removed grant, tier changes),
  with unchanged pairs summarized by count.
- The report runs on the same evaluation path as the R-2 harness —
  one shared implementation, no second evaluator.
- Missing candidate path or an unparseable candidate is a hard error
  (the `PolicyLoadError` posture); the canonical bundle is never
  modified by the tool.

### R-4: Rollout runbook

- `docs/guides/configuration-reference.md` gains the policy rollout
  runbook: edit → `make sync-policy` → `make verify` (schema +
  scenario guard) → `make policy-diff` review → commit → deploy →
  confirm the provenance hash on the matrix/readiness surfaces.
- The runbook records the restart posture explicitly: bundles are
  cached keyed on the configured path, so a changed ConfigMap takes
  effect on pod restart — hot reload is deliberately absent.

### R-5: Copy-parity coverage extended to the overlay

The existing contract test binding packaged ≡ canonical copies is
extended to the overlay copy
(`shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`), so
manual overlay drift fails `make verify` exactly like packaged drift.

### R-6: Living-state docs and release train

- CHANGELOG 0.30.0 entry + release note + release-notes index;
  version lockstep; `make verify` green before and after
  `make build`; live check on the canonical deployment (provenance
  hash visible on the matrix surface and matching the deployed
  bundle file, scenario guard demonstrably failing on a deliberate
  local flip, `policy-diff` output on a sample candidate,
  operator/observer matrix regression).

## Design Decisions

Promoted from `docs/workspace/policy-rollout-controls-spike.md`
(Option B) on 2026-09-01 operator sign-off; the memo's five open
questions are resolved here:

- **Q-1: Scenario table granularity.** **Resolved: curated but
  complete on grants.** Every rule's grant is covered by at least
  one expectation plus the named denials — the table states intent
  rather than restating the bundle cell-for-cell, keeping the
  authoring surface small while no grant can flip silently.
- **Q-2: Where the harness evaluates.** **Resolved: import the
  engine modules.** Re-implementing evaluation in the script would
  create a second evaluator that can drift from enforcement; the
  engines are the contract, and the shared-contracts script already
  runs under `uv` in a product context (`validate-policy` runs in
  tool-gateway's environment today).
- **Q-3: Hash exposure scope.** **Resolved: matrix + readiness
  first.** Those are the operator live-check-visible surfaces; a
  portal Settings rendering is parked behind the first operator ask.
- **Q-4: Version bump enforcement.** **Resolved: documented
  discipline.** A verify-time Git comparison adds machinery for a
  review-discipline problem; revisit on the first observed drift.
- **Q-5: Overlay drift.** **Resolved: parity test extended to the
  overlay copy** — the same byte-identical posture as the packaged
  copies, since `make sync-policy` already treats it as a managed
  target.
- **Q-6: Version target.** **Resolved: v0.30.0 (minor).** New make
  targets and additive response fields are additive platform
  capability; no breaking surface.

## Invariants preserved

- No new policy actions, no new audit event types; the bundle YAML
  schema and both engines' evaluation semantics (deny-by-default,
  deny > require_approval > allow, priority within outcome class,
  disabled-skip) are untouched.
- The `policy:read` gate on the matrix route is unchanged; the
  provenance block adds fields to an already-gated response.
- Rollout stays ConfigMap + restart: no hot reload, no reload
  endpoint, no in-flight bundle swap — the fail-fast
  `PolicyLoadError` posture survives untouched.
- Bundle-change auditability rides Git history plus the live
  provenance hash; no bundle-lifecycle audit event in this slice.

## Impact

- `products/platform-gateway` — provenance hash in `bundle_metadata`,
  matrix payload + readiness surfaces + tests.
- `products/tool-gateway` — provenance hash + readiness parity + tests.
- `shared/shared-contracts` — `policy-scenarios.yaml`,
  `validate_policy_scenarios.py`, parity-test extension.
- Root `Makefile` — `policy-diff` target; scenario guard wired into
  `verify`.
- `docs/guides/configuration-reference.md` — rollout runbook.
- contracts touched: none changed — `policy-rule.schema.json` and
  `policy-decision.schema.json` keep their shapes.

## Parked / promotion triggers

- **Staged promotion (staging vs production bundles)** — parked per
  the spike: one overlay, one cluster, one operator cohort makes
  staging buy nothing; promote with the policy-center service.
  2026-09-01 operator adjudication: dev/qa/prd environments are
  planned, and policy changes must pass through all of them before
  finalizing in production — but the follow-on slice should be
  **deployment promotion of identical content** (the canonical
  bundle rides the normal deploy pipeline; promotion is confirmed
  by the provenance hash chain across environments), not divergent
  per-environment bundles with a promotion flag. Environment-
  specific differences, if any, are Kustomize overlay patches on
  the canonical bundle, the runtime-profiles pattern. Adjudicated
  against keeping this slice pure Option B; the promotion slice
  lands with the qa/prd overlays.
- **Hot reload / reload endpoint** — parked; conflicts with the
  fail-fast restart posture; revisit only with the policy-center.
- **Bundle-lifecycle audit event** (`policy_bundle_loaded` or
  similar) — parked; promote on the first governance ask for
  audited bundle lifecycle, with its own event-type decision.
- **Portal rendering of the provenance block** — parked behind Q-3;
  promote on the first operator ask.
- **Version monotonicity enforcement** — parked behind Q-4; promote
  on the first observed version drift.

## Changelog

- 2026-09-01: promoted from the spike memo (Option B) on operator
  sign-off and created as `draft` with Q-1…Q-6 resolved; pending
  operator approval of the spec itself.
- 2026-09-01: scope adjudication — the operator confirmed planned
  dev/qa/prd environments with policy changes promoted through all
  of them, but chose to keep this slice pure Option B; environment
  promotion becomes a follow-on slice in the deployment-promotion
  shape (same content, hash-chain verification), recorded in Parked.
- 2026-09-01: operator approved the draft (`draft` → `approved`)
  with no requirement changes; delivery proceeds under the house
  train as v0.30.0.
- 2026-09-02: delivered as v0.30.0 (`approved` → `delivered`) —
  all six workstreams landed per plan.md: provenance hash on both
  engines' matrix/readiness surfaces, the scenario harness pinned
  into `make verify` (131 api / 19 tools expectations, full grant
  coverage enforced), `make policy-diff` on the shared evaluation
  path, the rollout runbook in the configuration reference, and
  overlay copy-parity; live check confirmed the readiness hashes
  match the canonical file byte-for-byte on both gateways and the
  matrix surface carries the fingerprint under the unchanged
  `policy:read` gate.
