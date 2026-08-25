---
kind: build_system
name: Multi-Product Make + Docker Build System with Coordinated Image Tags and GitOps Deployment
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
    - shared/base-images/base-uv/Dockerfile
    - VERSION
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
---

## What system/approach is used

The repository uses a **Make-driven multi-product build** layered on top of **Docker image builds**, **uv-managed Python environments**, and **Kustomize-based GitOps overlays**. A single root `Makefile` orchestrates per-product routines declared under `products/<name>/`, while shared behavior is factored into reusable fragments in `mk/` (`defaults.mk`, `image.mk`, `python.mk`). There is no CI configuration in `.github/workflows`; the verification gate is the local `make verify` target, which runs tests, renders Kustomize overlays, validates policy schemas, and enforces version lockstep — designed to be identical locally and under any CI.

## Key files and packages

- Root orchestration: `Makefile` (defines product lists, coordinated tag computation, `build`/`push`/`verify`/`deploy`/`e2e` targets)
- Shared defaults: `mk/defaults.mk` (overridable `IMAGE_PLATFORM`, `REGISTRY`, `AUTO_LOAD_KIND`, base image versions)
- Shared image fragment: `mk/image.mk` (per-product `build`/`push`/`lint` targets using `docker build --platform $(IMAGE_PLATFORM)`)
- Shared Python fragment: `mk/python.mk` (`uv sync --frozen` + `uv run pytest` with OTel exporters disabled)
- Per-product Makefiles (minimal): e.g. `products/platform-gateway/Makefile` sets `IMAGE_NAME` and includes both fragments
- Product Dockerfiles: e.g. `products/platform-gateway/Dockerfile` based on `luban-aiops/base-uv:al2023`, install deps with `uv sync --frozen --no-dev`, entrypoint via `uv run <service>`
- Base image: `shared/base-images/base-uv/Dockerfile` built by `make base-images`
- Version source of truth: `VERSION` (semver), enforced by `shared/shared-contracts/scripts/validate_version.py`
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml`, synced to consumers via `make sync-policy`
- GitOps deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` wraps overlay render and secret provisioning scripts; `kustomize build` checked by `make overlays`
- E2E demos: `shared/platform-ops/e2e/*.sh` invoked via `make e2e`

## Architecture and conventions

### Multi-product workspace
Each service lives under `products/<name>/` with its own `pyproject.toml`, `uv.lock`, `Dockerfile`, `Makefile`, and `tests/`. The root `Makefile` enumerates them in two lists:
- `PYTHON_PRODUCTS` — get `sync`/`test` via `mk/python.mk`
- `IMAGE_PRODUCTS` — get `build`/`push`/`lint` via `mk/image.mk`

This keeps each product's Makefile trivial (just set `IMAGE_NAME` and include the two fragments) while centralizing cross-cutting logic.

### Coordinated image tagging
The root `make build` computes a single `IMAGE_TAG` once using this formula:
```
<PLATFORM_VERSION>-<IMAGE_TAG_PREFIX>[-<IMAGE_TAG_PROFILE>]-<gitsha>[-dirty-<timestamp>]
```
where `PLATFORM_VERSION` comes from the root `VERSION` file. All images are tagged `luban-aiops/<product>:<IMAGE_TAG>`, then an `.images.env` file is written under `shared/platform-ops/gitops/dev-k8s/.images.env` that maps logical names (e.g. `AGENT_SERVICE_IMAGE`) to fully qualified tags. This file is consumed by the deploy step so all services ship as one release.

### Base image strategy
All Python services derive from a shared `luban-aiops/base-uv:al2023` image built from `shared/base-images/base-uv/Dockerfile`. Its `UV_VERSION` and `PYTHON_VERSION` are pinned in `mk/defaults.mk` (`BASE_UV_UV_VERSION ?= 0.12.1`, `BASE_UV_PYTHON_VERSION ?= 3.12`) and passed as `--build-arg` to ensure reproducible base layers.

### Python dependency management
Every Python product uses **uv** with a frozen lockfile: `uv sync --frozen` for both dependency installation and test execution. Tests run with OpenTelemetry exporters explicitly disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) so tracing SDKs stay initialized for tracing tests without emitting noise.

### Version lockstep enforcement
`VERSION` at the repo root is the single source of truth. `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which asserts that every product's `pyproject.toml` `[project] version`, `src/*/metadata.py` `SERVICE_VERSION`, optional `__version__`, and the operator portal's Vite wiring all match it. It also checks that the portal's `vite.config.ts` reads the root `VERSION` file at build time rather than hardcoding a value.

### Policy synchronization
A canonical policy YAML lives in `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to the three consumer locations (`tool-gateway`, `platform-gateway`, and the deployed `dev-k8s/base/shared/policy.yaml`). `make validate-policy` runs the shared schema validator against it.

### GitOps overlay rendering
`make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` over three overlays listed in `OVERLAYS`: `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`. Failure here blocks `make verify`, ensuring manifests are always renderable.

### Deploy flow
`make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which:
1. Renders the dev overlay via `deploy-overlay.sh`
2. Runs idempotent secret-provisioning scripts for token delegation, audit ingestion, skills credentials, incident intake, sessions DB, and OTel ingest
3. Optionally reconciles the Keycloak realm and portal OIDC client

Secret provisioning can be skipped per script via `SKIP_*_SECRETS=true` flags, enabling CI environments where secrets are injected externally.

### Local kind workflow
Setting `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<cluster>` after `make build` automatically loads all eight images into the named kind cluster, supporting rapid local iteration.

## Conventions and constraints

- **GNU make required**: documented in the root Makefile header; all targets assume GNU make semantics.
- **Pinned base versions**: `mk/defaults.mk` pins `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION`; comments explicitly say "never `latest`".
- **Command-line overrides win**: all defaults use `?=`, so callers can override `IMAGE_PLATFORM`, `REGISTRY`, `IMAGE_TAG_PREFIX`, etc. per invocation.
- **Frozen dependencies only**: Python products must use `uv sync --frozen`; no ad-hoc `pip install` or editable installs in build paths.
- **Single coordinated tag**: `make build` computes one `IMAGE_TAG` and applies it uniformly across all images; individual product `make build` still works standalone but loses coordination.
- **Version drift is a build failure**: `make validate-version` exits non-zero if any product diverges from `VERSION`; this is part of the `make verify` gate.
- **Policy must be copied from canonical location**: direct edits to consumer policy files are overwritten by `make sync-policy`; validation runs against the canonical copy.
- **Overlays must render cleanly**: `kustomize build` failures fail `make verify`, preventing broken manifests from being committed.
- **Image platform defaults to `linux/amd64`**: overridden to `linux/arm64` for native arm64 host/kind builds, but production deployment target remains amd64.