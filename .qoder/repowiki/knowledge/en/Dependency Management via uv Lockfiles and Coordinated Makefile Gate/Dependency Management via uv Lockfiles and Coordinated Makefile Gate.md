---
kind: dependency_management
name: Dependency Management via uv Lockfiles and Coordinated Makefile Gate
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/defaults.mk
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/package-lock.json
    - .python-version
    - shared/base-images/base-uv/Dockerfile
---

# Dependency Management

## Approach

The Luban AIOps Platform uses a **per-product dependency model** with two toolchains:

- **Python products** (seven services under `products/`): declared in each product's `pyproject.toml`, resolved and pinned by **uv** lockfiles (`uv.lock`) committed per product. The build system is built around `uv sync --frozen` — no transitive drift is allowed.
- **Operator portal SPA** (`products/operator-portal/web-ui/app`): declared in `package.json`, resolved by npm to `package-lock.json` (lockfileVersion 3).

There is no monorepo-level Python dependency manifest, no vendored third-party source, and no private PyPI registry configured at the workspace level. All Python packages resolve against the public `https://pypi.org/simple` index (visible in every `source = { registry = "https://pypi.org/simple" }` entry in the `uv.lock` files). No `uv.toml`, `UV_DEFAULT_INDEX`, `UV_PIP_INDEX_URL`, or `UV_CONSTRAINTS_FILE` configuration was found anywhere in the repository.

## Key Files

| File | Role |
|---|---|
| `Makefile` | Root orchestrator; defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`; exposes `make sync`, `make test`, `make verify` which delegate to per-product Makefiles |
| `mk/python.mk` | Shared `sync` / `test` targets for Python products — both run `uv sync --frozen` before pytest |
| `mk/defaults.mk` | Centralizes overridable build defaults including `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12` (the base image Dockerfile pins these) |
| `products/*/pyproject.toml` | Declares runtime dependencies with upper-bound major-version specifiers (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `agentscope>=2.0.4,<3.0`) |
| `products/*/uv.lock` | Fully pinned transitive tree with SHA-256 hashes of sdist/wheel artifacts from pypi.org |
| `products/operator-portal/web-ui/app/package.json` | Node.js dependencies and devDependencies |
| `products/operator-portal/web-ui/app/package-lock.json` | npm lockfile (v3) pinning the SPA's dependency tree |
| `.python-version` | Workspace-level Python version hint used by uv/pyenv-style tooling |
| `shared/base-images/base-uv/Dockerfile` | Base image that installs the pinned `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION` |

## Architecture and Conventions

### Per-product isolation
Each Python service owns its own `pyproject.toml` + `uv.lock`. There is no shared `requirements.txt`, no workspace-level `pyproject.toml`, and no `dependency-groups` sharing across products. Cross-cutting concerns are expressed as shared contracts under `shared/shared-contracts/` (schemas, policies, SQL), not as shared Python packages consumed through the package manager.

### Version specifier style
Runtime dependencies use **inclusive lower bounds with exclusive upper bounds on the next major version**, e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`, `redis>=6.2,<7.0`. This allows minor/patch upgrades within a major line while preventing breaking-major upgrades from being pulled in automatically. Dev/test dependencies follow the same pattern (e.g. `pytest>=8.3,<9.0`, `fakeredis>=2.26,<3.0`).

### Frozen resolution
Both `mk/python.mk:sync` and `mk/python.mk:test` invoke `uv sync --frozen`. The root `Makefile`'s `sync` target loops over all seven Python products and runs their individual `make sync`. This means the committed `uv.lock` is authoritative — running `uv sync` without `--frozen` is not part of the documented workflow.

### Base image pinning
`mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`. These values are passed as `--build-arg` into `shared/base-images/base-uv/Dockerfile`, which builds the `luban-aiops/base-uv:<tag>` image that every product Dockerfile inherits. The comment explicitly says "Pinned values below are defaults for reproducible builds — never `latest"`.

### Node/SPA dependencies
The operator portal is the only non-Python code path. It declares Node engines (`node >= 22.22.2`) and uses `vite` + `vitest` + `typescript` + `react` + `antd`. Its `package-lock.json` is committed alongside `package.json`.

### Release notes as change history
Release notes under `docs/agentic-aiops-platform/release-notes/` include entries such as `2026-08-28-dependency-hygiene.md` and `2026-09-27-dependency-refresh-agentscope-2-0-8.md`, `2026-10-31-dependency-refresh-agentscope-2-0-11.md`, documenting when dependency refreshes occur.

## Conventions and Constraints

- **Every Python product has its own `pyproject.toml` plus a committed `uv.lock`** — observed across all seven Python products under `products/`.
- **Transitive dependencies are fully pinned with SHA-256 hashes** in each `uv.lock` file; the lockfile records exact wheel/sdist URLs from `https://pypi.org/simple`.
- **`uv sync --frozen` is the enforced install command** — defined in `mk/python.mk` and invoked by both `make sync` and `make test` at the product and root levels.
- **No private PyPI registry or mirror is configured** — no `uv.toml`, no `UV_*` environment variables, no `index-url` overrides were found in the repository.
- **Major-version caps are used consistently** on runtime dependencies to prevent automatic breaking upgrades (e.g. `<1.0`, `<2.0`, `<3.0`, `<4.0`).
- **Dev/test dependencies are separated** into `[dependency-groups].dev` in `pyproject.toml` (e.g. `pytest`, `fakeredis`) and are not installed as runtime requirements.
- **The base image pins `uv` and `python` versions** via `mk/defaults.mk` (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`), and the root `Makefile` passes them as `--build-arg` to `docker build` for `shared/base-images/base-uv`.
- **Node dependencies are managed separately** under `products/operator-portal/web-ui/app/package.json` with a committed `package-lock.json` (lockfileVersion 3); the root Makefile does not orchestrate npm commands — it delegates to `make -C products/operator-portal test` and `web-build`.
- **Cross-service coupling is expressed as shared contracts, not shared packages**: policy bundles, JSON schemas, and SQL live under `shared/shared-contracts/` and are copied/synced by `make sync-policy` rather than installed via pip.