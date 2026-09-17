# SPEC-059 Plan: `acme-admin` — A Real Sample Application and Its Skill Suite

## Delivered adjustments

The design below records the original plan. Delivery uses a thin shared-fragment
Makefile, not a fixed line count, and runs in-cluster HTTP probes and reseeding
through `kubectl exec` in the tool-gateway container, not temporary curl pods.
Shared integration includes the root Makefile and runtime profile as well as
credential synchronization. See `tasks.md` for the completed implementation and
`spec.md`'s changelog for the narrowed reseed-security claim.

## Approach

Build the application first, prove it in isolation, then write the four skills
against it, then the walkthroughs and demos that assert them. No product code
changes at all, so nothing in this slice can regress a shipped service — the
risk is entirely in whether the sample is honest and whether the deploy path
works.

Five stages, each independently checkable:

1. **The application** (`samples/acme-admin/app/`): store, auth, JSON API, HTML
   pages, startup fail-closed, tests. Verifiable with `make -C … test` and a
   local `uv run` before any cluster exists.
2. **Packaging and deployment**: Dockerfile on the shared `base-uv` image, the
   eight-line `app/Makefile`, the `deploy/` kustomization, the credential second
   sink, the runtime-profile allowlist entries, and `make deploy-sample-app`
   with its assertions.
3. **The four skills**, in ladder order, so each one is authored against a
   behaviour the previous one already proved.
4. **Walkthroughs and demos**, one pair per sample plus the suite, each calling
   the header-gated reseed first.
5. **Documentation**, last, because it describes what shipped.

The two decisions that shape everything else:

- **One store, two surfaces.** A module-level `Store` object holds the users and
  the revision counter; the JSON API and the server-rendered HTML pages are two
  routers over it. That is what makes cross-skill verification possible at all —
  `LockUnlockUser` mutates over HTTP and `CheckUserStatus` reads the same row
  back off a rendered page — and it is what makes the suite one story instead of
  four demos.
- **The HTML forms POST through `fetch` and render in place.** The current
  target's pages are pure client-side fiction. These pages must really mutate,
  but they must also preserve the two SPEC-051 asymmetries and the element-id
  semantics the shipped skills read. Rendering the result into the same element
  the static page used (`#admin-login-status`, `#reset-status`) satisfies both:
  the mutation is real and the selector contract is unchanged.

## Design Per Requirement

### R-1: The application

- affected files: `samples/acme-admin/app/src/acme_admin/{__init__,store,auth,api,pages,main}.py`,
  `samples/acme-admin/app/tests/`, `pyproject.toml`, `uv.lock`, `.python-version`
- chosen approach:
  - `store.py` — a `Store` class holding `users: dict[str, User]`, a monotonic
    `revision: int`, a `last_reset` record and `started_at`. `User` is a
    dataclass with `username`, `full_name`, `email`, `role`, `locked`,
    `password_changed_at`, `last_modified`, `revision`. Mutations go through
    three methods (`lock`, `unlock`, `set_password`) that each bump the global
    revision, stamp the user with it, and return the user; a no-op raises a
    module-level `NoOpMutation` the router turns into a 409, and an unknown
    username raises `UnknownUser` → 404. `reseed()` restores the exact seed.
  - Identifier resolution accepts **username or email** (`alice` and
    `alice@example.com` address the same row), because the shipped samples use
    email-shaped identifiers and R-2 exists to make their rebase a retarget.
  - `auth.py` — two mechanisms over one password: HTTP Basic for the JSON API
    (a FastAPI dependency comparing against `ACME_ADMIN_PASSWORD` with
    `hmac.compare_digest`), and a random opaque session token in an
    `HttpOnly`/`SameSite=Lax` cookie for the HTML pages, held in a server-side
    set. The session is what lets the browser flow's login survive navigation,
    and it is deliberately not a JWT: a tutorial target that signs tokens teaches
    the wrong thing about where authority comes from.
  - `api.py` — the JSON router. `/healthz` and `/api/hello` unauthenticated;
    every `/api/users*` behind Basic auth. `/internal/reset-demo` behind the
    `X-Luban-Demo-Reset` header, named in no skill document.
  - `pages.py` — the HTML router rendering `string.Template` documents. Templates
    are module constants, not files, so the Dockerfile copies one tree and there
    is no template-search path to configure. `string.Template`'s `$` delimiters
    are chosen over f-strings because the preserved JavaScript is full of `{}`.
  - `main.py` — `create_app()`, the lifespan that reads `ACME_ADMIN_PASSWORD`
    and raises a `RuntimeError` naming the secret and the sync script when it is
    absent or empty, and `run()` for the `acme-admin` console script.
