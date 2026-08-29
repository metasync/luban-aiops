---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management with Frozen Sync
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - Makefile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/agent-platform/uv.lock
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## System Overview

The repository manages dependencies using a per-product, lockfile-first approach centered on **uv** (the fast Python package manager). Each product under `products/<name>/` is an independent Python package declared in its own `pyproject.toml`, with a committed `uv.lock` pinning every transitive dependency to exact versions and hashes. The frontend portal (`products/operator-portal/web-ui/app/package.json`) uses npm-style `package.json` with `package-lock.json` for the Node/React stack.

There is no monorepo-level dependency manifest — each product owns its own dependency graph. The root Makefile orchestrates cross-product operations like `make sync` (iterates over all Python products) and `make test`, but does not resolve dependencies centrally.

## Key Files and Packages

- `mk/python.mk` — shared Make targets that invoke `uv sync --frozen` and `uv run pytest`; this is the single entry point for installing and testing Python dependencies across all eight Python products.
- `mk/image.mk` and `mk/defaults.mk` — pinned base image settings: `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`, built into `shared/base-images/base-uv/Dockerfile` so containers reproduce the same uv version used locally.
- Root `Makefile` — declares `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and dispatches `sync`/`test` to each.
- Per-product `pyproject.toml` files — declare runtime dependencies with caret ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`) plus `[dependency-groups].dev` for test-only packages.
- Per-product `uv.lock` files — commit exact resolved versions, sources, and SHA256 hashes for every transitive dependency; the lockfiles are the source of truth for reproducible installs.
- `products/operator-portal/web-ui/app/package.json` — frontend dependencies (antd, react, vite, vitest, etc.) with `engines.node >= 22.22.2`.
- `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` — documents the adopted policy: "latest stable only" (no alpha/beta/RC/dev), with one recorded exception for OpenTelemetry instrumentation's permanent `0.xb` channel.

## Architecture and Conventions

1. **Per-product isolation**: Each service has its own `pyproject.toml` and `uv.lock`. There is no workspace-level `pyproject.toml` or shared virtual environment. Dependencies are resolved independently per product.

2. **Frozen resolution in CI and local dev**: `mk/python.mk` runs `uv sync --frozen`, which refuses to touch the lockfile — installs must match the committed `uv.lock` exactly. This enforces that dependency changes go through explicit updates rather than ad-hoc upgrades.

3. **Range-based declarations, lockfile-pinned resolution**: `pyproject.toml` declares semver-compatible ranges (e.g. `<3.0`, `<1.0`) to allow patch/minor bumps within a major, while `uv.lock` pins the exact version installed. Updates are done by regenerating the lockfile (via `uv`) and committing both files together.

4. **Shared base image pins uv and Python**: `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; the Dockerfile for `shared/base-images/base-uv` builds from these values, ensuring container environments match the developer environment.

5. **Frontend lockfile**: The portal uses `package.json` with caret ranges and a committed `package-lock.json` (visible in the tree as `node_modules/` being present), following standard npm practice.

6. **Version lockstep enforcement**: The root `Makefile` includes `validate-version` which runs `shared/shared-contracts/scripts/validate_version.py` against the repo root to keep the `VERSION` file, product versions, and portal versions synchronized — part of the broader dependency hygiene gate.

## Conventions and Constraints

- **Latest stable only**: The release notes explicitly state the adoption policy is "latest stable only — no alpha, beta, RC, or dev builds", with the sole exception of OpenTelemetry instrumentation packages on their permanent `0.xb` channel.
- **Major-version caps**: Runtime dependencies use upper bounds to prevent breaking majors (e.g. `fastapi>=0.115,<1.0`, `redis>=6.2,<7.0`, `psycopg[binary]>=3.2,<4.0`). The release notes document deliberate decisions to cap redis at `<7.0` because client 7 was an API-removal release and no Elasticsearch server is deployed.
- **Dev vs runtime separation**: Test-only packages live in `[dependency-groups].dev` in `pyproject.toml` and are not included in production installs.
- **Frozen installs**: `uv sync --frozen` is mandatory via the shared Make target; any drift between `pyproject.toml` ranges and `uv.lock` will fail the build.
- **No vendoring**: Dependencies are fetched from PyPI (`source = { registry = "https://pypi.org/simple" }` in lockfiles); there is no vendored copy of third-party code.
- **Base image reproducibility**: The shared base image pins uv and Python versions, so `docker build` produces deterministic environments regardless of host uv installation.
- **Verification gate**: `make verify` runs `test` (which invokes frozen `uv sync` + pytest), `overlays`, `validate-policy`, and `validate-version` — dependency-related checks are enforced as part of the pre-commit/pre-push gate.