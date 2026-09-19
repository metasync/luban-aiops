# SPEC-061: Retire `browser-check-target`, `InventoryHealth`, and the orphaned credential sets

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-19
- approved: 2026-09-19 (OQ-1..OQ-3 resolved on the draft's recommendations)
- delivered: 2026-09-19 (GitOps/config reduction + test fixtures; ships in the
  v0.39.0 release train — no `VERSION` bump, so the `CHANGELOG.md` entry stays
  under `Unreleased` until that train is cut). Live-validated on the orbstack
  `dev-luban-aiops` cluster: `make deploy` applied the reduced overlay (the
  orphaned `browser-check-target` Deployment/Service/pages ConfigMap pruned;
  `platform-runtime-config` allowlist converged to the single origin
  `http://acme-admin:8080`; `tool-gateway-browser-credentials` regenerated with
  exactly one set, `acme-admin`; `skills-platform-runbooks` carries only the five
  `guides-*` keys, no `web-checks/InventoryHealth.md`); `make deploy-sample-app`
  passed all nine assertions (including the credential cross-check that the one
  `acme-admin` set resolves for both surfaces); and `RUN_CHAT_LEG=true
  samples/acme-admin/demo-suite.sh` passed all four ladder demos plus both chat
  legs (138 ok / 0 failures) — the 0/0/1/1 card ladder holds through the agent
  on the reduced posture.
- release slice: R5 — Hardening and External Consumption (twenty-third R5
  slice, **v0.39.0** — riding in the same unreleased train as
  SPEC-060, because it finishes the `web-checks` consolidation SPEC-060
  began; SPEC-057 stays at v0.40.0. See OQ-1.)
- related ADRs: **ADR-0008** (spec delivery requires requirement-to-test
  traceability and *exercised samples* — the browser-flow coverage this
  slice stops providing through a platform runbook is already exercised,
  and live-validated for SPEC-060, by `samples/acme-admin/demo-suite.sh`
  rung 4 `password-reset`), **ADR-0007** (one HITL gate per mutating
  browser flow — unchanged; the gate keeps its worked example in the
  `acme-admin` suite rather than in `InventoryHealth`).
  lineage: completes the arc **SPEC-049** (browser web-check tools +
  `browser-check-demo.sh` + the `browser-check-target` static target) →
  **SPEC-050** (samples reorganized out-of-band; `browser-check-target`
  kept in the platform `browser-dev` profile because `InventoryHealth` and
  the e2e are platform assets) → **SPEC-058** (`http.get` built explicitly
  because `InventoryHealth` "complements the API-level checks" that did not
  exist) → **SPEC-059** (`acme-admin` + `CheckServiceHealth` supply that
  API-level check, and the four-rung suite demonstrates the browser flow
  gate against a target that really mutates) → **SPEC-060** (the samples
  rebased onto `acme-admin`; `browser-check-target` deliberately *kept* for
  `InventoryHealth` + `browser-check-demo.sh`, with its retirement named as
  a follow-up decision). This slice makes that follow-up decision: retire.

## Summary

Now that every browser tutorial runs against the stateful `acme-admin`
console and the platform's HTTP surface is shipped, the static
`browser-check-target` mock, its one platform runbook (`InventoryHealth`),
and its dedicated e2e (`browser-check-demo.sh`) are redundant: they
demonstrate nothing the `acme-admin` suite does not demonstrate better, and
`browser-check-demo.sh` is not even part of `make e2e`. This cleanup slice
retires all three, drops the two now-orphaned dev credential sets
(`browser-check-target`, `admin-portal`), repoints the product test fixtures
(and one incidental code comment) that borrow the retired origin string, and
corrects the living docs — leaving the `browser-dev` runtime profile as the browser *posture*
profile (sidecar + NetworkPolicy + env) that now permits exactly one origin,
`acme-admin`.

## Motivation

- **`InventoryHealth`'s teaching value is superseded, and its promise was
  only ever half-true.** Its Purpose claims it "Complements the API-level
  checks by exercising the rendered UI" — but until SPEC-058/059 there were
  *no* API-level checks, and the one that now exists (`CheckServiceHealth`,
  the `acme-admin/health-check` sample) is a *sample*, not a sibling in the
  platform runbook library. It is also `risk_class: write`, so "is the
  inventory portal healthy?" parks a HITL card — the exact anti-pattern
  SPEC-058's card-free `http.get` was built to replace.
- **Its target is a static mock that cannot teach verification.**
  `browser-check-target` serves six static pages; its `/status` is
  hard-coded `<td id="api-status">operational</td>`, and its reset page
  "reports success for any user." SPEC-059's whole premise was that a
  tutorial target with no server state cannot teach an agent to verify its
  own mutation — and `acme-admin` replaced it for every sample.
- **Its e2e is not in the gate, and its coverage is duplicated.**
  `browser-check-demo.sh` is *not* in the `make e2e` script list
  ([`Makefile:215`](../../../Makefile) runs `skills-demo`, `incident-demo`,
  `mutating-demo`, `http-check-demo`, and `acme-admin/demo-suite.sh`); it is
  a manual smoke test referenced only from `dev-k8s/README.md`. The browser
  flow + single-HITL-gate path it exercised is now covered — against a
  target that really mutates — by `demo-suite.sh` rung 4, which *is* in
  `make e2e` and whose live chat leg was validated for SPEC-060.
- **`admin-portal` is already orphaned.** SPEC-060 migrated its only
  consumers (the old `web-checks` `adhoc-password-reset` /
  `skill-graduation` samples) to the `acme-admin` credential set, yet
  `sync-browser-credentials.sh` still provisions it. Retiring the static
  target orphans `browser-check-target`'s credential set too.
- **Why now.** SPEC-060 explicitly deferred this ("Whether it is removed
  after the rebase is SPEC-060's decision"; it decided *keep* and named the
  follow-up). The samples consolidation is delivered and live-validated, so
  the follow-up is unblocked and the loose ends (a dangling "still ships"
  paragraph in `samples/README.md`, two dead credential sets, a stale
  authoring example) are cheapest to close in the same unreleased train.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Retire the `InventoryHealth` platform runbook and its skills-hub wiring

Delete `shared/platform-ops/skills/platform-runbooks/web-checks/InventoryHealth.md`
and the now-empty `web-checks/` directory; remove the
`web-checks-InventoryHealth.md=…` `configMapGenerator` entry from
`shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml` and the matching
`volumeMounts` key/path pair from
`shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml`.
Repoint the `platform-runbooks/README.md` web-check authoring guidance (its
step 3 currently says "See `web-checks/InventoryHealth.md` for the sample")
at the live `acme-admin` browser samples instead of a deleted file.

Acceptance criteria:

- No `InventoryHealth` file exists under `shared/platform-ops/skills/`, and
  the `platform-runbooks/web-checks/` directory is gone.
- `make verify`'s `overlays` leg renders the `dev-k8s` overlay green with no
  `web-checks-InventoryHealth.md` ConfigMap key and no dangling
  `skills-hub` volumeMount.
- `platform-runbooks/README.md` contains no link to a deleted file; its
  web-check guidance cross-references `samples/acme-admin/`.
- Repo grep for `InventoryHealth` is clean outside historical `CHANGELOG.md`,
  release notes, SPEC-058/059/060 docs, and the self-contained
  `products/skills-hub/tests/test_ingestion.py` web-check fixture — that test
  writes its *own* temporary `web/InventoryHealth.md` (a fictional
  `inventory.internal` target) into a tmpdir and ingests it, so it never
  references the retired runbook and is unaffected by its deletion. The
  incidental filename is left as-is, mirroring R-4's treatment of the generic
  `admin-portal` fixture string; renaming it would pull an unrelated product
  into a slice scoped to agent-platform test fixtures.

### R-2: Retire the `browser-check-target` static app from the `browser-dev` profile

Delete `browser-check-target-deployment.yaml`, `browser-check-target-service.yaml`,
and `browser-check-target-pages.yaml` from
`shared/platform-ops/gitops/runtime-profiles/browser-dev/`, and drop those
three from that directory's `kustomization.yaml` `resources` (keeping
`browser-sidecar-network-policy.yaml`, which selects `app: tool-gateway` and
is unrelated to the target). Remove `http://browser-check-target:8080` from
`browser.env`'s `GATEWAY_BROWSER_ALLOW_ORIGINS`, leaving
`http://acme-admin:8080`, and rewrite the surrounding comments (and the
`kustomization.yaml` header, which today calls `browser-check-target` "the
only origin") so the profile reads as the browser *posture* profile that
permits the one sample origin.

Acceptance criteria:

- The `browser-dev` overlay renders with no `browser-check-target`
  Deployment, Service, or pages ConfigMap.
- `GATEWAY_BROWSER_ALLOW_ORIGINS` in the rendered runtime config is exactly
  `http://acme-admin:8080`; `GATEWAY_BROWSER_ENABLED`,
  `GATEWAY_HTTP_*`, and the sidecar patch/NetworkPolicy are unchanged.
- `browser-sidecar-network-policy.yaml` and
  `tool-gateway-browser-sidecar.yaml` are untouched.
- `make verify`'s `overlays` leg is green.

### R-3: Retire `browser-check-demo.sh` and its references

Delete `shared/platform-ops/e2e/browser-check-demo.sh`. Confirm the
`make e2e` script list needs no change (the script was never in it). Update
`shared/platform-ops/gitops/dev-k8s/README.md` and
`shared/platform-ops/gitops/runtime-profiles/README.md` to drop the
`browser-check-target` / `browser-check-demo.sh` descriptions.

Acceptance criteria:

- `shared/platform-ops/e2e/browser-check-demo.sh` no longer exists; the
  remaining e2e scripts (`skills-demo`, `incident-demo`, `mutating-demo`,
  `http-check-demo`, `documents-demo`) are untouched.
- `make e2e`'s script list in the `Makefile` is unchanged.
- Repo grep for `browser-check-demo` is clean outside historical
  `CHANGELOG.md`, release notes, and SPEC-049/050/059/060 docs.
- The two GitOps READMEs no longer describe the retired target or script.

### R-4: Drop the orphaned `browser-check-target` and `admin-portal` credential sets

In `shared/platform-ops/gitops/sync-browser-credentials.sh`, reduce the
dev-default credential-sets file from three entries to one (`acme-admin`):
remove the `browser-check-target` (`svc-check`) and `admin-portal` (`admin`)
blocks and the now-unused `PASSWORD` / `ADMIN_PASSWORD` generation, and
rewrite the "three credential sets — two for the static sample target"
comment. The `acme-admin` entry and the second `acme-admin-credentials` sink
are unchanged. The illustrative `admin-portal` *string* used as a generic
credential-set name in skills-hub / agent-platform unit-test fixtures and in
`shared/shared-contracts/skill-format.md` is **not** a reference to the
provisioned set and stays as-is.

Acceptance criteria:

- The dev default in `sync-browser-credentials.sh` emits a
  `credential-sets.json` with exactly one key, `acme-admin`, and still writes
  the `acme-admin-credentials` secret from the same file.
- `sh -n shared/platform-ops/gitops/sync-browser-credentials.sh` passes.
- No live skill, demo, or profile resolves a `browser-check-target` or
  `admin-portal` credential set.

### R-5: Repoint product references off the retired origin string

`products/agent-platform/tests/` uses `http(s)://browser-check-target…` as a
convenient fictional origin in five files — `test_session_service.py`,
`test_session_workspace.py`, `test_prose_redaction.py`,
`test_secret_params.py`, `test_kernel_middleware.py`. Repoint those literals
to a neutral fictional origin, preserving each test's assertion semantics
(the host is incidental to what each test checks: origin round-tripping,
prose redaction, secret-parameter masking, kernel-middleware URL redaction).
One product **source** file also names the string — `prose_redaction.py:243`
uses `browser-check-target` purely as a comment example of a hyphenated,
lowercase-plus-punctuation identifier that must *not* be masked as a secret
(alongside `dev-luban-aiops`, `web-ui`). Refresh that one comment example to
a still-shipped identifier (e.g. `tool-gateway`) so the repo grep is genuinely
clean; the illustration and the redaction rule it documents are unchanged, so
no product behavior moves. This is otherwise test-only.

Acceptance criteria:

- Repo grep for `browser-check-target` under `products/` returns nothing.
- `make test` is green (the agent-platform suite passes unchanged in count).
- No product **behavior** changes: the sole `src/` edit is the incidental
  `prose_redaction.py` comment example (no logic, no redaction-rule change);
  every other edit is a test fixture.

### R-6: Documentation coherence and the recorded SPEC-060 decision reversal

Correct the living docs that still claim the static target ships:
`samples/README.md`'s "`browser-check-target` still ships, but no sample
drives it any more" paragraph, and any guide cross-reference. Add a
forward-pointing changelog line to `docs/specs/SPEC-060-*/spec.md` recording
that SPEC-061 reverses SPEC-060's *keep* decision (delivered specs are not
otherwise rewritten). Add a `CHANGELOG.md` entry under `Unreleased`
(v0.39.0), and add the SPEC-061 index row and roadmap row.

