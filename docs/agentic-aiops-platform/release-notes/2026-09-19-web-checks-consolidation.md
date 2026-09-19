# Web-Checks Consolidation onto ACME Admin

- Date: 2026-09-19
- Version: v0.39.0
- Specs: [SPEC-060](../../specs/SPEC-060-rebase-web-checks-samples-onto-acme-admin/spec.md),
  [SPEC-061](../../specs/SPEC-061-retire-browser-check-target/spec.md)

## Summary

This train consolidates the browser tutorial samples onto the stateful
`acme-admin` console and then retires the static mock they used to drive.
SPEC-060 rebases the surviving `web-checks` samples onto `acme-admin`; SPEC-061
makes the follow-up decision SPEC-060 deferred, removing the now-redundant
`browser-check-target` app, its one platform runbook, its dedicated e2e script,
and two orphaned dev credential sets. Neither slice changes product behavior,
shared contracts, the policy bundle, audit events, stream contracts, schemas, or
database migrations, so the train carries no runtime surface change — it is a
samples-and-docs migration plus a GitOps/config reduction and test-fixture
repoint.

## Delivered capabilities

- **SPEC-060 — samples rebased onto `acme-admin`.** `adhoc-password-reset` and
  `skill-graduation` move under `samples/acme-admin/` (leaf directory names
  preserved, so their skill ids are unchanged) and now drive the stateful
  console instead of the static target. `skill-graduation` is upgraded to reseed
  the store before act 1 and to prove both resets landed against real store state
  (`/api/users/{alice,bob}` `revision` + `password_changed_at`), with act 4's
  revision asserted higher than act 1's so a genuine replay is told apart from
  leftover authoring state. The approval-model triad (flow ↔ action ↔
  author/graduate) now shares one target that really mutates. The catalog
  (`samples/README.md`, `samples/acme-admin/README.md`), `demo-suite.sh` (six →
  five distinct ids), `demo-lib.sh`, `deploy-samples.sh`, `test_packaging.py`, and
  the Studio guide are reframed to match.
- **SPEC-061 — static target and orphaned consumers retired.** The
  `browser-check-target` Deployment/Service/pages ConfigMap, the
  `platform-runbooks/web-checks/InventoryHealth.md` runbook (plus its skills-hub
  ConfigMap generator entry and volume mount), and the manual
  `browser-check-demo.sh` e2e (never in the `make e2e` list) are removed.
  `sync-browser-credentials.sh` now generates only the `acme-admin` credential
  set, dropping `browser-check-target` and `admin-portal`. The `browser-dev`
  profile survives as the browser *posture* profile (sidecar patch + CDP-deny
  NetworkPolicy + env), now permitting exactly one origin, `http://acme-admin:8080`.
  Five `products/agent-platform/tests/` fixtures and one incidental `src/` comment
  example are repointed off the retired origin string, with behavior unchanged.

The `acme-admin` suite that remains gated demonstrates the approval model:

| Sample | Surface | Effect | Cards |
|---|---|---|---|
| `health-check` | `http.get` | read | 0 |
| `user-status` | bound browser | read | 0 |
| `lock-unlock-user` | `http.post` | write | 1 action |
| `password-reset` | bound browser | write | 1 flow |

See the [sample README](../../../samples/acme-admin/README.md) for deployment,
endpoints, seed data, credential synchronization, and the walkthroughs.

## Review corrections

The code-and-documentation review of the combined train found three issues, all
fixed before the release:

- **Critical — a maintained sample-app guard was left red.** SPEC-061 deleted
  `browser-check-target-pages.yaml`, which `samples/acme-admin/app/tests/test_pages.py`
  (shipped by SPEC-059 R-2) read as the source of truth for the 28-id element
  contract that shipped skills' `web.extract` / `web.click` selectors address. The
  module-scoped `contract` fixture asserted the file existed, erroring three
  tests. The contract is now transcribed into the test as an inlined literal, so
  the guard still fails mechanically on a template id rename without depending on
  a retired artifact. The full sample-app suite is green (110 passed, 0 errors).
- **A living guide still asserted the retired app ships.**
  `docs/guides/configuration-reference.md` described `browser-dev` as shipping
  "the sample browser-check-target app"; it now records that SPEC-061 retired the
  static target and that the profile's one allowlisted origin is the out-of-band
  `acme-admin` sample app.
- **The `samples/web-checks/` category was emptied, not removed.** Two zero-byte
  `WALKTHROUGH.md` stubs survived the migration, contradicting the CHANGELOG claim
  that the whole category is gone. Both stubs and their now-empty directories are
  removed.

## Validation

- `make verify`: green — 2,681 backend product tests, four overlay renders,
  18 policy rules, 137 API and 19 tool-policy scenarios, version lockstep at
  0.39.0, and all secret-vocabulary checks.
- Sample-app suite (`samples/acme-admin/app`): 110 passed, 0 errors after the
  `test_pages.py` contract fix.
- Live validation on the orbstack `dev-luban-aiops` cluster: `make deploy` applied
  the reduced overlay (the orphaned `browser-check-target` Deployment/Service/pages
  ConfigMap pruned; `platform-runtime-config` allowlist converged to the single
  origin `http://acme-admin:8080`; `tool-gateway-browser-credentials` regenerated
  with exactly one set, `acme-admin`; `skills-platform-runbooks` carries only the
  five `guides-*` keys). `make deploy-sample-app` passed all nine assertions, and
  `RUN_CHAT_LEG=true samples/acme-admin/demo-suite.sh` passed all four ladder demos
  plus both chat legs (138 ok / 0 failures).

## Deploy and live-test notes

```sh
make build
make deploy
make deploy-sample-app
make deploy-samples
```

The `browser-dev` profile enables the browser connector and allowlists exactly one
origin, `acme-admin`. Credential synchronization populates both the gateway
credential set and the application secret from the single `acme-admin` set.
`make deploy-samples` without `SAMPLE=` installs all five skill documents.
Because `deploy-overlay.sh` applies without `--prune`, a cluster that previously
ran `browser-check-target` must have those three resources removed once by hand;
a fresh cluster never creates them.
