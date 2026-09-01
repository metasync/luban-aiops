# SPEC-048: Policy Testing and Rollout Controls (v0.30.0)

**Date:** 2026-09-02
**Slice:** R5 — Hardening and External Consumption (tenth R5 slice)
**Spec:** `docs/specs/SPEC-048-policy-testing-rollout-controls/`

## What shipped

The policy bundle change workflow was bare: an edit to the canonical
bundle reached both running gatekeepers through one `make sync-policy`
+ deploy with no rehearsal step, no impact report, no regression guard
on granted access, and no way to verify which bundle a running gateway
actually enforces. SPEC-048 adds four repo-native controls around the
existing engines — none of which touches evaluation semantics:

1. **Bundle provenance (R-1).** Both policy engines compute a SHA-256
   fingerprint of the exact loaded bundle text at load time (computed,
   never authored). platform-gateway surfaces it on the policy matrix
   response (unchanged `policy:read` gate) and `/health/ready`;
   tool-gateway on `/health/ready`. A deploy can be confirmed against
   `shasum -a 256 shared/shared-contracts/policies/policy-default.yaml`
   without shelling into the pod. The canonical bundle header now
   documents the version-bump discipline (bump `version` on every rule
   change; review discipline, Git history as the authority — no
   monotonicity machinery).
2. **Scenario-expectation harness (R-2).** `policy-scenarios.yaml`
   pins per-(role, action) outcome expectations in two sections
   honoring the deliberate engine non-parity (131 api expectations
   over the 21-action vocabulary incl. the `require_approval` tier
   pins; 19 tools expectations where require_approval rules are
   skipped at load per SPEC-030 R-2), plus named denials (auditor
   holds nothing but `audit:read`, observer denied every
   mutating/authoring/governance surface, developer excluded from
   tier_2 decision-making) and the deny-by-default floor.
   `make validate-policy-scenarios` — part of `make verify` — imports
   the real engines (never a re-implementation) and mechanically
   enforces full grant coverage: any new grant without a recorded
   expectation fails the gate until the author records the intent in
   the same commit.
3. **`policy-diff` impact report (R-3).** `make policy-diff
   CANDIDATE=<bundle>` enumerates every per-(role, action) outcome
   transition between the canonical bundle and a candidate — new
   grants, removed grants, allow↔deny, approval-tier changes — for
   both engines, with unchanged pairs count-summarized and both
   bundles' provenance hashes in the header. It shares the harness
   evaluator; a missing or unparseable candidate is a hard error
   (the `PolicyLoadError` posture). Review-time tooling: exit 0 with
   the report, canonical bundle never modified.
4. **Rollout runbook + overlay parity (R-4, R-5).** The
   configuration reference gained the full rollout sequence (edit →
   `make sync-policy` → `make verify` → `make policy-diff` → commit
   → deploy → confirm the provenance hash) with the explicit
   ConfigMap + pod-restart posture (path-keyed caching, no hot
   reload), and the copy-parity contract tests now cover the GitOps
   overlay copy (`dev-k8s/base/shared/policy.yaml`) under the same
   byte-identical posture as the packaged copies.

No new policy actions, no new audit event types, no bundle schema or
evaluation-semantics changes, no new routes, no new env knobs.

## Validation

- `make verify` green before **and** after `make build` at 0.30.0:
  all product suites, overlays, schema check, scenario guard
  (131 api / 19 tools, full grant coverage), and version lockstep.
- Harness self-tests pinned in both products' suites: a deliberately
  flipped grant exits non-zero, the identical bundle exits zero.
- Diff self-tests cover every transition category plus the hard-error
  paths; the removed-grant fixture demonstrates the honest non-parity
  (api engine unchanged behind the require_approval rule, tools
  engine `allow → deny`).
- Live check on the canonical deployment: both gateways'
  `/health/ready` carry the fingerprint matching the canonical file
  byte-for-byte (`2d8c435b…`), the matrix surface carries it under
  the unchanged gate for operator and observer, auditor stays 403,
  and the operator matrix cells regress clean.

## Parked

Staged promotion, hot reload, policy-center, change windows, and
bundle-lifecycle audit events remain the policy-center-shaped
remainder. The 2026-09-01 environment-promotion discussion was
adjudicated and parked: dev/qa/prd policy promotion rides a follow-on
deployment-promotion slice (same content, hash-chain verification).
