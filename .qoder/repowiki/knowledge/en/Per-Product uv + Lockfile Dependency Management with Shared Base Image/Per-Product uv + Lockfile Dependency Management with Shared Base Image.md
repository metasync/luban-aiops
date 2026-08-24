---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management with Shared Base Image
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/defaults.mk
    - docs/workspace/python-container-strategy.md
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
---

## System / Approach

The workspace uses **uv** as the single Python package and interpreter manager, with one `pyproject.toml` per product under `products/<name>/`. Each product declares its runtime dependencies in `[project.dependencies]`, dev-only dependencies in a `[dependency-groups].dev` section, and pins the build backend to `uv_build>=0.8.14,<0.9.0` via `[build-system]`. A corresponding `uv.lock` file is committed alongside each product's manifest and is copied into every container image.

For the Node.js frontend (`operator-portal/web-ui/app`), dependencies are managed conventionally via `package.json` plus a checked-in `package-lock.json`, with an `.nvmrc` pinning Node ≥ 22.

There is no monorepo-level dependency manifest — each product owns its own dependency graph independently.

## Key Files

- Per-product manifests: `products/*/pyproject.toml` (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway)
- Per-product lockfiles: `products/*/uv.lock` (committed alongside each `pyproject.toml`)
- Frontend manifest: `products/operator-portal/web-ui/app/package.json` + `package-lock.json`
- Shared Make fragments: `mk/python.mk` (defines `sync`/`test` targets that run `uv sync --frozen`), `mk/defaults.mk` (pins `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`)
- Container strategy doc: `docs/workspace/python-container-strategy.md` (documents the enforced `uv sync --frozen --no-dev` image build pattern)
- Root orchestrator: `Makefile` lists all Python products in `PYTHON_PRODUCTS` and runs `make -C products/$p sync` / `test` across them
- Dockerfiles: every Python product copies `.python-version`, `pyproject.toml`, and `uv.lock` before running `uv sync --frozen --no-dev`

## Architecture and Conventions

### Version ranges
All runtime dependencies use **caret-style upper bounds** (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `cryptography>=43.0,<45.0`). This allows minor/patch updates within a major version while preventing breaking upgrades. Dev dependencies follow the same pattern (e.g. `pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`).

### Interpreter pinning
Each product root contains a `.python-version` file; the shared base image (`shared/base-images/base-uv/Dockerfile`) installs a pinned `uv` version and sets `UV_PYTHON` so `uv sync` resolves the interpreter deterministically. The root `.python-version` also exists for workspace-wide reference.

### Deterministic builds
- Development: `make sync` (root) or `make -C products/<name> sync` invokes `uv sync --frozen`, which refuses to resolve against PyPI and requires the committed `uv.lock` to match exactly.
- CI / images: Dockerfiles copy only `.python-version`, `pyproject.toml`, and `uv.lock` first, then run `uv sync --frozen --no-dev`; the environment variable `UV_NO_SYNC=1` is set at the image level (inherited from the base image) so subsequent layers do not re-resolve.
- The `mk/python.mk` fragment enforces this by always invoking `uv sync --frozen` before `uv run pytest`.

### Build backend
Every Python product uses `uv_build` as its PEP 517 build backend (`[build-system].requires = ["uv_build>=0.8.14,<0.9.0"]`), keeping packaging consistent across services.

### Shared base image
`mk/defaults.mk` defines `BASE_UV_IMAGE=luban-aiops/base-uv`, `BASE_UV_TAG=al2023`, `BASE_UV_UV_VERSION=0.12.1`, and `BASE_UV_PYTHON_VERSION=3.12`. The root `Makefile`'s `base-images` target builds this image from `shared/base-images/base-uv/Dockerfile`, and `make build` depends on it. All Python product Dockerfiles start from `FROM luban-aiops/base-uv:al2023`.

### Frontend dependencies
The operator portal uses standard npm: `package.json` declares runtime deps (`react`, `antd`, `@ant-design/x`, etc.) and dev deps (`vite`, `vitest`, `typescript`, testing libs). A `package-lock.json` is committed under `products/operator-portal/web-ui/app/` to freeze versions. Node version is pinned via `.nvmrc` (≥ 22).

## Conventions and Constraints

- **One `pyproject.toml` per product** — there is no workspace-level `pyproject.toml` aggregating dependencies; each service manages its own graph.
- **Lockfiles are committed and mandatory** — `uv sync --frozen` is used everywhere (development, tests, image builds); any change to `pyproject.toml` must be followed by a regenerated `uv.lock`.
- **Dev vs runtime separation** — test-only packages live exclusively in `[dependency-groups].dev`; production images install with `--no-dev`.
- **No vendoring of third-party code** — packages are resolved from PyPI at build time; nothing is vendored into source control beyond lockfiles.
- **No private index configured** — the manifests contain no `index-url`, `extra-index-url`, or `pip.conf`; resolution goes to the default PyPI.
- **Interpreter selection is explicit** — `.python-version` files plus `UV_PYTHON` in the base image ensure the same CPython version is used locally and in containers.
- **Build toolchain is pinned centrally** — `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION` in `mk/defaults.mk` are the single source of truth for the uv and Python versions used by `make base-images` and the shared Dockerfile.
- **Frontend uses npm lockfile** — `package-lock.json` is checked in; `npm ci` is implied by the presence of the lockfile in standard CI flows.