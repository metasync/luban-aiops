---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management with Coordinated Versioning
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/defaults.mk
    - VERSION
    - shared/shared-contracts/scripts/validate_version.py
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/platform-gateway/uv.lock
    - products/audit-service/pyproject.toml
    - products/audit-service/uv.lock
    - products/identity-broker/pyproject.toml
    - products/identity-broker/uv.lock
    - products/incident-service/pyproject.toml
    - products/incident-service/uv.lock
    - products/skills-hub/pyproject.toml
    - products/skills-hub/uv.lock
    - products/tool-gateway/pyproject.toml
    - products/tool-gateway/uv.lock
    - products/operator-portal/web-ui/app/package.json
---

## System / Approach

The monorepo manages dependencies per product using **uv** as the Python package manager and **npm/pnpm** for the single Node.js frontend. Each Python product under `products/` is an independent project with its own `pyproject.toml`, a sibling `uv.lock` lockfile, and a `.python-version` pin. The root Makefile orchestrates dependency installation across all products via shared `mk/python.mk` targets that invoke `uv sync --frozen`, guaranteeing that builds and tests resolve against the committed lockfiles.

There is no workspace-level `pyproject.toml` or shared Python dependency manifest — each service declares its own runtime and dev dependencies explicitly. Dev-only packages are grouped under `[dependency-groups] dev = [...]` in each `pyproject.toml` (e.g. `pytest`, `jsonschema`, `fakeredis`).

The Node.js frontend (`products/operator-portal/web-ui/app/package.json`) uses npm-style `dependencies`/`devDependencies` with a `package-lock.json`; there is no vendored `node_modules` checked in.

## Key Files

- `Makefile` — root orchestration: `make sync` iterates `PYTHON_PRODUCTS` and runs `make -C products/<name> sync`; `make verify` includes `validate-version` which enforces version lockstep.
- `mk/python.mk` — shared `sync` target: `uv sync --frozen` (lockfile-enforced) and test runner that disables OTel exporters to keep test output clean.
- `mk/defaults.mk` — pins shared base image tool versions (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`); these control the Docker base image used by every product build.
- Per-product manifests:
  - `products/agent-platform/pyproject.toml`
  - `products/platform-gateway/pyproject.toml`
  - `products/audit-service/pyproject.toml`
  - `products/identity-broker/pyproject.toml`
  - `products/incident-service/pyproject.toml`
  - `products/skills-hub/pyproject.toml`
  - `products/tool-gateway/pyproject.toml`
- Per-product lockfiles: `products/*/uv.lock` (committed alongside `pyproject.toml`).
- `shared/shared-contracts/scripts/validate_version.py` — enforces that every product's `pyproject.toml` `[project] version`, each product's `src/*/metadata.py` `SERVICE_VERSION`, any `__version__` in package roots, and the portal's Vite wiring all match the single source of truth at the root `VERSION` file.
- `VERSION` — single source of truth for the platform semver; read by `make validate-version`.
- `products/operator-portal/web-ui/app/package.json` — frontend dependency declarations.

## Architecture and Conventions

- **Per-product isolation**: Each service owns its own dependency graph. There is no cross-product Python import of another product's code; inter-service communication happens over HTTP/gRPC contracts defined in `shared/shared-contracts/schemas/*.schema.json`. This keeps dependency graphs small and avoids shared transitive conflicts.
- **Lockfile-first installs**: All `uv` invocations use `--frozen`, so CI and local development must update the lockfile (via `uv lock`) before committing changes. No floating resolutions are allowed at install time.
- **Version pinning style**: Runtime dependencies use caret ranges with explicit upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `agentscope>=2.0.4,<3.0`), preventing accidental major-version upgrades while allowing minor/patch updates. Dev dependencies follow the same pattern.
- **Shared base image**: The Docker images for all Python services are built from `shared/base-images/base-uv`, whose `UV_VERSION` and `PYTHON_VERSION` are pinned in `mk/defaults.mk`. This ensures reproducible environments across products.
- **Coordinated release versioning**: The root `VERSION` file is the single source of truth. `make validate-version` (invoked by `make verify`) scans every product's `pyproject.toml` version, `metadata.py` `SERVICE_VERSION`, and the portal's Vite config wiring, failing if any drift is detected. This couples dependency updates to coordinated releases.
- **Policy files as deploy-time dependencies**: Policy bundles live in `shared/shared-contracts/policies/policy-default.yaml` and are copied into each gateway/service via `make sync-policy`, keeping policy enforcement logic decoupled from Python dependencies.

## Conventions and Constraints

- **Python**: Every Python product must have a `pyproject.toml` with a `[project] version` matching the root `VERSION`, and a committed `uv.lock`. Adding a new product requires adding it to the `PYTHON_PRODUCTS` list in the root `Makefile` so `make sync` and `make test` cover it.
- **Dependency groups**: Runtime vs. dev dependencies are separated via `[dependency-groups] dev = [...]`; only runtime deps should be listed under `[project].dependencies`.
- **No vendoring**: Dependencies are resolved from PyPI (and any configured registry) at install/build time; nothing is vendored into the repo except the lockfiles.
- **Node.js**: Frontend dependencies are declared in `package.json` with a `package-lock.json`; there is no workspace-level npm configuration.
- **Base image reproducibility**: Base image tool versions (`BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`) are pinned defaults in `mk/defaults.mk` and overridden only via make variables; they must not be left as `latest`.
- **Verification gate**: `make verify` runs `test`, `overlays`, `validate-policy`, and `validate-version` — any dependency or version change that breaks one of these checks blocks the pipeline.