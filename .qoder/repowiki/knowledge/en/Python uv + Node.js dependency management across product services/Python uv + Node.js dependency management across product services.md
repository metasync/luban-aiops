---
kind: dependency_management
name: Python uv + Node.js dependency management across product services
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - Makefile
    - .python-version
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
---

## Approach

The Luban AIOps platform is a Python monorepo of nine backend products plus an operator-portal SPA. Dependency management is split between two toolchains:

- **Python**: `uv` (Astral) as both resolver and installer, with one `pyproject.toml` + `uv.lock` per product under `products/<name>/`. The build backend is `uv_build`.
- **Node.js / TypeScript**: the operator-portal SPA (`products/operator-portal/web-ui/app/package.json`) uses npm; its `node_modules/` directory is committed alongside the source.

There is no shared Python virtualenv at the repo root — each product owns its own lockfile. The root `.python-version = 3.12` declares the interpreter version for development, while every product's `pyproject.toml` constrains `requires-python = ">=3.11"`.

## Key files

- `mk/python.mk` — shared Make targets `sync` and `test`; `sync` runs `uv sync --frozen`, enforcing that only the committed `uv.lock` may be installed.
- Root `Makefile` — aggregates per-product `make -C products/$p sync|test|build|push`; `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` enumerates all Python products.
- Per-product `pyproject.toml` + `uv.lock` under `products/*/` — declare runtime deps in `[project.dependencies]` and dev-only deps in `[dependency-groups].dev`.
- `shared/base-images/base-uv/Dockerfile` — pinned base image: installs `uv==0.12.1` from `https://astral.sh/uv/${UV_VERSION}/install.sh`, sets `UV_PYTHON=3.12`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- `products/operator-portal/web-ui/app/package.json` — SPA dependencies managed by npm; `node_modules/` is checked into the repo.
- Root `.python-version` — pins the development interpreter to `3.12`.

## Architecture and conventions

1. **Per-product lockfiles, not a workspace.** Each product has its own `pyproject.toml` and `uv.lock`; there is no PEP 751 workspace or shared `pyproject.toml` aggregating them. The root `Makefile` iterates over `PYTHON_PRODUCTS` to invoke each product's Makefile.

2. **Frozen installs in CI and Docker.** `mk/python.mk` uses `uv sync --frozen`, so builds fail if `uv.lock` drifts from `pyproject.toml`. The base image also sets `UV_NO_SYNC=1`, meaning images are built with a pre-synced environment rather than resolving at container start.

3. **Version pinning style.** Runtime dependencies use broad upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`, `uvicorn[standard]>=0.30,<1.0`) to allow patch/minor updates while blocking major bumps. Dev dependencies follow the same pattern (`pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`).

4. **Build backend pinned.** Every Python product declares `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"`, ensuring reproducible sdist/wheel builds.

5. **Base image pins uv and Python versions.** `shared/base-images/base-uv/Dockerfile` hardcodes `ARG UV_VERSION=0.12.1` and `ARG PYTHON_VERSION=3.12`; the root `Makefile` passes these through `--build-arg BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION` when building `base-images`.

6. **No private registry or vendoring for third-party packages.** No `pip.conf`, `PYPI_MIRROR`, `UV_INDEX_URL`, `extra-index-url`, or `vendor/` directories were found. Packages resolve directly from PyPI (and public registries like ECR for the Amazon Linux base image). The only vendored code is the operator-portal's `node_modules/`.

7. **Cross-cutting scripts run via `uv run`.** Policy validation, secret-vocabulary checks, and password-policy validation in the root `Makefile` invoke `uv run python ...` against `shared/shared-contracts/scripts/*`, pulling their own transient environments rather than installing into a global venv.

## Conventions and constraints

- **Observed convention:** All Python products live under `products/<name>/` and expose entry points via `[project.scripts]` in their `pyproject.toml` (e.g. `agent-service`, `platform-gateway`, `tool-gateway`).
- **Observed convention:** Runtime and dev dependencies are separated using PEP 731 `[dependency-groups]` (`dev` group), not separate requirement files.
- **Enforced rule:** `mk/python.mk` runs `uv sync --frozen`; any change to `pyproject.toml` without updating `uv.lock` fails the `sync` target and therefore the `test` target.
- **Enforced rule:** The root `Makefile` lists every Python product in `PYTHON_PRODUCTS`; adding a new Python service requires registering it there for `make sync`, `make test`, `make lint`, and `make build` to cover it.
- **Enforced rule:** Container images are built from `shared/base-images/base-uv`, which pins `uv==0.12.1` and `python==3.12`; changing the interpreter requires updating both this Dockerfile and the root `.python-version`.
- **Enforced rule:** The operator-portal SPA is excluded from the Python product matrix — the root `Makefile` comment (SPEC-063 R-8c) states `operator-portal` is not a uv product and is tested separately via `make portal-test` running Vitest and `tsc/vite`.
- **No evidence of:** private PyPI mirrors, `pip.conf`/`PIP_INDEX_URL` configuration, `UV_INDEX_URL`, `UV_EXTRA_INDEX_URL`, or vendored Python wheels beyond the committed `node_modules/` of the SPA.