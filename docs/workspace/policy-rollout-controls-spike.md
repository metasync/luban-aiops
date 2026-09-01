# Spike: Policy Testing and Rollout Controls (R5 slice 10, SPEC-048 candidate)

Status: spike complete — recommended shape below; promotion to SPEC-048 draft pending operator sign-off
Date: 2026-09-01
Roadmap home: delivery-roadmap R5 "What It Delivers" — "better policy testing and rollout controls" (integration point: `policy repo <-> CI/CD`); the last untouched R5 governance deliverable
Verified against: policy engine, bundle tooling, and GitOps posture at 0.29.3 (SPEC-004/030/019 as delivered)

## 1. Question

The policy engine cluster is the platform's most live-validated surface:
deny-by-default evaluation (SPEC-004), three outcomes with approval tiers
(SPEC-030), and a transparency matrix (SPEC-019) have all survived
repeated live approval-test campaigns. But the *change workflow* around the
bundle is still bare: an edit to the canonical bundle reaches both running
gatekeepers through one `make sync-policy` + deploy with no rehearsal step,
no impact report, no regression guard on granted access, and no way for an
operator to verify which bundle a running gateway actually enforces. R5
promises "better policy testing and rollout controls" with the integration
point `policy repo <-> CI/CD`. What is the smallest decision-complete slice
that makes policy changes testable, reviewable, and verifiable in flight —
without building the policy-center service, staged promotion, or hot reload?

## 2. Findings — verified current state

- **Two evaluation engines, deliberately non-parity.** platform-gateway
  (`services/policy_engine.py`) evaluates the 21-action API vocabulary;
  tool-gateway evaluates its tool-invocation vocabulary (`tools:*` on the
  delegated/confirmer identity). Same semantics in both: deny-by-default,
  explicit deny > require_approval > allow, priority within an outcome
  class, disabled rules skipped, `PolicyLoadError` fail-fast on load.
- **One canonical bundle, four copies.** `shared/shared-contracts/policies/
  policy-default.yaml` is copied by `make sync-policy` into both packaged
  copies and `dev-k8s/base/shared/policy.yaml`; a contract test binds
  packaged ≡ canonical. Overlay copies can drift manually.
- **Validation exists; testing does not.** `make validate-policy` (wired
  into `make verify`) schema-validates the canonical bundle and detects
  duplicate rule ids. There is no scenario/expectation harness: nothing
  fails when a rule edit silently flips a grant. No `dry_run`, `what-if`,
  or `simulate` path exists anywhere in either gateway.
- **The bundle already carries a version, half-used.** `version: 1` is
  parsed and exposed by `bundle_metadata()` (version + configured vs
  packaged-default source) and rendered on the SPEC-019 transparency
  surface. It is not bumped by convention, not verified against Git, and
  carries no content hash — two different bundles can both say `version: 1`.
- **Rollout is ConfigMap + restart, invisible in flight.** Both gateways
  mount the `platform-policy` ConfigMap at `/etc/luban/policy/policy.yaml`
  and cache the parsed bundle keyed on the path — a changed ConfigMap is
  never re-read, so rollout means pod restart. That posture is fine (and
  stays), but a running gateway exposes no content fingerprint, so after a
  deploy nobody can confirm the enforced bundle is the intended one short
  of shelling into the pod.
- **Policy changes are a frequent operation, not a rare event.** The
  canonical bundle has been edited 17 times since inception (every SPEC
  adding an action touched it); the recent five commits alone cover
  SPEC-030/031/039/044/045.
- **No audit of bundle changes.** The audit vocabulary has per-request
  `policy_decision` events but no bundle-lifecycle event; the change
  history lives only in Git.

## 3. Options weighed

| Option | Shape | Cost | Verdict |
|---|---|---|---|
| A. Provenance only | Bundle content hash beside the existing version on `bundle_metadata()`/matrix/health; documented version-bump discipline | Small | Honest but passive: drift becomes visible, flips stay unguarded |
| B. Provenance + testing + impact report | A plus: a scenario-expectation harness pinned into `make verify` (fails on unintended grant/deny flips), and a bundle-diff report that enumerates per (role, action) outcome changes between two bundles for reviewers | Medium | **Recommended** — closes "testing" and "rollout controls" with repo-native, CI-runnable tooling; reuses every delivered substrate |
| C. B + staged promotion and hot reload | Separate staging/production bundles, promotion flag, reload endpoint on the gatekeepers | Large | Deferred — one overlay, one cluster, one operator cohort: staging buys nothing yet; reload conflicts with the fail-fast restart posture. This is policy-center-shaped remainder |

