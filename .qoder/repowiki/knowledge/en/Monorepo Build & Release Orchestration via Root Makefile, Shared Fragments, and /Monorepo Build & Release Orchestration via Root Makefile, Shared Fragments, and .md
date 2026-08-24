---
kind: build_system
name: Monorepo Build & Release Orchestration via Root Makefile, Shared Fragments, and GitOps Overlays
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
    - shared/base-images/base-uv/Dockerfile
    - products/platform-gateway/Makefile
---

## What system/approach is used

The workspace uses a **Makefile-driven monorepo build system** centered on a root `Makefile` that orchestrates per-product Python builds (via `uv`), container image creation (via `docker`), policy synchronization, Kustomize overlay validation, and coordinated deployment to Kubernetes. There is no CI configuration in this repository; the root Makefile is explicitly designed as a "forge-agnostic" gate (`make verify`) intended to run identically locally and under any CI provider.

Python dependencies are managed per product with `uv` using frozen lockfiles (`uv sync --frozen`). Container images are built with Docker, sharing a common base image (`shared/base-images/base-uv`, based on Amazon Linux 2023 + pinned Python/uv versions). Deployment targets are expressed as Kustomize overlays under `shared/platform-ops/gitops/`, with a dev overlay plus runtime-profile overlays (dashscope, deepseek, openai, mutating-dev).

## Key files and packages

- `Makefile` — master entry point; defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), computes coordinated `IMAGE_TAG`, delegates per-product `sync/test/lint/build/push`, runs `overlays`, `validate-policy`, `validate-version`, and wraps `deploy.sh`.
- `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`); included by both root and per-product fragments.
- `mk/image.mk` — shared Docker image targets (`build`, `push`, `lint` with hadolint fallback) consumed by every product Makefile; sets `IMAGE_REF` naming convention `luban-aiops/<name>:<tag>`.
- `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `uv run pytest` with OTel exporters disabled during tests.
- `products/*/Makefile` — minimal wrappers that set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`.
- `VERSION` — single source of truth for platform semver; read by root Makefile and enforced by `validate_version.py`.
- `shared/shared-contracts/scripts/validate_version.py` — enforces version lockstep across `VERSION`, every `products/*/pyproject.toml`, each product's `src/*/metadata.py` (`SERVICE_VERSION`), package `__init__.py` `__version__`, and operator portal Vite wiring.
- `shared/shared-contracts/scripts/validate_policy.py` — validates canonical policy bundle against JSON schema.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — orchestrated deploy script invoked by `make deploy`; applies overlay, then provisions secrets (delegation, audit, skills, incidents, sessions DB, OTel) and reconciles Keycloak realm + portal OIDC client.
- `shared/platform-ops/gitops/dev-k8s/.images.env` — state file written by `make build` containing the coordinated tag and per-service image refs consumed by the overlay.
- `shared/base-images/base-uv/Dockerfile` — shared base image built by `make base-images`.

## Architecture and conventions

1. **Two-level Makefile design**: The root Makefile owns cross-cutting concerns (coordinated tagging, overlay checks, policy/version validation, e2e demos). Each product has a tiny Makefile that only declares `IMAGE_NAME` and includes shared fragments from `mk/`. This lets products be built standalone (`make -C products/<name>`) or via the root aggregator.

2. **Coordinated image tagging**: `IMAGE_TAG` is computed once at the root as `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`, where semver comes from `VERSION`, prefix/profile come from `IMAGE_TAG_PREFIX`/`IMAGE_TAG_PROFILE`, and git SHA/timestamp reflect clean/dirty tree state. All images produced by `make build` share this tag.

3. **Image state file**: After building all images, `make build` writes `.images.env` under `shared/platform-ops/gitops/dev-k8s/` with `IMAGE_TAG` and one `*_IMAGE` variable per service (agent-service, platform-gateway, tool-gateway, identity-service, audit-service, skills-hub, incident-service, web-ui). The deploy script reads this file to render overlays with consistent image references.

4. **Policy synchronization**: A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. Consumers validate it via `make validate-policy`.

5. **Version lockstep enforcement**: `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which parses `VERSION` and asserts every product's `pyproject.toml` version, `SERVICE_VERSION` in `metadata.py`, optional `__version__` in package roots, and that the operator portal's Vite config reads `VERSION` at build time (SPEC-023). Any drift fails the verification gate.

6. **Kustomize overlay validation**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on each overlay in `OVERLAYS` (dev-k8s plus runtime profiles) to catch rendering errors before deployment.

7. **Local kind integration**: When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all built images into the named kind cluster after building them.

8. **Per-product structure**: Every Python product follows the same layout: `src/<service>/`, `tests/`, `Dockerfile`, `Makefile`, `pyproject.toml`, `uv.lock`, `.python-version`. Services expose a consistent internal structure (`app.py`, `main.py`, `core/config.py`, `core/metrics.py`, `core/observability.py`, `core/telemetry.py`, `schemas/`, `services/`, `api/routes/`).

## Conventions and constraints

- **GNU make required**: The root Makefile header states it requires GNU make (default on macOS/Linux).
- **No `latest` tags**: `mk/defaults.mk` comments explicitly require pinned values for reproducible builds — never `latest`.
- **Frozen dependency resolution**: Python products use `uv sync --frozen`, enforcing exact pinning from `uv.lock`.
- **Single source of truth for version**: `VERSION` is the authoritative platform semver; `make validate-version` enforces that all products stay in lockstep.
- **Image naming convention**: Images are tagged `luban-aiops/<name>:<tag>` locally; when `REGISTRY` is set they are re-tagged to `<registry>/luban-aiops/<name>:<tag>` before push.
- **Verification gate**: `make verify` aggregates `test`, `overlays`, `validate-policy`, and `validate-version`; it is documented as the pre-commit/pre-push gate and must pass locally and in CI.
- **Deploy prerequisites**: `make deploy` expects a running cluster with `kubectl` context pointing to the target; it deploys the `dev-k8s` overlay and provisions secrets via helper scripts, failing if required environment variables (e.g. `OO_ROOT_USER_EMAIL/OO_ROOT_USER_PASSWORD` for OTel) are missing unless skipped via `SKIP_*_SECRETS` flags.
- **Multi-target platform builds**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64` for native arm64 host/kind builds); the base image and all product images honor this setting.