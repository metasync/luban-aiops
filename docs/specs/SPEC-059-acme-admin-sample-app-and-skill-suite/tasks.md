# SPEC-059 Tasks: `acme-admin` — A Real Sample Application and Its Skill Suite

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.
The sample application stays outside the product build loops. Shared integration
changes are additive: credential synchronization, root Makefile targets, and the
`browser-dev` runtime profile.

## R-1: The application

Lands first and is provable in isolation with `uv run pytest` before any
cluster exists.

- [x] `store.py` — `Store` holding `users`, monotonic `revision`, `last_reset`,
      `started_at`; `User` dataclass; `lock`/`unlock`/`set_password` each bumping
      the global revision and stamping the user; `NoOpMutation` → 409,
      `UnknownUser` → 404; `reseed()` restoring the exact seed; username-or-email
      identifier resolution
      (`samples/acme-admin/app/src/acme_admin/store.py`)
- [x] `auth.py` — HTTP Basic for the JSON API (`hmac.compare_digest` against
      `ACME_ADMIN_PASSWORD`) plus a random opaque session token in an
      `HttpOnly`/`SameSite=Lax` cookie held in a server-side set
      (`samples/acme-admin/app/src/acme_admin/auth.py`)
- [x] `api.py` — JSON router: `/healthz` and `/api/hello` unauthenticated,
      every `/api/users*` behind Basic auth, `/internal/reset-demo` behind the
      `X-Luban-Demo-Reset` header (`…/api.py`)
- [x] `pages.py` — HTML router rendering `string.Template` module constants,
      forms posting through `fetch` and rendering into the same element ids the
      static pages used (`…/pages.py`)
- [x] `main.py` — `create_app()`, the lifespan raising a `RuntimeError` naming
      the secret and the sync script when `ACME_ADMIN_PASSWORD` is absent/empty,
      and `run()` for the `acme-admin` console script (`…/main.py`)
- [x] `pyproject.toml` + committed `uv.lock` + `.python-version`; FastAPI on the
      shared toolchain, no Jinja2, no DB driver
- [x] `/api/hello`'s `name` validated against `^[A-Za-z0-9 _.-]{1,64}$`, 422
      outside it
- [x] test: health payload's eight keys and types; hello's echo and pattern
      refusal; seeded user set; lock/unlock/password each bumping `last_modified`
      **and** `revision`; 404 and 409; auth required on `/api/users*` and absent
      on `/healthz`/`/api/hello`; `reset-demo` refusing without the header and
      restoring the exact seed with it (`samples/acme-admin/app/tests/`)

## R-2: Rebase compatibility

- [x] six routes with the trailing-slash shapes (`/`, `/status`, `/admin/`,
      `/admin/users/`, `/admin/users/reset/`, `/admin/users/reset/done/`)
- [x] every id in the 28-id contract present with the same semantics, plus
      `reset-timestamp`; auto-login 100 ms `setInterval`; reset pre-fill from
      `?user=&newpw=` kept with the "does NOT auto-submit" comment; both now
      issue real `fetch` POSTs rendering into `#admin-login-status`/`#reset-status`
- [x] `/admin/users/` without a session returns 302 to `/admin/`
- [x] test: `html.parser` walks each rendered page asserting its full id set, so
      a template edit cannot silently break a shipped skill's selectors
      (`samples/acme-admin/app/tests/test_pages.py`)

## R-3: One generated password, two secret sinks

- [x] generated branch writes a third random `ACME_PASSWORD` into the
      credential-sets JSON as an `acme-admin` entry **and** into a new
      `acme-admin-credentials` secret as `ACME_ADMIN_PASSWORD`
      (`shared/platform-ops/gitops/sync-browser-credentials.sh`)
- [x] `BROWSER_CREDENTIAL_SETS_FILE` branch reads the `acme-admin` entry and
      writes the same secret, failing loudly naming the missing key when absent
- [x] `SKIP_BROWSER_CREDENTIALS=true` still exits 0 having written nothing;
      existing secrets remain, while an unprovisioned app fails closed at startup
- [x] both sinks created before the existing tool-gateway rollout restart

## R-4: Stand-alone packaging

- [x] thin `app/Makefile` with `../../../mk/` includes; **not** added to
      `IMAGE_PRODUCTS`/`PYTHON_PRODUCTS` (`samples/acme-admin/app/Makefile`)
- [x] Dockerfile mirroring `products/audit-service/Dockerfile` on `base-uv`:
      `COPY --chown=app:app`, `uv sync --frozen --no-dev`, `EXPOSE 8080`,
      `CMD ["uv","run","acme-admin"]`, no `USER` line (`…/app/Dockerfile`)
- [x] test: skill discovery finds the two previously shipped skill dirs and
      none under `app/`, `deploy/`, `tests/`; derived ids stay pairwise distinct
      (`samples/acme-admin/app/tests/test_packaging.py`). The live suite asserts
      all six mounted ids, including the four new skills.

## R-5: Manifests and the runtime-profile allowlist