- `/api/hello`'s `name` is validated against `^[A-Za-z0-9 _.-]{1,64}$` and
  refused with 422 outside it, so it cannot carry markup into a rendered page.
- alternatives rejected: Jinja2 templates (a new dependency and a template
  directory for six small pages); SQLite or a PVC (R-1's in-memory store is the
  design — a tutorial target that needs provisioning stops being one); a
  single-page app (the skills read server-rendered HTML, and an SPA would make
  `web.extract` race hydration).

### R-2: Rebase compatibility

- affected files: `samples/acme-admin/app/src/acme_admin/pages.py`,
  `samples/acme-admin/app/tests/test_pages.py`
- chosen approach: the six routes are declared with the trailing-slash shapes
  the current target serves (`/`, `/status`, `/admin/`, `/admin/users/`,
  `/admin/users/reset/`, `/admin/users/reset/done/`), and the rendered documents
  carry every id in the contract with the same semantics. A test walks the
  rendered HTML of each page with `html.parser` and asserts the full id set for
  that page, so a template edit cannot silently break a shipped skill's
  selectors. The test also asserts `reset-timestamp`, which the spec's 28-id
  list omits but the current target serves — being a superset costs nothing and
  keeps the retarget honest.
- The auto-login timer is kept verbatim in intent: a 100 ms `setInterval` that
  calls `adminDoLogin()` once both fields are non-empty, which now issues the
  real `fetch` POST. The reset page's pre-fill from `?user=&newpw=` is kept
  verbatim, including the "does NOT auto-submit" comment, and `doReset` now
  issues a real `fetch` POST whose response is rendered into `#reset-status`.
- `/admin/users/` without a session returns 302 to `/admin/`, matching the
  acceptance criterion.
- alternatives rejected: keeping the pages static and adding a separate "real"
  UI — two UIs over one store is exactly the confusion this slice removes.

### R-3: One generated password, two secret sinks

- affected files: `shared/platform-ops/gitops/sync-browser-credentials.sh`
- chosen approach: the generated branch gains a third random value
  (`ACME_PASSWORD`) written into the credential-sets JSON as an `acme-admin`
  entry **and** into a new `acme-admin-credentials` secret as
  `ACME_ADMIN_PASSWORD`. The `BROWSER_CREDENTIAL_SETS_FILE` branch reads the
  `acme-admin` entry out of the operator's file with a small `python3 -c` JSON
  read and writes the same secret from it, failing with a message naming the
  missing key when the operator's file has no `acme-admin` entry — because the
  app cannot start without it and a silent default would be worse.
  `SKIP_BROWSER_CREDENTIALS=true` still exits 0 having written nothing, and the
  app then fails closed at startup.
- Both sinks are created before the tool-gateway rollout restart the script
  already performs, so one invocation leaves the cluster consistent.
- alternatives rejected: a second generator script (two random values, and the
  two surfaces could disagree); `kubectl create secret` from the app's own
  deploy script (the app would then own a credential it also consumes, and a
  redeploy would rotate it under a running gateway).

### R-4: Stand-alone packaging

- affected files: `samples/acme-admin/app/{Makefile,Dockerfile,pyproject.toml,.python-version,README.md}`,
  `samples/acme-admin/app/tests/test_packaging.py`
