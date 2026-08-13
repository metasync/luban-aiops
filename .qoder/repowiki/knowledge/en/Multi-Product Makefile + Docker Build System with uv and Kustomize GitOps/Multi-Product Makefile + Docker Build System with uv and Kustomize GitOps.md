---
kind: build_system
name: Multi-Product Makefile + Docker Build System with uv and Kustomize GitOps
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/tool-gateway/Makefile
    - products/identity-broker/Makefile
    - products/operator-portal/Makefile
    - products/agent-platform/Dockerfile
    - products/tool-gateway/Dockerfile
    - products/operator-portal/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

This repository uses a layered Makefile-based build system that coordinates Python packaging, container image builds, and Kubernetes deployment across multiple products.

**Build orchestration**: The root `Makefile` defines cross-cutting targets (`sync`, `test`, `lint`, `build`, `push`, `verify`, `deploy`) that delegate to per-product Makefiles under `products/<name>/`. Products are classified into `PYTHON_PRODUCTS` (agent-platform, identity-broker, tool-gateway) and `IMAGE_PRODUCTS` (agent-platform, identity-broker, tool-gateway, operator-portal).

**Shared fragments**: Two include files in `mk/` provide reusable targets:
- `mk/image.mk`: Container image build/push/lint using Docker. Sets `IMAGE_REF` as `luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>` (with optional `REGISTRY` prefix). Lints Dockerfiles via `hadolint` with a docker-run fallback.
- `mk/python.mk`: Python dependency sync and test execution via `uv sync --frozen` and `uv run pytest`.

**Per-product Makefiles**: Each product's `Makefile` is minimal — only sets `IMAGE_NAME` and includes the shared fragments. This keeps product definitions declarative and consistent.

**Python packaging**: All Python products use `pyproject.toml` with `uv_build` as the build backend, `uv.lock` for frozen dependencies, and `.python-version` for runtime pinning. Entrypoints are declared in `[project.scripts]` (e.g., `agent-service`, `api-gateway`).

**Container images**: Python product Dockerfiles use the official `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` base image, install dependencies with `uv sync --frozen --no-dev`, and run via `uv run <entrypoint>`. The operator-portal uses `nginx:1.27-alpine` serving static HTML/CSS/JS.

**Image tagging strategy**: The root `make build` computes a coordinated `IMAGE_TAG` once using `<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for uncommitted changes), then writes it plus all four image references to `shared/platform-ops/gitops/dev-k8s/.images.env`. This file is consumed by the deploy pipeline to ensure all services reference the same built images.

**Kubernetes deployment**: Uses Kustomize overlays under `shared/platform-ops/gitops/` (`dev-k8s`, `runtime-profiles/*`). The `make overlays` target validates all overlays render successfully. Deployment runs `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which calls `deploy-overlay.sh` and optionally reconciles an OIDC client.

**Verification gate**: `make verify` runs all product tests plus Kustomize overlay rendering checks — designed to be the single pre-commit/pre-push gate used both locally and in CI.