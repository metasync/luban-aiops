---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Reproducible Builds
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
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/agent-platform/Dockerfile
    - products/operator-portal/web-ui/app/package.json
---

## What system/approach is used

The Luban AIOps Platform monorepo manages dependencies through **per-product Python dependency manifests** using [uv](https://docs.astral.sh/uv/) as the package manager and resolver, paired with per-product `uv.lock` lockfiles. The frontend (`products/operator-portal/web-ui/app`) uses npm via `package.json` + `package-lock.json`. There is no shared Python workspace or monorepo-level `pyproject.toml`; each product under `products/*` is an independent uv project.

Python packages are resolved from the public PyPI registry (`https://pypi.org/simple`, visible in every `uv.lock` entry) — no private index or vendored wheels are configured at the repository level.

Container images are built with Docker, using a shared base image that pins `uv` (0.12.1) and installs it into `/usr/local/bin`. Product images copy only `pyproject.toml`, `uv.lock`, `.python-version`, and `src/`, then run `uv sync --frozen --no-dev` to install runtime deps deterministically without dev extras.

## Key files and packages

- Per-product dependency declarations: `products/*/pyproject.toml` (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway). All declare `requires-python = ">=3.11"` and use `build-backend = "uv_build"` with `uv_build>=0.8.14,<0.9.0`.
- Per-product lockfiles: `products/*/uv.lock` — frozen resolution graphs pinning exact transitive versions and wheel/sdist hashes from `pypi.org/simple`.
- Shared Makefile fragments:
  - `mk/python.mk` — defines `sync` and `test` targets that run `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled for test output cleanliness.
  - `mk/image.mk` — shared docker build/push targets; product Makefiles include it and set `IMAGE_NAME`.
  - `mk/defaults.mk` — included by `image.mk` for default registry/tag settings.
- Base image: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal, pinned `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, runs as non-root `app` user (uid 1000), sets `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Product Dockerfiles (e.g. `products/agent-platform/Dockerfile`) — copy `pyproject.toml` + `uv.lock` first, then `uv sync --frozen --no-dev`, then `CMD ["uv", "run", "<entrypoint>"]`.
- Frontend: `products/operator-portal/web-ui/app/package.json` (npm, Node `>=22`, React/AntD stack) with `package-lock.json`.
- Root `.python-version` file (present at repo root) — consumed by uv to select interpreter when none is found.

## Architecture and conventions

- **Per-product isolation**: Each service owns its own `pyproject.toml` and `uv.lock`. Dependencies are not hoisted to a shared location; there is no `uv workspace` configuration.
- **Frozen resolutions everywhere**: Both development (`make sync`, `make test` in `mk/python.mk`) and production builds (`uv sync --frozen --no-dev` in Dockerfiles) use `--frozen`, meaning the lockfile must be committed and cannot be auto-updated during the build. Any dependency change requires updating the relevant `pyproject.toml` and regenerating `uv.lock`.
- **Version pinning style**: Runtime dependencies use caret/hat ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`). This allows patch/minor updates within a major version while preventing breaking changes. Dev dependencies follow the same pattern (e.g. `pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`).
- **Shared dependency surface**: Across all seven Python services, common dependencies are declared identically (FastAPI, httpx, PyJWT, cryptography, opentelemetry-* SDKs, prometheus-client, pydantic, uvicorn[standard], psycopg[binary] where DB-backed). This is enforced by convention rather than a shared package — each product declares them explicitly.
- **No vendoring**: No `vendor/` directories or vendored wheels exist. All third-party code comes from PyPI at resolve time.
- **No private registry**: No `uv.config.toml`, `PYPI_URL`, `PIP_INDEX_URL`, or `[index]` sections were found. All packages resolve from `https://pypi.org/simple`.
- **Frontend separation**: Only the operator portal web UI uses npm; backend services do not mix JS dependencies.

## Conventions and constraints

- **Constraint: Build reproducibility via `--frozen`**. Every `uv sync` invocation in this repo uses `--frozen` (see `mk/python.mk` and all product Dockerfiles). This enforces that the committed `uv.lock` is authoritative — builds will fail if the lockfile drifts from `pyproject.toml`.
- **Constraint: Python version pinned per product**. Each `pyproject.toml` declares `requires-python = ">=3.11"`; the shared base image defaults to Python 3.12 but per-product `.python-version` files can override the interpreter selection.
- **Constraint: Non-root container execution**. The base image creates user `app` (uid 1000) and `USER app` is set; products inherit this and should not switch users.
- **Convention: Uniform dependency groups**. Every product follows the same `pyproject.toml` shape: `[project]` with `name`, `version`, `description`, `requires-python`, `dependencies`; optional `[dependency-groups].dev`; `[project.scripts]` mapping CLI names to `module:run`; `[build-system]` using `uv_build`.
- **Convention: Major-version bounds on all runtime deps**. No dependency is pinned to an exact version in `pyproject.toml`; all use lower-bound + upper-bound ranges to allow safe upgrades while blocking major breaks.
- **Convention: Dev-only extras via `[dependency-groups].dev`**. Test/dev tools (pytest, jsonschema, fakeredis) are isolated from runtime dependencies and excluded from images via `--no-dev`.
- **Constraint: Image layering copies `uv.lock` before source**. Dockerfiles copy `pyproject.toml` and `uv.lock` first so dependency installation is cached across source changes.