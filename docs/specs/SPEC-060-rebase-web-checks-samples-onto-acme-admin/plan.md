# SPEC-060 Plan: Rebase the `web-checks` Samples onto `acme-admin`

## Approach

A samples-and-docs retarget, not a rewrite: SPEC-059 R-2 made `acme-admin` serve
the same six URL shapes and 28 element ids as `browser-check-target`, so the two
surviving samples move with an origin/credential-set swap plus prose updates, and
`skill-graduation` additionally gains store-verification legs that the static
target could never support. Work is grouped into six stages that mirror the
requirement set: author the trio (this stage), retire the duplicate, migrate the
two samples, update the catalog and wiring, then bookkeeping and verification.
Leaf directory names are preserved throughout so `deploy-samples.sh`'s
leaf-dir slug rule keeps every surviving skill id stable.

## Design Per Requirement

### R-1: Retire the static-mock `password-reset` sample

- affected: `samples/web-checks/password-reset/` (deleted),
  `samples/acme-admin/password-reset/skill/ResetAcmePassword.md` (collision note).
- approach: `git rm -r` the static sample; rewrite `ResetAcmePassword.md`'s
  present-tense collision rationale as a historical note (the id it avoided now
  no longer ships).
- alternatives: keep both reset samples — rejected, the static one is a strictly
  weaker duplicate of a delivered skill.

### R-2: Migrate `adhoc-password-reset` onto `acme-admin`

- affected: `samples/acme-admin/adhoc-password-reset/` (`git mv` from
  `samples/web-checks/`), its `skill/ResetPasswordAdHoc.md`, `demo/demo.sh`,
  `WALKTHROUGH.md`, `README.md`.
- approach: swap origin `browser-check-target` → `acme-admin` and credential set
  `admin-portal` → `acme-admin`; source `../../demo-lib.sh` for
  `reseed_demo`/`app_http_authed`; add a post-approval store-verification leg;
  keep the no-`web_target`/no-`risk_class` unbound trait and the one-card-per-write
  assertion.
- alternatives: rewrite the demo on the acme-admin harness from scratch —
  rejected, the existing deterministic legs stay valid under the R-2 id contract.

### R-3: Migrate and upgrade `skill-graduation` onto `acme-admin`

- affected: `samples/acme-admin/skill-graduation/` (`git mv`), its `demo/demo.sh`
  (1020 lines), `WALKTHROUGH.md`, `README.md`.
- approach: retarget `ADMIN_TARGET`, the credential set in leg 3 and the act-1/act-4
  prompts, the `('Sup3rSecret','admin-portal')` regression guard, the leg-2
  `kubectl exec` deployment, the pasted-target fixture host, and the verification
  URLs; reseed before act 1 and add store-verification legs for both resets.
  Rewrite the walkthrough's "URLs are NOT verification" lesson into "verify
  against real store state".
- alternatives: retarget without the verification upgrade — rejected, the upgrade
  is the entire point of moving to a stateful target.

### R-4: Consolidate the catalog and retire the `web-checks` category

- affected: `samples/README.md`, `samples/acme-admin/README.md`,
  `samples/acme-admin/demo-suite.sh`, `samples/acme-admin/demo-lib.sh`,
  `docs/guides/studio-guide.md` (+ `skills-guide.md` if referenced),
  `samples/acme-admin/password-reset/WALKTHROUGH.md`.
- approach: drop the "Web checks" catalog section and fold the two samples into
  the ACME Admin section; update the expected-id set six → five in
  `demo-suite.sh`; fix the "three shipped samples under `samples/web-checks/`"
  framing in the acme-admin README and demo-lib header; restore the triad
  entry-point framing in the surviving `password-reset` walkthrough.

### R-5: Leave `browser-check-target` and its platform consumers untouched

- affected: nothing (a control, not a change).
- approach: do not touch the `browser-dev` runtime profile, `InventoryHealth`,
  `browser-check-demo.sh`, or `sync-browser-credentials.sh`; assert via repo grep
  that no product/contract/policy/GitOps file changed.

### R-6: Exercised-sample gate and naming clarification

- affected: `samples/acme-admin/README.md` (naming note), this spec (naming note),
  the two migrated demos and `demo-suite.sh` (exercised in verification).
- approach: run the full demo path against a live dev cluster before marking
  delivered; add the one-line `acme` = fictional-company-placeholder note.

## Sequencing And Dependencies

1. Stage 1 — author the trio, index row, roadmap row. Depends on nothing.
2. Stage 2 — retire `web-checks/password-reset`. Depends on Stage 1.
3. Stage 3 — migrate `adhoc-password-reset`. Depends on Stage 2 (sibling refs).
4. Stage 4 — migrate + upgrade `skill-graduation`. Depends on Stage 3 (sibling
   refs and the shared demo-lib).
5. Stage 5 — catalog, suite, and wiring. Depends on Stages 2-4.
6. Stage 6 — bookkeeping and verification. Depends on Stage 5.

## Test Strategy

- unit tests: none added (no product code); the `acme-admin` app suite is
  unaffected and still runs under `make verify`.
- contract tests: none (no contract change).
- integration / overlay validation: `make verify` green (docs link resolution,
  product suites, overlays render unchanged); `make deploy-samples` yields exactly
  five distinct ids; `samples/acme-admin/demo-suite.sh` passes; both migrated
  demos pass their deterministic legs and `RUN_CHAT_LEG=true` chat acts against
  `acme-admin` including store verification; repo grep for `samples/web-checks`,
  `ResetUserPassword`, `resetuserpassword` clean outside historical records.
- ADR-0008 gate: a live dev-cluster pass over both migrated demos before
  `delivered`.

## Rollout And Migration

- deployment or configuration changes required: none. Samples install out-of-band
  via `make deploy-samples`; the `acme-admin` app and origin allowlist already
  ship (SPEC-059).
- backward compatibility notes: one skill id
  (`samples/password-reset-resetuserpassword`) is intentionally removed with the
  retired sample; the two migrated samples keep their ids via preserved leaf
  names.
- rollback approach: `git revert` the slice; `make undeploy-samples` then
  `make deploy-samples` restores the prior ConfigMap. No state migration.