Acceptance criteria:

- No living doc asserts that `browser-check-target` ships or that
  `InventoryHealth` exists.
- `SPEC-060/spec.md`'s changelog names SPEC-061 as the reversal; its
  Requirements/Non-Goals text is otherwise unchanged.
- `CHANGELOG.md` has a SPEC-061 entry under `Unreleased`; the spec index and
  roadmap each carry a SPEC-061 row.
- Every internal link in the new and edited documents resolves.

## Non-Goals

- **No change to the browser tool surface, the HITL flow gate, the deviation
  guard, or any product behavior.** The fifteen `web.*` tools, ADR-0007's
  one-gate-per-flow, and SPEC-051/054/055 semantics are untouched; R-5 edits
  test fixtures plus one incidental `src/` comment example, changing no logic.
- **No change to `acme-admin` or the sample suite.** They already provide the
  API-level check (`CheckServiceHealth`) and the browser-flow gate example
  (`ResetAcmePassword`); this slice removes a redundant predecessor, it does
  not add a sample.
- **Not retiring the `browser-dev` runtime profile.** It survives as the
  committed browser posture (sidecar patch + CDP-deny NetworkPolicy + env),
  now permitting one origin.
- **Not re-adding an API-level `InventoryHealth` runbook to the platform
  library.** The platform runbook library keeps its Kubernetes
  troubleshooting guides and `sre-alerting`; a browser web-check example now
  lives in `samples/acme-admin/`, and pointing a *platform* runbook at a
  *sample* app would invert SPEC-050 R-11's tutorial→platform arrow.
