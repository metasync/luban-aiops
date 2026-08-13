---
kind: dependency_management
name: Per-Product Python Dependency Management with uv and Frozen Lockfiles
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/agent-platform/.python-version
    - docs/workspace/python-container-strategy.md
    - docs/workspace/backend-service-layout-convention.md
---

## System / Approach

The workspace uses **uv** (Astral) as the sole Python package manager across all backend products. Each product under `products/` is an independent Python package declared in its own `pyproject.toml`, with a co-located `uv.lock` lockfile that pins every transitive dependency to exact versions. There is no monorepo-level `pyproject.toml` or shared virtual environment — each service manages its own dependency graph.

The build system is Make-driven (`mk/python.mk`) and wraps uv commands: `make sync` runs `uv sync --frozen` and `make test` re-syncs then runs pytest. The `--frozen` flag enforces that installs must match `uv.lock` exactly, preventing drift between development and CI.

Python interpreter selection is explicit via per-product `.python-version` files (all set to `3.12`), which uv resolves automatically. A shared base image (`shared/base-images/base-uv/Dockerfile`) installs a pinned `uv` version (`0.12.1`) and sets `UV_PYTHON=3.12` plus `UV_PYTHON_INSTALL_DIR=/app/.python` so uv can fetch the interpreter deterministically inside containers without a system Python.

## Key Files

- Per-product manifests:
  - `products/agent-platform/pyproject.toml`, `products/platform-gateway/pyproject.toml`, `products/tool-gateway/pyproject.toml`, `products/identity-broker/pyproject.toml`
  - Corresponding `uv.lock` files in each product directory
  - Per-product `.python-version` files
- Shared tooling:
  - `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen`
  - `shared/base-images/base-uv/Dockerfile` — pinned uv + Python runtime image
- Documentation:
  - `docs/workspace/backend-service-layout-convention.md` — prescribes using `uv.lock` with `uv sync --frozen`
  - `docs/workspace/python-container-strategy.md` — prescribes copying `pyproject.toml` and `uv.lock` into images and running `uv sync --frozen --no-dev` for production builds

## Architecture and Conventions

- **Version pinning style**: All runtime dependencies use caret-style ranges that allow patch updates but block minor/major bumps (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `cryptography>=43.0,<45.0`). This balances security patch uptake with API stability.
- **Dev vs runtime deps**: Optional dev-only packages (pytest, jsonschema, fakeredis) are declared under `[dependency-groups] dev = [...]` rather than separate files; they are installed alongside runtime deps during development but excluded from production images via `--no-dev`.
- **Build backend**: Every product declares `build-system.requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"`, ensuring reproducible sdist/wheel builds.
- **Entrypoints**: Executable scripts are registered via `[project.scripts]` (e.g. `agent-service`, `platform-gateway`, `tool-gateway`, `identity-service`) so Docker CMDs invoke them uniformly.
- **Container strategy**: Product Dockerfiles copy only `.python-version`, `pyproject.toml`, `uv.lock`, and `README.md` before running `uv sync --frozen --no-dev`, guaranteeing that the image contains exactly the locked dependency tree.
- **No vendoring / no private registry**: Dependencies are resolved from PyPI (and any uv-configured index). No `vendor/` directories, no `requirements.txt`, no `pip.conf`/`pip.ini` overrides were found in this repository.

## Conventions and Constraints

- **Deterministic installs**: `uv sync --frozen` is used everywhere (Make targets, documented container builds); this forbids installing packages not present in `uv.lock`. Violations fail the command.
- **Locked lockfiles**: `uv.lock` is committed alongside each product's source; it is the single source of truth for exact transitive versions.
- **Interpreter pinning**: `.python-version` at both repo root and per-product level pins Python 3.12; the base image hardcodes `UV_PYTHON=3.12` as a fallback.
- **Shared dependency alignment**: Common libraries (FastAPI, httpx, PyJWT, cryptography, PyYAML, Pydantic, OpenTelemetry exporters/instrumentation, prometheus-client, uvicorn) appear across multiple products with aligned version ranges, keeping cross-service binaries compatible.
- **Production images exclude dev deps**: Container builds pass `--no-dev` to `uv sync`, so only runtime dependencies ship to production.
- **Base image reuse**: All backend services inherit from `shared/base-images/base-uv`, which pins uv itself and provides a non-root `app` user, ensuring consistent dependency resolution behavior across services.