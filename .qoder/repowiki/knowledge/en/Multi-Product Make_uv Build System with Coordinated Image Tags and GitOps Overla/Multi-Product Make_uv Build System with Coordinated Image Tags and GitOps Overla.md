---
kind: build_system
name: Multi-Product Make/uv Build System with Coordinated Image Tags and GitOps Overlays
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
    - products/agent-platform/Dockerfile
    - products/agent-platform/pyproject.toml
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/shared-contracts/scripts/validate_version.py
    - VERSION
---

## What system/approach is used

The repository uses a **multi-product Python workspace** built entirely with **GNU make + uv (Python package manager) + Docker**. There is no CI pipeline file in this snapshot; the build surface is the root `Makefile` plus shared fragments under `mk/`, one product `Makefile` per service, and per-product `Dockerfile`s. Deployment targets are rendered via **Kustomize overlays** under `shared/platform-ops/gitops/`. Versioning is driven by a single root `VERSION` file that all products must stay lockstep with.

## Key files and packages

- Root orchestrator: `Makefile` — declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, computes a coordinated `IMAGE_TAG`, and dispatches to per-product makefiles.
- Shared build fragments:
  - `mk/defaults.mk` — single source of overridable settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
  - `mk/image.mk` — generic `build` / `push` / `lint` targets for any product that sets `IMAGE_NAME`.
  - `mk/python.mk` — `sync` (frozen `uv sync`) and `test` (runs `pytest` with OTLP exporters disabled).
- Per-product entrypoints: e.g. `products/agent-platform/Makefile` includes both `../../mk/image.mk` and `../../mk/python.mk`; each product also has a `Dockerfile` and `pyproject.toml` (with `uv_build` backend) and an `.python-version` pinning the interpreter.
- Base image: `shared/base-images/base-uv/Dockerfile` builds `luban-aiops/base-uv:<tag>` from Amazon Linux 2023 with a pinned `uv` version.
- GitOps overlays: `shared/platform-ops/gitops/dev-k8s/` (base overlay), plus runtime-profile overlays (`runtime-profiles/default|mutating-dev|browser-dev`). Rendered via `kustomize build --load-restrictor LoadRestrictionsNone`.
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml` is copied into consumers via `make sync-policy` and validated via scripts under `shared/shared-contracts/scripts/`.
- Version lock: root `VERSION` (currently `0.36.1`) is read as `PLATFORM_VERSION` and enforced against product versions by `shared/shared-contracts/scripts/validate_version.py`.

## Architecture and conventions

1. **Root-first orchestration**: The top-level `Makefile` is the only entrypoint most users invoke. It loops over `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists to run `sync`, `test`, `build`, `push`, and `lint` uniformly across every service.
2. **Coordinated image tagging**: `make build` at the repo root computes a single `IMAGE_TAG` of the form `<semver>-<prefix>[-<profile>]-<gitsha>` (dirty builds append `-dirty-<timestamp>`). All images are tagged with that same tag and written to `shared/platform-ops/gitops/dev-k8s/.images.env`, which the deploy script consumes so every deployed component shares one immutable artifact set.
3. **Per-product isolation with shared fragments**: Each product’s `Makefile` is tiny — it only sets `IMAGE_NAME` and includes `mk/image.mk` and `mk/python.mk`. All cross-cutting logic lives in `mk/`. This lets `make -C products/<name>` work standalone while still honoring the same defaults.
4. **Frozen dependency resolution**: Every Python product uses `uv sync --frozen` against its own `uv.lock`, guaranteeing reproducible installs. Tests run with `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` to keep test output clean while keeping the SDK active for tracing tests.
5. **Base image strategy**: All service images derive from `FROM luban-aiops/base-uv:al2023`, built once via `make base-images` with pinned `UV_VERSION` and `PYTHON_VERSION` from `mk/defaults.mk`. No product pins its own Python or uv version in the Dockerfile.
6. **Kustomize-only deployment**: There are no Helm charts. `make overlays` validates every overlay by running `kustomize build`; `make deploy` runs `shared/platform-ops/gitops/dev-k8s/deploy.sh` against the current cluster context. Samples are installed separately via `make deploy-samples` so the base overlay never references them (enforced by SPEC-050 R-11).
7. **Policy-as-code distribution**: The canonical policy YAML under `shared/shared-contracts/policies/` is the single source of truth. `make sync-policy` copies it into `tool-gateway`, `platform-gateway`, and the dev-k8s base overlay. `make validate-policy` and `make validate-policy-scenarios` exercise both engines against the same bundle.
8. **Version lockstep enforcement**: `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root, ensuring every product’s `pyproject.toml` version matches the root `VERSION` file.
9. **Local kind integration**: When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all nine images into the named kind cluster after building them.

## Conventions and constraints

- **Every Python product must have**: a `pyproject.toml` with a `[project.scripts]` entrypoint, a `uv.lock`, a `Dockerfile` based on `luban-aiops/base-uv`, and a `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`.
- **Products must be registered** in the root `Makefile`'s `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists to participate in `make verify`, `make build`, etc.
- **Image tags must be deterministic**: the root `IMAGE_TAG` computation forbids `latest` and always embeds a git short SHA; dirty trees get a timestamp suffix. This is enforced by the shell expression in the root `Makefile`.
- **No product may reference samples in the base overlay** — sample skills are deployed out-of-band via `make deploy-samples` (SPEC-050 R-11).
- **Policy bundles must be kept in sync**: changes to `shared/shared-contracts/policies/policy-default.yaml` must be propagated via `make sync-policy`; otherwise `make validate-policy` will fail because consumer copies diverge.
- **Build reproducibility**: `uv sync --frozen` is mandatory for both install and test; there is no `--upgrade` path in the standard targets.
- **Cross-platform builds**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden globally (e.g. `make build IMAGE_PLATFORM=linux/arm64`) and propagates through both base-image and product-image builds.
- **Verification gate**: `make verify` is the pre-commit/pre-push gate and combines `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, and `validate-version` into one command intended to run identically locally and in CI.