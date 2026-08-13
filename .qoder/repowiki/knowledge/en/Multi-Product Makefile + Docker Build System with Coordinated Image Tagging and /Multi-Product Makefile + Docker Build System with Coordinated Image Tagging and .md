---
kind: build_system
name: Multi-Product Makefile + Docker Build System with Coordinated Image Tagging and GitOps Deploy
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
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## Overview

The repository uses a **Makefile-driven, multi-product build system** centered on Docker container images built from per-product `Dockerfile`s. A root `Makefile` orchestrates shared concerns (base image builds, coordinated tagging, test/lint aggregation, GitOps overlay validation, and deployment) while each product under `products/<name>/` declares only its image name and includes shared fragments from `mk/`. There is no CI pipeline file in `.github/workflows`; the `make verify` target is documented as the forge-agnostic pre-commit/pre-push gate.

## Core Components

### Root Makefile (`Makefile`)
- Declares `PYTHON_PRODUCTS` (`agent-platform`, `identity-broker`, `platform-gateway`, `tool-gateway`) and `IMAGE_PRODUCTS` (adds `operator-portal`).
- Computes a single coordinated `IMAGE_TAG` once: `<prefix>[-<profile>]-<gitsha>` for clean trees, appending `-dirty-<timestamp>` when `git status --porcelain` reports changes.
- Builds all images via `make -C products/$p build IMAGE_TAG=... IMAGE_PLATFORM=...`, then writes a shared state file at `shared/platform-ops/gitops/dev-k8s/.images.env` containing the tag plus full image refs for every product.
- Provides `sync`, `test`, `lint`, `overlays` (kustomize build checks), `verify` (tests + overlays), `deploy` (wraps `dev-k8s/deploy.sh`), `clean`, and optional `AUTO_LOAD_KIND` to load images into a kind cluster after build.

### Shared Fragments (`mk/`)
- `mk/defaults.mk`: Single source of overridable defaults using `?=` so command-line flags win. Pinned values include `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`, `BASE_UV_IMAGE=luban-aiops/base-uv`, `BASE_UV_TAG=al2023`, default `IMAGE_PLATFORM=linux/amd64`, and `IMAGE_TAG_PREFIX=dev-k8s`.
- `mk/image.mk`: Defines `build`, `push`, `lint`, and `help` targets. Sets `IMAGE_CONTEXT ?= .`, computes `IMAGE_REF` as `luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>` (or `<REGISTRY>/luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>`). Linting falls back from `hadolint` to `docker run hadolint/hadolint` if the binary is missing.
- `mk/python.mk`: Defines `sync` (`uv sync --frozen`) and `test` (`uv sync --frozen && uv run pytest`). Requires GNU make and `uv`.

### Per-Product Makefiles
Each product's `Makefile` is minimal — e.g. `products/agent-platform/Makefile` sets `IMAGE_NAME := agent-service` and includes `../../mk/image.mk` and `../../mk/python.mk`. This pattern is repeated across all Python products.

### Container Images
- Base image: `shared/base-images/base-uv/Dockerfile` built via `make base-images` with `--platform $(IMAGE_PLATFORM)` and pinned `UV_VERSION` / `PYTHON_VERSION` build args.
- Product images: Each `products/<name>/Dockerfile` follows the same shape — `FROM luban-aiops/base-uv:al2023`, copy `pyproject.toml`, `uv.lock`, `src`, run `uv sync --frozen --no-dev`, expose port 8000, and `CMD ["uv", "run", "<entrypoint>"]`.

### Deployment & GitOps
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` runs `../deploy-overlay.sh`, then `../sync-delegation-secrets.sh`, and optionally reconciles an OIDC client via `reconcile-portal-oidc-client.sh`. Namespace defaults to `dev-luban-aiops`.
- The deploy script reads image references from `shared/platform-ops/gitops/dev-k8s/.images.env`, which is written by the root `make build` step — this is how coordinated tagging flows into Kubernetes manifests.
- Overlay rendering is validated by `make overlays`, which runs `kustomize build` against `dev-k8s`, `runtime-profiles/dashscope`, `runtime-profiles/deepseek`, and `runtime-profiles/openai`.

## Architecture & Conventions

- **Forge-agnostic**: The root `Makefile` comment states `make verify` is the pre-commit/pre-push gate and should run identically locally and under any CI.
- **Coordinated tagging**: All images share one `IMAGE_TAG` computed once at the root level; individual product `IMAGE_TAG` overrides are ignored because the root passes it explicitly to each product build.
- **Pinned dependencies**: Both Python deps (`uv.lock`, frozen via `uv sync --frozen`) and base image versions (`al2023`, `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`) are pinned to avoid drift.
- **Cross-platform builds**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be set to `linux/arm64` for local arm64/kind builds; the same flag propagates to base image and all product image builds.
- **Registry push flow**: Set `REGISTRY=<host>` to re-tag images to `<REGISTRY>/luban-aiops/<name>:<tag>` before pushing; otherwise images stay local.
- **Kind integration**: `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<cluster>` auto-loads all five product images into the named kind cluster after `make build`.
- **Per-product isolation**: Each product has its own `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, `Makefile`, and `tests/` directory; the root never touches product internals directly beyond invoking their Makefiles.

## Constraints & Rules Observed

- Every Python product must provide a `Makefile` that sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk` to participate in root-level `sync`, `test`, `build`, `push`, and `lint`.
- Products must use `uv sync --frozen` (never `uv pip install`) to enforce lock-file fidelity.
- Dockerfiles must derive from `luban-aiops/base-uv:al2023` and use `uv sync --frozen --no-dev` for production image layers.
- Image tags must not use `latest`; they are derived from git SHA (with dirty detection).
- Deployment relies on `shared/platform-ops/gitops/dev-k8s/.images.env` being present and up-to-date; `make deploy` does not rebuild images itself.
- Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/*` must render cleanly; `make verify` fails if any overlay build errors.

## Key Files

- `Makefile` — root orchestration, coordinated tagging, aggregate targets
- `mk/defaults.mk` — single source of overridable build defaults
- `mk/image.mk` — shared `build`/`push`/`lint` Docker targets
- `mk/python.mk` — shared `uv sync`/`pytest` targets
- `products/*/Makefile` — per-product thin wrappers setting `IMAGE_NAME`
- `products/*/Dockerfile` — product container definitions
- `shared/base-images/base-uv/Dockerfile` — shared Python base image
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — dev-cluster deployment entrypoint
- `shared/platform-ops/gitops/dev-k8s/.images.env` — coordinated image ref state file
- `shared/platform-ops/gitops/{dev-k8s,runtime-profiles/*}/kustomization.yaml` — GitOps overlays validated by `make overlays`