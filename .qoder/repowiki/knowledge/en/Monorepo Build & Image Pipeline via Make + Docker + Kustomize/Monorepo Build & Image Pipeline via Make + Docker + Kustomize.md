---
kind: build_system
name: Monorepo Build & Image Pipeline via Make + Docker + Kustomize
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - products/platform-gateway/Makefile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml
    - shared/platform-ops/e2e/skills-demo.sh
    - shared/platform-ops/e2e/incident-demo.sh
    - shared/platform-ops/e2e/mutating-demo.sh
---

## What system/approach is used

The Luban AIOps monorepo uses a **Make-driven, forge-agnostic build system** that coordinates eight Python services and one web portal into container images, validates them against shared contracts, renders GitOps overlays, and deploys to a Kubernetes cluster. The core stack is:

- **GNU Make** as the orchestration layer (root `Makefile` plus per-product `Makefile`s).
- **Docker** for image builds, with a shared base image (`shared/base-images/base-uv`).
- **uv** (Python package manager) for dependency resolution and test execution, using frozen lockfiles (`uv.lock`) per product.
- **Kustomize** for rendering Kubernetes manifests under `shared/platform-ops/gitops/<overlay>`.
- **Shell scripts** for deployment (`deploy.sh`, secret sync scripts, e2e demos).

There is no CI configuration file in `.github/workflows`; the root `Makefile` explicitly states that `make verify` is the pre-commit/pre-push gate intended to run identically locally and under any CI.

## Key files and packages

- **Root orchestrator**: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), computes a coordinated `IMAGE_TAG`, delegates per-product tasks, runs policy/version validation, renders overlays, and drives deploy/e2e.
- **Shared fragments**:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, tag prefix/profile).
  - `mk/image.mk` — shared `build` / `push` / `lint` targets; resolves `IMAGE_REF` from `IMAGE_NAME` and optional `REGISTRY`.
  - `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `uv run pytest` with OTel exporters disabled during tests.
- **Per-product Makefiles** (e.g. `products/platform-gateway/Makefile`) are minimal: set `IMAGE_NAME` and include both fragments.
- **Version source of truth**: `VERSION` (semver string, e.g. `0.23.2`); consumed by root `IMAGE_TAG` computation and validated by `shared/shared-contracts/scripts/validate_version.py`.
- **GitOps overlays**: `shared/platform-ops/gitops/dev-k8s/`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`; rendered via `kustomize build --load-restrictor LoadRestrictionsNone`.
- **Deploy entrypoint**: `shared/platform-ops/gitops/dev-k8s/deploy.sh`, invoked by `make deploy`.
- **Policy bundle**: canonical copy at `shared/shared-contracts/policies/policy-default.yaml`, synced to consumers via `make sync-policy`.
- **E2E scripts**: `shared/platform-ops/e2e/*.sh` (skills-demo, incident-demo, mutating-demo), executed by `make e2e`.

## Architecture and conventions

1. **Two-level Makefile design** — Root `Makefile` owns cross-cutting concerns (coordinated tagging, overlay rendering, policy/version checks, deploy). Each product has a tiny `Makefile` that only declares `IMAGE_NAME` and includes shared fragments. This lets `make -C products/<name>` work standalone while also enabling `make -C . verify` to iterate all products.

2. **Coordinated image tagging** — The root `IMAGE_TAG` is computed once and propagated to every product via `$(MAKE) -C products/$$p build IMAGE_TAG=$(IMAGE_TAG)`. Tag format: `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`. All images share this tag, ensuring version lockstep across services.

3. **Image registry strategy** — Images are always built locally first as `luban-aiops/<name>:<tag>`. If `REGISTRY` is set, they are re-tagged to `$(REGISTRY)/luban-aiops/<name>:<tag>` and pushed. Push is gated on `REGISTRY` being non-empty.

4. **Base image pinning** — The shared base image `shared/base-images/base-uv` is built once via `make base-images` with pinned `UV_VERSION` and `PYTHON_VERSION` from `mk/defaults.mk`. Product images inherit it.

5. **Dependency management** — Each product has its own `pyproject.toml` + `uv.lock`. `make sync` / `make test` use `uv sync --frozen` to enforce exact versions. Tests run with OpenTelemetry exporters disabled (`OTEL_TRACES_EXPORTER=none`, etc.) to avoid noise while keeping the SDK active for tracing tests.

6. **Verification gate** — `make verify` = `test` + `overlays` + `validate-policy` + `validate-version`. It is designed to be the single command run before commits/pushes and in CI.

7. **Policy synchronization** — A single canonical `policy-default.yaml` lives under `shared/shared-contracts/policies/`. `make sync-policy` copies it to each consumer location (tool-gateway, platform-gateway, dev-k8s base). Consumers validate it against a JSON schema via `make validate-policy`.

8. **Version lockstep enforcement** — `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to ensure the root `VERSION` matches every product's declared version and the operator portal.

9. **Deployment model** — `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which reads the coordinated image tags written to `shared/platform-ops/gitops/dev-k8s/.images.env` by `make build`. Overlays are validated beforehand by `make overlays`.

10. **Kind integration** — Setting `AUTO_LOAD_KIND=true` (plus `KIND_CLUSTER_NAME`) after `make build` auto-loads all images into the named kind cluster.

## Conventions and constraints

- **Every Python product must expose `sync` and `test` targets** via including `../../mk/python.mk`; otherwise it will not participate in root `make test` / `make verify`.
- **Every containerized product must expose `build`, `push`, `lint` targets** via including `../../mk/image.mk` and setting `IMAGE_NAME`; otherwise it will not participate in root `make build` / `make push` / `make lint`.
- **Products must be listed** in the `PYTHON_PRODUCTS` and/or `IMAGE_PRODUCTS` variables in the root `Makefile` to be included in bulk operations.
- **Image tags must never use `latest`** — enforced by the convention documented in `mk/defaults.mk` comments and by the deterministic tag computation.
- **All image platforms default to `linux/amd64`**; override via `IMAGE_PLATFORM=linux/arm64` for native arm64/kind builds.
- **Registry pushes are opt-in** — `make push` does nothing unless `REGISTRY` is set; local-only workflows are supported.
- **Overlays must render cleanly** — `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on each overlay; failure blocks verification.
- **Policy changes must go through the canonical bundle** — consumers should not edit their local copies directly; use `make sync-policy`.
- **E2E requires a deployed cluster** — `make e2e` expects `make deploy` to have completed and port-forwards for `platform-gateway:18083` and `identity-service:18081` to be active.