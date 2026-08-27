---
kind: dependency_management
name: uv-based Monorepo Dependency Management with Lockfiles and Coordinated Versioning
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - shared/shared-contracts/scripts/validate_version.py
    - shared/base-images/base-uv/Dockerfile
---

## System Overview

This monorepo manages dependencies for multiple Python services and a single Node.js frontend using **uv** as the package manager, with per-product `pyproject.toml` manifests and per-product `uv.lock` lockfiles. The root Makefile orchestrates dependency synchronization across all Python products via a shared `mk/python.mk` fragment that runs `uv sync --frozen`, ensuring every product installs exactly the versions pinned in its own lockfile.

## Key Files and Packages

- Per-product manifests: `products/*/pyproject.toml` declare runtime and dev dependencies (e.g. `agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`).
- Per-product lockfiles: each product ships a `uv.lock` alongside its `pyproject.toml`.
- Shared build fragments:
  - `mk/python.mk` — defines the `sync` target (`uv sync --frozen`) and test runner used by every Python product.
  - `mk/image.mk` — builds Docker images from each product's `Dockerfile`; images are tagged with a coordinated semver tag derived from the root `VERSION` file.
  - `mk/defaults.mk` — centralizes overridable defaults such as `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`, `IMAGE_PLATFORM=linux/amd64`, and `REGISTRY`.
- Root orchestration: `Makefile` enumerates `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and loops over them for `make sync`, `make test`, `make lint`, `make build`, `make push`.
- Frontend: `products/operator-portal/web-ui/app/package.json` declares React/AntD dependencies; no lockfile is committed (the directory contains `node_modules/`), so it relies on npm/yarn/pnpm resolution at build time.
- Version enforcement: `shared/shared-contracts/scripts/validate_version.py` asserts that every product's `pyproject.toml[project].version`, `src/*/metadata.py` `SERVICE_VERSION`, optional `__init__.py` `__version__`, and the portal's Vite wiring all match the single source of truth at `VERSION`.

## Architecture and Conventions

- **Per-product isolation**: Each service under `products/<name>/` is an independent uv project with its own `pyproject.toml` and `uv.lock`. There is no workspace-level `pyproject.toml` or shared virtual environment — `uv sync` is invoked per product.
- **Frozen installs in CI**: All `uv sync` invocations use `--frozen`, which refuses to update the lockfile. This enforces that dependency changes must be committed explicitly via `uv lock` before being merged.
- **Version pinning style**: Runtime dependencies use caret ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`) to allow compatible minor updates while blocking major-version breaks. Dev-only dependencies live in `[dependency-groups] dev = [...]` (pytest, jsonschema, fakeredis).
- **Shared base image**: `shared/base-images/base-uv/Dockerfile` is built once with a pinned `UV_VERSION` and `PYTHON_VERSION` from `mk/defaults.mk`, then consumed by all product images to ensure reproducible Python + uv environments.
- **Coordinated release versioning**: The root `VERSION` file is the single source of truth. `make validate-version` (via `validate_version.py`) fails if any product's declared version drifts. Image tags are computed as `<semver>-<prefix>[-<profile>]-<gitsha>` (dirty builds append `-dirty-<timestamp>`), and `make build` writes a `.images.env` state file listing all product images with the same tag.
- **Policy bundling**: Policy YAML files are copied from a canonical location (`shared/shared-contracts/policies/policy-default.yaml`) into each consumer via `make sync-policy`, mirroring the dependency model but for configuration artifacts.

## Conventions and Constraints

- **Every Python product must have a `pyproject.toml` and a `uv.lock`**; `make sync` will fail if `uv sync --frozen` cannot resolve the lockfile.
- **Dependency updates require committing the updated `uv.lock`**, because `--frozen` prevents implicit resolution against PyPI.
- **Python version constraint**: All Python products declare `requires-python = ">=3.11"`; the shared base image uses Python 3.12 (from `mk/defaults.mk`).
- **Build backend**: All Python products use `uv_build` (`build-system.requires = ["uv_build>=0.8.14,<0.9.0"]`, `build-backend = "uv_build"`).
- **No vendoring of third-party packages**: Dependencies are resolved from PyPI (or a configured registry) at install/build time; nothing is checked into `vendor/` directories.
- **Node.js frontend has no committed lockfile**: `package.json` uses caret ranges (`^`) and `node_modules/` exists in-tree, meaning the frontend does not participate in the frozen-lockfile discipline applied to Python code.
- **Cross-cutting constraints enforced by scripts**: `make verify` runs `test`, `overlays`, `validate-policy`, and `validate-version` together, so a PR cannot pass verification unless all product versions stay locked to `VERSION` and policy bundles remain valid.