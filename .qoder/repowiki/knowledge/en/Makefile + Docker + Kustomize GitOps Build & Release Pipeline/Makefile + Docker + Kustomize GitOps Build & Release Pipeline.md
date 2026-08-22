---
kind: build_system
name: Makefile + Docker + Kustomize GitOps Build & Release Pipeline
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
    - products/platform-gateway/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - VERSION
---

# Build System for the Agentic AIOPS Platform Monorepo

## What system/approach is used

The repository uses a **Makefile-driven monorepo build** layered on top of three core tools:

- **GNU Make** — root `Makefile` orchestrates cross-product targets (`sync`, `test`, `build`, `push`, `verify`, `deploy`, `e2e`) and delegates per-product work to each product's own `Makefile`.
- **Docker** — every service (and the operator portal) ships as a container image built from a per-product `Dockerfile`. A shared base image `shared/base-images/base-uv/Dockerfile` (Amazon Linux 2023 minimal, pinned `uv` 0.12.1, Python 3.12, non-root `app` user) is the single source of truth for the runtime image.
- **Kustomize** — GitOps overlays under `shared/platform-ops/gitops/` (dev-k8s base plus runtime profiles for dashscope/deepseek/openai/mutating-dev) are rendered via `kustomize build --load-restrictor LoadRestrictionsNone` as part of verification and deployment.

Python dependency management is handled per-product with **uv**: each product has `pyproject.toml` + `uv.lock`, and the shared fragment `mk/python.mk` runs `uv sync --frozen` and `uv run pytest` (with OTLP exporters disabled so tests stay clean).

There is no CI pipeline file in this repo; the root Makefile explicitly states it is "forge-agnostic" and intended to be the pre-commit/pre-push gate locally and under any CI.

## Key files and packages

- Root orchestration: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), computes coordinated `IMAGE_TAG`, coordinates `build`, `push`, `verify`, `deploy`, `e2e`, policy sync/version validation.
- Shared Make fragments:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `IMAGE_TAG_PREFIX/PROFILE`).
  - `mk/image.mk` — shared `build` / `push` / `lint` targets included by every product Makefile; resolves `IMAGE_REF` against `luban-aiops/<name>:<tag>` or `<REGISTRY>/luban-aiops/<name>:<tag>`.
  - `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `uv run pytest`.
- Base image: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal, pinned uv install, non-root `app` user, env vars pinning `UV_PYTHON=3.12` and `UV_LINK_MODE=copy`.
- Product Makefiles (minimal): e.g. `products/agent-platform/Makefile` sets `IMAGE_NAME := agent-service` then includes `../../mk/image.mk` and `../../mk/python.mk`; same pattern across all seven Python services plus `operator-portal`.
- Per-product Dockerfiles: e.g. `products/platform-gateway/Dockerfile` — `FROM luban-aiops/base-uv:al2023`, copies `.python-version pyproject.toml uv.lock src`, runs `uv sync --frozen --no-dev`, exposes 8000, runs via `uv run <entrypoint>`.
- GitOps overlay: `shared/platform-ops/gitops/dev-k8s/deploy.sh` — calls `deploy-overlay.sh`, then sequentially provisions secrets (delegation, audit, skills, incidents, sessions DB, OTel) and reconciles Keycloak realm + portal OIDC client.
- Version lock: `VERSION` (currently `0.7.0`) is the single source of truth; `make validate-version` enforces that every product version stays in lockstep with it via `shared/shared-contracts/scripts/validate_version.py`.
- Policy sync: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into both gateway consumers (`tool-gateway`, `platform-gateway`) and the deployed `policy.yaml`.

## Architecture and conventions

### Coordinated image tagging
The root `Makefile` computes one `IMAGE_TAG` once and reuses it for every product image. The tag format is `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`: semver comes from `VERSION`, prefix/profile come from `IMAGE_TAG_PREFIX`/`IMAGE_TAG_PROFILE`, and git SHA/dirty detection ensures reproducible tags. After building all images, the tag is written to `shared/platform-ops/gitops/dev-k8s/.images.env`, which the deploy script reads to render overlays with the correct image references.

### Fragment-based Makefile design
Each product Makefile is intentionally tiny — it only declares `IMAGE_NAME` and includes the shared fragments. All logic lives in `mk/*.mk`, so adding a new product means creating a directory with a `Dockerfile`, `pyproject.toml`, `uv.lock`, and a 3-line Makefile. The root `Makefile` maintains two explicit lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`) that drive iteration.

### Base image strategy
All backend services derive from the shared `luban-aiops/base-uv:al2023` image, which pins uv and Python versions at build time via `--build-arg`. Products do not install system Python; `uv sync` resolves the interpreter from each product's `.python-version` file. Images run as uid 1000 (`app` user) and use `UV_LINK_MODE=copy` for deterministic installs.

### GitOps-first deployment
Deployment is entirely Kustomize-based. `make overlays` renders every overlay to verify they build; `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies the dev-k8s overlay and then runs a series of idempotent secret-provisioning scripts (delegation, audit, skills, incidents, sessions DB, OTel). Runtime profiles (dashscope/deepseek/openai/mutating-dev) are separate overlays selected via helper scripts under `shared/platform-ops/gitops/`.

### Verification gate
`make verify` is the canonical pre-commit/pre-push gate and combines four checks:
1. `test` — runs each Python product's `pytest` suite via `uv run pytest`.
2. `overlays` — renders every Kustomize overlay to catch broken manifests.
3. `validate-policy` — validates the canonical policy bundle against its JSON schema.
4. `validate-version` — asserts that every product's declared version matches the root `VERSION`.

### Cross-cutting concerns
- Image platform is centralized in `mk/defaults.mk` (`IMAGE_PLATFORM ?= linux/amd64`); overrides propagate from root to products.
- Optional kind integration: setting `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME` auto-loads all built images into the named cluster after `make build`.
- E2E demos live in `shared/platform-ops/e2e/` and are invoked via `make e2e` against a deployed cluster with port-forwards.

## Conventions and constraints

- **Every Python service must have** `pyproject.toml`, `uv.lock`, `.python-version`, a `Dockerfile` based on `luban-aiops/base-uv:al2023`, and a `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`.
- **Product names in the root Makefile are the source of truth** — adding a new product requires updating `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists in addition to creating the product directory.
- **Image tags must be pinned** — the base image comment explicitly forbids `latest`; all versions (uv, Python, base image tag) are overridden via `--build-arg` or `mk/defaults.mk` variables.
- **Images run as non-root user** `app` (uid 1000) — enforced by the shared base image Dockerfile.
- **Dependencies are frozen** — `uv sync --frozen` is used everywhere, including inside Docker builds (`--no-dev` for production images).
- **Policy bundles are single-source** — `shared/shared-contracts/policies/policy-default.yaml` is the canonical copy; consumers receive it via `make sync-policy`, never edited directly.
- **Version lockstep is enforced** — `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to ensure every product version equals the root `VERSION` file.
- **GitOps overlays are validated before deploy** — `make overlays` fails if any overlay does not render cleanly; `make deploy` applies the dev-k8s overlay plus secret provisioning scripts.
- **Secret provisioning is opt-in/skip-able** — each `sync-*-secrets.sh` script respects a `SKIP_*_SECRETS=true` environment variable so CI can skip when secrets are injected externally.