- chosen approach: the eight-line product Makefile with `../../../mk/` includes,
  so `build`/`push`/`lint`/`sync`/`test` all work standalone. The Dockerfile
  mirrors `products/audit-service/Dockerfile` — `COPY --chown=app:app` the lock
  and `src`, `uv sync --frozen --no-dev`, `EXPOSE 8080`, `CMD ["uv","run","acme-admin"]`
  — and needs no `USER` line because `base-uv` already ends as `app` (uid 1000).
  The app is **not** added to `IMAGE_PRODUCTS`/`PYTHON_PRODUCTS`.
- `test_packaging.py` asserts the R-4 discovery criterion by running the same
  `find -type d -name skill` the deploy script runs, rooted at `samples/`, and
  checking the result contains exactly the four new sample dirs plus the three
  shipped ones and nothing under `app/`, `deploy/` or `tests/`. It also asserts
  the four derived skill ids are pairwise distinct and distinct from the three
  shipped ids — the slug-collision guard, made mechanical rather than a naming
  convention somebody has to remember.
- alternatives rejected: joining `IMAGE_PRODUCTS` (both root loops are hardcoded
  to `products/$$p`, so it would mean refactoring the root Makefile's iteration
  for one tutorial image, and it would put a tutorial image in `make build`'s
  duration and `.images.env` contract); a bare `docker build` in the deploy
  script (a second build convention with its own tag logic).

### R-5: Manifests and the runtime-profile allowlist

- affected files: `samples/acme-admin/deploy/{kustomization,deployment,service,networkpolicy}.yaml`,
  `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env`
- chosen approach: a self-contained kustomization with no namespace of its own
  (`make deploy-sample-app` passes `-n`), a Deployment labelled `app:
  acme-admin` with `replicas: 1`, `strategy: Recreate` and the reason in a
  comment, both probes on `/healthz`, resource requests/limits, the hardened
  securityContext and `ACME_ADMIN_PASSWORD` via `secretKeyRef` with no default.
  The Service is `ClusterIP` on 8080. The NetworkPolicy is ingress-only,
  `podSelector: app: acme-admin`, one `from` entry on `app: tool-gateway` and
  port 8080 — the sidecar shares the tool-gateway pod, so one rule covers both
  surfaces.
- `browser.env` gains `http://acme-admin:8080` to `GATEWAY_BROWSER_ALLOW_ORIGINS`
  and a new `GATEWAY_HTTP_ALLOW_ORIGINS` with the same value, plus
  `GATEWAY_HTTP_ENABLED=true` and `GATEWAY_HTTP_CREDENTIAL_SETS` pointing at the
  already-mounted browser credential file. `dev-k8s/base` names nothing.
- alternatives rejected: a new runtime profile (an operator would have to apply
  two profiles to run one tutorial); putting the origin in the base (SPEC-050
  R-11 — the base never names a sample).

### R-6: `make deploy-sample-app`

- affected files: `Makefile`, `samples/acme-admin/deploy.sh`
- chosen approach: three `.PHONY` targets beside `deploy-samples`, with
  `deploy_sample_app` as a two-line alias for `deploy-sample-app` so both the
  hyphenated house spelling and the requested underscore spelling work, and both
  carrying `## ` help text. `undeploy-sample-app` delegates with `ACTION=undeploy`.
- The script is deploy-then-assert, in the R-6 order: `kustomize build`
  pre-flight; compute or read `IMAGE_TAG` (`.images.env` when `make build` wrote
  it, otherwise the same shell expression the root Makefile uses, so there is no
  second divergent tag path); `$(MAKE) -C samples/acme-admin/app build`;
  `kind load` under the same `AUTO_LOAD_KIND`/`KIND_CLUSTER_NAME` conditions;
  `kustomize build | kubectl apply -n` plus a `kubectl set image` to the built
  tag and `rollout status`; then the assertions, each a small shell function
  that `die`s naming itself. In-cluster HTTP assertions run through
  `kubectl run --rm -i curl-<pid>` on `curlimages/curl` rather than a
  port-forward, so the script has no host-port requirement and no background
  process to leak.
