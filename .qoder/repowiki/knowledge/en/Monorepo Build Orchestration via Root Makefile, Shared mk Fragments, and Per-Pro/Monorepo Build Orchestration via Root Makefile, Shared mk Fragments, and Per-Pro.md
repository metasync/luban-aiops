---
kind: build_system
name: Monorepo Build Orchestration via Root Makefile, Shared mk Fragments, and Per-Product Dockerfiles
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
    - products/operator-portal/Dockerfile
    - VERSION
---

## Approach

The repository is a monorepo of independently containerized Python services (plus the operator-portal SPA) orchestrated by a single GNU Make entry point at the workspace root. There is no CI YAML in this repo; the `Makefile` comment states that `make verify` is the forge-agnostic pre-commit/pre-push gate intended to run identically locally and under any CI. Build logic is split into three layers:

1. **Root `Makefile`** — aggregates per-product routines, owns cross-cutting concerns (GitOps overlay checks, policy sync/validation, dashboard validation, coordinated deploy).
2. **Shared fragments under `mk/`** — `defaults.mk` (all overridable build settings), `image.mk` (docker build/push/lint targets), `python.mk` (`uv sync --frozen` + pytest with OTel exporters disabled).
3. **Per-product `Makefile`** — tiny delegators that set `IMAGE_NAME` and include both `../../mk/image.mk` and `../../mk/python.mk`.

Python dependency management uses `uv` with per-product `pyproject.toml` + `uv.lock`; builds use `uv sync --frozen` so lockfiles are authoritative. The operator-portal SPA uses npm (`npm ci`, Vite/React) and is built separately from the Python products.

## Key Files

- `Makefile` — master orchestrator: product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), coordinated image tag computation, policy/dashboard/version gates, e2e demo runner.
- `mk/defaults.mk` — single source of truth for overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`).
- `mk/image.mk` — shared `build` / `push` / `lint` targets using `docker build --platform $(IMAGE_PLATFORM)`.
- `mk/python.mk` — shared `sync` / `test` targets running `uv sync --frozen` then `pytest` with OTEL exporters set to `none`.
- `shared/base-images/base-uv/Dockerfile` — pinned Amazon Linux 2023 base image with pinned `uv` (default `0.12.1`) and Python `3.12`, running as non-root user `app` (uid 1000).
- Each product's `Dockerfile` (under `products/<name>/`) — copies `.python-version`, `pyproject.toml`, `uv.lock`, `src/`; runs `uv sync --frozen --no-dev`; CMD invokes the service entrypoint via `uv run`.
- `products/operator-portal/Dockerfile` — multi-stage Node 22 build producing an nginx-unprivileged runtime serving hashed assets.
- `VERSION` — single source of truth for the platform release version (semver); read by the root Makefile to compute `PLATFORM_VERSION` and propagated into images via `IMAGE_TAG`.

## Architecture and Conventions

### Coordinated Image Tagging
The root `Makefile` computes one `IMAGE_TAG` once and passes it to every product build. The tag format is `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees and appends `-dirty-<timestamp>` when `git status --porcelain` reports changes. This ensures all images in a deployment share a coherent tag derived from the commit SHA and the `VERSION` file.

### Product Registration Lists
Products are explicitly enumerated in two root-level variables:
- `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`
- `IMAGE_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway operator-portal`

Adding a new product requires registering it in both lists plus adding its `Makefile`/`Dockerfile`.

### Policy Bundles Are Single-Sourced
Canonical policies live in `shared/shared-contracts/policies/` and are copied to consumers via `make sync-policy`. Two bundles are managed this way: `policy-default.yaml` (copied to `tool-gateway`, `platform-gateway`, and `dev-k8s/base/shared/policy.yaml`) and `password-policy.yaml` (SPEC-062 R-2, copied only to `tool-gateway`). Consumers validate them through scripts under `shared/shared-contracts/scripts/`.

### GitOps Overlay Validation
Overlays under `shared/platform-ops/gitops/` are validated with `kustomize build --load-restrictor LoadRestrictionsNone` for each of `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, and `runtime-profiles/browser-dev`.

### Dashboard Validation
OpenObserve dashboards under `shared/platform-ops/dashboards/` are validated offline by `validate_dashboards.py` (SPEC-065 R-3): parse, envelope/panel schema, and every metric reference must resolve to an emitted `OTEL_MIRROR_FAMILIES` stream.

### Version Lockstep
`make validate-version` delegates to `shared/shared-contracts/scripts/validate_version.py` which enforces that the root `VERSION` file, every product's declared version, and the portal are kept in lockstep.

### Secret Vocabulary Validation
`make validate-secret-vocabulary` runs `shared/shared-contracts/scripts/validate_secret_vocabulary.py` against `agent-platform`, `tool-gateway`, and `skills-hub` to keep secret literal declarations synchronized.

### Base Image Strategy
All backend services inherit from `luban-aiops/base-uv:al2023`, which pins uv and Python versions via build args (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`). Products declare their interpreter via `.python-version`; `uv sync` resolves it deterministically. The base image is built first via `make base-images` and can be auto-loaded into a local kind cluster via `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>`.

### Operator Portal Build Isolation
The operator-portal SPA is not a uv product. Its `Makefile` runs Vitest unit tests and a Vite production build (`web-build` target). The root `verify` target includes `portal-test` to ensure the SPA is type-checked and builds even though it is excluded from `make test`.

### Deployment State File
`make build` writes `shared/platform-ops/gitops/dev-k8s/.images.env` containing `IMAGE_TAG` and every image reference (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, etc.), which `make deploy` consumes to render the overlay with consistent image tags.

## Conventions and Constraints

- **GNU make required**: documented in the root `Makefile` header; the project states it requires GNU make (default on macOS and Linux).
- **Pinned base image versions**: `mk/defaults.mk` comments state "Pinned values below are defaults for reproducible builds — never `latest"`; `shared/base-images/base-uv/Dockerfile` pins uv `0.12.1` and Python `3.12`.
- **Non-root containers**: `shared/base-images/base-uv/Dockerfile` creates user `app` (uid 1000) and sets `USER app`; product Dockerfiles inherit this.
- **Frozen Python dependencies**: `mk/python.mk` always runs `uv sync --frozen`; no transitive resolution at build time.
- **Coordinated tagging**: the root `Makefile` computes `IMAGE_TAG` once and propagates it to every product; individual product `IMAGE_TAG` overrides are ignored when driven from the root.
- **Verification gate composition**: `make verify` chains product tests, kustomize overlay renders, dashboard validation, policy validation (canonical + scenarios), version lockstep check, secret vocabulary check, password policy check, secret-delivery demo, portal unit+build tests, and the execution failure test — intended as the pre-commit/pre-push gate.
- **Samples out-of-band**: the root `Makefile` and comments (SPEC-050 R-11) enforce that tutorial samples are installed via `make deploy-samples` and are never part of the base overlay, so `make deploy` never names a sample.
- **Registry re-tagging**: `mk/image.mk` only re-tags and pushes when `REGISTRY` is set; without it, images stay local under `luban-aiops/<name>:<tag>`.
- **Image platform override**: `IMAGE_PLATFORM ?= linux/amd64` in `mk/defaults.mk` allows cross-compilation (e.g., `linux/arm64` for native kind builds on arm64 hosts).
- **Operator portal delivery gate**: SPEC-023 R-1 in the operator-portal Dockerfile documents the multi-stage build; the root `Makefile` enforces that the SPA's full Vitest suite and production build pass as part of `verify`.