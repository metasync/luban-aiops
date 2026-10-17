---
kind: build_system
name: Luban Platform Workspace Build & Artifact System
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/python.mk
    - mk/image.mk
    - VERSION
    - products/agent-platform/Makefile
    - products/operator-portal/Makefile
    - products/agent-platform/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
---

## Approach

The Luban platform is a Python/Node monorepo built with **GNU make** as the top-level orchestrator, **uv** for per-product Python dependency resolution and test execution, **Docker** for container images, and **kustomize** for GitOps Kubernetes overlays. There is no CI configuration file in `.github/` (only issue templates and PR templates); the root `Makefile` is explicitly documented as "Forge-agnostic" and intended to be the single pre-commit/pre-push gate run identically locally and under any CI.

## Top-level orchestration (`Makefile`)

The root Makefile declares two product lists:
- `PYTHON_PRODUCTS` — eight services that ship a uv-based test suite: `agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`.
- `IMAGE_PRODUCTS` — nine products that produce Docker images (the above eight plus `operator-portal`).

Key targets:
- `sync` / `test` / `lint` — iterate over every product and delegate.
- `base-images` — build the shared `luban-aiops/base-uv` image from `shared/base-images/base-uv/Dockerfile` using pinned `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION`.
- `build` — builds all images with a coordinated tag, then writes `shared/platform-ops/gitops/dev-k8s/.images.env` containing `AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, `TOOL_GATEWAY_IMAGE`, `IDENTITY_SERVICE_IMAGE`, `AUDIT_SERVICE_IMAGE`, `SKILLS_HUB_IMAGE`, `INCIDENT_SERVICE_IMAGE`, `EXECUTION_RUNTIME_IMAGE`, `WEB_UI_IMAGE` — one key per service, all sharing the same tag.
- `push` — re-tags each image through `REGISTRY` and pushes.
- `overlays` — runs `kustomize build --load-restrictor LoadRestrictionsNone` against every overlay listed in `OVERLAYS` (`dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`, `runtime-profiles/ansible-dev`).
- `validate-dashboards` — validates OpenObserve dashboards offline (`shared/platform-ops/dashboards/validate_dashboards.py`).
- `verify` — the canonical verification gate combining `test`, `overlays`, `validate-dashboards`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, `secret-delivery-demo`, `portal-test`, `execution-failure-test`.
- `deploy` / `deploy-samples` / `undeploy-samples` / `e2e` — wrap scripts under `shared/platform-ops/gitops/dev-k8s/deploy.sh` and `shared/platform-ops/e2e/`.

Coordinated image tagging logic (lines 56–69) computes `IMAGE_TAG` once: `<semver>-<prefix>[-<profile>]-<gitsha>` for a clean tree, or `<semver>-<prefix>[-<profile>]-dirty-<timestamp>` when `git status --porcelain` reports changes. The semver comes from the root `VERSION` file; prefix/profile come from `mk/defaults.mk` (`IMAGE_TAG_PREFIX ?= dev-k8s`, `IMAGE_TAG_PROFILE ?=`).

## Shared fragments (`mk/`)

Three include files are consumed by both the root Makefile and per-product Makefiles:

- `mk/defaults.mk` — single source of truth for overridable settings via `?=`: `IMAGE_PLATFORM ?= linux/amd64`, `REGISTRY ?=`, `AUTO_LOAD_KIND ?= false`, `KIND_CLUSTER_NAME ?=`, `BASE_UV_IMAGE ?= luban-aiops/base-uv`, `BASE_UV_TAG ?= al2023`, `BASE_UV_UV_VERSION ?= 0.12.1`, `BASE_UV_PYTHON_VERSION ?= 3.12`. Guarded against double inclusion via `ifndef LUBAN_DEFAULTS_INCLUDED`.
- `mk/python.mk` — provides `sync` (`uv sync --frozen`) and `test` (re-syncs, then runs `pytest` with `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` so OTLP noise does not leak into test output while the SDK stays active for tracing tests).
- `mk/image.mk` — provides `help`, `build`, `push`, `lint`. `build` always tags locally as `luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>`; if `REGISTRY` is set it additionally re-tags to `$(REGISTRY)/luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>`. `lint` prefers `hadolint` on PATH, falls back to `docker run hadolint/hadolint`, and silently skips if neither is available.

## Per-product Makefiles

Each product under `products/<name>/` has a tiny Makefile that only sets `IMAGE_NAME` and includes the two shared fragments. Example (`products/agent-platform/Makefile`):

```
IMAGE_NAME := agent-service
include ../../mk/image.mk
include ../../mk/python.mk
```

The operator portal is the exception: its Makefile also defines `test` and `web-build` targets that invoke `npm --prefix web-ui/app test` and `npm --prefix web-ui/app run build` because it is a Vite/Vitest SPA served by nginx, not a uv product. The root Makefile's `portal-test` target delegates to these and is part of `verify` (per SPEC-063 R-8c comment).

## Container images

All Python services follow the same Dockerfile pattern (see `products/agent-platform/Dockerfile`): multi-stage build starting from `luban-aiops/base-uv:al2023`, copy `.python-version pyproject.toml uv.lock README.md src`, run `uv sync --frozen --no-dev`, expose port 8000, and exec the entrypoint via `uv run <module>`.

The operator portal uses a separate Dockerfile at `products/operator-portal/Dockerfile` with `IMAGE_CONTEXT := ../..` so it can access the root `VERSION` file and the Vite project under `web-ui/app`.

## Versioning and policy contracts

- `VERSION` at the repo root holds the single source-of-truth platform version (`0.48.0`). It is read by the root Makefile as `PLATFORM_VERSION` and used in coordinated image tags.
- `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to enforce lockstep between `VERSION`, each product's declared version, and the portal.
- Policy bundles are authored once in `shared/shared-contracts/policies/` and synced to consumers via `make sync-policy`; `make validate-policy` and `make validate-policy-scenarios` validate them against JSON schema and scenario expectations across both engines.
- Secret vocabulary and password policy are similarly centralized and validated via `make validate-secret-vocabulary` and `make validate-password-policy`.

## GitOps deployment

Kubernetes manifests live under `shared/platform-ops/gitops/`. The base overlay (`dev-k8s/base/`) contains one subdirectory per service (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`, `operator-portal`, `infra`) plus `shared/runtime-config.env` and `shared/policy.yaml`. Runtime profiles (`runtime-profiles/{default,mutating-dev,browser-dev,ansible-dev}`) are layered on top. Deployment is performed by `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which reads the coordinated image list from `shared/platform-ops/gitops/dev-k8s/.images.env` written by `make build`.

## Conventions and constraints

- Every Python product pins dependencies via `uv.lock` and installs with `uv sync --frozen`; development-only deps are excluded from images via `--no-dev`.
- Image builds default to `linux/amd64` (`IMAGE_PLATFORM ?= linux/amd64`) but can be overridden to `linux/arm64` for local kind builds.
- All images share a single coordinated `IMAGE_TAG` computed from `VERSION` + git SHA; there is no per-image versioning.
- The `verify` target is the authoritative gate: it must pass before push/deploy and combines unit tests, kustomize rendering, dashboard validation, policy validation, secret vocabulary checks, portal SPA tests, and failure-injection proofs.
- Samples (`samples/acme-admin/`) are intentionally kept out of the base overlay (SPEC-050 R-11) and installed separately via `make deploy-samples`.
- The operator portal's Vitest suite is treated as a release gate even though it is not a uv product — zero tests fail the build, and no integration skip toggle is accepted.