## 4. Recommended shape (SPEC-048 candidate)

### 4.1 Bundle provenance (contracts + engines, additive)

- `bundle_metadata()` gains the loaded bundle's SHA-256 content hash
  beside the existing `version`/`source`; the matrix route and both
  gateways' readiness surfaces carry it, so a live check can confirm the
  enforced bundle matches the intended commit. Bundle schema unchanged —
  the hash is computed, not authored.
- Version-bump discipline documented in the bundle header and the
  configuration reference: bump `version` on every rule change; review
  discipline enforces it (no cross-commit monotonicity machinery — Git
  history is the authority).

### 4.2 Policy testing: scenario-expectation guard (CI-runnable)

- A curated scenario table (YAML, beside the canonical bundle) naming the
  expected outcome for sentinel (role, action) pairs: every grant in the
  canonical bundle plus deliberate denials (auditor gets nothing,
  observer denied mutating/documents/skill-draft surfaces, developer
  excluded from approval decisions). A new script in
  `shared/shared-contracts/scripts/` evaluates the canonical bundle
  against the table with the exact engine semantics and fails on any
  mismatch; wired into `make verify` beside `validate-policy`.
- Effect: no rule edit can silently flip an operator-visible grant —
  the author must edit the expectation in the same commit, making the
  intent change explicit and reviewable. This is the policy analog of the
  portal's vitest vocabulary drift guard (SPEC-046).
- The harness runs on both engines' vocabularies in one table (sections
  per engine), honoring the deliberate non-parity.

### 4.3 Rollout controls: impact report (review-time tooling)

- A `make policy-diff CANDIDATE=<path>` target comparing the canonical
  bundle against a candidate file, emitting per (role, action) outcome
  transitions (allow→deny, allow→require_approval, new grant, removed
  grant) across both vocabularies. Pure evaluation, no gateway import
  beyond the engine module — reviewers run it before merge; the same code
  powers the scenario harness.
- The rollout runbook lands in `docs/guides/configuration-reference.md`:
  edit → sync-policy → verify (validate + scenarios) → policy-diff review
  → commit → deploy → confirm hash on the matrix surface.

### 4.4 Deliberately out of scope

Staged promotion, hot reload/reload endpoints, the policy-center service,
change windows, two-person approval of policy edits (approval extensions
stay parked on the exploration backlog behind their recorded trigger), and
a new audit event type — bundle-change auditability rides Git history plus
the live provenance hash; if operators ask for audited bundle lifecycle,
that is a follow-on slice with its own event-type decision.

## 5. Open questions for the spec phase

1. **Scenario table granularity**: full 21-action × role matrix vs curated
   sentinel set. Leaning curated-but-complete-on-grants (every rule's
   grant covered, plus the named denials) so the table states intent
   instead of restating the bundle.
2. **Where the harness evaluates**: import the engine modules from both
   products (coupling) vs re-implement evaluation in the script (drift
   risk). Leaning engine import from platform-gateway for API actions and
   tool-gateway for tool actions — the engines are the contract.
3. **Hash exposure scope**: matrix + readiness only, or also the portal
   Settings/Platform surface. Leaning matrix + readiness first (operator
   live-check visible), portal later.
4. **Version bump enforcement**: documented discipline vs a verify-time
   check comparing against Git. Leaning documented discipline; revisit on
   the first observed drift.
5. **Overlay drift**: `sync-policy` keeps the four copies byte-identical,
   but manual overlay edits remain possible. Decide whether the contract
   test extends to the overlay copy (leaning yes — same parity-test
   pattern as the packaged copies).

## 6. Recommendation

Promote to **SPEC-048: Policy Testing and Rollout Controls** as R5 slice
10 (0.30.0 train). Scope: bundle provenance hash on the transparency and
readiness surfaces, the scenario-expectation guard in `make verify`, the
`policy-diff` impact report, and the documented rollout runbook. Explicitly
out of scope: staged promotion, hot reload, policy-center, change windows,
and new audit event types — those remain the policy-center-shaped R5
remainder, and this slice's contract must stay compatible with them.