- [x] self-contained kustomization (no own namespace), Deployment `app:
      acme-admin` `replicas: 1` `strategy: Recreate` with the reason commented,
      both probes on `/healthz`, hardened securityContext, `ACME_ADMIN_PASSWORD`
      via `secretKeyRef` with no default; `ClusterIP` Service on 8080;
      ingress-only NetworkPolicy `from: app: tool-gateway` port 8080
      (`samples/acme-admin/deploy/{kustomization,deployment,service,networkpolicy}.yaml`)
- [x] `browser.env` gains `http://acme-admin:8080` to
      `GATEWAY_BROWSER_ALLOW_ORIGINS`, a new `GATEWAY_HTTP_ALLOW_ORIGINS` with
      the same value, `GATEWAY_HTTP_ENABLED=true` and
      `GATEWAY_HTTP_CREDENTIAL_SETS`; `dev-k8s/base` names nothing
      (`shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env`)
- [x] test/assertion: `kustomize build samples/acme-admin/deploy` renders;
      `make overlays` still green; `dev-k8s/base` contains no `acme-admin` string

## R-6: `make deploy-sample-app`

- [x] three `.PHONY` targets beside `deploy-samples`, `deploy_sample_app` a
      two-line alias, both with `## ` help; `undeploy-sample-app` delegates with
      `ACTION=undeploy` (`Makefile`)
- [x] `deploy.sh` deploy-then-assert in R-6 order: `kustomize build` pre-flight;
      compute/read `IMAGE_TAG`; `$(MAKE) -C samples/acme-admin/app build`;
      `kind load` under the same conditions; `kubectl apply -n` + `set image` +
      `rollout status`; then each assertion a small function that `die`s naming
      itself; in-cluster HTTP via `kubectl exec` in the tool-gateway container
      (`samples/acme-admin/deploy.sh`)
- [x] assertions: rollout complete; applied tag == built tag; `/healthz` 200 with
      the R-1 keys; `/api/hello?name=luban` echoes; `/api/users` 200 with creds
      and 401 without; the secret exists; both allowlists contain the origin
- [x] `undeploy` removes Deployment/Service/NetworkPolicy and the app secret
      only, and does not touch allowlist entries
- [x] the `e2e` target's prerequisite echo gains a `make deploy-sample-app` line

## R-7: The four skills (ladder order)

- [x] `health-check/skill/CheckServiceHealth.md` — `http.get` read, **0 cards**;
      frontmatter title/description/tags/version, **no** `web_target`, **no**
      `risk_class`
- [x] `user-status/skill/CheckUserStatus.md` — browser read, `web_target:
      http://acme-admin:8080/`, **no** `risk_class` (defaults read), exists to
      verify what `LockUnlockUser` did
- [x] `lock-unlock-user/skill/LockUnlockUser.md` — `http.post` write, **1 `action`
      card**; `risk_class: write`, no `web_target`; body `{"locked": true}`
      leaves no trace hole
- [x] `password-reset/skill/ResetAcmePassword.md` — bound browser flow write,
      **1 `flow` card**; `web_target`, `risk_class: write`, `flow_intent`; routes
      the credential through `web.fill_credential`, the one-time value through
      `?newpw=`
- [x] titles/tags framed around `acme-admin`, sharp against the shipped
      `admin-portal` sample (SPEC-056's `qwen3:1.7b` tool-selection failure is
      the reason); the slug-collision name `ResetAcmePassword.md` honoured

## R-8: Walkthroughs and demos

- [x] four `WALKTHROUGH.md` + four `README.md`, one pair per sample
- [x] five demo scripts (four `demo/demo.sh` + `demo-suite.sh` at the sample
      root), each reseeding via curl in the tool-gateway container with
      `X-Luban-Demo-Reset: 1` first; card-count assertions querying the
      platform-gateway for `confirmation_request` frames; chat legs opt-in behind
      `RUN_CHAT_LEG=true`
- [x] `demo-suite.sh` runs the four in ladder order then re-runs
      `CheckUserStatus`'s read to assert the lock landed (cross-skill verification)
- [x] the `make e2e` hardcoded list gains
      `$(SAMPLES_DIR)/acme-admin/demo-suite.sh` (`Makefile`)

## R-9: Documentation

- [x] app README (endpoints, seed data, credential arrangement, state model and
      its `replicas: 1` consequence, how to write a new walkthrough)
      (`samples/acme-admin/README.md`)
- [x] `samples/README.md` gains an `acme-admin` section stating both targets
      exist and why
- [x] `skills-guide.md` gains the read-only-skill pattern illustrated by
      `CheckServiceHealth` (`docs/guides/skills-guide.md`)
- [x] `studio-guide.md` and `tool-configuration.md` cross-references
- [x] every relative link checked mechanically before delivery

## Delivery Gate

- [x] first live deploy + assertion run green (depends on SPEC-058 delivered)
- [x] browser verification of all four walkthroughs against the deployed cluster
- [x] all acceptance criteria in `spec.md` verified
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated; spec status set to `delivered`
