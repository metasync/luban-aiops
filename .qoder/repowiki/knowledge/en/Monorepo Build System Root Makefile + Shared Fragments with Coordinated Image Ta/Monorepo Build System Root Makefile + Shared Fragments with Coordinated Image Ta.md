---
kind: build_system
name: 'Monorepo Build System: Root Makefile + Shared Fragments with Coordinated Image Tags and GitOps Overlays'
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - products/operator-portal/Dockerfile
    - VERSION
---

## What system/approach is used

The repository uses a **GNU Make-driven monorepo build system** centered on a root `Makefile` that delegates to per-product Makefiles under `products/<name>/`. Python products use **uv** (with frozen `uv.lock`) for dependency resolution, and all container images are built with **Docker** from per-product `Dockerfile`s. Deployment is driven by **Kustomize overlays** under `shared/platform-ops/gitops/`, orchestrated through a `deploy.sh` script that also provisions secrets and reconciles Keycloak clients. There is no CI pipeline file in this snapshot; the root `make verify` target is explicitly documented as the pre-commit/pre-push gate intended to run identically locally and in CI.

## Key files and packages

- **Root orchestrator**: `Makefile` — declares product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), computes a coordinated `IMAGE_TAG`, runs `sync/test/lint/build/push`, validates policy and version lockstep, renders Kustomize overlays, and invokes `deploy.sh`.
- **Shared fragments**:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*` versions).
  - `mk/image.mk` — shared `build`/`push`/`lint` targets using `docker build --platform $(IMAGE_PLATFORM)`; resolves `IMAGE_REF` against `luban-aiops/` registry or an optional `REGISTRY` override.
  - `mk/python.mk` — shared `sync test` targets running `uv sync --frozen` then `uv run pytest` with OTel exporters disabled during tests.
- **Base image**: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal with pinned `uv` (0.12.1) and Python 3.12, running as non-root `app` user.
- **Per-product Makefiles** — tiny stubs that set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk` (e.g. `products/platform-gateway/Makefile`, `products/agent-platform/Makefile`).
- **Version lockstep enforcement**: `shared/shared-contracts/scripts/validate_version.py` — reads root `VERSION` as the single source of truth and checks every `products/*/pyproject.toml`, `src/*/metadata.py` (`SERVICE_VERSION`), `src/*/__init__.py` (`__version__`), and the operator portal's Vite wiring.
- **Deployment scripts**: `shared/platform-ops/gitops/dev-k8s/deploy.sh` wraps overlay rendering and secret provisioning scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-sessions-db.sh`, `sync-otel-secrets.sh`, `reconcile-luban-realm.sh`, `reconcile-portal-oidc-client.sh`).
- **Portal build**: `products/operator-portal/Dockerfile` — multi-stage Node 22 build copying the repo root so `vite.config.ts` can read `../../../../VERSION` at build time, then serving via nginx.

## Architecture and conventions

1. **Coordinated image tagging**: The root `Makefile` computes one `IMAGE_TAG` per invocation using the formula `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for dirty trees). All images produced by `make build` share this tag, and `.images.env` under `shared/platform-ops/gitops/dev-k8s/` records the exact tags consumed by the dev overlay.
2. **Product decomposition**: Each microservice lives under `products/<name>/` with a uniform layout (`src/<package>/`, `tests/`, `pyproject.toml`, `uv.lock`, `Dockerfile`, `Makefile`). The root Makefile enumerates them in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` — new services must be added to both lists.
3. **Fragmented Makefiles**: Product Makefiles contain only `IMAGE_NAME := <name>` plus two `include` lines. All logic lives in `mk/*.mk`, making cross-cutting changes (image platform, lint tooling, uv flags) a single edit.
4. **Frozen Python builds**: Both development (`uv sync --frozen`) and production Docker layers (`RUN uv sync --frozen --no-dev`) pin dependencies to `uv.lock`; there is no runtime pip install.
5. **Single-version policy**: `VERSION` at the repo root is the authoritative semver. `make validate-version` enforces that every product's `pyproject.toml`, service metadata module, and portal build-time injection match it.
6. **Policy synchronization**: A canonical `policy-default.yaml` under `shared/shared-contracts/policies/` is copied into each consumer (`products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`) via `make sync-policy`.
7. **GitOps-first deployment**: `make deploy` calls `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders Kustomize overlays and runs idempotent secret-provisioning scripts guarded by `SKIP_*_SECRETS=true` environment variables for CI environments.
8. **Local kind integration**: Setting `AUTO_LOAD_KIND=true` after `make build` auto-loads all images into a named kind cluster (`KIND_CLUSTER_NAME` required), enabling local end-to-end testing via `make e2e`.
9. **Verification gate**: `make verify` chains `test`, `overlays` (kustomize build check for all overlays), `validate-policy`, and `validate-version` — designed as the pre-commit/pre-push gate.

## Conventions and constraints

- **GNU make required**: The root Makefile header states it requires GNU make (default on macOS/Linux); POSIX sh is used for portability.
- **Image platform default**: `IMAGE_PLATFORM ?= linux/amd64`; overrides propagate from root to per-product builds via `$(IMAGE_PLATFORM)`.
- **Registry convention**: Images are tagged `luban-aiops/<name>:<tag>` locally; setting `REGISTRY=<host>` re-tags and pushes to `<REGISTRY>/luban-aiops/<name>:<tag>`.
- **Non-root containers**: The base image creates an `app` user (uid 1000) and sets `USER app`; product images inherit this.
- **No `latest` tags**: `mk/defaults.mk` comments enforce pinned values — never `latest` — for reproducible builds.
- **Overlay list is explicit**: `OVERLAYS := dev-k8s runtime-profiles/dashscope runtime-profiles/deepseek runtime-profiles/openai runtime-profiles/mutating-dev` — adding a new overlay requires editing this list.
- **Secret provisioning is opt-in in CI**: Each `sync-*secrets.sh` script respects a `SKIP_*_SECRETS=true` env var so CI can skip interactive secret setup.
- **Portal build context**: The operator portal Dockerfile copies the repo root so `vite.config.ts` can resolve `../../../../VERSION`; changing this path requires updating both the Dockerfile and the version validator's regex.
- **E2E prerequisites**: `make e2e` expects `make deploy` to have completed and port-forwards for `platform-gateway:18083` and `identity-service:18081` to be active.