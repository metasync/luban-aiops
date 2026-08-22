---
kind: build_system
name: Makefile-driven monorepo build with uv, Docker images, and Kustomize GitOps overlays
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
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
---

## Build system overview

The Luban AIOps platform is a Python microservices monorepo built entirely through GNU Make. There is no CI pipeline file in this repository; the root `Makefile` defines a single verification gate (`make verify`) that is intended to run identically locally and under any CI (the Makefile comments state it is "Forge-agnostic" and the pre-commit/pre-push gate). Each product under `products/` is an independent Python package with its own `pyproject.toml`, `uv.lock`, `Dockerfile`, and a tiny Makefile that only sets `IMAGE_NAME` and includes shared fragments from `mk/`.

## Core components

### Shared Makefile fragments (`mk/`)

- `mk/defaults.mk` — single source of overridable build settings via `?=` assignment: target platform (`IMAGE_PLATFORM ?= linux/amd64`), coordinated image tag prefix/profile (`IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`), optional registry re-tag target (`REGISTRY`), auto-load into kind (`AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`), and pinned base-image versions (`BASE_UV_IMAGE=luban-aiops/base-uv:al2023`, `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`). Guarded against double inclusion with `LUBAN_DEFAULTS_INCLUDED`.
- `mk/image.mk` — container image targets included by every product Makefile. Builds with `docker build --platform $(IMAGE_PLATFORM) -t luban-aiops/$(IMAGE_NAME):$(IMAGE_TAG)`, optionally re-tags to `$(REGISTRY)/luban-aiops/...` when `REGISTRY` is set, pushes via `docker push`, and lints the Dockerfile with `hadolint` (falls back to `docker run hadolint/hadolint` if not installed).
- `mk/python.mk` — Python dependency and test targets: `uv sync --frozen` then `uv run pytest`. Enforces frozen lockfiles for reproducible installs.

### Root orchestration (`Makefile`)

- Declares two lists: `PYTHON_PRODUCTS` (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) and `IMAGE_PRODUCTS` (same plus operator-portal/web-ui).
- Computes a coordinated `IMAGE_TAG` once per invocation using the root `VERSION` file (semver), optional profile, git short SHA, and a `-dirty-YYYYMMDDHHMMSS` suffix when the working tree has uncommitted changes.
- `make build` first builds the shared base image (`base-images`), then iterates `IMAGE_PRODUCTS` calling each product's `make build IMAGE_TAG=... IMAGE_PLATFORM=...`, writes all resulting image refs into `shared/platform-ops/gitops/dev-k8s/.images.env`, and optionally loads them into a local kind cluster when `AUTO_LOAD_KIND=true`.
- `make push` re-tags and pushes every product image to `$(REGISTRY)`.
- `make verify` runs the full gate: `test` → `overlays` → `validate-policy` → `validate-version`.
- `make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies the dev-k8s Kustomize overlay and provisions secrets (delegation, audit, skills, incidents, OTel) and Keycloak realm/client reconciliation.

### Per-product Makefiles

Each product Makefile is minimal — e.g. `products/platform-gateway/Makefile` only sets `IMAGE_NAME := platform-gateway` and includes `../../mk/image.mk` and `../../mk/python.mk`. This pattern keeps product-specific logic out of the root Makefile while preserving a uniform interface.

### Container images

- All service Dockerfiles use the shared base image `FROM luban-aiops/base-uv:al2023` (built from `shared/base-images/base-uv/Dockerfile` with pinned `UV_VERSION` and `PYTHON_VERSION`).
- Images copy `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, and `src/`, then run `uv sync --frozen --no-dev` at build time.
- The runtime entrypoint is `uv run <service-name>` (e.g. `uv run platform-gateway`).
- The operator portal uses a separate nginx-based Dockerfile producing `web-ui`.

### Versioning and policy synchronization

- Single source of truth for the platform release version is the root `VERSION` file (currently `0.7.0`). The coordinated image tag prefixes this semver.
- `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root to enforce that the VERSION file stays in lockstep with product and portal versions.
- Policy files are synchronized from one canonical location (`shared/shared-contracts/policies/policy-default.yaml`) to consumers via `make sync-policy`, which copies it into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. Validation is done via `make validate-policy` running `shared/shared-contracts/scripts/validate_policy.py`.

### GitOps / deployment overlays

- Kustomize overlays live under `shared/platform-ops/gitops/`: `dev-k8s/` (base + per-service overlays) and `runtime-profiles/{dashscope,deepseek,openai}/` (profile-specific configmaps/secrets).
- `make overlays` validates every overlay with `kustomize build --load-restrictor LoadRestrictionsNone`.
- `deploy.sh` applies the overlay and calls helper scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-sessions-db.sh`, `sync-otel-secrets.sh`, `reconcile-luban-realm.sh`, `reconcile-portal-oidc-client.sh`) to provision environment-specific resources. Secrets provisioning can be skipped via `SKIP_*_SECRETS=true` flags for CI environments.

## Conventions and constraints observed

- Every Python product must expose `sync` and `test` targets via `include ../../mk/python.mk`; tests run inside the product directory so `uv` resolves that product's `pyproject.toml`/`uv.lock`.
- Dependency resolution is locked: `uv sync --frozen` is used everywhere (build, test, and development), preventing drift between environments.
- Image tags follow a coordinated scheme: `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`, computed once at the root and propagated to all products via `IMAGE_TAG`.
- Multi-platform builds default to `linux/amd64` but can be overridden per-invocation (e.g. `make build IMAGE_PLATFORM=linux/arm64`); the comment explicitly notes `linux/arm64` is for native local/kind builds on arm64 hosts.
- No `latest` tags are used anywhere; all base images and uv/python versions are pinned in `mk/defaults.mk`.
- The `verify` target is the authoritative pre-commit/pre-push gate and must pass before pushing code; it combines unit tests, Kustomize overlay validation, policy schema validation, and version lockstep checks.
- Deployment is GitOps-first: `make deploy` renders Kustomize overlays and relies on external secret-provisioning scripts rather than embedding secrets in manifests.