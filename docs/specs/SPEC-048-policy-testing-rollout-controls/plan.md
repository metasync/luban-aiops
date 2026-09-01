# SPEC-048 Implementation Plan

## Approach

Four repo-native controls around the existing policy engines, none of
which touches evaluation semantics: a SHA-256 content-hash provenance
field on both engines' metadata/health surfaces (R-1), a
scenario-expectation harness pinned into `make verify` (R-2), a
`make policy-diff` review-time impact report sharing the harness's
evaluator (R-3), the rollout runbook in the configuration reference
(R-4), and copy-parity coverage extended to the overlay bundle (R-5).
The harness and diff both import the real engine modules — no second
evaluator. No new policy actions, no new audit event types, no bundle
schema changes, no routes added; the matrix payload gains one field on
an already-gated response. Version lockstep 0.29.3 → 0.30.0.

## Workstreams

### W-1: Bundle provenance hash in both engines (R-1)

- `platform-gateway/services/policy_engine.py`: `load_bundle` keeps
  the exact loaded text reachable for hashing (module global
  `_bundle_hash` computed from the same string `_parse_rules`
  consumed — configured path via `read_text`, packaged default via
  `_packaged_bundle_text()`); `bundle_metadata` gains `sha256` beside
  `version`/`source`. The hash is computed at load time, never
  authored in the bundle; the path-keyed cache posture is unchanged.
- `tool-gateway/services/policy_engine.py`: the same hash capture on
  its `load_bundle` path; a `bundle_metadata()`-equivalent (or the
  existing health builder in `services/gateway_service.py`) exposes
  the hash on the health/readiness surface beside the existing
  `policy_rules` count.
- `api/routes/policy.py`: the matrix route payload carries the hash —
  it rides the existing `bundle_metadata` embed, so no gate change
  (`policy:read` stays) and no new route.
- Bundle header comment in the canonical YAML documents the
  version-bump discipline (bump `version` on every rule change;
  review discipline, Git history as authority — no monotonicity
  machinery).
- Tests: hash stability (same bytes → same hash; one-byte edit →
  different hash), configured-path vs packaged-default both carry it,
  matrix payload shape assertion gains `sha256`, tool-gateway health
  carries it; the SPEC-019 transparency tests extend rather than
  rewrite.

### W-2: Scenario-expectation harness in `make verify` (R-2)

- `shared/shared-contracts/policies/policy-scenarios.yaml`: one table
  with two sections (`api` for the platform-gateway 21-action
  vocabulary, `tools` for the tool-gateway vocabulary, honoring the
  deliberate non-parity). Curated but complete on grants: every
  canonical rule's roles × actions covered by at least one
  expectation, plus the named denials — auditor gets nothing,
  observer denied mutating/documents/skill-draft/approvals surfaces,
  developer excluded from tier_2 decision-making, and the
  deny-by-default floor for ungranted pairs.
- `shared/shared-contracts/scripts/validate_policy_scenarios.py`:
  loads the canonical bundle, imports the product engine (Q-2: the
  engines are the contract — no re-implementation), evaluates each
  scenario, fails non-zero on any mismatch with a per-scenario
  diff line. Stdlib-only besides the engine import and PyYAML
  (already a product dependency). One `--engine {api|tools}` selector
  so each product's frozen uv env runs only its section.
- Root `Makefile`: `validate-policy-scenarios` target mirroring the
  `validate-policy` pattern — run once under `products/platform-gateway`
  (`--engine api`) and once under `products/tool-gateway`
  (`--engine tools`); wired into `verify` beside `validate-policy`.
- Tests: the harness is self-testing via a deliberately-mutated
  fixture bundle in the script's test path (flip a grant → non-zero
  exit; identical bundle → zero).

### W-3: `policy-diff` impact report (R-3)

