---
kind: build_system
name: Multi-Product Makefile + Docker + Kustomize Build & Release Pipeline
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
    - VERSION
    - shared/shared-contracts/scripts/validate_version.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml
---

## What system/approach is used

The workspace uses a **Makefile-driven, multi-product build system** centered on three layers:

1. **Root `Makefile`** — orchestrates cross-cutting concerns (sync, test, lint, image build/push, GitOps overlay validation, policy sync/validate, version lockstep check, deploy, e2e). It enumerates Python products and image-producing products via `PYTHON_PRODUCTS` / `IMAGE_PRODUCTS` lists.
2. **Shared fragments in `mk/`** — reusable Makefile snippets (`defaults.mk`, `image.mk`, `python.mk`) that every product includes so `make -C products/<name>` works identically to root-level invocations.
3. **Per-product `Dockerfile` + `pyproject.toml` + `uv.lock`** — each service under `products/` is independently built as a container image using `docker build --platform $(IMAGE_PLATFORM)` against the shared base image `luban-aiops/base-uv:al2023`.

Container images are tagged with a **coordinated tag** computed once by the root Makefile: `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for uncommitted changes), written into `.images.env` and consumed by the deploy step. The single source of truth for the platform semver is the root `VERSION` file; a dedicated script enforces lockstep across all products.

Deployment uses **Kustomize overlays** under `shared/platform-ops/gitops/` (`dev-k8s`, `runtime-profiles/*`). The root `overlays` target runs `kustomize build` to validate them, and `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies the overlay and then provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) via helper scripts.

## Key files and packages

- `Makefile` — master entry point; defines `verify`, `build`, `push`, `deploy`, `e2e`, `sync-policy`, `validate-version`, `overlays`, etc.
- `mk/defaults.mk` — overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- `mk/image.mk` — shared `build`/`push`/`lint` targets for Docker images; resolves `IMAGE_REF` from `IMAGE_NAME` + `IMAGE_TAG` + optional `REGISTRY`.
- `mk/python.mk` — shared `sync`/`test` targets using `uv sync --frozen` and `uv run pytest` with OTEL exporters disabled during tests.
- `shared/base-images/base-uv/Dockerfile` — pinned Amazon Linux 2023 minimal base with pinned `uv` (0.12.1) and Python 3.12, running as non-root user `app` (uid 1000).
- `products/*/Makefile` — thin wrappers setting `IMAGE_NAME` and including `../../mk/image.mk` and `../../mk/python.mk`.
- `products/*/Dockerfile` — copy `.python-version`, `pyproject.toml`, `uv.lock`, `src`; run `uv sync --frozen --no-dev`.
- `VERSION` — single source of truth for platform semver (currently `0.36.1`).
- `shared/shared-contracts/scripts/validate_version.py` — validates that every product's `pyproject.toml` version, `metadata.SERVICE_VERSION`, package `__version__`, and portal Vite wiring all match `VERSION`.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — applies Kustomize overlay and provisions secrets via `sync-*` scripts.
- `shared/platform-ops/gitops/dev-k8s/*.yaml` — per-service deployment/service manifests plus `kustomization.yaml`.
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle copied to consumers via `make sync-policy`.

## Architecture and conventions

- **Per-product isolation**: Each product has its own `pyproject.toml`, `uv.lock`, `tests/`, `Dockerfile`, and `Makefile`. The root Makefile delegates to them rather than containing product-specific logic.
- **Shared base image strategy**: All backend services derive from `luban-aiops/base-uv:al2023`, which pins uv and Python versions at build time via `--build-arg`. Product images install dependencies with `uv sync --frozen --no-dev` for reproducible builds.
- **Coordinated tagging**: A single `IMAGE_TAG` is computed once and reused for all images, ensuring consistent versioning across services. The tag embeds git SHA and dirty-state metadata.
- **GitOps-first deployment**: Kubernetes manifests live under `shared/platform-ops/gitops/` and are validated via `kustomize build`. Overlays include `dev-k8s` and runtime profiles (`default`, `mutating-dev`, `browser-dev`).
- **Secret provisioning gate**: `deploy.sh` calls multiple `sync-*` scripts that can be skipped via environment variables (`SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, etc.), allowing CI to inject secrets externally.
- **Policy synchronization**: Canonical policy lives in `shared/shared-contracts/policies/`; `make sync-policy` copies it to `tool-gateway`, `platform-gateway`, and the dev-k8s overlay. Validation runs against both engines via `validate-policy-scenarios`.
- **Version lockstep enforcement**: `make validate-version` runs `validate_version.py`, which checks `VERSION` against every product's `pyproject.toml`, `metadata.py`, `__init__.py`, and the operator portal's Vite config wiring.
- **Local kind integration**: Setting `AUTO_LOAD_KIND=true` after `make build` automatically loads all built images into a named kind cluster (`KIND_CLUSTER_NAME`).

## Conventions and constraints

- **GNU make required**: The root Makefile comment states it requires GNU make (default on macOS/Linux); all fragments assume GNU make semantics.
- **Frozen dependency resolution**: Python products use `uv sync --frozen` everywhere (both development and production images), pinning exact transitive versions from `uv.lock`.
- **Non-root containers**: Base image creates user `app` (uid 1000) and sets `USER app`; product images inherit this convention.
- **No `latest` tags**: `mk/defaults.mk` comments explicitly state pinned values must never use `latest`; all images are tagged with explicit semver/git-sha combinations.
- **Single source of truth for version**: `VERSION` is the authoritative semver; `validate_version.py` enforces that all product versions match it or the build fails.
- **Registry re-tagging**: When `REGISTRY` is set, images are additionally tagged as `$(REGISTRY)/luban-aiops/$(IMAGE_NAME):$(IMAGE_TAG)` before push.
- **Image platform control**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g., `linux/arm64` for native arm64 local/kind builds).
- **Overlay validation as gate**: `make verify` includes `overlays`, which runs `kustomize build` against all configured overlays; failures block verification.
- **E2E prerequisites**: `make e2e` expects `make deploy` to have completed and requires port-forwards for `platform-gateway` (18083) and `identity-service` (18081) before running demo scripts.
- **Sample isolation**: Tutorial samples are deployed out-of-band via `make deploy-samples` so the base overlay never names a sample (per SPEC-050 R-11).
- **CI-friendly secret skipping**: Deploy scripts honor `SKIP_*_SECRETS` environment variables so CI environments can skip secret provisioning when secrets are injected externally.