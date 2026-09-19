# SPEC-061 Tasks: Retire `browser-check-target`, `InventoryHealth`, and the orphaned credential sets

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Retire the `InventoryHealth` runbook and its skills-hub wiring

- [x] Delete `shared/platform-ops/skills/platform-runbooks/web-checks/InventoryHealth.md` and the empty `web-checks/` dir
- [x] Drop the `web-checks-InventoryHealth.md=…` entry from `dev-k8s/base/kustomization.yaml`
- [x] Drop the matching `items` key/path pair from `dev-k8s/base/skills-hub/skills-hub-deployment.yaml`
- [x] Repoint `platform-runbooks/README.md` step 3 web-check guidance at `samples/acme-admin/` (OQ-3)

## R-2: Retire the `browser-check-target` static app from `browser-dev`

- [x] Delete `browser-check-target-{deployment,service,pages}.yaml`
- [x] Drop the three from `browser-dev/kustomization.yaml` `resources` (keep `browser-sidecar-network-policy.yaml`); rewrite the header comment
- [x] Remove `http://browser-check-target:8080` from `browser.env`'s `GATEWAY_BROWSER_ALLOW_ORIGINS`; rewrite the allowlist comment

## R-3: Retire `browser-check-demo.sh` and its references

- [x] Delete `shared/platform-ops/e2e/browser-check-demo.sh`
- [x] Confirm the `make e2e` list (Makefile:215) is unchanged — five scripts (`skills-demo`, `incident-demo`, `mutating-demo`, `http-check-demo`, `acme-admin/demo-suite.sh`); `browser-check-demo.sh` was never in it
- [x] Rewrite the `dev-k8s/README.md` "Browser Web-Check Posture" section (drop the target + script; point at `demo-suite.sh`)
- [x] Rewrite the `runtime-profiles/README.md` browser-dev paragraph (drop the `browser-check-target` web app)

## R-4: Drop the orphaned `browser-check-target` and `admin-portal` credential sets

- [x] Reduce `sync-browser-credentials.sh` dev-default to one set (`acme-admin`); remove the two blocks + `PASSWORD`/`ADMIN_PASSWORD`
- [x] Rewrite the "three credential sets" comment and the header "sample target apps" phrasing
- [x] `sh -n shared/platform-ops/gitops/sync-browser-credentials.sh` — syntax clean

## R-5: Repoint product references off the retired origin string

- [x] Replace `browser-check-target` → `acme-admin` in the five `products/agent-platform/tests/` fixtures (OQ-2)
- [x] Refresh the `prose_redaction.py:243` comment example → `tool-gateway`
- [x] Confirm no product `src/` logic changed (comment only)

## R-6: Documentation coherence and the recorded SPEC-060 decision reversal

- [x] Rewrite `samples/README.md`'s "`browser-check-target` still ships" paragraph → retired by SPEC-061
- [x] Append a forward-pointing changelog note to `SPEC-060/spec.md` recording the reversal
- [x] Add the `CHANGELOG.md` `Unreleased` (v0.39.0) SPEC-061 entry

## Verification

- [x] `make verify` green — `overlays` renders the reduced `browser-dev`/`dev-k8s` (allowlist exactly `http://acme-admin:8080`, zero `browser-check-target`/`InventoryHealth` keys); `validate-version` (0.38.0 lockstep), `validate-secret-vocabulary`, `validate-policy` (18 rules), `validate-policy-scenarios` (137 api + 19 tools) all pass
- [x] `make test` green — 8/8 product suites, 2681 passed / 0 failed (agent-platform 1317 unchanged in count)
- [x] Repo grep for `browser-check-target`, `InventoryHealth`, `browser-check-demo` clean outside historical records (CHANGELOG, release notes, SPEC-049/050/058/059/060/061 docs, the self-contained skills-hub ingestion fixture, and the gitignored `.workspaces/` scratch)
- [x] Repo grep for `admin-portal` clean outside the generic unit-test/`skill-format.md` string + historical records

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified — R-1..R-6 acceptance criteria are all static and confirmed (rendered-overlay allowlist, deleted files absent, `sh -n` clean, `make test`/`overlays` green, grep clean, living docs corrected)
- [x] live dev-cluster `make deploy` + `samples/acme-admin/demo-suite.sh` pass on the reduced posture (ADR-0008) — **passed 2026-09-19** on the orbstack `dev-luban-aiops` cluster: `make deploy` applied the reduced overlay (orphaned `browser-check-target` Deployment/Service/pages ConfigMap pruned; allowlist converged to the one origin `http://acme-admin:8080`; `tool-gateway-browser-credentials` regenerated with exactly one set `acme-admin`; `skills-platform-runbooks` carries only the five `guides-*` keys), `make deploy-sample-app` passed all nine assertions (incl. the credential cross-check), and `RUN_CHAT_LEG=true demo-suite.sh` passed all four ladder demos + both chat legs (138 ok / 0 failures) — the 0/0/1/1 card ladder holds through the deepseek agent on the reduced posture
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] roadmap row in `docs/agentic-aiops-platform/delivery-roadmap.md` updated
- [x] spec status set to `delivered` — 2026-09-19 (ships in the v0.39.0 release train; no `VERSION` bump for a GitOps/config-reduction + test-fixture slice)
