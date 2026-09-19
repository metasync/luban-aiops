# SPEC-061 Plan: Retire `browser-check-target`, `InventoryHealth`, and the orphaned credential sets

## Approach

A cleanup slice that removes a redundant predecessor rather than adding
capability. SPEC-060 rebased every browser tutorial onto the stateful
`acme-admin` app but deliberately *kept* the static `browser-check-target`
mock shipped for its platform consumers, naming their retirement as the
follow-up decision. This slice makes that decision: retire. The work is a
set of deletions plus the doc/config coherence they obligate — remove the
runbook and its skills-hub wiring, remove the three static-target GitOps
resources and its allowlist origin, remove the manual e2e, drop the two
orphaned dev credential sets, repoint the incidental product references off
the retired origin string, and correct the living docs. Nothing here changes
product behavior, contracts, policy, or audit; the only `src/` touch is a
one-line comment example. Work is grouped into six stages mirroring the
requirement set, then bookkeeping and verification.

## Design Per Requirement

### R-1: Retire the `InventoryHealth` runbook and its skills-hub wiring

- affected: `shared/platform-ops/skills/platform-runbooks/web-checks/InventoryHealth.md`
  (deleted, and the now-empty `web-checks/` dir),
  `shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml` (line 39
  `configMapGenerator` file entry),
  `shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml`
  (lines 110-111 `items` key/path pair),
  `shared/platform-ops/skills/platform-runbooks/README.md` (step 3).
- approach: delete the file and `rmdir` the empty directory; drop the
  `web-checks-InventoryHealth.md=…` generator line and the matching
  `volumeMounts` `items` pair so the ConfigMap and its mount stay in sync;
  rewrite README step 3 to keep the web-check authoring *guidance* (browser
  web-check skills declare `web_target` + `risk_class`) but repoint the
  worked example at `samples/acme-admin/` instead of the deleted file
  (OQ-3 resolution). The self-contained
  `products/skills-hub/tests/test_ingestion.py` fixture that writes its own
  temporary `web/InventoryHealth.md` (fictional `inventory.internal` target) is
  left untouched — it never reads the retired runbook, and renaming it would
  pull skills-hub into a slice scoped to agent-platform test fixtures.
- alternatives: keep the runbook and add a real JSON health endpoint to a
  platform target — rejected, that inverts SPEC-050 R-11's tutorial→platform
  arrow and duplicates `CheckServiceHealth`; the platform runbook library
  keeps its Kubernetes troubleshooting scope.

### R-2: Retire the `browser-check-target` static app from `browser-dev`

- affected: `shared/platform-ops/gitops/runtime-profiles/browser-dev/`
  (`browser-check-target-deployment.yaml`, `browser-check-target-service.yaml`,
  `browser-check-target-pages.yaml` deleted; `kustomization.yaml` resources +
  header comment; `browser.env` allowlist + comment).
- approach: delete the three `browser-check-target-*` files and drop them from
  `kustomization.yaml`'s `resources` (keeping `browser-sidecar-network-policy.yaml`,
  which selects `app: tool-gateway`); remove `http://browser-check-target:8080`
  from `GATEWAY_BROWSER_ALLOW_ORIGINS` leaving `http://acme-admin:8080`; rewrite
  the `kustomization.yaml` header (which calls the target "the only origin") and
  the `browser.env` allowlist comment so the profile reads as the browser
  *posture* profile permitting the one out-of-band sample origin.
- alternatives: leave the allowlist entry dangling — rejected, a two-origin
  allowlist naming a host that no longer resolves is exactly the stale-config
  wart this slice closes; the reduction keeps deny-by-default intact.

### R-3: Retire `browser-check-demo.sh` and its references

