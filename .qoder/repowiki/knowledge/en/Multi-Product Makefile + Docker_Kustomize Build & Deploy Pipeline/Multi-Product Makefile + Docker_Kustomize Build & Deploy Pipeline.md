---
kind: build_system
name: Multi-Product Makefile + Docker/Kustomize Build & Deploy Pipeline
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
    - shared/platform-ops/gitops/deploy-overlay.sh
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## Overview

Luban AIOps uses a **Makefile-driven, multi-product build system** that coordinates Python (uv) dependency management, container image builds, policy synchronization, GitOps overlay rendering, and Kubernetes deployment. There is no CI pipeline file in `.github/`; the root `make verify` target is designed to be the pre-commit/pre-push gate run locally or by any forge.

## Core Architecture

### Root orchestrator (`Makefile`)
- Declares two product lists: `PYTHON_PRODUCTS` (6 services with pytest suites) and `IMAGE_PRODUCTS` (7 images including `operator-portal`).
- Computes a single coordinated `IMAGE_TAG` per invocation using `<prefix>[-<profile>]-<gitsha>` for clean trees and `<...>-dirty-<timestamp>` for dirty trees; defaults prefix to `dev-k8s`.
- Aggregates per-product targets via `$(MAKE) -C products/<name> <target>` so `make test`, `make lint`, `make build`, `make push` iterate all products uniformly.
- Writes a shared state file `shared/platform-ops/gitops/dev-k8s/.images.env` containing `IMAGE_TAG` plus one `*_IMAGE` variable per service — consumed by the deploy scripts.
- Provides cross-cutting targets: `base-images` (builds `shared/base-images/base-uv`), `sync-policy` (copies canonical policy from `shared/shared-contracts/policies/policy-default.yaml` into both gateway products and the K8s overlay), `validate-policy` (runs `shared/shared-contracts/scripts/validate_policy.py`), `overlays` (kustomize build check on all overlays), `verify` (test + overlays + validate-policy), and `deploy`.

### Shared fragments under `mk/`
- `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`). All values use `?=`, so command-line overrides always win. Includes a guard against double inclusion.
- `mk/image.mk` — shared Docker image targets (`build`, `push`, `lint`) included by each product Makefile. Requires the includer to set `IMAGE_NAME`; computes `IMAGE_REF` as `luban-aiops/<name>:<tag>` (or `<REGISTRY>/luban-aiops/<name>:<tag>`). Lint falls back to `docker run hadolint/hadolint` when `hadolint` is not installed.
- `mk/python.mk` — shared `sync` and `test` targets that run `uv sync --frozen` then `uv run pytest` inside the product directory so each product resolves its own `pyproject.toml` / `uv.lock`.

### Per-product Makefiles
Each product under `products/<name>/` has a tiny Makefile that only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. Example: `products/agent-platform/Makefile` declares `IMAGE_NAME := agent-service` and includes both fragments. This keeps every product's build surface identical.

### Container images
- Base image: `shared/base-images/base-uv/Dockerfile` builds an Amazon Linux 2023 minimal image with a pinned `uv` binary, no system Python, non-root `app` user (uid 1000), and environment variables pinning `UV_PYTHON=3.12`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Product images follow a uniform pattern: `FROM luban-aiops/base-uv:al2023`, copy `.python-version pyproject.toml uv.lock README.md src`, run `uv sync --frozen --no-dev`, expose port 8000, `CMD ["uv", "run", "<entrypoint>"]`.
- Images are built locally by default; pushing requires setting `REGISTRY`.

### GitOps & Deployment
- Overlays live under `shared/platform-ops/gitops/`: a `dev-k8s` base overlay plus runtime-profile overlays (`dashscope`, `deepseek`, `openai`). The root `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on each.
- `shared/platform-ops/gitops/deploy-overlay.sh` reads `.images.env`, renders the overlay via `kubectl kustomize`, applies it, then patches each deployment image with `kubectl set image` and waits for rollout status (120s timeout per deployment).
- `deploy.sh` wraps the overlay deploy, then provisions secrets via helper scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`) and optionally reconciles Keycloak realm/portal OIDC client.
- Optional `AUTO_LOAD_KIND=true` in `make build` auto-loads all built images into a kind cluster named by `KIND_CLUSTER_NAME`.

## Conventions & Constraints

- **Single tag across all services**: `make build` computes one `IMAGE_TAG` and writes it into `.images.env`; all seven services share the same tag, ensuring deployments stay in lockstep.
- **Frozen dependencies**: Python products use `uv sync --frozen` everywhere (both dev/test and production image builds), pinning versions from `uv.lock`.
- **Non-root containers**: Base image creates uid 1000 `app` user; product images inherit it.
- **No `latest` tags**: `mk/defaults.mk` comments explicitly forbid `latest`; tags are git-sha based, with `-dirty-<timestamp>` suffix for uncommitted changes.
- **Policy is single-sourced**: `policy-default.yaml` lives in `shared/shared-contracts/policies/` and must be propagated to consumers via `make sync-policy`; `make validate-policy` enforces schema compliance.
- **Overlay validation is part of verification**: `make verify` fails if any overlay does not render cleanly.
- **Per-product isolation**: Each product has its own `Dockerfile`, `pyproject.toml`, `uv.lock`, `tests/`, and `.python-version`; the root Makefile never touches product internals directly.
- **Cross-platform builds**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64` for native kind builds); base image build also honors it.