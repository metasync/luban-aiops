# SPEC-048 Tasks

## R-1: Bundle provenance on the live surfaces (W-1)

- [x] `platform-gateway/services/policy_engine.py`: `load_bundle`
      captures `_bundle_hash` (SHA-256 of the exact loaded text,
      configured path and packaged default); `bundle_metadata` gains
      `sha256` beside `version`/`source`; cache posture unchanged
- [x] `tool-gateway/services/policy_engine.py`: the same hash
      capture; the health/readiness builder exposes it beside the
      existing `policy_rules` count
- [x] `api/routes/policy.py`: the matrix payload carries the hash via
      the existing `bundle_metadata` embed — gate (`policy:read`)
      and route shape unchanged
- [x] Canonical bundle header comment documents the version-bump
      discipline (bump on every rule change; Git history as
      authority); `make sync-policy` after the edit
- [x] Tests: hash stability and sensitivity, both load sources,
      matrix payload shape, tool-gateway health shape; SPEC-019
      transparency tests extended, not rewritten

## R-2: Scenario-expectation harness in `make verify` (W-2)

- [x] `shared/shared-contracts/policies/policy-scenarios.yaml`: two
      sections (`api`, `tools`); every canonical grant covered by at
      least one expectation plus the named denials (auditor nothing,
      observer denied mutating/documents/skill-draft/approvals,
      developer excluded from tier_2 decisions, deny-by-default floor)
- [x] `shared/shared-contracts/scripts/validate_policy_scenarios.py`:
      imports the product engine (`--engine {api|tools}` selector),
      evaluates the canonical bundle against the table, non-zero exit
      with per-scenario diff on mismatch; stdlib + PyYAML only
- [x] Root `Makefile`: `validate-policy-scenarios` target (run under
      both products' uv envs, the `validate-policy` pattern); wired
      into `verify`
- [x] Self-test: mutated fixture bundle → non-zero; identical → zero

## R-3: `policy-diff` impact report (W-3)

- [x] `shared/shared-contracts/scripts/policy_diff.py`: per-(role,
      action) outcome transitions between canonical and `CANDIDATE`
      across both vocabularies, unchanged pairs count-summarized;
      shares the W-2 evaluation path; missing/unparseable candidate
      is a hard error; identical candidate → zero exit, "no
      transitions"; canonical bundle never modified
- [x] Root `Makefile`: `policy-diff` target with mandatory
      `CANDIDATE` (usage error on absence), run under both products'
      uv envs
- [x] Tests: each transition category on fixture pairs, hard-error
      paths, identical no-op

## R-4: Rollout runbook (W-5)

- [x] `docs/guides/configuration-reference.md`: policy rollout
      runbook (edit → sync-policy → verify → policy-diff → commit →
      deploy → confirm hash) and the explicit ConfigMap + restart
      posture; no new env knobs, no authorization-matrix change

## R-5: Copy-parity coverage extended to the overlay (W-4)

- [x] Both products' `test_policy_engine.py` parity assertions gain
      `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`
      under the same byte-identical posture

## R-6: Living-state docs and release train (W-6)

- [x] Version lockstep 0.29.3 → 0.30.0; `make verify` green before
      **and** after `make build`; `make deploy`
- [x] Live check: provenance hash on the matrix surface matches the
      deployed bundle file, both gateways' health carry it, scenario
      guard fails on a deliberate local flip (then restored),
      `policy-diff` on a sample candidate, operator/observer matrix
      regression
- [x] CHANGELOG 0.30.0 + release note + index; commit/scan/tag/push
      per the house train (never combined); final clean rebuild +
      redeploy
