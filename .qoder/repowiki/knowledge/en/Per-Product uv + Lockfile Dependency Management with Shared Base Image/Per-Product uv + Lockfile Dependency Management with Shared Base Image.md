---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management with Shared Base Image
category: dependency_management
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/execution-runtime/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/package-lock.json
    - mk/python.mk
    - Makefile
    - shared/base-images/base-uv/Dockerfile
---

# Dependency Management in Luban AIOps Platform

## System Overview

The repository uses a **per-product dependency management** model built on **uv** (the fast Python package manager and resolver) with **lockfiles** (`uv.lock`) pinned to exact versions, and a shared container base image that pins the uv runtime itself. The frontend web UI under `products/operator-portal/web-ui/app/` uses **npm/pnpm-style** dependencies declared in `package.json` with a `package-lock.json` lockfile.

There is no monorepo-level `pyproject.toml`, no vendored third-party code, and no private PyPI registry configured — all Python packages are resolved from the public PyPI index (`https://pypi.org/simple`).

## Key Files and Packages

### Python products (8 services)
Each product under `products/<name>/` declares its own `pyproject.toml` and ships a committed `uv.lock`. The manifest pattern is consistent across every service:

- `requires-python = ">=3.11"` (enforced by each product).
- Runtime dependencies use **upper-bound major-version pinning** (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`, `cryptography>=43.0,<45.0`, `httpx>=0.27,<1.0`, `PyJWT>=2.8,<3.0`, `PyYAML>=6.0,<7.0`, `redis>=6.2,<7.0`, `psycopg[binary]>=3.2,<4.0`, `prometheus-client>=0.20,<1.0`, `uvicorn[standard]>=0.30,<1.0`).
- Development-only dependencies live in `[dependency-groups] dev = [...]` (`pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`; `fakeredis` for agent-platform).
- Each product exposes CLI entry points via `[project.scripts]` (e.g. `agent-service`, `platform-gateway`, `tool-gateway`, `audit-service`, `identity-service`, `incident-service`, `skills-hub`, `execution-runtime`).
- Build backend is `uv_build` with `uv_build>=0.8.14,<0.9.0` pinned in `[build-system]`.

Lockfiles: `products/agent-platform/uv.lock` (and equivalent per product) record the full transitive resolution tree with `source = { registry = "https://pypi.org/simple" }` and SHA256 hashes for every wheel/sdist, ensuring reproducible installs.

### Frontend
`products/operator-portal/web-ui/app/package.json` declares React/AntD/Vite dependencies with caret ranges (`^`) and is accompanied by `package-lock.json` as the lockfile. Node version is constrained via `engines.node = ">=22"` and `.nvmrc`.

### Shared base image
`shared/base-images/base-uv/Dockerfile` builds a minimal Amazon Linux 2023 image with a **pinned uv binary** (`UV_VERSION=0.12.1` installed via `curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh`) and sets environment variables `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=<version>` so containers run with a deterministic uv/python stack.

## Architecture and Conventions

### Per-product isolation
Each service owns its own dependency graph. There is no shared Python workspace or cross-product `requirements.txt`. This means adding a new library requires editing exactly one `pyproject.toml` plus committing the regenerated `uv.lock`.

### Version pinning strategy
Runtime dependencies use **semantic upper bounds** (`>=X.Y,<Z.0`) rather than exact pins in `pyproject.toml`, allowing minor/patch updates while blocking breaking major upgrades. The *exact* versions are then locked by `uv.lock`, which is what CI and containers consume.

### Frozen installs in CI
The shared Make target in `mk/python.mk` runs `uv sync --frozen`, which refuses to resolve against the network and instead installs strictly from the committed `uv.lock`. This enforces that dependency changes must be committed explicitly — you cannot silently drift during test runs.

### Coordinated build pipeline
The root `Makefile` lists `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and provides `make sync` / `make test` / `make build` that iterate over every product. All images are tagged with a coordinated `IMAGE_TAG` derived from the root `VERSION` file; the same tag is applied to every product image, keeping runtime dependency versions synchronized across services at deploy time.

### No vendoring, no private registry
All Python packages resolve from `https://pypi.org/simple`. There is no `pip.conf`, `PYPI_URL`, `uv config`, `GOPRIVATE`, or vendor directory. Secrets and credentials are not part of dependency management here (they are provisioned separately via GitOps secret-sync scripts under `shared/platform-ops/gitops/`).

## Conventions and Constraints

- **Every Python product must have a `pyproject.toml` and a committed `uv.lock`**; `make verify` will fail if tests cannot run because the lockfile is missing or out of date.
- **Dependency changes require committing the updated `uv.lock`**: `uv sync --frozen` in CI prevents uncommitted resolution drift.
- **Python version is pinned per product** via `.python-version` files and enforced by the shared base image's `UV_PYTHON` env var.
- **Major-version upper bounds are required** in `pyproject.toml` for all runtime dependencies (observed uniformly across all eight services); this is the de facto convention preventing accidental breaking upgrades.
- **Dev-only dependencies go in `[dependency-groups] dev`**, not in the main `dependencies` list, keeping production images lean.
- **Frontend dependencies follow npm conventions**: `package.json` + `package-lock.json` under `products/operator-portal/web-ui/app/`, with Node >= 22 enforced via `engines`.
- **No cross-product Python package sharing**: there is no `shared/shared-sdk` published as a PyPI package consumed by other products; inter-service communication is HTTP-based using JSON schemas defined in `shared/shared-contracts/schemas/`.