---
kind: build_system
name: Monorepo Build, Image & GitOps Pipeline via Make + uv + Kustomize
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
---

## 1. What system/approach is used

The Luban AIOps platform is built as a **Make-driven monorepo** that composes seven Python services and one web portal into coordinated container images, then deploys them through **Kustomize-based GitOps overlays**. The build stack is:

- **GNU make** at the repository root (`Makefile`) orchestrates cross-cutting concerns (test, lint, image build, policy sync, version validation, overlay render, deploy).
- **uv** is the Python dependency manager and runner; every product uses `pyproject.toml` + `uv.lock`, with `uv sync --frozen` for reproducible installs.
- **Docker** builds per-product images from each product's `Dockerfile`, all based on a shared `shared/base-images/base-uv` image pinned to Amazon Linux 2023 + a fixed Python/uv version.
- **Kustomize** renders Kubernetes manifests under `shared/platform-ops/gitops/<overlay>`; the root `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` against each overlay to validate them.
- **Shell scripts** under `shared/platform-ops/gitops/dev-k8s/deploy.sh` orchestrate secret provisioning, overlay deployment, and Keycloak reconciliation.

There are no CI workflow files in `.github/workflows`; the repo is forge-agnostic — `make verify` is documented as the pre-commit/pre-push gate intended to run identically locally and under any CI.

## 2. Key files and packages

- Root orchestrator: `Makefile` — defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`, computes `IMAGE_TAG`, and wires `sync/test/lint/build/push/verify/deploy/e2e/clean`.
- Shared build fragments in `mk/`:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`).
  - `mk/image.mk` — shared `build/push/lint` targets for Docker images; sets `IMAGE_REF = luban-aiops/<name>:<tag>` (optionally prefixed by `REGISTRY`).
  - `mk/python.mk` — shared `sync/test` targets using `uv sync --frozen` and `uv run pytest` with OTel exporters disabled during tests.
- Per-product Makefiles (e.g. `products/agent-platform/Makefile`) are minimal: set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`.
- Product `Dockerfile`s follow a uniform pattern: `FROM luban-aiops/base-uv:al2023`, copy `pyproject.toml` + `uv.lock` + `src`, run `uv sync --frozen --no-dev`, expose port 8000, exec via `uv run <service-entrypoint>`.
- Version lockstep enforcement: `VERSION` file at repo root; `shared/shared-contracts/scripts/validate_version.py` checks it against every `products/*/pyproject.toml`, every `products/*/src/*/metadata.py` (`SERVICE_VERSION`), optional `__version__`, and the operator-portal Vite wiring.
- Policy sync: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into `platform-gateway`, `tool-gateway`, and the Kustomize base `policy.yaml`.
- Deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` calls `deploy-overlay.sh` plus `sync-*-secrets.sh` scripts for delegation, audit, skills, incidents, sessions DB, OTel, and optionally reconciles Keycloak realm and portal OIDC client.

## 3. Architecture and conventions

- **Fragmented Makefile design**: The root `Makefile` holds only orchestration logic; reusable behavior lives in `mk/*.mk`. Each product Makefile includes these fragments, so `make -C products/<name> test` works standalone or via the root aggregator.
- **Coordinated image tagging**: The root `make build` computes a single `IMAGE_TAG` once using `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]` and passes it to every product build. After building, it writes `shared/platform-ops/gitops/dev-k8s/.images.env` containing `IMAGE_TAG` plus one `*_IMAGE=luban-aiops/<svc>:<tag>` line per service, which the deploy script consumes.
- **Base image pinning**: All images derive from `luban-aiops/base-uv:al2023`, built once by `make base-images` with pinned `BASE_UV_PYTHON_VERSION=3.12` and `BASE_UV_UV_VERSION=0.12.1` (overridable via `mk/defaults.mk`).
- **Multi-platform support**: `IMAGE_PLATFORM ?= linux/amd64` propagates through `docker build --platform $(IMAGE_PLATFORM)`; `linux/arm64` is supported for local kind builds.
- **Kind integration**: Setting `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<cluster>` after `make build` auto-loads all eight images into the named kind cluster.
- **Single source of truth for versions**: `VERSION` is the canonical semver; `make validate-version` enforces lockstep across all products and the portal build-time injection.
- **Policy as code**: The canonical policy bundle lives under `shared/shared-contracts/policies/`; consumers must keep copies in sync via `make sync-policy`, validated by `make validate-policy` against a JSON schema.
- **GitOps overlays as first-class artifacts**: Overlays under `shared/platform-ops/gitops/` are rendered and validated as part of `make verify`; deployment is a thin wrapper around `deploy-overlay.sh` plus idempotent secret-sync scripts.

## 4. Conventions and constraints

- **Every Python product must have**: a `Dockerfile`, a `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`, a `pyproject.toml` + `uv.lock`, and a `src/<package>/metadata.py` exposing `SERVICE_VERSION` matching the root `VERSION`.
- **Image naming convention**: Images are tagged `luban-aiops/<image-name>:<coordinated-tag>`; when `REGISTRY` is set they are re-tagged to `$(REGISTRY)/luban-aiops/<image-name>:<tag>` before push.
- **Dependency management**: `uv sync --frozen` is mandatory — no unpinned resolution is allowed in either dev or production images.
- **Test execution**: Tests run with `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` so tracing SDKs stay active but produce no OTLP noise.
- **Verification gate**: `make verify` runs `test`, `overlays`, `validate-policy`, and `validate-version`; this is the documented pre-commit/pre-push gate.
- **Version drift is enforced**: `validate_version.py` exits non-zero if any `pyproject.toml`, `metadata.py`, `__init__.py`, or portal Vite wiring diverges from `VERSION`.
- **Policy drift is enforced**: `sync-policy` is the prescribed way to propagate changes; there is no automated watcher — developers must run it manually.
- **Deployment prerequisites**: `make deploy` expects secrets to be provisioned by the `sync-*-secrets.sh` helpers (or injected externally via `SKIP_*_SECRETS=true` flags) and requires a live kube context pointing at the target cluster.