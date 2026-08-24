---
kind: dependency_management
name: Per-Product uv Lockfiles with Shared Base Image and Makefile Orchestration
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/agent-platform/.python-version
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/.nvmrc
---

# Dependency Management in the Agentic AIOps Platform

## System Overview

The workspace is a multi-product Python/Node monorepo. Each backend product under `products/` is an independent Python package managed by **uv** (Astral's Python package manager), with its own `pyproject.toml` and a per-product `uv.lock` lockfile. The frontend operator portal (`products/operator-portal/web-ui/app`) uses **npm** with `package.json` + `package-lock.json`. There is no shared Python dependency manifest at the repository root — each product owns its dependencies independently.

## Key Files and Packages

- Per-product manifests: `products/*/pyproject.toml` declare runtime `dependencies`, optional `[dependency-groups].dev` for test-only packages, and a `[build-system]` pinning `uv_build>=0.8.14,<0.9.0` as the build backend.
- Per-product lockfiles: `products/*/uv.lock` (one per product) provide deterministic resolution; the Make targets invoke `uv sync --frozen` to enforce them.
- Node manifest: `products/operator-portal/web-ui/app/package.json` plus `package-lock.json` for the React/Vite UI.
- Shared tooling:
  - `mk/python.mk` — shared `sync` / `test` make targets that run `uv sync --frozen` then `uv run pytest` with OTel exporters disabled during tests.
  - `mk/image.mk` — shared Docker image build/push targets used by every product Makefile.
  - `shared/base-images/base-uv/Dockerfile` — shared base image built from Amazon Linux 2023 minimal, installing a pinned `uv` version (default `0.12.1`) and setting `UV_PYTHON`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON_INSTALL_DIR=/app/.python` so each container installs its own interpreter per product `.python-version`.
- Version pin files: each product has a `.python-version` file (e.g. `products/agent-platform/.python-version` = `3.12`; `web-ui/app/.nvmrc` pins Node ≥ 22).

## Architecture and Conventions

### Python dependency strategy

- **Per-package isolation**: there is no workspace-level `pyproject.toml` or shared virtual environment. Each product resolves its own dependency graph against its own `uv.lock`, so upgrades are scoped to one service.
- **Version ranges**: runtime dependencies use caret-style upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`). This allows patch/minor updates while blocking breaking major versions. Dev dependencies follow the same pattern (`pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`).
- **Build-time pinning**: `[build-system]` pins `uv_build` to a narrow range, ensuring reproducible builds across environments.
- **Frozen installs in CI/dev**: `mk/python.mk` always runs `uv sync --frozen`, meaning the lockfile is authoritative — `uv` will refuse to resolve anything outside `uv.lock`. New dependencies must be added via `uv add ...` (which regenerates the lock) rather than editing it by hand.
- **Runtime interpreter selection**: the shared base image does not ship a system Python. Instead, `UV_PYTHON=${PYTHON_VERSION}` combined with `UV_PYTHON_INSTALL_DIR=/app/.python` makes `uv sync` install the exact interpreter declared in the product's `.python-version` into the image, guaranteeing the same CPython version used locally and in containers.
- **No vendoring of third-party code**: all third-party libraries are resolved from PyPI at build time; nothing is vendored under `src/`.

### Node dependency strategy

- The operator portal web UI is a standalone npm project inside `products/operator-portal/web-ui/app/`, using standard `package.json` + `package-lock.json` conventions. Dependencies include Ant Design, React, Vite, Vitest, and TypeScript. No custom registry or private scope is configured in the visible config.

### Containerization ties

- Every product ships a `Dockerfile` that layers on top of the shared `base-uv` image. Because the base image sets `UV_NO_SYNC=1`, the actual `uv sync` happens at image build time (via the product Makefile's `build` target), freezing the dependency set into the image layers.
- Image tags default to the short git SHA (`IMAGE_TAG ?= $(shell git rev-parse --short HEAD ...)`), tying a deployed image to a specific dependency snapshot.

## Conventions and Constraints

| Area | Observed convention / constraint | Source |
|---|---|---|
| Dependency declaration location | All Python dependencies live in each product's `pyproject.toml` under `[project.dependencies]`; dev-only deps go under `[dependency-groups].dev`. | `products/*/pyproject.toml` |
| Deterministic installs | Development and CI use `uv sync --frozen`, which refuses to touch the lockfile. | `mk/python.mk` |
| Build backend | All products pin `uv_build>=0.8.14,<0.9.0` as their PEP 517 build backend. | `products/*/pyproject.toml` `[build-system]` |
| Python version pinning | Each product declares a single CPython version in `.python-version`; the shared base image installs that interpreter into `/app/.python`. | `shared/base-images/base-uv/Dockerfile`, `products/*/.python-version` |
| Major-version caps | Runtime dependencies consistently cap the next major version (e.g. `<1.0` for FastAPI/Uvicorn, `<3.0` for Pydantic/AgentScope). | `products/*/pyproject.toml` |
| No global workspace lock | There is no root `uv.lock` or `requirements.txt`; each product manages its own lockfile independently. | Absence of root manifest; per-product `uv.lock` present |
| No vendored third-party code | Libraries are installed from PyPI at build time; no `vendor/` directories exist. | File tree inspection |
| Node engine pinning | Web UI declares `engines.node >= 22` and an `.nvmrc` file. | `products/operator-portal/web-ui/app/package.json`, `.nvmrc` |
| Image tagging | Images are tagged with the commit SHA by default, binding deployments to a specific dependency snapshot. | `mk/image.mk` |

## Notable Observations

- **Private registries / authentication**: No `uv.toml`, `pip.conf`, `.netrc`, or npm registry overrides are visible in the repository. If a private PyPI or npm registry is used, it is expected to be supplied via environment variables or host configuration outside this repo.
- **Cross-product shared Python packages**: There is no `shared/` Python package referenced from other products' `pyproject.toml` files; inter-service communication is HTTP-based over well-defined JSON schemas in `shared/shared-contracts/schemas/`, not through shared Python imports.
- **Testing isolation**: Tests run against the frozen lockfile with OTel exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) to avoid network noise during unit tests.