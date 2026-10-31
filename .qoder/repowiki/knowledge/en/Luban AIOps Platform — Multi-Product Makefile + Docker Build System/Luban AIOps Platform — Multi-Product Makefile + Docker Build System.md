---
kind: build_system
name: Luban AIOps Platform — Multi-Product Makefile + Docker Build System
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - products/operator-portal/Makefile
    - VERSION
---

## Overview

The Luban Agentic AIOps Platform is a multi-product monorepo (10 services, shared contracts/SDK, platform ops, samples) built with **GNU Make** as the top-level orchestrator and **Docker** for containerization. Each product is self-contained (its own `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, `Makefile`) and delegates build/test logic to shared fragments under `mk/`. There is no CI pipeline file in this repository; the root `make verify` target is documented as the forge-agnostic pre-commit/pre-push gate.

## Architecture of the Build System

### Root Makefile (`Makefile`)

The root Makefile is the single entry point. It declares two product lists:
- `PYTHON_PRODUCTS` — eight Python services that ship a uv test suite.
- `IMAGE_PRODUCTS` — nine products that produce container images (the eight Python services plus `operator-portal`).

It owns cross-cutting concerns: coordinated image tagging, GitOps overlay validation (`kustomize build`), dashboard schema validation, policy synchronization/validation, version lockstep checks, secret-vocabulary validation, e2e demo orchestration, and the `deploy` wrapper around `shared/platform-ops/gitops/dev-k8s/deploy.sh`.

Key targets:
- `sync` / `test` / `lint` — iterate over all products.
- `base-images` — build `shared/base-images/base-uv`.
- `build` — invoke per-product `make build IMAGE_TAG=...`, then write `.images.env` under `shared/platform-ops/gitops/dev-k8s/` with one `*_IMAGE=luban-aiops/<name>:<tag>` line per service, and optionally `kind load docker-image` when `AUTO_LOAD_KIND=true`.
- `push` — push every image (optionally re-tagged via `REGISTRY`).
- `verify` — the comprehensive gate combining product tests, overlay rendering, dashboard validation, policy validation/scenarios/diff, version lockstep, secret vocabulary, password-policy check, secret-delivery demo, portal SPA test+build, audit contract test, delegated-custody/runtime/multiproc/edge integration tests, and execution-failure test.
- `overlays` — renders every Kustomize overlay listed in `OVERLAYS` (dev-k8s plus runtime-profiles variants).
- `validate-dashboards` — runs `shared/platform-ops/dashboards/validate_dashboards.py` (SPEC-065 R-3).
- `observability-livecheck` — runs `shared/platform-ops/e2e/observability-livecheck.sh` (SPEC-065 R-4).
- `deploy` / `deploy-samples` / `undeploy-samples` / `e2e` — cluster deployment and demo orchestration.

### Shared Fragments (`mk/`)

Three fragments are included by both the root Makefile and per-product Makefiles:

- `defaults.mk` — single source of truth for overridable settings using `?=` so command-line overrides win. Defines `IMAGE_PLATFORM` (default `linux/amd64`), `IMAGE_TAG_PREFIX` (`dev-k8s`), `IMAGE_TAG_PROFILE`, `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, and the pinned base-image defaults (`BASE_UV_IMAGE=luban-aiops/base-uv`, `BASE_UV_TAG=al2023`, `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`). Guarded against double inclusion via `LUBAN_DEFAULTS_INCLUDED`.
- `image.mk` — provides `help`, `build`, `push`, `lint` targets for any product. Sets `IMAGE_CONTEXT ?= .`, `IMAGE_DOCKERFILE ?= $(IMAGE_CONTEXT)/Dockerfile`, `IMAGE_TAG ?= git rev-parse --short HEAD || dev`, and resolves `IMAGE_REF` to either `luban-aiops/<name>:<tag>` or `<REGISTRY>/luban-aiops/<name>:<tag>`. Dockerfile lint falls back from `hadolint` to `docker run hadolint/hadolint`.
- `python.mk` — provides `sync` and `test` targets. `sync` runs `uv sync --frozen`; `test` runs `uv sync --frozen` then `uv run pytest` with OTLP exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) so tracing tests can stay active without noisy network calls.

