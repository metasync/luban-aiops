---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management with Shared Base Image
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/package-lock.json
---

## System Overview

The repository manages dependencies using **uv** (Astral's Python package manager) at the per-product level, combined with a shared container base image that pins `uv` and Python versions. The operator-portal web UI uses **npm** (`package.json` + `package-lock.json`). There is no monorepo-level dependency manifest — each product under `products/` is an independent uv project.

## Key Files and Packages

- Per-product manifests: `products/*/pyproject.toml` declare runtime and dev dependencies via PEP 621 `[project]` and `[dependency-groups]` tables.
- Per-product lockfiles: `products/*/uv.lock` pin every transitive dependency to exact versions and include SHA-256 hashes, sourced from `https://pypi.org/simple`.
- Shared build tooling:
  - `mk/python.mk` — shared Make targets `sync` and `test` that invoke `uv sync --frozen` and `uv run pytest`, enforcing deterministic installs.
  - `mk/image.mk` — shared Docker image build/push targets used by each product's `Makefile`.
  - `shared/base-images/base-uv/Dockerfile` — shared base image that pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`, installs uv into `/usr/local/bin`, sets `UV_NO_SYNC=1` so products must explicitly `uv sync`, and runs as non-root user `app` (uid 1000).
- Web UI: `products/operator-portal/web-ui/app/package.json` declares React/AntD dependencies; `package-lock.json` locks them.
- Root `.python-version` and per-product `.python-version` files constrain interpreter selection.

## Architecture and Conventions

### Python services (all backend microservices)

1. **Dependency declaration**: Each service's `pyproject.toml` lists runtime deps in `[project].dependencies` (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`) and test/dev deps in `[dependency-groups].dev` (e.g. `pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`). This separates production from development requirements.
2. **Version pinning strategy**: Runtime dependencies use semver-compatible upper bounds (e.g. `<1.0`, `<2.0`, `<3.0`) to allow patch/minor updates while preventing breaking changes. Dev dependencies are similarly bounded.
3. **Lockfile enforcement**: `mk/python.mk`'s `sync` target runs `uv sync --frozen`, which refuses to install anything not recorded in `uv.lock`. This guarantees reproducible builds across environments.
4. **Shared base image**: All backend Dockerfiles inherit from `shared/base-images/base-uv`, which pins `uv` and Python, sets `UV_PYTHON_INSTALL_DIR=/app/.python`, and disables automatic syncing (`UV_NO_SYNC=1`). Product Dockerfiles must call `uv sync` during build to populate `/app/.venv` from the lockfile.
5. **No vendoring or private registry**: All packages resolve from PyPI (`source = { registry = "https://pypi.org/simple" }` in lockfiles). No `vendor/` directories, no `pip.conf`/`uv.toml` private index configuration is present.
6. **Build system**: `[build-system].requires = ["uv_build>=0.8.14,<0.9.0"]` and `build-backend = "uv_build"` standardize packaging across products.

### Node.js web UI

- Declared in `products/operator-portal/web-ui/app/package.json` with caret ranges (`^6.0.0`, `^18.3.1`, etc.).
- `package-lock.json` provides deterministic resolution for CI/build.
- Node version constrained via `.nvmrc` and `engines.node >= 22`.

## Conventions and Constraints

- **Frozen installs are mandatory**: The shared `mk/python.mk` target uses `uv sync --frozen`; any drift between `pyproject.toml` and `uv.lock` breaks the build. This is enforced by the Makefile, not by lint rules.
- **Python version pinned per product**: Each product has a `.python-version` file (and root `.python-version`), consumed by uv when resolving interpreters.
- **Runtime vs dev separation**: Dependencies are split into `[project].dependencies` (runtime) and `[dependency-groups].dev` (testing, linting), keeping production images lean.
- **Semver-compatible upper bounds**: All runtime dependencies cap major versions (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `redis>=6.2,<7.0`) to prevent accidental breaking upgrades.
- **Deterministic container builds**: The shared base image pins `uv` and Python versions, and `UV_NO_SYNC=1` forces explicit `uv sync` steps, ensuring the same lockfile is always applied inside containers.
- **No cross-product Python dependency sharing**: Each product owns its own `pyproject.toml` and `uv.lock`; there is no workspace-level `pyproject.toml` aggregating dependencies.