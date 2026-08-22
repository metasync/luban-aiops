---
kind: build_system
name: 'Monorepo Build & Release System: Root Makefile, Shared Fragments, Coordinated Image Tags, and GitOps Deploy'
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - products/agent-platform/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## What system/approach is used

The repository uses a **GNU Make-driven monorepo build** centered on a root `Makefile` that orchestrates per-product builds via shared fragments under `mk/`. Each product in `products/<name>/` declares a tiny Makefile that includes `../../mk/image.mk` (container image targets) and `../../mk/python.mk` (uv-based dependency sync + pytest). The root Makefile enumerates all Python and image products and runs them in parallel loops. Container images are built with Docker against a shared base image (`shared/base-images/base-uv`) and tagged with a coordinated tag derived from the single-source `VERSION` file plus git SHA and optional profile suffix. Deployment is GitOps-driven through Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/`, invoked via `make deploy` which wraps `deploy.sh`.

## Key files and packages

- `Makefile` — root orchestration: lists `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, computes `IMAGE_TAG`, defines `build`, `push`, `test`, `lint`, `overlays`, `verify`, `deploy`, `e2e`, `sync-policy`, `validate-version`, `base-images`, `clean`.
- `mk/defaults.mk` — single source of overridable defaults: `IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`, `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, `BASE_UV_IMAGE`, `BASE_UV_TAG`, `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`.
- `mk/image.mk` — shared Docker image targets (`build`, `push`, `lint`); resolves `IMAGE_REF` as `luban-aiops/<name>:<tag>` or `<REGISTRY>/luban-aiops/<name>:<tag>`; falls back to `hadolint` docker-run if not installed locally.
- `mk/python.mk` — shared uv + pytest targets: `uv sync --frozen` then `uv run pytest` with OTLP exporters disabled for test isolation.
- `products/*/Makefile` — minimal per-product files that set `IMAGE_NAME` and include the two shared fragments.
- `products/*/Dockerfile` — uniform pattern: `FROM luban-aiops/base-uv:al2023`, copy `.python-version pyproject.toml uv.lock README.md src`, `RUN uv sync --frozen --no-dev`, `EXPOSE 8000`, `CMD ["uv", "run", "<entrypoint>"]`.
- `shared/base-images/base-uv/Dockerfile` — pinned AL2023 + uv + Python version base image.
- `VERSION` — single semver source of truth (e.g. `0.8.1`).
- `shared/shared-contracts/scripts/validate_version.py` — enforces lockstep between `VERSION`, every `products/*/pyproject.toml` `[project] version`, every `src/*/metadata.py` `SERVICE_VERSION`, any `__version__`, and `operator-portal/web-ui/app.js` `PLATFORM_VERSION`.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — renders overlay via `deploy-overlay.sh`, then provisions secrets (delegation, audit, skills, incidents, OTel), sessions DB, and reconciles Keycloak realm / portal OIDC client.
- `shared/platform-ops/gitops/dev-k8s/.images.env` — written by root `make build`; consumed by the overlay to pin image tags.

## Architecture and conventions

### Layered makefile composition
The root Makefile delegates to per-product Makefiles, which delegate to shared fragments in `mk/`. This keeps each product's Makefile to ~10 lines while centralizing image building, linting, and Python tooling. Defaults live in `mk/defaults.mk` and can be overridden at the command line (e.g. `make build IMAGE_PLATFORM=linux/arm64 REGISTRY=ghcr.io/me`).

### Coordinated image tagging
Image tags are computed once at the root level using the formula `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for uncommitted changes). The same `IMAGE_TAG` is passed to every product's `make build`, ensuring all services ship together. After building, the root Makefile writes `IMAGE_TAG` and per-service image names into `shared/platform-ops/gitops/dev-k8s/.images.env`, which the Kustomize overlay consumes so deployments always reference the exact built artifacts.

### Base image strategy
All Python services derive from `shared/base-images/base-uv:al2023`, built with pinned `UV_VERSION` and `PYTHON_VERSION` from `mk/defaults.mk`. Production images install dependencies with `uv sync --frozen --no-dev`, guaranteeing reproducible installs from `uv.lock`.

### Version lockstep enforcement
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which parses `VERSION` and checks it against:
- Every `products/*/pyproject.toml` `project.version`
- Every `products/*/src/*/metadata.py` `SERVICE_VERSION = ...`
- Any `__version__` in package roots
- `operator-portal/web-ui/app.js` `PLATFORM_VERSION`
A mismatch causes the verification gate to fail.

### Policy synchronization
A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. `make validate-policy` validates it against a JSON schema via `shared/shared-contracts/scripts/validate_policy.py`.

### GitOps deployment flow
`make deploy` calls `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which:
1. Renders the overlay via `deploy-overlay.sh` (kustomize).
2. Provisions secrets through dedicated `sync-*-secrets.sh` scripts (delegation, audit, skills, incidents, OTel).
3. Creates the sessions database via `sync-sessions-db.sh`.
4. Optionally reconciles the Keycloak realm and portal OIDC client.
Overlays under `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai,mutating-dev}` select runtime profiles.

### Verification gate
`make verify` composes `test overlays validate-policy validate-version`, intended as the pre-commit/pre-push gate. It runs every product's pytest suite, validates all Kustomize overlays render, validates the canonical policy, and enforces version lockstep.

### E2E and kind integration
`make e2e` runs demo scripts under `shared/platform-ops/e2e/` against a deployed cluster. `make build` supports `AUTO_LOAD_KIND=true` (with `KIND_CLUSTER_NAME`) to auto-load all built images into a local kind cluster after building.

## Conventions and constraints

- **Single source of truth for platform version**: `VERSION` must be valid semver (`MAJOR.MINOR.PATCH`); all products must match it exactly, enforced by `make validate-version`.
- **Frozen Python dependencies**: All products use `uv sync --frozen` against `uv.lock`; no transitive drift is allowed.
- **Uniform Dockerfile layout**: Every service follows the same `FROM luban-aiops/base-uv:al2023` → copy → `uv sync --frozen --no-dev` → `EXPOSE 8000` → `CMD ["uv", "run", "<entrypoint>"]` pattern.
- **Coordinated tagging**: Images are never tagged ad-hoc; the root `IMAGE_TAG` (derived from `VERSION` + git SHA ± dirty flag) is propagated to all products.
- **Overlay-first deployment**: Runtime configuration lives in Kustomize overlays under `shared/platform-ops/gitops/`; the `.images.env` state file pins built image diggs/tags for reproducibility.
- **Policy as code**: The canonical policy YAML is copied to consumers; consumers do not maintain their own copies independently.
- **Verification gate**: `make verify` (tests + kustomize render + policy validation + version lockstep) is the documented pre-commit/pre-push entry point.
- **Base image pinning**: `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION` are pinned in `mk/defaults.mk`; `latest` tags are explicitly avoided.
- **Registry abstraction**: Setting `REGISTRY` re-tags and pushes images to an alternate registry; otherwise images stay local under `luban-aiops/*`.