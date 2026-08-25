---
kind: build_system
name: 'Monorepo Build System: Coordinated Makefile, Shared Fragments, Kustomize GitOps'
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - products/platform-gateway/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - VERSION
---

## Overview

The Luban AIOps platform is a Python microservices monorepo built with a layered Makefile system. A root `Makefile` orchestrates cross-cutting concerns (tests, linting, image builds, policy sync, version validation, overlay rendering, deployment) while delegating per-product work to shared fragments under `mk/`. Each product in `products/<name>/` has a tiny Makefile that only declares its image name and includes the shared fragments.

## Core Tools

- **GNU make** — primary build orchestrator; all targets are `.PHONY` and use `SHELL := /bin/sh` for portability.
- **uv** — Python dependency manager and runner (`uv sync --frozen`, `uv run pytest`). Every Python product pins dependencies via `pyproject.toml` + `uv.lock`; tests run with OTEL exporters disabled to avoid OTLP noise.
- **Docker** — container image builder; each product `Dockerfile` copies `src/`, runs `uv sync --frozen --no-dev`, and executes via `uv run <entrypoint>`.
- **Kustomize** — GitOps overlays under `shared/platform-ops/gitops/` (dev-k8s, runtime-profiles/default, runtime-profiles/mutating-dev); rendered by `make overlays` via `kustomize build --load-restrictor LoadRestrictionsNone`.
- **kind** — optional local cluster loading controlled by `AUTO_LOAD_KIND=true` + `KIND_CLUSTER_NAME`.
- **hadolint** — Dockerfile linting, falling back to `docker run hadolint/hadolint` when not installed.

## Architecture of the Build System

### Root Makefile (`Makefile`)
Defines two product lists:
- `PYTHON_PRODUCTS`: agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway
- `IMAGE_PRODUCTS`: same plus operator-portal

Key targets:
- `sync` / `test` / `lint` — iterate over products and invoke their per-product Makefiles.
- `base-images` — builds `shared/base-images/base-uv` using `BASE_UV_IMAGE`/`BASE_UV_TAG`/`BASE_UV_UV_VERSION`/`BASE_UV_PYTHON_VERSION` from `mk/defaults.mk`.
- `build` — builds every image with a coordinated tag, writes `shared/platform-ops/gitops/dev-k8s/.images.env` containing `IMAGE_TAG` and one `*_IMAGE=luban-aiops/<service>:<tag>` per service, then optionally loads images into kind.
- `push` — re-tags and pushes every image to `$(REGISTRY)`.
- `sync-policy` — copies `shared/shared-contracts/policies/policy-default.yaml` into both gateway services and the dev-k8s base overlay.
- `validate-policy` / `validate-version` — run scripts under `shared/shared-contracts/scripts/`.
- `overlays` — validates every Kustomize overlay.
- `verify` — aggregation target: `test overlays validate-policy validate-version` (the pre-commit/pre-push gate).
- `deploy` — delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which runs `deploy-overlay.sh` plus secret provisioning scripts (delegation, audit, skills, incidents, sessions-db, otel) and optional Keycloak realm reconciliation.
- `e2e` — runs demo scripts against a deployed cluster.

### Shared Fragments (`mk/`)

- **`defaults.mk`** — single source of truth for overridable settings using `?=` so command-line flags always win. Defines `IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`, `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, and base image versions. Guarded against double inclusion via `LUBAN_DEFAULTS_INCLUDED`.
- **`image.mk`** — provides `help`/`build`/`push`/`lint` targets. Requires the including Makefile to set `IMAGE_NAME` (and optionally `IMAGE_CONTEXT`/`IMAGE_DOCKERFILE`). Computes `IMAGE_REF` as `luban-aiops/<name>:<tag>` locally or `<REGISTRY>/luban-aiops/<name>:<tag>` when `REGISTRY` is set.
- **`python.mk`** — provides `sync` and `test` targets that run `uv sync --frozen` and `uv run pytest` with OTEL exporters set to `none`.

### Per-Product Makefiles
Each product's `Makefile` is minimal — e.g. `products/agent-platform/Makefile` sets `IMAGE_NAME := agent-service` and includes `../../mk/image.mk` and `../../mk/python.mk`. This pattern is consistent across all Python services.

### Container Images
All Python services use the shared base image `FROM luban-aiops/base-uv:al2023` (built from `shared/base-images/base-uv/Dockerfile`). The Dockerfile pattern is uniform: copy `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, then `src/`, run `uv sync --frozen --no-dev`, expose `8000`, and `CMD ["uv", "run", "<entrypoint>"]`.

### Versioning & Tagging
- Single source of truth: root `VERSION` file (currently `0.13.0`).
- Coordinated tag computed at the root: `<semver>-<prefix>[-<profile>]-<gitsha>`, with `-dirty-<timestamp>` appended if `git status --porcelain` reports uncommitted changes.
- `IMAGE_TAG` can be overridden on the command line; otherwise it falls back to short git SHA.
- `validate-version` enforces lockstep between `VERSION`, each product's declared version, and the portal version via `shared/shared-contracts/scripts/validate_version.py`.

### Policy Management
A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml` and is mirrored into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` via `make sync-policy`. Validation uses `shared/shared-contracts/scripts/validate_policy.py`.

### Deployment Flow
`make deploy` → `shared/platform-ops/gitops/dev-k8s/deploy.sh` → `deploy-overlay.sh` (runs kustomize) → series of `sync-*` scripts that provision secrets (delegation, audit, skills, incidents, sessions DB, OTel) → optional Keycloak realm/client reconciliation. Secrets can be skipped via `SKIP_*_SECRETS=true` flags for CI environments.

## Conventions & Constraints

- Every Python product must have `pyproject.toml`, `uv.lock`, `.python-version`, a `Dockerfile`, and a `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`.
- All images are tagged with the coordinated `IMAGE_TAG` produced by the root `make build`; individual product tags are not used directly by deployment.
- Image builds default to `linux/amd64`; override via `IMAGE_PLATFORM=linux/arm64` for native ARM builds.
- Dependency resolution is frozen: `uv sync --frozen` is used everywhere, ensuring reproducible builds.
- Tests disable telemetry exporters (`OTEL_TRACES_EXPORTER=none`, etc.) to keep output clean while keeping the SDK active for tracing tests.
- The verification gate `make verify` must pass before push/deploy; it runs tests, renders Kustomize overlays, validates policies, and checks version lockstep.
- Secret provisioning scripts are idempotent and skip-able via environment variables (`SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_SKILLS_SECRETS`, `SKIP_INCIDENT_SECRETS`, `SKIP_OTEL_SECRETS`) for CI.
- The root `clean` target removes `__pycache__`, `.pytest_cache`, and the generated `.images.env` state file.