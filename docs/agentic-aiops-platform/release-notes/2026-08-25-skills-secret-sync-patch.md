# v0.11.1 — Skills Secret-Sync Credential Patch

Date: 2026-08-25
Release type: patch (deployment-script fix and release housekeeping; no
service-code behavior change)

## Summary

v0.11.1 is a follow-up patch to v0.11.0 that ships the fix for the
skills-hub audit-credential wipe discovered during the v0.11.0 release
deploy, plus release housekeeping (version lockstep and dependency
lockfiles refreshed for the patch).

## Change Set

### Fixed

- **Audit credential wiped by skills secret sync**:
  `sync-skills-secrets.sh` rewrites the shared skills-hub
  `runtime-secrets.env` and runs *after* `sync-audit-secrets.sh` in
  `deploy.sh` order, so a plain `make deploy` wiped
  `SKILLS_AUDIT_CLIENT_SECRET` from the cluster Secret and 401'd every
  skills-hub emission until audit sync ran again (caught by live
  verification of the v0.11.0 release deploy). The rewrite now
  preserves the audit line across the file reset, matching the existing
  OTLP-header preservation.

### Changed

- Version lockstep bumped to 0.11.1 (VERSION, pyproject, metadata,
  `__version__`) and per-product `uv.lock` files refreshed.

## Validation

- `make validate-version` green at 0.11.1; `make verify` gate green.
- Live-verified in dev-k8s during the v0.11.0 release deploy: with the
  corrected script, re-running `sync-audit-secrets.sh` →
  `sync-skills-secrets.sh` in order keeps `SKILLS_AUDIT_CLIENT_SECRET`
  present in the skills-hub Secret and pod environment; the restarted
  skills-hub pod shows zero 401s and `audit_emits_total{result="ok"}`
  increasing.
- L3 deep security review at the push gate returned zero findings.

## Upgrade Notes

- No breaking changes; no new knobs. The fix is entirely in
  `shared/platform-ops/gitops/sync-skills-secrets.sh` — re-run the
  secret-sync scripts (or `make deploy`) to converge any cluster that
  lost the key.
