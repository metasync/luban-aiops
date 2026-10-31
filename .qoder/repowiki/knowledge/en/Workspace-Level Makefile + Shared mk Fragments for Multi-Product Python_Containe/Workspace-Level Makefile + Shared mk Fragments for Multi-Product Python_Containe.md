---
kind: build_system
name: Workspace-Level Makefile + Shared mk Fragments for Multi-Product Python/Container Builds
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - products/operator-portal/Makefile
    - shared/base-images/base-uv/Dockerfile
---

# Build System Overview

The Luban Agentic AIOps Platform is a multi-product workspace (nine Python services plus an operator-portal SPA) built through a single root `Makefile` that delegates per-product work to shared fragments under `mk/`. There is no CI configuration in this repository snapshot (no `.github/workflows`); the build system is purely local/Makefile-driven.

## Approach and Tools

- **GNU make** is the orchestrator. The root `Makefile` declares itself "Forge-agnostic" and is intended as the pre-commit/pre-push gate (`make verify`).
- **uv** is the Python dependency manager and runner; every Python product has its own `pyproject.toml` + `uv.lock`, and builds use `uv sync --frozen` (lockstep enforced).
- **Docker** builds container images from each product's `Dockerfile`; images are tagged `luban-aiops/<name>:<IMAGE_TAG>` locally, with optional re-tagging/pushing to a `REGISTRY`.
- **kustomize** renders GitOps overlays under `shared/platform-ops/gitops` as part of verification.
- **Vitest + TypeScript** build the operator-portal SPA (non-Python product).
- **hadolint** lints Dockerfiles (with a docker-run fallback).
- **kind** can auto-load built images into a local cluster via `AUTO_LOAD_KIND=true`.

## Key Files

- `Makefile` — root orchestrator: product lists, coordinated image tag computation, policy/dashboard/version validation, overlay rendering, deploy/e2e orchestration.
- `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `BASE_UV_*`, `REGISTRY`, `AUTO_LOAD_KIND`, etc.), all using `?=` so command-line overrides win.
- `mk/image.mk` — shared `build` / `push` / `lint` targets for container images; requires the including Makefile to set `IMAGE_NAME` (and optionally `IMAGE_CONTEXT` / `IMAGE_DOCKERFILE`).
- `mk/python.mk` — shared `sync` / `test` targets for Python products; runs `uv sync --frozen` then `pytest` with OTLP exporters disabled.
- `products/*/Makefile` — thin wrappers that set `IMAGE_NAME` and include `../../mk/image.mk` (+ `../../mk/python.mk` for Python products).
- `products/operator-portal/Makefile` — non-Python product: adds `test` (vitest) and `web-build` (vite/tsc) targets; sets `IMAGE_CONTEXT := ../..` because the Dockerfile needs the root `VERSION` file.
- `shared/base-images/base-uv/Dockerfile` — shared base image built by `make base-images`.
- `shared/platform-ops/gitops/` — kustomize overlays validated by `make overlays`.
- `shared/platform-ops/dashboards/validate_dashboards.py` — offline dashboard schema/metric-reference validator invoked by `make validate-dashboards`.
- `shared/shared-contracts/scripts/*` — policy, version, secret-vocabulary, password-policy validators invoked from the root Makefile.

## Architecture and Conventions

### Product taxonomy
Products are enumerated centrally:
- `PYTHON_PRODUCTS` = agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway.
- `IMAGE_PRODUCTS` = same eight plus operator-portal.
Root targets like `sync`, `test`, `lint`, `build`, `push` iterate these lists and delegate via `$(MAKE) -C products/$$p ...`.

### Coordinated image tagging
The root computes one `IMAGE_TAG` once: `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` when the tree is dirty). All images produced by `make build` share this tag. After building, the root writes `shared/platform-ops/gitops/dev-k8s/.images.env` with the canonical image names (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, etc.) consumed by the deploy script.

### Version lockstep
The root `VERSION` file is the single source of truth for the platform release semver. `make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` against it and every product. The coordinated image tag prefixes the semver from `VERSION`.

### Policy contract model
Canonical policies live in `shared/shared-contracts/policies/`. `make sync-policy` copies them into consumer locations (`products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`). Consumers validate via `make validate-policy` and scenario tests via `make validate-policy-scenarios`.

### Secret vocabulary lockstep
`make validate-secret-vocabulary` enforces alignment between agent-platform, tool-gateway, and skills-hub secret literal vocabularies via `shared/shared-contracts/scripts/validate_secret_vocabulary.py`.

### Verification gate
`make verify` aggregates the full pre-commit/pre-push surface: product tests, kustomize overlay render checks, dashboard validation, policy validation/scenarios, version lockstep, secret-vocabulary check, password-policy validation, secret-delivery demo, portal test+build, audit contract test, and execution failure test.

### Base image strategy
All Python service images derive from `luban-aiops/base-uv:<tag>`, which is built once by `make base-images` using pinned `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12` on Amazon Linux 2023. Each product `Dockerfile` copies only `src`, `pyproject.toml`, `uv.lock`, `.python-version`, and `README.md`, then runs `uv sync --frozen --no-dev`.

### Operator portal exception
The operator-portal is not a uv product. Its Makefile defines `test` (vitest) and `web-build` (vite/tsc), and the root `verify` target calls both via `make -C products/operator-portal test` and `make -C products/operator-portal web-build`. The Dockerfile lives at `products/operator-portal/Dockerfile` but uses `IMAGE_CONTEXT := ../..` to access the root `VERSION` file.

### Deployment flow
`make deploy` runs `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which consumes the `.images.env` written by `make build`. Samples are deployed out-of-band via `make deploy-samples` (never named in the base overlay per SPEC-050 R-11). E2E scripts under `shared/platform-ops/e2e/` are orchestrated by `make e2e`.

## Conventions and Constraints

- Every Python product must have a `Makefile` that sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk` (observed across all eight Python services).
- Dependencies are installed with `uv sync --frozen`; there is no unfrozen install path in the build.
- Image builds default to `linux/amd64` (`IMAGE_PLATFORM ?= linux/amd64`) and use the `luban-aiops/` namespace; cross-compilation is supported via `IMAGE_PLATFORM=linux/arm64`.
- `make verify` is the authoritative pre-commit/pre-push gate and is documented as forge-agnostic (root `Makefile` header comment).
- The operator-portal SPA unit suite runs via vitest and fails on zero tests — there is no skip/zero-tests green path (documented in `products/operator-portal/Makefile` and root `Makefile` comment referencing SPEC-063 R-8c).
- Dashboard definitions under `shared/platform-ops/dashboards/` are validated offline by `make validate-dashboards` (SPEC-065 R-3) to prevent artifact rot between deploys.
- Policy bundles are authored once in `shared/shared-contracts/policies/` and copied to consumers via `make sync-policy`; consumers validate against JSON schemas via scripts in `shared/shared-contracts/scripts/`.
- The coordinated image tag is computed once and reused across all product images and the `.images.env` state file written by `make build`.
- Samples (acme-admin, skills) are deployed out-of-band via `make deploy-samples` / `make deploy-sample-app` and are never referenced from the base kustomize overlay (per SPEC-050 R-11).

No CI pipeline files were found in this repository snapshot; the build system is Makefile-driven and intended to be run locally or integrated into an external CI that executes `make verify`.