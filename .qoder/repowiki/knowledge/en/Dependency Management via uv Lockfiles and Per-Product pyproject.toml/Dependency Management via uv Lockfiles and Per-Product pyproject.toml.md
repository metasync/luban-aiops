---
kind: dependency_management
name: Dependency Management via uv Lockfiles and Per-Product pyproject.toml
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/defaults.mk
    - Makefile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/agent-platform/.python-version
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
---

# Dependency Management

## Approach

The Luban AIOps Platform is a multi-product Python workspace (nine services under `products/`, plus an operator-portal SPA). Dependency management is handled by **uv** as the sole package manager for Python, with each product owning its own `pyproject.toml` and committed `uv.lock`. The operator-portal web UI uses npm-style dependencies declared in `products/operator-portal/web-ui/app/package.json`.

There is no vendoring of third-party source code — all packages are resolved from PyPI (`https://pypi.org/simple`, as recorded in every `uv.lock`). No private registry, `UV_INDEX_URL`, `index-url`, or `extra-index-url` configuration was found anywhere in the repository; dependency resolution goes directly to the public index.

## Key Files

- `mk/python.mk` — shared `sync` / `test` targets that invoke `uv sync --frozen` and `uv run pytest`; this is the single entry point for installing and running tests across all Python products.
- `mk/defaults.mk` — pins the base image's `BASE_UV_UV_VERSION = 0.12.1` and `BASE_UV_PYTHON_VERSION = 3.12`, which are baked into the shared `shared/base-images/base-uv` Docker image used by every product container.
- Root `Makefile` — aggregates per-product `sync`, `test`, `build`, `push` via `for p in $(PYTHON_PRODUCTS); do $(MAKE) -C products/$$p ...`
- Per-product `pyproject.toml` — declares runtime `dependencies`, `[dependency-groups] dev`, `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]`, and `requires-python`.
- Per-product `uv.lock` — fully pinned lockfile with hashes, wheel URLs, and `resolution-markers` for multiple Python/platform combinations.
- Per-product `.python-version` — e.g. `3.12` in `products/agent-platform/.python-version`.
- `products/operator-portal/web-ui/app/package.json` — frontend dependencies (React, Ant Design, Vite, Vitest).

## Architecture and Conventions

### Python: one `pyproject.toml` + `uv.lock` per product

Each service under `products/<name>/` is an independent uv project:

- `pyproject.toml` declares runtime dependencies with **upper-bound version specifiers** (e.g. `agentscope>=2.0.4,<3.0`, `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`). This constrains major versions while allowing minor/patch upgrades.
- `uv.lock` is committed alongside the manifest and records exact resolved versions, hashes, and wheel URLs from PyPI.
- Dev-only dependencies live in `[dependency-groups] dev` (e.g. `pytest>=8.3,<9.0`, `fakeredis>=2.26,<3.0`) rather than legacy `dev-dependencies`.
- The build backend is `uv_build` (`requires = ["uv_build>=0.8.14,<0.9.0"]`).
- `requires-python` is set at the project level (e.g. `>=3.11`), while `.python-version` files pin the developer-facing interpreter (e.g. `3.12`).

### Frozen installs enforced everywhere

`mk/python.mk` runs `uv sync --frozen` for both `sync` and `test`, meaning the lockfile is authoritative — no network resolution or transitive drift is allowed during CI or local development. The root Makefile delegates to these targets for every Python product.

### Base image pins toolchain versions

`mk/defaults.mk` pins `BASE_UV_UV_VERSION = 0.12.1` and `BASE_UV_PYTHON_VERSION = 3.12`. The root `make base-images` target builds `shared/base-images/base-uv` with those values, and every product Dockerfile layers on top of it. This ensures the uv binary and Python interpreter inside containers match the lockfile's `requires-python` and the developer environment.

### Frontend dependencies

The operator portal SPA (`products/operator-portal/web-ui/app/package.json`) declares React 19, Ant Design 6, Vite 8, Vitest 4, and TypeScript ~5.9. It uses `engines.node = ">=22.22.2"` and has no lockfile in the checked-in tree (npm/yarn/pnpm lockfiles were not found). The root `Makefile` invokes `make -C products/operator-portal test` and `web-build` through the portal's own Makefile.

### Cross-cutting orchestration

The root `Makefile` defines `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and iterates over them for `sync`, `test`, `lint`, `build`, and `push`. There is no monorepo-level `pyproject.toml` aggregating all dependencies — each product is self-contained.

## Conventions and Constraints

- **Every Python product owns its own `pyproject.toml` and `uv.lock`** — observed across all nine services under `products/`. Dependencies are never imported from a shared workspace manifest.
- **Runtime dependencies use upper-bound specifiers** (e.g. `<3.0`, `<1.0`, `<4.0`) in `pyproject.toml`, pinning major versions while permitting minor/patch updates.
- **Lockfiles are committed and installed frozen** — `mk/python.mk` enforces `uv sync --frozen`; any drift between `pyproject.toml` and `uv.lock` will fail the install step.
- **No private registry or custom index** — grep across all config files found zero occurrences of `UV_INDEX_URL`, `index-url`, or `extra-index-url`; all packages resolve from `https://pypi.org/simple` as recorded in `uv.lock` entries.
- **Toolchain versions are centralized in `mk/defaults.mk`** — `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION` are the single source of truth for the uv binary and Python interpreter baked into the shared base image.
- **Dev dependencies are isolated** in `[dependency-groups] dev` in `pyproject.toml`, separate from runtime `dependencies`.
- **Frontend dependencies are declared in `package.json`** under `dependencies` and `devDependencies`, with an `engines.node` constraint.
- **No vendored third-party source** — the repository contains no `vendor/`, `third_party/`, or equivalent directory holding copied library code.

## Notable External Dependencies

The most significant external dependency is `agentscope>=2.0.4,<3.0` (currently resolved to 2.0.11 in the lockfile) and its companion `agentscope-runtime>=1.1,<2.0` (resolved to 1.1.6.post2), which form the agentic runtime kernel referenced throughout the platform. Other common libraries include FastAPI, Pydantic, Redis, psycopg[binary], PyJWT[crypto], OpenTelemetry SDK/instrumentations, APScheduler, and Uvicorn.