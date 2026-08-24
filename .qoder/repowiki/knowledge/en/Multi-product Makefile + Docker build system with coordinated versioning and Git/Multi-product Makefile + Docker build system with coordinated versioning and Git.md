---
kind: build_system
name: Multi-product Makefile + Docker build system with coordinated versioning and GitOps overlays
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - products/operator-portal/Makefile
    - products/operator-portal/Dockerfile
---

## What system/approach is used

The workspace uses a **Makefile-driven multi-product build** layered on top of **Docker images**, **uv (Python dependency manager)**, and **Kustomize-based GitOps overlays**. There is no CI pipeline file in the repository; the root `Makefile` declares itself "Forge-agnostic" and intended to run identically locally and under any CI. Each product under `products/` has its own small `Makefile` that includes shared fragments from `mk/`, so the same targets (`build`, `push`, `test`, `sync`, `lint`) are available per-product and from the workspace root.

## Key files and packages

- `Makefile` — workspace root orchestrator: defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, computes a coordinated `IMAGE_TAG`, delegates per-product builds, runs `verify` (tests + kustomize overlay render + policy validation + version lockstep), and wraps `deploy.sh` for dev-k8s deployment.
- `mk/defaults.mk` — single source of overridable build settings via `?=` (e.g. `IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`).
- `mk/image.mk` — shared container-image targets (`build`, `push`, `lint` with hadolint fallback). Requires each including Makefile to set `IMAGE_NAME`; supports overriding `IMAGE_CONTEXT` and `IMAGE_DOCKERFILE`.
- `mk/python.mk` — shared Python targets using `uv sync --frozen` and `uv run pytest` with OTel exporters disabled during tests.
- `shared/base-images/base-uv/Dockerfile` — shared base image built by `make base-images`: Amazon Linux 2023 minimal, pinned `uv` (default 0.12.1) installed via installer script, non-root `app` user (uid 1000), no system Python — interpreter resolved from each product's `.python-version`.
- `VERSION` — single source of truth for platform semver; consumed by the root Makefile tag computation and enforced by `validate_version.py`.
- `shared/shared-contracts/scripts/validate_version.py` — enforces that every product's `pyproject.toml` `[project] version`, `src/*/metadata.py` `SERVICE_VERSION`, optional `__version__`, and operator-portal Vite wiring all match `VERSION`.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — deploys the dev-k8s Kustomize overlay plus idempotent secret provisioning scripts (delegation, audit, skills, incident, sessions DB, OTel) and optional Keycloak realm/client reconciliation.
- Per-product `Dockerfile`s (e.g. `products/agent-platform/Dockerfile`, `products/operator-portal/Dockerfile`) — thin wrappers around the shared fragments; operator-portal uses a two-stage build (node:22-alpine → nginxinc/nginx-unprivileged) with repo-root context so vite.config.ts can read `../../../../VERSION`.
- `products/*/Makefile` — tiny files setting `IMAGE_NAME` and including `../../mk/image.mk` and `../../mk/python.mk`.

## Architecture and conventions

### Coordinated image tagging
The root `Makefile` computes one `IMAGE_TAG` once per invocation as `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` when the working tree has uncommitted changes). All product images are built with this same tag, then written into `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy step references exactly the images just built. The tag prefix/profile default to `dev-k8s` / empty but are overridable via `IMAGE_TAG_PREFIX` and `IMAGE_TAG_PROFILE`.

### Product decomposition
Each service is an independent Python package with `pyproject.toml` + `uv.lock`, a `Dockerfile`, and a `Makefile`. The root `Makefile` enumerates them in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists and iterates over them for `sync`, `test`, `lint`, `build`, `push`. New products must be added to both lists to participate in workspace-wide commands.

### Base image strategy
All backend services derive from `luban-aiops/base-uv:al2023`, which pins uv and Python versions via build args (`BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`). Products declare their interpreter in `.python-version`; `uv sync` resolves it deterministically. Production images use `uv sync --frozen --no-dev` to install only runtime dependencies.

### Policy synchronization
A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. Validation runs against the JSON schema via `make validate-policy`.

### Version lockstep
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which reads `VERSION` and checks:
- Every `products/*/pyproject.toml` `[project] version`
- Every `products/*/src/*/metadata.py` `SERVICE_VERSION = ...`
- Any `products/*/src/*/__init__.py` declaring `__version__`
- Operator-portal's `vite.config.ts` contains the expected pattern that reads `../../../../VERSION` and defines `__PLATFORM_VERSION__` at build time (SPEC-023 R-1)

Any drift causes `validate-version` to fail, blocking `make verify`.

### Deployment flow
`make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which runs `deploy-overlay.sh` (Kustomize) and then sequentially calls secret-sync scripts guarded by `SKIP_*_SECRETS=true` environment variables for CI environments. A `reconcile-portal-oidc-client.sh` step is gated by `RECONCILE_OIDC_PORTAL_CLIENT` (default true).

### Local kind workflow
Setting `AUTO_LOAD_KIND=true` after `make build` auto-loads all built images into a kind cluster named by `KIND_CLUSTER_NAME`. This enables local development without pushing to a registry.

## Conventions and constraints

- **GNU make required**: documented in the root Makefile header; all targets assume GNU make semantics.
- **Frozen Python deps**: `uv sync --frozen` is used everywhere; `uv.lock` is the authoritative dependency manifest and must not be mutated by hand.
- **No system Python in containers**: the base image installs uv only; interpreters are fetched into `/app/.python` per product.
- **Non-root containers**: base image creates `app` user (uid 1000); product images inherit it.
- **Single version source**: `VERSION` is the only place to bump the release; `make validate-version` enforces propagation to all products.
- **Coordinated tags**: all images share one `IMAGE_TAG` computed once per `make build` invocation; there is no per-product tagging.
- **Registry push gating**: `make push` only re-tags and pushes when `REGISTRY` is set; otherwise images stay local under `luban-aiops/<name>:<tag>`.
- **Dockerfile lint fallback**: `hadolint` is preferred; if unavailable, `docker run --rm -i hadolint/hadolint` is attempted; if neither exists, lint is skipped with a message.
- **Overlay rendering gate**: `make verify` runs `kustomize build` against each overlay in `OVERLAYS` (`dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`) and fails on render errors.
- **E2E demos**: `make e2e` requires a deployed cluster plus port-forwards to `platform-gateway:18083` and `identity-service:18081`; it runs three demo scripts under `shared/platform-ops/e2e/`.
- **Operator portal build context**: because the Vite config reads `../../../../VERSION`, the operator-portal product sets `IMAGE_CONTEXT := ../..` so the Docker build context is the repository root.