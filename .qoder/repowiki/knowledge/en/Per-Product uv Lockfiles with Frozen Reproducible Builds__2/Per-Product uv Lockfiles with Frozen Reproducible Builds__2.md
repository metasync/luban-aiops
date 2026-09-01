---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Reproducible Builds
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/agent-platform/Dockerfile
    - products/operator-portal/web-ui/app/package.json
---

## What system/approach is used

The workspace manages dependencies with **uv** (Astral) as the Python package manager and lockfile tool, and **npm/pnpm-style `package.json` + `package-lock.json`** for the single Node.js frontend. Each product under `products/` is an independent Python distribution declared in its own `pyproject.toml`, with a co-located `uv.lock` that pins every transitive dependency to exact versions and SHA256 hashes. The build system enforces reproducibility by always invoking `uv sync --frozen` — both in CI via shared Make targets and inside Docker images at build time.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` declare `[project]` dependencies with semver ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `agentscope>=2.0.4,<3.0`) plus `[dependency-groups].dev` for test-only packages (`pytest`, `jsonschema`, `fakeredis`).
- Per-product lockfiles: `products/*/uv.lock` pin every resolved package to an exact version and source URL (all resolve from `https://pypi.org/simple`), including transitive deps like `agentscope-runtime`, `a2a-sdk`, `ag-ui-protocol`, `elasticsearch`, `kubernetes`, etc.
- Shared build fragments:
  - `mk/python.mk` — defines `sync` and `test` targets that run `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled so tests stay quiet.
  - `mk/image.mk` — generic Docker image build/push target used by each product.
  - `mk/defaults.mk` — central defaults for base image tags (`BASE_UV_IMAGE=luban-aiops/base-uv`, `BASE_UV_TAG=al2023`, `BASE_UV_PYTHON_VERSION=3.12`, `BASE_UV_UV_VERSION=0.12.1`).
  - `shared/base-images/base-uv/Dockerfile` — shared base image that installs a pinned `uv` (via `UV_VERSION` arg) onto Amazon Linux 2023 minimal, sets `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=3.12`, and runs as non-root user `app`.
- Product Dockerfiles (e.g. `products/agent-platform/Dockerfile`) copy only `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, and `src/`, then run `uv sync --frozen --no-dev` to install runtime deps without dev extras.
- Frontend: `products/operator-portal/web-ui/app/package.json` declares React/AntD dependencies; `package-lock.json` lives alongside it.

## Architecture and conventions

- **One manifest per product**: there is no monorepo-level `pyproject.toml` or workspace file. Each service (`agent-platform`, `platform-gateway`, `tool-gateway`, `audit-service`, `identity-broker`, `incident-service`, `skills-hub`, `execution-runtime`) owns its own dependency set and lockfile.
- **Semver-ranged declarations, locked resolution**: `pyproject.toml` uses caret/range constraints (e.g. `<3.0`, `>=0.115,<1.0`) to allow patch/minor updates while blocking breaking changes; `uv.lock` captures the exact resolved tree.
- **Frozen builds everywhere**: `--frozen` is passed to `uv sync` in `mk/python.mk` and in every product Dockerfile, guaranteeing that CI, local dev, and production images install exactly what is checked into version control.
- **Shared base image strategy**: all backend services derive from `luban-aiops/base-uv:al2023`, which ships a pinned `uv` and a pinned Python interpreter path (`/app/.python/<version>`). This avoids embedding a full system Python in images and lets `uv` manage interpreters deterministically.
- **No vendoring of third-party wheels**: dependencies are fetched from PyPI at build time; nothing is vendored into the repo.
- **No private registry configured**: grep across the repo finds no `UV_INDEX_URL`, `index-url`, `pip.conf`, `PIP_*_INDEX`, or `uv.config` overrides — all packages resolve against the public `https://pypi.org/simple` index.

## Conventions and constraints

- **Python version pinning**: every product specifies `requires-python = ">=3.11"` and carries a `.python-version` file; the shared base image defaults to Python 3.12 via `UV_PYTHON`.
- **Build backend pinned**: each `pyproject.toml` sets `build-system.requires = ["uv_build>=0.8.14,<0.9.0"]` and `build-backend = "uv_build"`, ensuring consistent builds even before dependencies are installed.
- **Dev vs runtime separation**: runtime deps live under `[project].dependencies`; test-only tools (`pytest`, `jsonschema`, `fakeredis`) live under `[dependency-groups].dev` and are excluded from production images via `uv sync --frozen --no-dev`.
- **Reproducible container images**: Dockerfiles copy `uv.lock` and invoke `uv sync --frozen --no-dev`, so the image content is fully determined by the committed lockfile.
- **Frontend lockfile**: the operator portal's `package-lock.json` (checked in alongside `package.json`) pins the Node.js dependency tree, matching the same frozen-reproducibility philosophy applied to Python.