# Build System and Deploy Pipeline

How the workspace builds, tags, and ships: the layered Makefile architecture, the
coordinated image tag, the `build → push → deploy` handoff, and the policy/version
sync-and-validate routines that guard a release. This is the contributor's map of the
machinery; the deep deployer reference lives in the
[dev-k8s overlay README](../../shared/platform-ops/gitops/dev-k8s/README.md), the
container base decision in
[Python Container Strategy](../workspace/python-container-strategy.md), and version
policy in [CONTRIBUTING](../../CONTRIBUTING.md#versioning).

Everything runs through GNU `make` (default on macOS and Linux) and is
forge-agnostic: the same targets run locally and under any CI. Required tools are
`make`, `docker`, `uv`, and `kustomize` (for the overlay render checks).

## The three layers

Build logic is split so that root invocations and standalone per-product
invocations resolve the *same* configuration:

| Layer | File(s) | Owns |
|---|---|---|
| Orchestration | root `Makefile` | Cross-cutting concerns: the coordinated image tag, `build`/`push` fan-out, policy & version validation, the `verify` gate, and the `deploy` pipeline |
| Shared fragments | `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk` | Reusable per-product targets and the single source of overridable build config |
| Product routines | `products/<name>/Makefile` | Sets `IMAGE_NAME` (and context overrides) and includes the fragments |

The split is deliberate: **`mk/defaults.mk` holds configuration only** (every value
uses `?=` so a command-line override always wins), while the root `Makefile` and the
other fragments hold processing logic. `defaults.mk` guards against double inclusion
(`LUBAN_DEFAULTS_INCLUDED`) because both the root `Makefile` and `mk/image.mk`
include it in one parse.

Run `make help` at the root for the cross-cutting targets, or
`make -C products/<name> help` for a single product's routines.

### `mk/` fragments

- **`mk/defaults.mk`** — pinned, overridable build settings: `IMAGE_PLATFORM`
  (default `linux/amd64`, the deploy target; use `linux/arm64` for native kind builds
  on arm64 hosts), `IMAGE_TAG_PREFIX` / `IMAGE_TAG_PROFILE`, `REGISTRY`,
  `AUTO_LOAD_KIND` / `KIND_CLUSTER_NAME`, and the shared base-image pins
  `BASE_UV_IMAGE` / `BASE_UV_TAG` / `BASE_UV_UV_VERSION` / `BASE_UV_PYTHON_VERSION`.
  Pins are for reproducible builds — **never `latest`**.
- **`mk/image.mk`** — `build`, `push`, `lint` for one product. The including
  Makefile must set `IMAGE_NAME`; it may set `IMAGE_CONTEXT` (default `.`) and
  `IMAGE_DOCKERFILE` (default `$(IMAGE_CONTEXT)/Dockerfile`). `lint` runs `hadolint`,
  falling back to `docker run hadolint/hadolint`, and skips cleanly if neither is
  available.
- **`mk/python.mk`** — `sync` and `test` for a `uv` product (`uv sync --frozen`, then
  `uv run pytest` under no-op OTEL exporters). See
  [Testing Strategy](testing-strategy.md) for what the suite covers.

### Per-product Makefile anatomy

A product Makefile is a few lines: set the image name, include the fragments.

```makefile
IMAGE_NAME := tool-gateway

include ../../mk/image.mk
include ../../mk/python.mk
```

Two things to know when adding or editing one:

- **The directory name is not always the image name.** `agent-platform` builds
  `agent-service`, `identity-broker` builds `identity-service`, and
  `operator-portal` builds `web-ui`. `IMAGE_NAME` is authoritative.
- **`operator-portal` is the exception.** It is a SPA, not a `uv` product, so it
  includes only `mk/image.mk`, and its build context is the repo root
  (`IMAGE_CONTEXT := ../..`, `IMAGE_DOCKERFILE := Dockerfile`) because the image
  needs more than the product directory. It is covered by `make portal-test`, not
  `make test` (see [Testing Strategy](testing-strategy.md#tier-4--operator-portal-spa-gate-portal-test)).

## The coordinated image tag

All product images ship under **one** tag computed once in the root `Makefile` from
the `VERSION` file, so a rollout is atomic and traceable:

```
<semver>-<prefix>[-<profile>]-<gitsha>            # clean tree
<semver>-<prefix>[-<profile>]-<gitsha>-dirty-<ts> # uncommitted changes
```

`<semver>` is the root `VERSION` file (the single source of truth — do not hard-code
it anywhere), `<prefix>` is `IMAGE_TAG_PREFIX` (default `dev-k8s`), `<profile>` is the
optional `IMAGE_TAG_PROFILE`, and `<gitsha>` is `git rev-parse --short HEAD`. A
standalone `make -C products/<name> build` without an explicit `IMAGE_TAG` falls back
to just the short SHA (or `dev` outside a git tree); the root `make build` always
passes its computed tag down to each product.

Override on the command line, for example:

```bash
make build IMAGE_TAG_PROFILE=experiment          # tag a throwaway build set
make build IMAGE_PLATFORM=linux/arm64            # native arm64/kind build
make base-images BASE_UV_UV_VERSION=<pinned>     # bump the shared base uv pin
```

## Build → push → deploy

```
make base-images   # build shared/base-images/base-uv  (prerequisite of build)
make build         # build every image under the coordinated tag; write .images.env
make push          # push each image (set REGISTRY to re-tag for a remote registry)
make deploy        # apply the dev-k8s overlay at the built tag; provision secrets
```

- **`make base-images`** builds the shared `luban-aiops/base-uv:al2023` base from
  `shared/base-images/base-uv/Dockerfile`. It is a prerequisite of `make build`, so a
  normal build refreshes it automatically. The base owns the non-root `app` user and
  the `uv`/Python environment contract — see
  [Python Container Strategy](../workspace/python-container-strategy.md).
- **`make build`** builds every `IMAGE_PRODUCTS` entry with the coordinated tag, then
  writes the build state to `shared/platform-ops/gitops/dev-k8s/.images.env`
  (`IMAGE_TAG` plus one `<SERVICE>_IMAGE=` line per workload). With
  `AUTO_LOAD_KIND=true` (and `KIND_CLUSTER_NAME` set) it also `kind load`s the images
  into a local cluster.
- **`make deploy`** wraps `deploy.sh`, which sources `.images.env`, applies the
  overlay at the explicit tag, waits for rollout, provisions the per-service secrets
  (delegation, audit ingest, execution signing/handoff, skills, incident, browser,
  connector credentials — each idempotent with a `SKIP_*` toggle for CI), initializes
  databases, and reconciles the Keycloak client. If `.images.env` is missing, deploy
  fails with "Run `make build` first" rather than guessing a tag.

`.images.env` is the handoff contract between build and deploy: **never apply a raw
`kustomize build` of the overlay** — the placeholders only resolve to real tags
through the deploy path. The deployer's deep reference (rollout, runtime profiles,
restore interlocks) is the
[dev-k8s overlay README](../../shared/platform-ops/gitops/dev-k8s/README.md).

## Policy, contract, and version sync

Cross-service contracts are authored once and synced to every consumer, then
validated in the gate. The canonical policy bundles live under
`shared/shared-contracts/policies/`; `make sync-policy` copies them into each
gateway's packaged fallback and the dev-k8s ConfigMap source.

| Target | Purpose |
|---|---|
| `make sync-policy` | Copy the canonical policy + password-policy bundles to all consumer locations |
| `make validate-policy` | Validate the canonical bundle against its JSON schema |
| `make validate-policy-scenarios` | Evaluate recorded scenario expectations through both engines (api + tools) |
| `make policy-diff CANDIDATE=<path>` | Per-(role, action) outcome transitions between canonical and a candidate bundle |
| `make validate-version` | Enforce version lockstep between `VERSION`, every product, and the portal |
| `make validate-secret-vocabulary` | Enforce secret-literal lockstep across agent-platform / tool-gateway / skills-hub |
| `make validate-password-policy` | Validate the password-policy contract and pin the connector floor to it |

Version lockstep is a release invariant: every `products/*/pyproject.toml`, every
`metadata.py` `SERVICE_VERSION`, and the portal's `PLATFORM_VERSION` must equal the
root `VERSION`. See [CONTRIBUTING — Versioning](../../CONTRIBUTING.md#versioning) for
the semver rules and the release-cut workflow (`CHANGELOG.md` `Unreleased` →
versioned section → tag).

## The verification gate

`make verify` is the pre-commit / pre-push gate. Beyond the product test suites and
the disposable-Postgres integration proofs (covered in
[Testing Strategy](testing-strategy.md)), it runs the overlay render check
(`overlays`), the dashboard validation, and every policy/version/contract validator
above. Run it before any commit that touches code, manifests, or policy.

## Conventions

- Config lives in `mk/defaults.mk`; processing logic lives in the Makefiles and
  fragments. Add a new overridable knob to `defaults.mk` with `?=`, not inline.
- Pins are explicit and reproducible — never `latest` for the base image, `uv`, or
  Python.
- Never hard-code the platform version in docs, manifests, or scripts; read `VERSION`
  (or `$(PLATFORM_VERSION)` in make). Hard-coded versions drift the moment the next
  release cuts.
- Keep the non-root `app` user and the deployment `securityContext`; no service may
  regress to root.
- Adding a product: create `products/<name>/` with a minimal Makefile (set
  `IMAGE_NAME`, include the fragments), then add it to `PYTHON_PRODUCTS` and/or
  `IMAGE_PRODUCTS` in the root `Makefile` and to the `.images.env` block in `build`.

## Related documentation

- [Testing Strategy](testing-strategy.md) — the `verify` gate's test tiers
- [Python Container Strategy](../workspace/python-container-strategy.md) — the shared base image decision
- [CONTRIBUTING](../../CONTRIBUTING.md) — versioning, spec-driven workflow, change principles
- [dev-k8s overlay README](../../shared/platform-ops/gitops/dev-k8s/README.md) — deployer's deep reference
- [Configuration Reference](configuration-reference.md) — runtime environment variables and secrets
- [Architecture Overview](architecture-overview.md) — what the built workloads are and how they connect