- **No policy-bundle change, no contract change, no new audit event type.**
  Policy is tier-based; removing an allowlist origin and two credential sets
  is a configuration reduction, not a policy edit.
- **No `VERSION` bump in this slice.** It rides the unreleased v0.39.0 train
  (with SPEC-060); the release cut performs the lockstep bump.

## Impact

- products touched: `products/agent-platform/tests/` (five test files;
  string fixtures only) plus one incidental comment line in
  `products/agent-platform/src/agent_service/services/prose_redaction.py`
  (an example identifier in a code comment — no logic change).
- shared touched:
  `shared/platform-ops/skills/platform-runbooks/{web-checks/InventoryHealth.md,README.md}`;
  `shared/platform-ops/gitops/runtime-profiles/browser-dev/{browser-check-target-deployment.yaml,browser-check-target-service.yaml,browser-check-target-pages.yaml,kustomization.yaml,browser.env}`;
  `shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml`;
  `shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml`;
  `shared/platform-ops/gitops/sync-browser-credentials.sh`;
  `shared/platform-ops/e2e/browser-check-demo.sh`;
  `shared/platform-ops/gitops/dev-k8s/README.md`;
  `shared/platform-ops/gitops/runtime-profiles/README.md`.
- samples touched: `samples/README.md`.
- docs touched: `docs/specs/README.md`,
  `docs/agentic-aiops-platform/delivery-roadmap.md`,
  `docs/specs/SPEC-060-rebase-web-checks-samples-onto-acme-admin/spec.md`
  (changelog note), `CHANGELOG.md`.
