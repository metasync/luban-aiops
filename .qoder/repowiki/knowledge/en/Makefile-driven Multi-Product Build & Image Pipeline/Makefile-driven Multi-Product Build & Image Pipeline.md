---
kind: build_system
name: Makefile-driven Multi-Product Build & Image Pipeline
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/python.mk
    - mk/image.mk
    - products/platform-gateway/Makefile
    - products/operator-portal/Makefile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/.images.env
    - shared/platform-ops/dashboards/validate_dashboards.py
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - shared/shared-contracts/scripts/validate_password_policy.py
---

## Approach

The Luban Agentic AIOps Platform uses a **GNU Make-based monorepo build system** with shared fragments under `mk/` and per-product thin Makefiles under `products/<name>/`. There is no CI workflow YAML in `.github/workflows`; the root `Makefile` declares itself forge-agnostic (`make verify` is the pre-commit/pre-push gate) and is intended to run identically locally and under any CI.

Python products are built with **uv** (lockfile-frozen), containerized via **Docker**, and deployed through **kustomize** overlays under `shared/platform-ops/gitops/`. The operator portal is an npm/Vite SPA whose tests and production build are invoked from its product Makefile.

## Key Files

- `Makefile` — master orchestrator: product lists, coordinated image tagging, policy sync/validation, overlay rendering, dashboard validation, e2e demo runner, and the `verify` gate.
- `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` + `pytest` with OTLP exporters disabled for test output cleanliness.
- `mk/image.mk` — shared `build` / `push` / `lint` (hadolint with docker-run fallback) targets; computes `IMAGE_REF` from `IMAGE_NAME` + `IMAGE_TAG` + optional `REGISTRY`.
- `products/*/Makefile` — thin wrappers that set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk` (operator-portal only includes `image.mk` and adds `test` / `web-build` for the Vite SPA).
- `shared/base-images/base-uv/Dockerfile` — shared base image built by `make base-images`.
- `VERSION` — single source of truth for the platform semver used in coordinated image tags.
- `shared/platform-ops/gitops/` — kustomize overlays validated by `make overlays`.
- `shared/platform-ops/dashboards/validate_dashboards.py` — offline dashboard schema/metric-reference validator invoked by `make validate-dashboards`.
- `shared/shared-contracts/scripts/` — policy, version, secret-vocabulary, password-policy validators invoked from the root Makefile.

## Architecture & Conventions

### Product taxonomy
Products are classified into two root-level lists:
- `PYTHON_PRODUCTS` — agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway (each has `pyproject.toml` + `uv.lock` + pytest suite).
- `IMAGE_PRODUCTS` — same as above plus `operator-portal` (SPA served by nginx).

Root targets iterate these lists: `make sync`, `make test`, `make lint`, `make build`, `make push` dispatch to each product's Makefile.

### Coordinated image tagging
The root `Makefile` computes one `IMAGE_TAG` once and passes it to every product build. Tag format: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, `<...>-dirty-<YYYYMMDDHHmmSS>` for dirty trees. The tag prefix/profile default to `dev-k8s` (overridable via `IMAGE_TAG_PREFIX` / `IMAGE_TAG_PROFILE`). After building, the root writes `shared/platform-ops/gitops/dev-k8s/.images.env` with all nine service images keyed by env var names consumed by the dev-k8s deploy script.

### Shared base image
`make base-images` builds `luban-aiops/base-uv:<BASE_UV_TAG>` from `shared/base-images/base-uv/Dockerfile` with pinned `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` (from `mk/defaults.mk`). All Python product Dockerfiles inherit this base.

### Policy distribution
Canonical policy bundles live in `shared/shared-contracts/policies/`. `make sync-policy` copies them into every consumer location (tool-gateway, platform-gateway, gitops base). Consumers then validate against JSON schemas via scripts under `shared/shared-contracts/scripts/`.

### Version lockstep
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file matches every product's declared version.

### Secret vocabulary lockstep
`make validate-secret-vocabulary` enforces that the secret-literal registry is consistent across agent-platform, tool-gateway, and skills-hub.

### Password policy contract
Per SPEC-062 R-2, `password-policy.yaml` is authored once beside the policy bundle and synced into tool-gateway; `make validate-password-policy` pins the connector floor to it.

### GitOps overlay validation
`make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on every overlay listed in `OVERLAYS` (dev-k8s plus runtime-profiles variants).

### Dashboard validation
`make validate-dashboards` runs `shared/platform-ops/dashboards/validate_dashboards.py` to parse OpenObserve dashboards, validate envelope/panel schemas, and assert every metric reference resolves to an emitted `OTEL_MIRROR_FAMILIES` stream (SPEC-065 R-3).

### Portal frontend
The operator portal is not a uv product. Its Makefile defines `test` (runs `npm test` in `web-ui/app`) and `web-build` (runs `tsc --noEmit && vite build`). `make verify` delegates to both via `portal-test` (SPEC-063 R-8c); Vitest fails on zero tests so there is no skip path.

### E2E & demo harness
`make e2e` runs the scripts under `shared/platform-ops/e2e/` plus `samples/acme-admin/demo-suite.sh` against a deployed cluster. `make deploy-samples` / `undeploy-samples` installs tutorial skills out-of-band from the base overlay (SPEC-050 R-11).

### Kind integration
When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` auto-loads all nine images into the named kind cluster after building.

## Conventions & Constraints

- **Forge-agnostic gate**: `make verify` is the canonical pre-commit/pre-push gate and must pass identically locally and under any CI (stated in the root Makefile header).
- **Frozen dependencies**: Python products use `uv sync --frozen`; no dependency resolution at build time.
- **Pinned base image versions**: `mk/defaults.mk` explicitly pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; comments state "never latest".
- **Single source of truth for image tag**: the root `Makefile` computes `IMAGE_TAG` once and propagates it to every product build; individual product Makefiles do not compute their own tags.
- **Version lockstep enforced**: `make validate-version` runs a script that compares the root `VERSION` with every product's declared version.
- **Policy bundles are canonical-copy-only**: consumers never edit policies directly; they receive copies via `make sync-policy`.
- **Overlay render check required**: `make overlays` validates every kustomize overlay before deployment.
- **Dashboard artifact validity enforced**: `make validate-dashboards` rejects dashboards whose metric references do not resolve to emitted OTEL families (SPEC-065 R-3).
- **Portal build included in verify**: `make verify` runs both the portal's Vitest suite and its production Vite build; no integration skip toggle is accepted as a release pass (SPEC-063 R-8c).
- **Image lint falls back gracefully**: `make lint` tries `hadolint` first, then `docker run hadolint/hadolint`, then skips if neither is available.
- **Registry re-tagging**: setting `REGISTRY` causes `make push` to re-tag local images to `<REGISTRY>/luban-aiops/<name>:<tag>` before pushing.