---
kind: build_system
name: Multi-Product Makefile + Docker Build System with Coordinated Versioning
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
    - products/agent-platform/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## Overview

The repository uses a **Makefile-driven, multi-product build system** centered on a root `Makefile` that orchestrates per-product Python builds (via `uv`) and container image creation (via `docker`). All shared logic is factored into reusable fragments under `mk/`, while each product in `products/<name>/` declares only its identity (`IMAGE_NAME`, `pyproject.toml`, `Dockerfile`) and includes the shared fragments.

## Core Components

### Root orchestration (`Makefile`)
- Declares two product lists: `PYTHON_PRODUCTS` (8 services) and `IMAGE_PRODUCTS` (same plus `operator-portal`).
- Single source of truth for the platform version lives in the root `VERSION` file; it is read at parse time as `PLATFORM_VERSION` and used to compose the coordinated image tag.
- Image tag computation: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, or `<...>-dirty-<timestamp>` when `git status --porcelain` reports changes. The prefix/profile come from `IMAGE_TAG_PREFIX` / `IMAGE_TAG_PROFILE` (default `dev-k8s`).
- After building all images, writes `.images.env` under `shared/platform-ops/gitops/dev-k8s/` containing every service image reference tagged with the coordinated `IMAGE_TAG`; this file is consumed by `make deploy`.
- Provides cross-cutting targets: `sync`, `test`, `lint`, `base-images`, `build`, `push`, `overlays` (kustomize build checks), `verify` (gate combining tests + overlays + policy validation + version lockstep), `deploy`, `e2e`, `clean`.
- Policy synchronization: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into both gateway consumers and the GitOps overlay base.

### Shared fragments (`mk/`)
- `defaults.mk`: single source of overridable defaults using `?=` so command-line overrides always win. Covers `IMAGE_PLATFORM` (default `linux/amd64`), `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, and pinned base image versions (`BASE_UV_IMAGE=luban-aiops/base-uv`, `BASE_UV_TAG=al2023`, `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`). Includes a guard against double inclusion.
- `image.mk`: provides `build`, `push`, `lint` targets for any product that sets `IMAGE_NAME`. Builds with `--platform $(IMAGE_PLATFORM)`, tags locally as `luban-aiops/<name>:<tag>`, and optionally re-tags to `$(REGISTRY)/luban-aiops/<name>:<tag>`. Linting falls back to `hadolint` → `docker run hadolint/hadolint` → skip if neither is available.
- `python.mk`: provides `sync` (`uv sync --frozen`) and `test` (re-syncs then runs `pytest` with OTLP exporters disabled via `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` so tracing tests stay functional without network noise).

### Per-product Makefiles
Each product's `Makefile` is minimal — typically just setting `IMAGE_NAME` and including `../../mk/image.mk` and `../../mk/python.mk`. Example: `products/agent-platform/Makefile` sets `IMAGE_NAME := agent-service` and includes both fragments.

### Container images
- Base image built from `shared/base-images/base-uv/Dockerfile` using Alpine Linux 2023 + uv + Python 3.12.
- Product images follow a uniform pattern: `FROM luban-aiops/base-uv:al2023`, copy `pyproject.toml`, `uv.lock`, `src/`, run `uv sync --frozen --no-dev`, expose port 8000, and `CMD ["uv", "run", "<entrypoint>"]`.
- `operator-portal` is a Node.js Nginx static site built separately; its `Dockerfile` is included in `IMAGE_PRODUCTS` but does not use `mk/image.mk` directly.

### Version management
- `VERSION` at repo root is the single source of truth for the platform semver.
- `shared/shared-contracts/scripts/validate_version.py` enforces lockstep: every product's `pyproject.toml` `[project] version`, every `src/*/metadata.py` `SERVICE_VERSION`, any `__version__` in package roots, and the operator portal's Vite wiring must match `VERSION` exactly. It also asserts that `operator-portal/web-ui/app/vite.config.ts` reads the root `VERSION` file at build time (SPEC-023) rather than hardcoding a literal.
- Called via `make validate-version` from the root Makefile.

### Deployment & GitOps
- `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which:
  - Calls `deploy-overlay.sh` to apply Kustomize overlays.
  - Runs a series of `sync-*` scripts to provision secrets (delegation, audit, execution signing/handoff, skills, incidents, OTel, sessions DB, Keycloak realm/portal client). Each script supports a `SKIP_*_SECRETS=true` env var for CI environments where secrets are injected externally.
- Overlays validated via `make overlays` using `kustomize build --load-restrictor LoadRestrictionsNone`.

### Local development helpers
- `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` after `make build` auto-loads all built images into the named kind cluster.
- `make e2e` runs demo scripts under `shared/platform-ops/e2e/` against a deployed dev cluster (requires prior `make deploy` and port-forwards for `platform-gateway` and `identity-service`).

## Conventions & Constraints

- Every Python product must have a `pyproject.toml` + `uv.lock` pair; dependencies are resolved with `uv sync --frozen` (lockfile-only, no network drift).
- Image builds target `linux/amd64` by default; override via `IMAGE_PLATFORM=linux/arm64` for native arm64/kind builds.
- All images are tagged with a coordinated tag derived from `VERSION` + git SHA (+ `-dirty-<timestamp>` for uncommitted changes); pushing requires setting `REGISTRY`.
- The verification gate `make verify` combines `test`, `overlays`, `validate-policy`, and `validate-version`; it is intended as the pre-commit/pre-push check across any forge.
- Policy files are centralized in `shared/shared-contracts/policies/` and copied out via `make sync-policy`; consumers do not edit them directly.
- Secrets provisioning during `make deploy` is idempotent and skippable per subsystem via environment variables, enabling CI pipelines to inject secrets through other mechanisms.