- contracts touched: none.
- identity / policy / audit / execution safety impact: no new policy action,
  no new audit event type, no bundle edit. The change is a **reduction** of
  the dev secret surface (two credential sets removed) and of the browser
  allowlist (two origins → one, still deny-by-default). No shipped product
  behavior changes.
- living state docs to update on delivery: `samples/README.md`,
  `platform-runbooks/README.md`, `dev-k8s/README.md`,
  `runtime-profiles/README.md`, `CHANGELOG.md`, the spec index and roadmap
  rows.

## Open Questions

Resolved at approval 2026-09-19, each on the draft's recommendation.

- **OQ-1 — release slice.** Ride v0.39.0 alongside SPEC-060, or take a slot
  of its own? *Recommend v0.39.0:* the two form one coherent "web-checks
  consolidation" train (rebase the samples, then retire the mock they left),
  the train is still `Unreleased`, and a two-spec train has precedent
  (v0.38.0 shipped SPEC-058 + SPEC-059). SPEC-057 stays at v0.40.0.
  **Resolved: ride v0.39.0** with SPEC-060; no `VERSION` bump in this slice.
- **OQ-2 — fixture repoint target.** What neutral origin should R-5's five
  test files adopt? *Recommend* a clearly-fictional host that preserves each
  test's intent (e.g. keep an `.invalid`-style or `acme-admin`-shaped origin
  per test); the exact string is a plan-time detail, constrained only by "no
  `browser-check-target` remains and every assertion still holds."
  **Resolved: `acme-admin`** as the single replacement across all five files
  (`http(s)://acme-admin[:8080]` for the URL/origin fixtures, `acme-admin`
  for the two prose-identifier fixtures). It is the surviving browser origin,
  the host is incidental to every assertion, and it carries the identical
  lowercase-plus-punctuation character-class profile as `browser-check-target`
  (two classes, no digit), so the redaction/masking behavior the prose tests
  assert is unchanged.
- **OQ-3 — web-check authoring guidance.** Should `platform-runbooks/README.md`
  keep a `web-checks/` authoring note at all once the directory is gone?
  *Recommend* yes, but repointed: a one-line note that browser web-check
  skills declare `web_target` + `risk_class` and a worked example lives in
  `samples/acme-admin/`, so the guidance survives without shipping a
  platform-owned example that duplicates the samples. **Resolved: keep it,
  repointed** at `samples/acme-admin/` per the recommendation.

## Changelog

- 2026-09-19: created as `draft` from the post-SPEC-060 review that found the
  `InventoryHealth` / `browser-check-target` / `admin-portal` loose ends;
  scoped as a cleanup slice with the operator's decision to fold in the
  orphaned `admin-portal` credential-set removal.
- 2026-09-19: approved — OQ-1..OQ-3 resolved on the draft's recommendations
  (ride v0.39.0; repoint R-5 fixtures to `acme-admin`; keep the repointed
  web-check authoring note). `plan.md` and `tasks.md` authored; implementation
  proceeds.
