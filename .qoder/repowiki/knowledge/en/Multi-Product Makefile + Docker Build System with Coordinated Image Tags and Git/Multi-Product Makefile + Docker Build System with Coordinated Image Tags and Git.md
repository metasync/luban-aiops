---
kind: build_system
name: Multi-Product Makefile + Docker Build System with Coordinated Image Tags and GitOps Deployment
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
    - products/agent-platform/Makefile
    - products/operator-portal/Makefile
    - products/agent-platform/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - shared/shared-contracts/policies/policy-default.yaml
---

## Overview

The Luban AIOps repository uses a **Makefile-driven, multi-product build system** centered on a root `Makefile` that orchestrates per-product Python builds (via `uv`), container image creation (via `docker`), policy validation, GitOps overlay rendering (`kustomize`), and coordinated deployment to a Kubernetes cluster. There are no CI pipeline files in `.github/workflows`; the verification gate (`make verify`) is designed to be forge-agnostic and run identically locally and in any CI.

## Core Architecture

### Root orchestration (`Makefile`)
- Declares two product lists: `PYTHON_PRODUCTS` (8 services) and `IMAGE_PRODUCTS` (same plus `operator-portal`).
- Computes a **coordinated image tag** once: `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for uncommitted changes). The semver comes from the single source of truth `VERSION` file at the repo root.
- Builds all images via `make -C products/<name>`, then writes an `.images.env` state file under `shared/platform-ops/gitops/dev-k8s/` listing every service image reference — consumed by the deploy script so all components ship the same version.
- Provides cross-cutting targets: `sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `e2e`, `clean`.

### Shared fragments in `mk/`
- `mk/defaults.mk`: Single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_IMAGE`, `BASE_UV_TAG`, `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`). All values use `?=`, so command-line overrides always win.
- `mk/image.mk`: Shared Docker image targets (`build`, `push`, `lint`). Each product Makefile only sets `IMAGE_NAME` (and optionally `IMAGE_CONTEXT` / `IMAGE_DOCKERFILE`) and includes this fragment. Lint falls back from `hadolint` to `docker run hadolint/hadolint` when the binary is missing.
- `mk/python.mk`: Shared `uv sync --frozen` and `pytest` targets; disables OTel exporters during tests to avoid noise while keeping tracing SDK active.

### Per-product Makefiles
Each product under `products/<name>/` has a tiny Makefile that just declares `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. Non-Python products like `operator-portal` include only `image.mk` and override `IMAGE_CONTEXT` to point at the repo root so the multi-stage Dockerfile can access `VERSION` and the Vite web UI.

### Container images
- Base image: `shared/base-images/base-uv/Dockerfile` built as `luban-aiops/base-uv:<tag>` using pinned `UV_VERSION` and `PYTHON_VERSION` from `mk/defaults.mk`.
- Product images: Multi-stage or single-stage Dockerfiles per product, all based on `luban-aiops/base-uv:al2023`, running `uv sync --frozen --no-dev` and invoking the entrypoint via `uv run <module>`.
- Images are tagged locally as `luban-aiops/<name>:<IMAGE_TAG>` and optionally re-tagged/pushed to `$(REGISTRY)/luban-aiops/<name>:<IMAGE_TAG>`.

### Versioning strategy
- **Single source of truth**: `VERSION` at the repo root (currently `0.36.0`).
- `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to enforce lockstep between the root `VERSION`, each product's declared version, and the portal.
- The coordinated image tag embeds the platform version, optional profile suffix, git short SHA, and a dirty timestamp marker.

### Policy management
- Canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`.
- `make sync-policy` copies it into three consumer locations (tool-gateway, platform-gateway, dev-k8s base overlay).
- `make validate-policy` validates against JSON schema; `make validate-policy-scenarios` evaluates scenario expectations against both engines; `make policy-diff CANDIDATE=<path>` reports per-(role, action) differences.

### Secret vocabulary enforcement
- `make validate-secret-vocabulary` runs `shared/shared-contracts/scripts/validate_secret_vocabulary.py` to ensure secret-literal declarations stay in lockstep across agent-platform, tool-gateway, and skills-hub.

### GitOps & deployment
- Overlays under `shared/platform-ops/gitops/` (dev-k8s, runtime-profiles/*) are validated via `kustomize build --load-restrictor LoadRestrictionsNone` in `make overlays`.
- `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies the overlay and then sequentially provisions secrets (delegation, audit, execution signing, handoff, skills, incidents, browser credentials, sessions DB, OTel) via dedicated `sync-*` scripts, with `SKIP_*_SECRETS=true` flags for CI environments.
- Optional OIDC realm reconciliation (`reconcile-luban-realm.sh`, `reconcile-portal-oidc-client.sh`) is gated by `RECONCILE_OIDC_PORTAL_CLIENT`.
- Local kind integration: `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` auto-loads all built images into the named kind cluster after `make build`.

### E2E & samples
- `make e2e` runs shell scripts under `shared/platform-ops/e2e/` against a deployed cluster (requires port-forwarding to platform-gateway and identity-service).
- `make deploy-samples` installs tutorial skills from `samples/` into the dev namespace; `make undeploy-samples` removes them.

## Conventions & Constraints

1. **Every Python product must have a `pyproject.toml` + `uv.lock`** — dependency resolution is frozen via `uv sync --frozen`.
2. **Every containerized product must have a `Dockerfile`** and a thin `Makefile` including `../../mk/image.mk`.
3. **Image tags are coordinated, not per-product** — the root `make build` computes one `IMAGE_TAG` and writes it into `.images.env`; deploy reads this file so all services share the same version.
4. **Base images are pinned** — `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`, `BASE_UV_TAG=al2023`; never use `latest`.
5. **Platform version is the single source of truth** — enforced by `make validate-version`; all product versions must match `VERSION`.
6. **Policy bundles are canonical-only** — consumers copy via `make sync-policy`; never edit copies directly.
7. **Secrets are provisioned by scripts, not baked into images** — `deploy.sh` calls `sync-*` scripts with skip flags for CI.
8. **Verification gate is uniform** — `make verify` runs tests, kustomize overlay checks, policy validation, scenario evaluation, version lockstep, and secret vocabulary validation; intended as the pre-commit/pre-push gate.