### Per-Product Makefiles

Each product follows an identical minimal pattern:

```make
IMAGE_NAME := <service-name>
include ../../mk/image.mk
include ../../mk/python.mk
```

Exceptions:
- `products/operator-portal/Makefile` — sets `IMAGE_CONTEXT := ../..` and `IMAGE_DOCKERFILE := Dockerfile` because its multi-stage Dockerfile needs the repo-root `VERSION` file and the Vite project at `web-ui/app`. It adds `test` (npm Vitest) and `web-build` (tsc + vite build) targets; it has no Python suite and is explicitly excluded from `make test` (SPEC-063 R-8c). The root `portal-test` target invokes both.
- `products/policy-center/` — only contains a README; no build artifacts.

### Container Images

All backend services share the custom base image `shared/base-images/base-uv/Dockerfile`, which:
- Starts from `public.ecr.aws/amazonlinux/amazonlinux:2023-minimal`.
- Installs a pinned `uv` version (default `0.12.1`) into `/usr/local/bin`.
- Creates a non-root `app` user (uid 1000).
- Pins Python via `UV_PYTHON=${PYTHON_VERSION}` (default `3.12`) and installs interpreters under `/app/.python`.
- Exposes `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `HOME=/home/app`.

Product Dockerfiles follow a uniform pattern: copy `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, then `src/`, run `uv sync --frozen --no-dev`, expose port 8000, and `CMD ["uv", "run", "<entrypoint>"]`.

The operator portal uses a separate multi-stage Dockerfile at `products/operator-portal/Dockerfile` that builds the Vite SPA and serves it via nginx.

### Versioning Strategy

- Single source of truth: `VERSION` (currently `0.51.0`).
- Coordinated image tag computed by the root Makefile: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, `<semver>-<prefix>[-<profile>]-<gitsha>-dirty-<timestamp>` for dirty trees.
- `make validate-version` delegates to `shared/shared-contracts/scripts/validate_version.py` to enforce lockstep between `VERSION`, each product's declared version, and the portal's version.

### Policy & Contract Validation

Policy bundles are authored once in `shared/shared-contracts/policies/` and synced to consumers via `make sync-policy` (copies to tool-gateway, platform-gateway, and the GitOps base overlay). Consumers validate via `make validate-policy`, scenario evaluation via `make validate-policy-scenarios`, and diffing via `make policy-diff CANDIDATE=<path>`.

Secret vocabulary and password-policy contracts are similarly validated through dedicated scripts under `shared/shared-contracts/scripts/`.

### Conventions and Constraints

- Every Python product pins dependencies via `uv.lock` and installs with `uv sync --frozen` — no floating versions at build time.
- All container images use the shared `luban-aiops/base-uv:al2023` base image; no product defines its own system Python.
- Image tags are deterministic and include the short git SHA; dirty working trees append `-dirty-<timestamp>`.
- `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g., `linux/arm64` for native kind on arm64 hosts).
- `REGISTRY` is optional; when unset images are tagged locally as `luban-aiops/<name>:<tag>`, when set they are re-tagged to `<REGISTRY>/luban-aiops/<name>:<tag>` before push.
- The root `make verify` is the authoritative pre-commit/pre-push gate and must pass unchanged across local and CI environments.
- Operator portal SPA tests and production build are gated separately via `make portal-test` (SPEC-063 R-8c); `make test` never covers it.
- Samples (`samples/acme-admin`) are installed out-of-band via `make deploy-samples` and are never part of the base Kustomize overlay (SPEC-050 R-11).
- Kustomize overlays are validated offline via `make overlays` using `kustomize build --load-restrictor LoadRestrictionsNone`.
- OpenObserve dashboards are validated offline against emitted metric families (SPEC-065 R-3).
- No CI workflow files exist in this repository; the author guidelines direct that build-system concerns be covered here rather than fabricating CI configuration.