- `shared/shared-contracts/scripts/policy_diff.py`: compares the
  canonical bundle against `CANDIDATE=<path>`, enumerating every
  per-(role, action) outcome transition across both vocabularies
  (allow→deny, allow→require_approval, approval-tier changes, new
  grant, removed grant) with unchanged pairs summarized by count.
  Shares the exact evaluation path of the W-2 harness — one
  evaluator, two entry points. Missing or unparseable candidate is a
  hard error (the `PolicyLoadError` posture); identical content
  exits zero with a "no transitions" report. The canonical bundle is
  never modified.
- Root `Makefile`: `policy-diff` target (`CANDIDATE` mandatory,
  error with usage on absence) running under both product envs the
  same way as W-2.
- Tests: transition detection for each category against fixture
  pairs, hard-error paths (missing file, malformed YAML), no-op
  identical candidate.

### W-4: Overlay copy-parity extension (R-5)

- The existing contract assertions in
  `products/platform-gateway/tests/test_policy_engine.py` and
  `products/tool-gateway/tests/test_policy_engine.py` (packaged ≡
  canonical) gain the overlay copy
  `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` under
  the same byte-identical posture, so manual overlay drift fails
  `make verify` exactly like packaged drift.

### W-5: Rollout runbook (R-4)

- `docs/guides/configuration-reference.md`: the policy rollout
  runbook section — edit → `make sync-policy` → `make verify`
  (schema + scenario guard) → `make policy-diff CANDIDATE=...`
  review → commit → deploy → confirm the provenance hash on the
  matrix/readiness surfaces — plus the explicit restart posture
  (bundles cached keyed on the configured path; a changed ConfigMap
  takes effect on pod restart; hot reload deliberately absent).
- No new env knobs; `authorization-matrix.md` untouched (no new
  actions).

### W-6: House train (R-6 + release)

- Version lockstep 0.29.3 → 0.30.0 (VERSION, pyproject.toml,
  metadata.py, `__init__.py`, uv.lock across products, portal
  wiring); `make verify` green before **and** after `make build`;
  `make deploy`.
- Browser/API live check on the canonical deployment: provenance
  hash visible on the matrix surface and matching the deployed
  bundle file's SHA-256, both gateways' health carry it, the
  scenario guard demonstrably fails on a deliberate local flip
  (then restored), `policy-diff` output on a sample candidate, and
  the operator/observer matrix regression.
- CHANGELOG 0.30.0 + release note + release-notes index; commit →
  scan gate → tag v0.30.0 → push (never combined); final clean
  rebuild + redeploy.

## Sequencing

1. **W-1** first — the hash semantics and surfaces are referenced by
   the runbook and verified in the live check.
2. **W-2** next — the shared evaluator that W-3 builds on.
3. **W-3** after W-2 — reuses the harness's evaluation path.
4. **W-4** independent; lands whenever, before W-6.
5. **W-5** after W-1…W-3 — the runbook documents what now exists.
6. **W-6** last, per the house train.

## Risks

- **Engine import coupling from shared scripts.** The scenario and
  diff scripts import product engine modules, creating a
  shared-contracts → products dependency direction. Mitigation:
  same precedent as `validate_policy.py` (run inside a product's uv
  env); engines are the contract (Q-2) and drift from a
  re-implementation is the worse failure.
- **Harness granularity surprise.** A rule author may hit a scenario
  failure for an edit they consider behavior-neutral (e.g., a
  priority shuffle that doesn't change outcomes). Mitigation: the
  table asserts outcomes for sentinel pairs only, not rule internals;
  the fix is the explicit same-commit expectation edit, which is the
  intended review surface.
- **Hash over mounted text.** The hash covers the exact loaded text,
  so trailing-newline differences between an editor and `cp` change
  it. That is correct behavior (different bytes = different bundle)
  and the runbook says to confirm against the canonical file's hash.
- **policy-diff verbosity on large candidates.** Full-bundle rewrites
  produce long transition lists. Mitigation: unchanged pairs are
  count-summarized; the report is review-time tooling, not a pager.
- **Scope creep toward the policy-center.** Staged promotion, hot
  reload, change windows, and bundle-lifecycle audit events remain
  parked per spec.md (the 2026-09-01 environment-promotion
  adjudication included); this slice's surfaces are the contract the
  follow-on slices build on.