- The `e2e` target's prerequisite echo gains a `make deploy-sample-app` line.
- alternatives rejected: a `make` target with inline shell (the assertions are
  too long to live in a recipe, and `deploy-samples.sh` already sets the
  script-beside-target convention); `kubectl exec` into the tool-gateway pod
  (that image has no curl, and depending on it couples the sample to a product
  image's contents).

### R-7: The four skills

- affected files: `samples/acme-admin/{health-check,user-status,lock-unlock-user,password-reset}/skill/*.md`
- chosen approach: the ladder table in R-7 exactly. Frontmatter per skill:
  - `CheckServiceHealth.md` — `title`, `description`, `tags`, `version`. **No**
    `web_target`, **no** `risk_class`: those are browser-flow keys and a skill
    that never touches the browser must not declare them.
  - `CheckUserStatus.md` — `web_target: http://acme-admin:8080/`, no
    `risk_class`, which ingestion defaults to `read`. Declaring a target on a
    read skill is the teaching point: `web_target` is target discipline, not
    approval.
  - `LockUnlockUser.md` — `risk_class: write`, no `web_target`. Valid since
    SPEC-055 R-3 decoupled them, and this is the first shipped skill to exercise
    that decoupling without a `kind: executable_flow`.
  - `ResetAcmePassword.md` — `web_target`, `risk_class: write`, `flow_intent`.
- Body shape follows the shipped `ResetUserPassword.md`: Purpose, Preconditions,
  Procedure (numbered, tool-named), Interpretation, Tutorial notes.
- Naming: `ResetAcmePassword.md`, not `ResetUserPassword.md`, because
  `deploy-samples.sh`'s id excludes the category directory and would collide
  byte-identically with the shipped `samples/password-reset-resetuserpassword`.
  Titles and tags are framed around `acme-admin` and the user-administration
  console; the shipped sample keeps its `admin-portal` framing.
- Gradability: `LockUnlockUser`'s body is `{"locked": true}`, a non-secret
  scalar, so `parameterize_for_trace` leaves no hole; `ResetAcmePassword` routes
  the credential through `web.fill_credential` and the one-time value through
  `?newpw=`.
- alternatives rejected: naming the file `ResetUserPassword.md` and changing the
  slug rule (would re-id every shipped sample skill); giving `CheckServiceHealth`
  a `web_target` for symmetry (it would declare a browser flow it never opens).

### R-8: Walkthroughs and demos

- affected files: four `WALKTHROUGH.md`, four `README.md`, five `demo/*.sh`
  (`demo-suite.sh` at the sample root), `Makefile`
- chosen approach: each `demo.sh` is self-contained and starts by reseeding over
  `kubectl run … curl -X POST -H 'X-Luban-Demo-Reset: 1'`, so a run is
  reproducible regardless of what the previous one left. Assertions are
  `curl`/`kubectl`-based and deterministic; the card-count assertions query the
  platform-gateway for the session's frames and count `confirmation_request`,
  which is the only way to prove "parks zero cards" rather than assert it. The
  chat legs stay opt-in behind `RUN_CHAT_LEG=true`, matching the shipped samples,
  so `make e2e` is deterministic.
- `demo-suite.sh` runs the four in ladder order and then re-runs
  `CheckUserStatus`'s underlying read to assert the lock landed — the
  cross-skill verification that is this slice's whole claim.
- The `make e2e` hardcoded list gains `$(SAMPLES_DIR)/acme-admin/demo-suite.sh`.
- alternatives rejected: making the chat legs mandatory (a model in the loop
  makes `make e2e` non-deterministic, which is why the shipped samples gate
  theirs).

### R-9: Documentation

- affected files: `samples/README.md`, `samples/acme-admin/README.md`,
  `docs/guides/skills-guide.md`, `docs/guides/studio-guide.md`,
  `docs/guides/tool-configuration.md`
- chosen approach: the app README is the operator's entry point (endpoints, seed
  data, the credential arrangement, the state model and its `replicas: 1`
  consequence, how to write a new walkthrough). `samples/README.md` gains an
  `acme-admin` section that states plainly both targets exist and why.
  `skills-guide.md` gains the read-only-skill pattern illustrated by
  `CheckServiceHealth` — a shipped skill, not a hypothetical one.
