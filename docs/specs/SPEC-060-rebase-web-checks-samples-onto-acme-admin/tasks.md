# SPEC-060 Tasks: Rebase the `web-checks` Samples onto `acme-admin`

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Retire the static-mock `password-reset` sample

- [x] `git rm -r samples/web-checks/password-reset/`
- [x] Rewrite `ResetAcmePassword.md` collision rationale as historical (`samples/acme-admin/password-reset/skill/`)

## R-2: Migrate `adhoc-password-reset` onto `acme-admin`

- [x] `git mv samples/web-checks/adhoc-password-reset samples/acme-admin/adhoc-password-reset`
- [x] Retarget `skill/ResetPasswordAdHoc.md` (origin, credential set, sibling cross-refs); keep no-`web_target`/no-`risk_class`
- [x] Retarget `demo/demo.sh` (origin, credential set, `kubectl exec` deployment, source `../../demo-lib.sh`) and add a post-approval store-verification leg
- [x] Retarget `WALKTHROUGH.md` + `README.md` (origin, credential set, demo paths, sibling refs)

## R-3: Migrate and upgrade `skill-graduation` onto `acme-admin`

- [x] `git mv samples/web-checks/skill-graduation samples/acme-admin/skill-graduation`
- [x] Retarget `demo/demo.sh` (`ADMIN_TARGET`, credential set in leg 3 + act prompts + regression guard, leg-2 `kubectl exec`, fixture host, verification URLs)
- [x] Upgrade `demo/demo.sh`: reseed before act 1, add store-verification legs for both resets
- [x] Rewrite `WALKTHROUGH.md` "URLs are NOT verification" lesson into "verify against real store state"; retarget refs
- [x] Retarget `README.md`

## R-4: Consolidate the catalog and retire the `web-checks` category

- [x] `samples/README.md`: drop "Web checks" section, fold two samples into ACME Admin, rewrite "both targets" paragraph, fix `SAMPLE=` example + collision note
- [x] `samples/acme-admin/README.md`: fix "three shipped samples under `samples/web-checks/`", skill-graduation path, reframe suite
- [x] `samples/acme-admin/demo-suite.sh`: expected-id set six → five, update comments
- [x] `samples/acme-admin/demo-lib.sh`: update header comment
- [x] `docs/guides/studio-guide.md` (+ `skills-guide.md` if referenced): repoint to `samples/acme-admin/skill-graduation/`
- [x] Restore triad entry-point framing in `samples/acme-admin/password-reset/WALKTHROUGH.md`
- [x] Repoint the three ladder walkthroughs' `skill-graduation` cross-links; fix `deploy-samples.sh` help examples and `app/tests/test_packaging.py` ids

## R-5: Leave `browser-check-target` and its platform consumers untouched

- [x] Confirm no change to the `browser-dev` runtime profile, `InventoryHealth`, `browser-check-demo.sh`, `sync-browser-credentials.sh`

## R-6: Exercised-sample gate and naming clarification

- [x] Add the `acme` = fictional-company-placeholder note to `samples/acme-admin/README.md`
- [x] Live dev-cluster pass over both migrated demos (ADR-0008) — **passed 2026-09-19** against the stateful `acme-admin` console (`adhoc-password-reset` + `skill-graduation`, `RUN_CHAT_LEG=true`), both resets verified in the store

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified — live-cluster gate passed 2026-09-19; `make verify` green
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] roadmap backlog row added in `docs/agentic-aiops-platform/delivery-roadmap.md`
- [x] spec status set to `delivered` — 2026-09-19 (ships in the v0.39.0 release train; no `VERSION` bump for a samples-and-docs slice)