- affected: `shared/platform-ops/e2e/browser-check-demo.sh` (deleted),
  `shared/platform-ops/gitops/dev-k8s/README.md` (the "Browser Web-Check
  Posture" section, lines ~663-690),
  `shared/platform-ops/gitops/runtime-profiles/README.md` (lines ~43-56).
- approach: delete the script; confirm the `make e2e` list (Makefile:215) is
  unchanged (the script was never in it); rewrite the two README passages so
  they describe the profile as the browser posture permitting the `acme-admin`
  origin (deployed out-of-band) and point the smoke-test example at the gated
  `samples/acme-admin/demo-suite.sh` rather than the deleted script.
- alternatives: fold the script's disabled/enabled-branch assertions into
  another e2e — rejected, the browser flow gate is already covered against a
  mutating target by `demo-suite.sh` rung 4, which *is* in `make e2e`.

### R-4: Drop the orphaned `browser-check-target` and `admin-portal` credential sets

- affected: `shared/platform-ops/gitops/sync-browser-credentials.sh`
  (dev-default block lines 70-94; header comment lines 29-35).
- approach: reduce the generated dev-default `credential-sets.json` from three
  entries to one (`acme-admin`); remove the `browser-check-target` (`svc-check`)
  and `admin-portal` (`admin`) blocks and the now-unused `PASSWORD` /
  `ADMIN_PASSWORD` generation (keep `ACME_PASSWORD`); rewrite the "three
  credential sets — two for the static sample target" comment and the header's
  "dev sets for the sample target apps" phrasing. The `acme-admin` entry, the
  second `acme-admin-credentials` sink, and the override path are unchanged.
  The illustrative `admin-portal` *string* in skills-hub / agent-platform unit
  fixtures and `skill-format.md` is a generic set name, not the provisioned
  set, and stays as-is.
- alternatives: keep provisioning them harmlessly — rejected, they are dead
  secrets post-SPEC-060; a cleanup slice should shrink the dev secret surface.

### R-5: Repoint product references off the retired origin string

- affected: `products/agent-platform/tests/{test_session_service.py,test_session_workspace.py,test_prose_redaction.py,test_secret_params.py,test_kernel_middleware.py}`
  and one comment in
  `products/agent-platform/src/agent_service/services/prose_redaction.py:243`.
- approach: replace every `browser-check-target` literal with `acme-admin`
  (OQ-2 resolution) — `http://acme-admin:8080` for the origin round-trip
  fixture, `https://acme-admin/reset?…` for the URL-redaction and secret-param
  fixtures, `runbook acme-admin` for the two prose-identifier fixtures — and
  refresh the `prose_redaction.py` comment example to `tool-gateway`. The host
  is incidental to every assertion; `acme-admin` shares `browser-check-target`'s
  two-character-class (lowercase + punctuation, no digit) profile, so the
  "identifier survives masking / is not harvested" assertions hold unchanged.
- alternatives: invent a `.invalid` host — rejected, `acme-admin` is the real
  surviving origin, reads naturally, and needs no per-test bespoke string.

### R-6: Documentation coherence and the recorded SPEC-060 decision reversal

- affected: `samples/README.md` (the "`browser-check-target` still ships"
  paragraph, lines ~68-76), `docs/specs/SPEC-060-*/spec.md` (changelog note),
  `CHANGELOG.md` (Unreleased entry), the spec index and roadmap rows (status).
- approach: rewrite the samples/README paragraph from "still ships for its
  platform consumers" to "retired by SPEC-061" (the category, runbook, e2e and
  credential sets are gone); append a forward-pointing changelog line to
  SPEC-060's `spec.md` recording that SPEC-061 reverses its *keep* decision
  (the delivered spec's Requirements/Non-Goals text is otherwise untouched);
  add the CHANGELOG `Unreleased` entry; flip the SPEC-061 status on delivery.
- alternatives: rewrite SPEC-060's body — rejected, delivered specs are not
  rewritten; a changelog note preserves the decision history.

## Sequencing And Dependencies

1. Stage 1 — approve the spec, author the trio, index row, roadmap row. Done.
2. Stage 2 — R-1 (runbook + skills-hub wiring + runbooks README).
3. Stage 3 — R-2 (static-target GitOps resources + allowlist).
4. Stage 4 — R-3 (e2e script + two GitOps READMEs). Depends on R-2 (the
   READMEs describe both the target and the script).
5. Stage 5 — R-4 (credential sets) and R-5 (product fixtures); independent of
   each other and of Stages 2-4.
6. Stage 6 — R-6 bookkeeping, then verification. Depends on Stages 2-5.

## Test Strategy

- unit tests: none added; R-5 edits existing agent-platform fixtures, so
  `make test`'s agent-platform suite must pass unchanged in count.
- contract tests: none (no contract change).
- integration / overlay validation: `make verify` green — the `overlays` leg
  renders `dev-k8s` and `browser-dev` with no `browser-check-target`
  Deployment/Service/pages ConfigMap, no `web-checks-InventoryHealth.md`
  ConfigMap key, and no dangling skills-hub volumeMount;
  `GATEWAY_BROWSER_ALLOW_ORIGINS` renders exactly `http://acme-admin:8080`;
  `validate-policy`, `validate-policy-scenarios`, `validate-version`
  (`VERSION=0.38.0` unchanged), and `validate-secret-vocabulary` all pass.
  `sh -n sync-browser-credentials.sh` passes.
- grep gates: repo grep for `browser-check-target`, `InventoryHealth`,
  `browser-check-demo` clean outside historical `CHANGELOG.md`, release notes,
  and SPEC-049/050/058/059/060 docs; `admin-portal` clean outside the generic
  unit-test/`skill-format.md` string and historical records.
- ADR-0008 gate: no new sample is exercised; the browser-flow coverage the
  retired assets stopped providing is already exercised — and was live-validated
  for SPEC-060 — by `samples/acme-admin/demo-suite.sh` rung 4. A live
  `make deploy` + `demo-suite.sh` pass on the dev cluster confirms the reduced
  posture still runs before `delivered`.

## Rollout And Migration

- deployment or configuration changes required: none for the product. On the
  dev cluster, `make deploy` re-renders the reduced `browser-dev` posture; the
  orphaned `browser-check-target` Deployment/Service/ConfigMap from a prior
  deploy are pruned by kustomize (or removed once manually), and
  `sync-browser-credentials.sh` re-issues `tool-gateway-browser-credentials`
  with the single `acme-admin` set.
- backward compatibility notes: the platform skill id
  `platform-runbooks/web-checks/inventoryhealth` is intentionally removed; no
  sample skill id changes (SPEC-060 already stabilized those). No product API,
  contract, or audit event changes.
- rollback approach: `git revert` the slice and `make deploy`; the static
  target, runbook, e2e and credential sets re-render. No state migration.