- Every relative link is checked mechanically before delivery; the repository
  has just paid a large price for links that do not resolve.

## Sequencing And Dependencies

1. R-1 application + its test suite — depends on nothing.
2. R-2 page/id contract tests — depends on stage 1.
3. R-4 packaging (Dockerfile, `app/Makefile`, packaging tests) — depends on
   stage 1.
4. R-3 credential second sink — depends on nothing, but must land before the
   first deploy.
5. R-5 manifests + `browser.env` — depends on stage 3 (the image name) and
   stage 4 (the secret name).
6. R-6 `make deploy-sample-app` — depends on stages 3–5.
7. **First live deploy and assertion run** — depends on stage 6, and on SPEC-058
   being implemented for the HTTP legs.
8. R-7 skills — depends on stage 7 (they are authored against observed
   behaviour, not intended behaviour).
9. R-8 walkthroughs and demos — depends on stage 8.
10. **Browser verification of every walkthrough** — depends on stage 9.
11. R-9 documentation — depends on stages 8–10.

SPEC-058 is a hard dependency for stages 7–9: two of the four skills cannot
exist without `http.get`/`http.post`. It is delivered first, at v0.38.0.

## Test Strategy

- unit tests: `samples/acme-admin/app/tests/` under `uv run pytest` via the
  shared `mk/python.mk` fragment — the R-1 store/API suite (health keys and
  types, hello echo and pattern refusal, the seeded set, each mutation bumping
  `last_modified` **and** `revision`, 404 and 409, auth required on
  `/api/users*` and absent on `/healthz` and `/api/hello`, `reset-demo` refusing
  without the header and restoring the exact seed with it), the R-2 rendered-id
  contract suite, and the R-4 packaging/slug suite.
- contract tests: none — no shared-contract change in this slice.
- integration / overlay validation: `kustomize build samples/acme-admin/deploy`
  in the deploy script's pre-flight (the `make overlays` loop prefixes
  `$(GITOPS_DIR)/` and cannot reach `samples/`); `make overlays` still green with
  the `browser.env` additions; a grep asserting `dev-k8s/base` contains no
  `acme-admin` string. Live validation is the deploy script's own assertions plus
  the five demo scripts under `make e2e`, and — because a walkthrough that has
  not been walked is a hypothesis — a live browser pass through each of the four
  walkthroughs against the deployed cluster, with the portal surfaces named in
  each one actually exercised.

## Rollout And Migration

- deployment or configuration changes required: none for the platform.
  `make deploy` is unchanged and works exactly as before with no sample app
  present. Activating the suite is two commands — `make deploy-sample-app` then
  `make deploy-samples` — and the `browser-dev` runtime profile carries the
  allowlist entries, so a cluster that does not apply that profile is untouched.
- backward compatibility notes: `browser-check-target` and the three shipped
  samples stay exactly as they are. The one shared file this slice edits is
  `sync-browser-credentials.sh`, and its change is additive: the two existing
  credential sets are still generated with the same names and shapes, so an
  existing cluster re-running the script gains a third set and a new secret
  without losing anything. An operator supplying `BROWSER_CREDENTIAL_SETS_FILE`
  without an `acme-admin` entry gets a loud failure naming the missing key
  rather than a broken app — that is the only behaviour change, and it is
  deliberate, because the alternative is a silent default password.
- rollback approach: `make undeploy-sample-app` removes the Deployment, Service,
  NetworkPolicy and the `acme-admin-credentials` secret and leaves every platform
  resource and `tool-gateway-browser-credentials` untouched. The allowlist
  entries are GitOps state and are removed by reverting `browser.env`, not by
  the script. Reverting the whole slice is a `git revert`: no product code, no
  schema, no persisted state.
