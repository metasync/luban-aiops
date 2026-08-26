---
kind: build_system
name: Multi-Product Workspace Build System with Coordinated Image Tags and GitOps Overlays
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/Makefile
    - products/platform-gateway/Dockerfile
    - products/operator-portal/Dockerfile
    - VERSION
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
---

# Build System Overview

This repository is a multi-product workspace for an Agentic AIOps platform. There is no monorepo build tool (no Gradle, Bazel, Nx, etc.); instead the build system is built on **GNU Make** with shared fragments under `mk/`, one product per directory under `products/<name>/`, and Kubernetes deployment via **Kustomize overlays** under `shared/platform-ops/gitops/`.

## What system/approach is used

- **Top-level orchestration**: `Makefile` at the repo root declares cross-cutting targets (`sync`, `test`, `lint`, `build`, `push`, `verify`, `deploy`, `e2e`) that delegate to each product's own `Makefile`. It enumerates Python products (`PYTHON_PRODUCTS`) and image-bearing products (`IMAGE_PRODUCTS`).
- **Shared fragments** in `mk/`:
  - `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`). All values use `?=`, so command-line overrides always win.
  - `mk/image.mk` — container-image targets (`build`, `push`, `lint`) included by every product Makefile; computes `IMAGE_REF` as `luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>` (optionally re-tagged under `$(REGISTRY)/...`). Lint falls back to `docker run hadolint/hadolint` when `hadolint` is not installed locally.
  - `mk/python.mk` — Python targets using **uv** with frozen lockfiles: `uv sync --frozen` then `uv run pytest`, with OTLP exporters disabled during tests so tracing tests can stay active without network noise.
- **Base image**: `shared/base-images/base-uv/Dockerfile` builds a pinned `amazonlinux:2023-minimal` image with a pinned `uv` version and a non-root `app` user (uid 1000); Python interpreters are resolved per-product from `.python-version` via `UV_PYTHON_INSTALL_DIR=/app/.python`.
- **Versioning**: The root `VERSION` file is the single source of truth for the platform semver. `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which checks that every `products/*/pyproject.toml [project].version`, every `src/*/metadata.py` `SERVICE_VERSION`, any `__version__` in package roots, and the operator portal's Vite wiring all match `VERSION`. Drift fails the build.
- **Coordinated image tagging**: The root `make build` computes a single `IMAGE_TAG` once (pattern `<semver>-<prefix>[-<profile>]-<gitsha>`, or `-dirty-<timestamp>` for dirty trees) and passes it to every product build. After building, it writes `shared/platform-ops/gitops/dev-k8s/.images.env` with the coordinated tag for every service image, consumed by `make deploy`.
- **Deployment**: `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which calls `deploy-overlay.sh` plus a sequence of secret-provisioning scripts (delegation, audit, execution-signing, skills, incidents, sessions DB, OTel) and optionally reconciles Keycloak realm + portal OIDC client. Deployment uses Kustomize overlays enumerated in `OVERLAYS` (`dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`), validated by `make overlays` via `kustomize build --load-restrictor LoadRestrictionsNone`.
- **Verification gate**: `make verify` = `test` + `overlays` + `validate-policy` + `validate-version`; intended as the pre-commit/pre-push gate.
- **Policy management**: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into both gateway services' policy directories and the deployed base overlay; `make validate-policy` validates against a JSON schema via `uv run python ../../shared/shared-contracts/scripts/validate_policy.py`.
- **End-to-end**: `make e2e` runs three demo scripts under `shared/platform-ops/e2e/` against a deployed cluster after port-forwarding the gateway and identity-service.

## Key files and packages

- Root orchestrator: `Makefile`
- Shared build defaults: `mk/defaults.mk`
- Shared image targets: `mk/image.mk`
- Shared Python targets: `mk/python.mk`
- Base image: `shared/base-images/base-uv/Dockerfile`
- Product examples: `products/agent-platform/Makefile`, `products/platform-gateway/Dockerfile`, `products/operator-portal/Dockerfile`
- Version enforcement: `VERSION`, `shared/shared-contracts/scripts/validate_version.py`
- Policy sync/validation: `shared/shared-contracts/policies/policy-default.yaml`, `shared/shared-contracts/scripts/validate_policy.py`
- Deployment entrypoint: `shared/platform-ops/gitops/dev-k8s/deploy.sh`
- Kustomize overlays: `shared/platform-ops/gitops/dev-k8s/kustomization.yaml` and `runtime-profiles/*`

## Architecture and conventions

1. **Per-product isolation with shared fragments**: Each product has a tiny `Makefile` that only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. This keeps product-specific logic minimal and centralizes behavior in `mk/`.
2. **Frozen dependency resolution**: Python dependencies are managed via `uv` with `uv.lock` files; `sync` and `test` always use `--frozen`, ensuring reproducible environments.
3. **Single coordinated image tag**: All images produced by `make build` share one `IMAGE_TAG` derived from `VERSION` + optional prefix/profile + git SHA, guaranteeing that all services in a deployment are mutually compatible.
4. **Non-root containers**: The base image creates an `app` user (uid 1000) and `USER app` is inherited by product images.
5. **GitOps-first deployment**: Overlays are rendered via `kustomize build` as part of verification; deployment is driven by shell scripts under `shared/platform-ops/gitops/`, not by imperative `kubectl apply`.
6. **Secret provisioning is scripted**: Secrets for token delegation, audit ingestion, execution signing, skills, incidents, sessions DB, and OTel are provisioned by dedicated scripts invoked from `deploy.sh`, with `SKIP_*_SECRETS=true` flags for CI environments where secrets are injected externally.
7. **Operator portal is a multi-stage Node+nginx build**: The portal Dockerfile builds a Vite SPA in a `node:22-alpine` stage and serves it via `nginxinc/nginx-unprivileged:1.27-alpine`; the build context is the repository root so `vite.config.ts` can read the root `VERSION` file at build time.

## Conventions and constraints

- **GNU make required**: The root Makefile comment states it requires GNU make (default on macOS and Linux).
- **Docker required**: Image build/lint targets require `docker`; lint falls back to running `hadolint/hadolint` in a container if the binary is not installed locally.
- **uv required for Python products**: `sync` and `test` depend on `uv`; Python products must have `pyproject.toml` and `uv.lock`.
- **Image platform default**: `IMAGE_PLATFORM ?= linux/amd64`; override to `linux/arm64` for native local/kind builds on arm64 hosts.
- **Registry push gated**: Images are tagged locally by default; pushing requires setting `REGISTRY=<registry>` so the extra tag is created before `docker push`.
- **Kind auto-load**: Setting `AUTO_LOAD_KIND=true` (with `KIND_CLUSTER_NAME` set) loads all built images into the named kind cluster after `make build`.
- **Version lockstep enforced**: `make validate-version` exits non-zero if any product `pyproject.toml`, `metadata.py` `SERVICE_VERSION`, `__version__`, or portal Vite wiring does not match `VERSION`.
- **Policy bundle must be synced**: `make sync-policy` copies the canonical `policy-default.yaml` into both gateway services and the deployed overlay; consumers are expected to keep them in sync.
- **Overlays must render cleanly**: `make overlays` runs `kustomize build` against each overlay path and fails the build if rendering fails.
- **E2E prerequisites**: `make e2e` requires a deployed cluster and port-forwards for `platform-gateway` (18083) and `identity-service` (18081).
- **No CI pipeline files in this snapshot**: No GitHub Actions workflows were found in `.github/`; the `verify` target is documented as the pre-commit/pre-push gate and would be the natural CI entry point.