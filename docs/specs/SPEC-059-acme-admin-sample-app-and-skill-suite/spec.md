# SPEC-059: `acme-admin` — A Real Sample Application and Its Single-Target Skill Suite

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-17
- approved: 2026-09-17
- delivered: 2026-09-17 (v0.38.0)
- release slice: R5 — Hardening and External Consumption (twenty-first R5
  slice, v0.38.0 — pulled in one release early alongside its SPEC-058
  dependency, whose tools two of the four skills cannot exist without, and one
  before SPEC-057, which moves to v0.40.0 to consume the repertoire this slice
  supplies)
- related ADRs: **ADR-0008** (spec delivery requires requirement-to-test
  traceability and *exercised samples* — R-8 is that obligation discharged for
  four new samples), ADR-0007 (one HITL gate per mutating browser flow — the
  browser skills in R-7 ride it unchanged; the login auto-submit that keeps
  authentication read-tier is preserved by R-2), **ADR-0011** (a composition
  carries no authority; each sub-skill keeps its own gate — this spec supplies
  the single-target repertoire SPEC-057 composes), ADR-0009 (graduate sessions
  into replayable executable skills — the suite is the demo asset graduation is
  taught against).
  lineage: depends on **SPEC-058** (`http.get`/`http.post` — two of the four
  skills cannot exist without it), extends SPEC-050 R-11 (samples install
  out-of-band so the base overlay never names a sample — the rule R-4/R-5/R-6
  are built around), SPEC-049 R-5 (named credential sets, secrets out of
  skills — R-3), SPEC-051 (the login-auto-submits / reset-does-not asymmetry
  R-2 preserves), SPEC-053 R-4 (`flow_intent`), SPEC-054 (`approval_kind`),
  SPEC-055 (graduation, which R-7's skills must remain graduable),
  SPEC-056 (Studio — the authoring surface the walkthroughs demonstrate in),
  SPEC-057 (composition — the consumer of this repertoire).
- drafting: from the 2026-09-17 design discussion on enriching the
  single-target skill walkthroughs. Decisions taken there and carried here:
  build the app first and rebase the existing walkthroughs onto it later
  (a separate slice, Non-Goals); the app is stand-alone with its own code and
  deployment; a root `make` convenience target deploys it; the app is named
  `acme-admin` rather than "sample portal", because "portal" already means
  `operator-portal`/`web-ui` throughout this repository and a second portal in
  the documentation would be genuinely ambiguous; all four skills ship now
  rather than three-now-plus-one-on-rebase.

## Summary

Replace the tutorial target's six static HTML pages with a small application
that actually behaves like one — `acme-admin`, a FastAPI user-administration
console with a health API, a service API, a login, a user list carrying real
status and modification state, and real lock/unlock and password-reset
mutations — and ship four single-target skills against it that together
demonstrate the approval model as a clean **0 / 0 / 1 / 1** card ladder: two
read-only skills that park nothing, and two mutating skills that park exactly
one card each, one over HTTP and one over the browser. The app is stand-alone
under `samples/`, builds with the platform's own image and Python fragments,
deploys to the local cluster with a new `make deploy-sample-app`, and keeps the
existing target's URL shapes and element ids so the three shipped samples can
be rebased onto it later without a rewrite.

## Motivation

**The current tutorial target cannot teach verification.** It is stock
`nginxinc/nginx-unprivileged` serving six static pages from a ConfigMap, with
no code and no state. Its reset page *"report[s] success for any user"*
([`password-reset/WALKTHROUGH.md:203`](../../../samples/web-checks/password-reset/WALKTHROUGH.md))
— the walkthrough says so out loud, and then has to explain why the URL it just
showed you is a lie. Its login accepts any credentials. Nothing it does
persists, so no skill can check whether a previous skill's mutation landed.
Four skills against that target are four disconnected demos; four skills
against a target with real state are one story, because the read-only skill can
prove what the mutating skill did.

**There is no read-only web-check skill anywhere in the repository, and the
platform's own skill library already pretends otherwise.** Every shipped
`web-checks` skill is `risk_class: write` — `password-reset`,
`adhoc-password-reset`, `skill-graduation`, `InventoryHealth` — because signing
into a page needs `web.click`, and `web.click` is write tier. So
[`InventoryHealth`](../../../shared/platform-ops/skills/platform-runbooks/web-checks/InventoryHealth.md),
which *is* a health check, parks a confirmation card. Its own Purpose line says
it "Complements the API-level checks by exercising the rendered UI" — and there
are **no API-level check skills in the library at all**, because until SPEC-058
there is no HTTP tool to write one with. An unauthenticated `http.get` against
`/healthz` closes both gaps at once: the first genuinely card-free read-only
skill, and the API-level complement a shipped skill already claims exists.

**SPEC-057 needs this repertoire before it can be demonstrated.** Composition
is defined as an ordered list of *published single-target skills*, and the
approved SPEC-057 has nothing to compose except the three existing samples, all
of which are the same password-reset mutation wearing different approval
clothes. Four skills on one target — two read, two write, two surfaces — is the
prerequisite asset, which is why this slice lands before SPEC-057 rather than
after it.

**Why a real image is unavoidable, and what that costs.** State requires a
service, a service requires an image, and this is the first sample to own one.
That intersects two existing constraints, both of which this spec honours
rather than works around: SPEC-050 R-11 keeps samples out of the base overlay
(R-5 puts the manifests under `samples/` and the allowlist entries in a runtime
profile, never in `dev-k8s/base`), and `make build` is the single coordinated
image path (R-6 reuses its `IMAGE_TAG` without joining `IMAGE_PRODUCTS`, so the
platform build does not grow a tutorial image). The stack is FastAPI + uv on the
shared `base-uv` image — the same toolchain as every product, so the sample
*looks like* the platform it is teaching, and there is no second build
convention to maintain.

## Requirements

### R-1: `acme-admin` — a small application that really works

A FastAPI service under `samples/acme-admin/app/`, Python 3.12 via uv with a
committed `uv.lock`, holding its state **in memory** in a single module-level
store. No database, no PVC, no external dependency: a tutorial target that
needs provisioning stops being a tutorial target.

Two parallel surfaces over one store, because that is what a real internal
application looks like and because the four skills need to choose between them:

**Machine surface (JSON).**

| endpoint | auth | purpose |
|---|---|---|
| `GET /healthz` | none | `status`, `service`, `version`, `hostname` (the pod name), `uptime_seconds`, `started_at`, `users_seeded`, `store_revision` — a health check with something to assert, not a bare 200 |
| `GET /api/hello?name=<n>` | none | `{"message": "hello, <n>!"}` — the "does the basic function work" probe; echoes the name so a skill can assert round-trip correctness, and validates `name` against a bounded pattern so it cannot be used to inject markup into a rendered page |
| `GET /api/users` | admin | the user list: `username`, `locked`, `last_modified`, `revision` |
| `GET /api/users/{username}` | admin | one user, same fields plus `password_changed_at` |
| `POST /api/users/{username}/lock` | admin | locks; bumps `last_modified` and `revision` |
| `POST /api/users/{username}/unlock` | admin | unlocks; same bumps |
| `POST /api/users/{username}/password` | admin | sets a new password; bumps both, records `password_changed_at` |
| `POST /internal/reset-demo` | see below | restores the deterministic seed state |

**Human surface (HTML)** — the six page shapes R-2 requires, server-rendered
from the same store, with forms that POST back to `/admin/...` routes.

Every mutating response carries the post-mutation `revision`, so a caller can
prove *which* action changed a row rather than only that something did. A
404 for an unknown username and a 409 for a no-op mutation (locking an already
locked user) are returned as real status codes — SPEC-058 R-3's
`mutation_confirmed` marker only means something if the target distinguishes
them.

`POST /internal/reset-demo` is the deterministic reseed the demo scripts need,
and it is **gated on a required request header** (`X-Luban-Demo-Reset`) that the
demo script sets with `curl` and that **`http.post` has no way to send**,
because SPEC-058 R-4 deliberately ships no `headers` parameter. The agent
therefore cannot reset the demo state mid-run even though the endpoint is on an
allowlisted origin — a structural control rather than a hope. No skill document
names this endpoint.

Acceptance criteria:

- `uv run pytest` in `samples/acme-admin/app/` passes a suite covering: the
  health payload's keys and their types; hello's echo and its pattern refusal;
  the seeded user set; lock/unlock/password mutations each bumping
  `last_modified` **and** `revision`; the 404 and 409 cases; auth required on
  every `/api/users*` route and absent on `/healthz` and `/api/hello`;
  `reset-demo` refusing without the header and restoring the exact seed with it.
- `curl /healthz` returns 200 with all eight keys; `curl /api/users` without
  credentials returns 401; with the synced admin credentials returns the seeded
  list.
- Two consecutive identical mutations return 200 then 409, and the second does
  not bump `revision`.
- The app runs as a non-root user and binds 8080.

### R-2: Rebase compatibility — the URL shapes and the element-id contract

The later rebase of the three shipped samples onto this app (a separate slice)
must be a retarget, not a rewrite. So `acme-admin` serves the same six URL
shapes the current target serves, and the same element ids the shipped skills'
`web.snapshot` refs and `web.extract` selectors address:

| current target | `acme-admin` |
|---|---|
| `/` , `/status` , `/admin/` , `/admin/users/` , `/admin/users/reset/` , reset-done | the same six paths |
| `index.html`, `status-index.html`, `admin-index.html`, `admin-users-index.html`, `admin-reset-index.html`, `admin-reset-done-index.html` | the same six rendered pages |

The id contract, taken from the current
[`browser-check-target-pages.yaml`](../../../shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-check-target-pages.yaml):
`admin-auth-status`, `admin-login-form`, `admin-username`, `admin-password`,
`admin-sign-in`, `admin-login-status`, `user-table`, `back-to-users`,
`target-user`, `new-password`, `confirm-password`, `confirm-reset`,
`reset-form`, `reset-status`, `confirmation-message`, `last-reset-user`,
`last-reset-time`, `last-reset-status`, `no-resets`, `api-status`,
`db-status`, `queue-status`, `checked-at`, and the public-login set
(`login-form`, `username`, `password`, `sign-in`, `login-status`). Every one is
present with the same semantics.

Two behavioural asymmetries are load-bearing and are preserved exactly, because
they are what holds a mutating browser flow to a single card (SPEC-051):

- **The login auto-submits** once both fields are filled — the current target's
  `_autoLoginTimer` polling loop, kept as-is. Authentication therefore costs
  only `web.fill_credential`, which is read tier, and parks nothing.
- **The reset form pre-fills from `?user=&newpw=` but does not auto-submit.**
  The sole `web.click` in the flow is "Confirm reset", which is the mutation the
  operator actually approves, and `flow_intent` describes it.

The `?newpw=` query convention is kept deliberately, so the gateway's
`_redact_secret_query` masking path — extracted into a shared helper by
SPEC-058 R-6 — stays exercised by a live sample rather than only by unit tests.

Two things change, and both are the point of the slice: the login now
**validates** credentials against the store (R-3) instead of accepting anything,
and the reset now **mutates** the store instead of reporting success for any
user.

Acceptance criteria:

- Every path in the table resolves with the same status code the current target
  returns for it (200 for the pages, 302 to `/admin/` for an unauthenticated
  `/admin/users/`).
- A test asserts the presence of all 28 ids on the pages that carry them, by
  parsing the rendered HTML — so a future template edit cannot silently break a
  shipped skill's selectors.
- Filling both login fields with valid credentials navigates to `/admin/users/`
  with no click; filling them with an invalid password renders a visible failure
  in `admin-login-status` and does not navigate.
- `/admin/users/reset/?user=alice&newpw=x` pre-fills `target-user` and
  `new-password`, and does **not** submit: the store is unchanged until
  `confirm-reset` is activated.
- After a real reset, `GET /api/users/alice` reports a bumped `revision` and
  `password_changed_at`, and `last-reset-user`/`last-reset-time` on the page
  reflect it.

### R-3: One generated admin password, written into two secrets

The admin credential is real, random, never committed, never echoed, and never
present in a skill document. [`sync-browser-credentials.sh`](../../../shared/platform-ops/gitops/sync-browser-credentials.sh)
already generates a random `admin-portal` password into the
`tool-gateway-browser-credentials` secret and is already called by
[`deploy.sh:43`](../../../shared/platform-ops/gitops/dev-k8s/deploy.sh); it is
extended to generate **one** value for `acme-admin` and write it to both
consumers:

- `tool-gateway-browser-credentials` → `credential-sets.json` gains an
  `acme-admin` entry, which is what `web.fill_credential(credential_set="acme-admin")`
  and SPEC-058 R-4's `http.post(credential_set="acme-admin")` resolve;
- a new `acme-admin-credentials` secret → `ACME_ADMIN_PASSWORD`, consumed by the
  app Deployment, which seeds its `admin` user with it.

One generator and two sinks is the only arrangement in which the browser
surface, the HTTP surface and the application cannot disagree about the
password. `BROWSER_CREDENTIAL_SETS_FILE` keeps its override behaviour, and the
override path must also produce the app-side secret — an operator supplying
their own sets supplies the app's password too, or the app cannot start.
`SKIP_BROWSER_CREDENTIALS=true` still skips both, and the app then fails closed
at startup rather than defaulting to a well-known password.

The seeded demo users (`alice`, `bob`, `carol`, `dave`, one of them pre-locked)
have **no** usable password — they are records, not accounts — so nothing about
them is a secret and nothing about them needs syncing.

Acceptance criteria:

- A fresh `make deploy` followed by `make deploy-sample-app` produces an app
  whose `admin` login succeeds with the credential-set value, asserted by
  `curl -u` inside the cluster and by a browser login through the gateway.
- No password literal appears in any file under `samples/`, in any skill
  document, in any manifest, or in any tool result; `make validate-secret-vocabulary`
  and a targeted grep both stay clean.
- With `SKIP_BROWSER_CREDENTIALS=true` and no `acme-admin-credentials` secret,
  the app pod does not start and says why in its logs (fail closed, not fail
  open to a default).
- Regenerating the secrets and restarting both deployments keeps the two
  surfaces in agreement.

### R-4: Stand-alone packaging that reuses the platform's own fragments

```
samples/acme-admin/
  README.md              what the app is, what it is for, how to deploy it
  app/
    pyproject.toml  uv.lock  Dockerfile  Makefile
    src/acme_admin/        the service
    tests/                 the R-1 suite
  deploy/
    kustomization.yaml  deployment.yaml  service.yaml  networkpolicy.yaml
  health-check/          README.md  WALKTHROUGH.md  skill/  demo/
  user-status/           …
  lock-unlock-user/      …
  password-reset/        …
```

`app/Makefile` is the eight-line product pattern —
[`products/audit-service/Makefile`](../../../products/audit-service/Makefile)
with a deeper relative include:

```make
IMAGE_NAME := acme-admin
include ../../../mk/image.mk
include ../../../mk/python.mk
```

so the app builds on the shared `base-uv` image, tags as
`luban-aiops/acme-admin:<IMAGE_TAG>`, lints under hadolint, and tests under
`uv sync --frozen && uv run pytest` with no new toolchain and no second
convention.

The app is **not** added to `IMAGE_PRODUCTS` or `PYTHON_PRODUCTS`
([`Makefile:15,17`](../../../Makefile)). Those lists drive `make build`,
`make push`, `make lint`, `make test` and `make sync` across the *platform*, and
both loops are hardcoded to `products/$$p`, so joining them would mean
refactoring the root Makefile's iteration for one tutorial image. Keeping the
app out preserves SPEC-050 R-11's dependency direction — tutorial → platform,
never the reverse — and keeps `make build`'s duration and `.images.env` contract
about shipped products. The app is built by `make deploy-sample-app` (R-6),
which passes the coordinated `IMAGE_TAG` down so the tag stays coherent and
there is no second, divergent `-dirty-<timestamp>` path.

Acceptance criteria:

- `make -C samples/acme-admin/app build IMAGE_TAG=t` produces
  `luban-aiops/acme-admin:t`; `make -C samples/acme-admin/app test` runs the
  R-1 suite; `make -C samples/acme-admin/app lint` passes hadolint.
- `make build` and `make test` at the root are unchanged in behaviour and
  duration and do not mention `acme-admin`; `.images.env` gains no key.
- The Dockerfile is multi-stage on `luban-aiops/base-uv:al2023`, installs from
  the frozen lock, and runs as a non-root user.
- `samples/deploy-samples.sh` discovers exactly the four new `skill/`
  directories and nothing under `app/`, `deploy/` or `tests/` — asserted, since
  its discovery is `find -type d -name skill` and a stray directory of that name
  anywhere in the tree would be packaged.

### R-5: Deployment manifests and the runtime-profile allowlist entries

`samples/acme-admin/deploy/` is a self-contained kustomization holding a
Deployment, a Service on 8080, and an ingress NetworkPolicy.

- **`replicas: 1` with `strategy: Recreate`**, and the reason recorded in a
  manifest comment: the store is in-memory, so a second replica is a second
  truth and a rolling update would briefly serve two of them. A tutorial target
  that intermittently disagrees with itself teaches nothing.
- Readiness and liveness probes on `/healthz`, resource requests and limits,
  `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, a
  non-root `runAsUser`, and `ACME_ADMIN_PASSWORD` from the R-3 secret via
  `secretKeyRef` with no default and no literal.
- **An ingress NetworkPolicy allowing only `app: tool-gateway` on 8080.** The
  browser sidecar shares the tool-gateway pod, so this one rule covers both the
  browser surface and SPEC-058's HTTP surface, and it mirrors the
  defense-in-depth posture of
  [`browser-sidecar-network-policy.yaml`](../../../shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml)
  (SPEC-049 C-1). Worth doing because, unlike the current static target, this
  app holds a real credential and can mutate state. Note that no *egress* policy
  exists anywhere in the repository today, so nothing additional is needed for
  the tool-gateway to reach it.
- **The base overlay names nothing.** Per SPEC-050 R-11, no `acme-admin`
  resource, image, or origin appears in `dev-k8s/base`. The allowlist entries go
  into the `browser-dev` runtime profile, which already hosts the tutorial
  target surface: `GATEWAY_BROWSER_ALLOW_ORIGINS` and the new
  `GATEWAY_HTTP_ALLOW_ORIGINS` each gain `http://acme-admin:8080`. One profile
  rather than a new one, because the walkthroughs need both surfaces against the
  same origin and splitting them would make an operator apply two profiles to
  run one tutorial. `browser-check-target` stays exactly as it is — nothing in
  this slice removes or edits it.

Acceptance criteria:

- `kustomize build samples/acme-admin/deploy` renders, and the rendered
  Deployment carries `replicas: 1`, `strategy: Recreate`, both probes, the
  non-root securityContext, and the `secretKeyRef`.
- `make overlays` still passes with **no** change to the `OVERLAYS` list, and a
  grep of `dev-k8s/base` finds no `acme-admin` string.
- With the `browser-dev` profile applied, the rendered
  `platform-runtime-config` carries `http://acme-admin:8080` in both allowlists,
  and `GATEWAY_HTTP_ENABLED=true` is present (SPEC-058 R-7 keeps the base at
  `false`).
- The NetworkPolicy selects the app pods and permits ingress on 8080 only from
  `app: tool-gateway`; a curl from any other pod times out.

### R-6: `make deploy-sample-app`, and what it proves before it exits

A root convenience target beside `deploy-samples`, delegating to
`samples/acme-admin/deploy.sh`:

```make
.PHONY: deploy-sample-app deploy_sample_app undeploy-sample-app
deploy-sample-app: ## Build and deploy the acme-admin sample app to the dev cluster
deploy_sample_app: deploy-sample-app
undeploy-sample-app: ## Remove the acme-admin sample app from the dev cluster
```

The canonical name is hyphenated because every root target is
(`deploy-samples`, `base-images`, `sync-policy`, `validate-version`); the
underscore spelling the request used is kept as a two-line alias so both work.
Both are listed in `make help`.

The script is a deploy *and an assertion*, in this order:

1. `kustomize build` the deploy dir as a pre-flight. `make overlays` cannot
   cover it — that loop prefixes `$(GITOPS_DIR)/`
   ([`Makefile:173`](../../../Makefile)) — so the render check lives here.
2. Build the image with the coordinated tag: read `IMAGE_TAG` from
   `.images.env` when `make build` has written it, otherwise compute it the same
   way, then `$(MAKE) -C samples/acme-admin/app build IMAGE_TAG=… IMAGE_PLATFORM=…`.
3. Load it into the local cluster (`kind load docker-image`) under the same
   `AUTO_LOAD_KIND`/`KIND_CLUSTER_NAME` conditions the root build uses.
4. Apply the rendered manifests with that tag, then `kubectl rollout status`.
5. **Assert, and fail loudly if any assertion misses**: the rollout completed;
   the applied image tag equals the one built; `GET /healthz` from inside the
   cluster returns 200 with the R-1 keys; `GET /api/hello?name=luban` returns
   the echoed greeting; `GET /api/users` with the synced credential returns 200
   and without it returns 401; the `acme-admin-credentials` secret exists; and
   both allowlists in the rendered runtime config contain the origin.
6. Print the two follow-up commands the operator still needs —
   `make deploy-samples` for the four skills, and the port-forward for the
   walkthroughs — rather than silently assuming them.

`undeploy-sample-app` removes the Deployment, Service and NetworkPolicy and the
`acme-admin-credentials` secret, leaves `tool-gateway-browser-credentials` and
every platform resource untouched, and does not remove the allowlist entries
(they are GitOps state, not script state).

Acceptance criteria:

- `make deploy-sample-app` on a cluster with `make deploy` already applied ends
  with every step-5 assertion passing, and is idempotent on a second run.
- Both spellings work: `make deploy_sample_app` and `make deploy-sample-app`.
- The deployed pod's image tag matches `IMAGE_TAG` from `.images.env` when
  present — asserted by the script, so a stale image cannot pass.
- Killing the app's routes (a deliberate break in a scratch run) makes the
  script exit non-zero naming the failed assertion, not exit 0.
- `make undeploy-sample-app` leaves `kubectl get deploy,svc,netpol -l app=acme-admin`
  empty and every platform deployment untouched.
- `make help` lists all three targets.

### R-7: Four single-target skills, and the 0 / 0 / 1 / 1 card ladder

Four samples under `samples/acme-admin/`, each self-contained in the existing
shape (`README.md`, `WALKTHROUGH.md`, `skill/`, `demo/`), each declaring exactly
one target origin:

| sample dir | skill | surface | tier | cards |
|---|---|---|---|---|
| `health-check/` | `CheckServiceHealth.md` | `http.get` `/healthz`, `/api/hello` | read | **0** |
| `user-status/` | `CheckUserStatus.md` | `web.navigate` + `web.extract` on `/admin/users/` | read (no `risk_class`) | **0** |
| `lock-unlock-user/` | `LockUnlockUser.md` | `http.post` `/api/users/{u}/lock` | write | **1** (`action`) |
| `password-reset/` | `ResetAcmePassword.md` | bound browser flow, `?newpw=` | write (`risk_class: write`, `flow_intent`) | **1** (`flow`) |

The surface split is deliberate and is the suite's main teaching content: the
two read-only skills show that a card is a property of *effect*, not of tooling
— one reads over HTTP, one reads a rendered page, neither parks anything. The
two mutating skills perform the same class of change over the two surfaces and
park **one card each of a different `approval_kind`**, so a reader sees
SPEC-054's discriminator from both sides without needing the ad-hoc sample. And
`CheckUserStatus` exists to verify what `LockUnlockUser` did, which is the
sentence that turns four demos into one runbook — and the shape SPEC-057 will
compose.

`CheckServiceHealth` carries **no** `web_target` and **no** `risk_class`: those
are browser-flow keys, and a skill that never touches the browser must not
declare them. It is the repository's first read-only skill that parks nothing.

Two naming rules, both mechanical, both because of how
[`deploy-samples.sh`](../../../samples/deploy-samples.sh) derives ids:

- **The skill id is `samples/<skill-dir-leaf>-<filename-slug>`.** The category
  directory is *not* part of it. So a new
  `samples/acme-admin/password-reset/skill/ResetUserPassword.md` would produce
  `samples/password-reset-resetuserpassword` — **byte-identical to the id the
  existing `samples/web-checks/password-reset/` already owns**, and two
  `--from-file` arguments with the same ConfigMap key is a hard failure, not a
  silent overwrite. Hence the filename `ResetAcmePassword.md`, which yields
  `samples/password-reset-resetacmepassword`. Every one of the four ids must be
  asserted distinct from the two shipped ones — `web-checks/skill-graduation`
  ships no skill document at all, because it graduates one at runtime, so the
  mounted set is six ids and not the seven this criterion originally counted.
- **Titles and tags must be sharply distinct from the shipped reset samples.**
  Two near-identical reset skills in one catalog is a tool-selection problem,
  not a cosmetics problem: SPEC-056's own delivery record has the graduation
  demo fail on the deployment's default `qwen3:1.7b` model's tool *selection*
  rather than on anything that spec touched. `ResetAcmePassword` is titled and
  tagged around `acme-admin` and the user-administration console; the shipped
  `ResetUserPassword` keeps its `admin-portal` framing. The operator chose to
  ship all four now rather than let the rebase supply the fourth, and this is
  the mitigation that decision requires.

Each mutating skill stays **graduable** under SPEC-055: `LockUnlockUser`'s body
is a non-secret scalar (`{"locked": true}`), so `parameterize_for_trace` leaves
no `<credential-reference>` hole and R-4's blast-radius re-validation passes;
`ResetAcmePassword` routes the credential through `web.fill_credential` and the
one-time value through `?newpw=`, exactly as the shipped sample does.

Acceptance criteria:

- `make deploy-samples` installs all six skill-bearing samples (the seventh
  sample directory, `web-checks/skill-graduation`, ships no document), and the
  six skill ids are pairwise distinct — asserted in the demo suite, with the
  four new ones named.
- `CheckServiceHealth` runs to completion parking **zero** confirmation cards,
  asserted by the demo script querying the session's frames for any
  `confirmation_request`.
- `CheckUserStatus` likewise parks zero cards, and reports a user's `locked`
  state and `last_modified` read off the rendered table.
- `LockUnlockUser` parks **exactly one** card with `approval_kind: "action"`
  whose `change_request.summary` names the origin, path and field; on approval
  the lock lands; `CheckUserStatus` re-run reports it.
- `ResetAcmePassword` parks **exactly one** card with `approval_kind: "flow"`
  and a `flow_intent` headline; the `newpw` value is masked in every result,
  evidence frame, card and durable record; the reset lands and is visible in
  `/api/users/{u}`.
- Running the four in sequence — health, status, lock, status — produces a
  transcript in which the final status check reports the change the lock made.
- A graduation dry-run of `LockUnlockUser` produces no credential hole
  (`<credential-reference>` appears nowhere in its authoring trace).

### R-8: Walkthroughs, demo scripts, and ADR-0008 compliance

Each of the four samples ships a `WALKTHROUGH.md` in the house shape —
prerequisites table, numbered live steps with the exact portal surface named
(**Chat** versus **Studio**, per SPEC-056), what the operator should see, and
the honest caveats — plus a `demo/demo.sh` that runs the same story
unattended against the deployed cluster and asserts it.

ADR-0008 is explicit that a shipped sample is only honest if its demo script
runs in the verification path, and it records that this is what did *not* happen
to the password-reset sample. So:

- Each `demo.sh` exits non-zero on any failed assertion, ends with a printed
  summary of what it proved, and calls `POST /internal/reset-demo` with `curl`
  and the R-1 header before it starts so a run is reproducible regardless of
  what the previous run left behind.
- A `samples/acme-admin/demo-suite.sh` runs all four in order and asserts the
  cross-skill verification step, which is the claim this whole slice makes.
- `make e2e` gains the suite. That target's script list is **hardcoded** at
  [`Makefile:196-199`](../../../Makefile), so a new script does not join it by
  existing; the list is edited explicitly, and the new entry is documented as
  depending on `make deploy-sample-app` having been run (the `e2e` target's
  existing prerequisite echo gains a line saying so, since today it names only
  `make deploy` and two port-forwards).

Acceptance criteria:

- All four `demo.sh` scripts and the suite pass against a deployed cluster, and
  each fails when its asserted behaviour is deliberately broken (spot-checked on
  the two card-count assertions and the cross-skill verification).
- `make e2e` runs the suite and reports `E2E_OK`.
- Every requirement R-1…R-7 maps to a named test or demo assertion in
  `docs/specs/SPEC-059-*/tasks.md`, per ADR-0008's traceability leg.
- Each `WALKTHROUGH.md` names the portal entry point it uses and does not
  instruct the reader to click anything the demo does not also exercise.

### R-9: Documentation

- `samples/README.md` gains an `acme-admin` section: what the app is, that it is
  the first sample to own an image, how to deploy it, and how it relates to
  `browser-check-target` (both exist; the older one still serves the three
  shipped samples until the rebase slice).
- `samples/acme-admin/README.md` is the app's own document: endpoints, seed
  data, the credential arrangement, the state model and its `replicas: 1`
  consequence, and how to write a new walkthrough against it.
- [`docs/guides/skills-guide.md`](../../guides/skills-guide.md) gains the
  read-only-skill pattern — what a skill with no `risk_class` looks like and why
  it parks nothing — which the guide cannot currently illustrate with any
  shipped example.
- [`docs/guides/studio-guide.md`](../../guides/studio-guide.md) already
  references the sample target; it gains the four-skill ladder as its
  development-session example set.
- [`docs/guides/tool-configuration.md`](../../guides/tool-configuration.md)
  activation checklists cross-reference the app as the dev target for `http.*`.
- `CHANGELOG.md`, `VERSION`, `docs/specs/README.md` and the delivery roadmap on
  delivery.

Acceptance criteria:

- Every internal link in the new and edited documents resolves (the repository
  has just paid a large price for links that do not).
- `samples/README.md` and the app README together let a new contributor deploy
  the app and run one walkthrough without reading a spec.
- The skills-guide's read-only section is illustrated by a shipped skill, not a
  hypothetical one.

## Non-Goals

- **Rebasing the three existing samples onto `acme-admin`.** The operator's
  stated sequence — app first, rebase later — and a deliberate unbundling: the
  rebase rewrites three `demo.sh` scripts, three walkthroughs, the
  `browser-check-demo.sh` e2e assertions and two shipped skill documents. Doing
  it here would make this slice unreviewable. It is the next slice (SPEC-060),
  and R-2 exists to make it a retarget.
- **Retiring `browser-check-target`.** It stays shipped and untouched. Whether
  it is removed after the rebase is SPEC-060's decision, not this one.
- **Persistent state, a database, multiple replicas, or a Helm chart.** R-1's
  in-memory store with a reseed endpoint is the design, not a compromise pending
  something better: a tutorial target's state should be reproducible on demand
  and vanish with the pod.
- **Any change to the three shipped samples, to `deploy-samples.sh`'s discovery
  or slug logic, or to the browser connector.** The slug rule is worked around
  by naming (R-7), not by changing the script — changing it would re-id every
  shipped sample skill.
- **An `http.*` tool surface.** That is SPEC-058, and this spec depends on it
  rather than restating it.
- **Composition.** SPEC-057 consumes this repertoire; nothing here declares a
  `composition` skill, because a composition of skills that do not yet exist
  cannot be demonstrated.
- **A CI workflow.** The repository deliberately has none; verification is
  `make verify` and `make e2e`.

## Impact

- products touched: **none**. No shipped product changes in this slice — which
  is the point of keeping SPEC-058 separate.
- samples touched: `samples/acme-admin/**` (new: app, deploy manifests, four
  sample dirs, five demo scripts), `samples/README.md`,
  `samples/deploy-samples.sh` (only if the R-4 discovery assertion requires a
  comment; no logic change).
- shared touched: `shared/platform-ops/gitops/sync-browser-credentials.sh`
  (R-3's second sink), `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env`
  (R-5's two allowlist entries and `GATEWAY_HTTP_ENABLED=true`).
- root touched: `Makefile` (three targets, the `e2e` script list, the `e2e`
  prerequisite echo, `make help` output).
- contracts touched: **none**.
- identity / policy / audit / execution safety impact: no new policy action, no
  new audit event type, no bundle edit. The app holds a real credential, so R-3
  (one generated value, two secret sinks, fail closed when skipped) and R-5's
  ingress NetworkPolicy are the safety content; R-1's header-gated reseed
  endpoint is the one place where "the agent could do this" is closed
  structurally rather than by instruction.
- living state docs to update on delivery: `samples/README.md`,
  `docs/guides/skills-guide.md`, `docs/guides/studio-guide.md`,
  `docs/guides/tool-configuration.md`, `docs/specs/README.md`,
  `docs/agentic-aiops-platform/delivery-roadmap.md`, `CHANGELOG.md`, `VERSION`.

## Open Questions

All five were resolved at approval on 2026-09-17, adopting the recommendation
recorded in the draft in every case. The original options are retained so the
decision stays auditable; from here a requirement changes only by agreement,
recorded in the changelog (the `approved`-spec rule).

- **OQ-1 — does `user-status` read the page or the API?** R-7 assigns it the
  browser, because the operator's requirement was a *web page* listing users and
  because the suite otherwise has no read-only browser skill. The alternative —
  `http.get /api/users/{u}` — makes both read-only skills HTTP and leaves the
  browser surface represented only by the mutating one. **Resolved: keep the
  browser**, and let `CheckServiceHealth` mention the API equivalent so a reader
  sees both.
- **OQ-2 — should `health-check` also assert through the browser?** A single
  skill that checks `/healthz` over HTTP and then the `/status` page over the
  browser teaches the two-surface comparison directly, but it mixes surfaces in
  one skill, which cuts against the single-target discipline SPEC-056/057 are
  about. **Resolved: no** — one surface per skill, and let the *composition* in
  SPEC-057 be where two surfaces meet.
- **OQ-3 — seed data realism.** Four users, one pre-locked, is enough for the
  ladder and small enough to assert on. Should the app also seed a
  recently-modified user so `last_modified` sorting is visible? **Resolved:
  yes**, one, with a fixed offset from `started_at` so assertions stay
  deterministic.
- **OQ-4 — where the walkthrough screenshots live.** The repository's
  `.qoder/*.png` evidence convention is gitignored (`*.png`), so walkthroughs
  cannot ship images. That is existing behaviour and this spec does not change
  it; noted because a "good walkthrough" instinctively wants diagrams, and the
  honest answer here is ASCII step tables. **Resolved: no change**; the
  walkthroughs use step tables, and live browser verification of each one is
  part of this slice's delivery gate rather than a shipped artefact.
- **OQ-5 — version slot**, inherited from SPEC-058 OQ-1. **Resolved: v0.39.0.**

## Changelog

- 2026-09-17: created as `draft` from the 2026-09-17 walkthrough-enrichment
  design discussion, carrying the operator's four decisions (build the app
  first and rebase later; a real `http.*` tool rather than a browser workaround;
  a stand-alone app with a root `make` target; all four skills now) and the name
  `acme-admin` in place of "sample portal".
- 2026-09-17: approved by the operator with all five open questions resolved as
  recommended — `user-status` reads the rendered page, `health-check` stays
  HTTP-only, a recently-modified user is seeded, walkthroughs ship step tables
  rather than images, and the version slot is v0.39.0.
- 2026-09-17: R-7's distinctness criterion corrected during implementation. It
  counted "seven samples … seven skill ids", derived from three shipped
  samples; only **two** shipped samples carry a `skill/*.md` document, because
  `web-checks/skill-graduation` graduates its skill at runtime rather than
  shipping one. The mounted set is therefore six ids, and
  `samples/acme-admin/demo-suite.sh` asserts six pairwise-distinct ids naming
  all four new ones. No requirement changed — the rule (every id distinct, the
  collision being a hard ConfigMap failure) is unchanged — only the count it
  was written against.
- 2026-09-17: delivered in **v0.38.0**, pulled in one release early alongside
  its SPEC-058 dependency and thereby collapsing the OQ-5 v0.39.0 slot recorded
  above. `make verify` green at 0.38.0 plus the app's own 110-test suite;
  deployed out-of-band with `make deploy-sample-app` (every `deploy.sh`
  assertion green, including the informational NetworkPolicy deny probe) and
  exercised by `demo-suite.sh`, the opt-in chat legs, `make e2e`, and a live
  browser pass over all four walkthroughs — including the rung-4 check that the
  confirmation page asked about `dave` reports `alice` from the store.
- 2026-09-17: pre-release documentation review scopes the reseed restriction
  precisely: the required header is unavailable to `http.get`/`http.post`,
  but it is not an authorization boundary against all agent capabilities
  (for example, approved browser JavaScript). Hiding the endpoint from
  skills and disabling OpenAPI are discoverability choices, not access control.
