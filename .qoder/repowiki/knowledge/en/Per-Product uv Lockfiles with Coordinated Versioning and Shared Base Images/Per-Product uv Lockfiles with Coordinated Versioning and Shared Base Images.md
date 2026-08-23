---
kind: dependency_management
name: Per-Product uv Lockfiles with Coordinated Versioning and Shared Base Images
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - Makefile
    - .python-version
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
---

## What system/approach is used

The repository uses **uv** as the Python package manager and dependency resolver. Each product under `products/` is an independent Python project declared via a `pyproject.toml`, and each maintains its own `uv.lock` lockfile. The frontend web portal (`products/operator-portal/web-ui/app/package.json`) uses npm with a `package-lock.json`. There is no monorepo-level `pyproject.toml` or workspace manifest — dependencies are managed per-product.

## Key files and packages

- Per-product dependency manifests: `products/*/pyproject.toml` (e.g. `agent-platform/pyproject.toml`, `platform-gateway/pyproject.toml`, `audit-service/pyproject.toml`, `identity-broker/pyproject.toml`, `incident-service/pyproject.toml`, `skills-hub/pyproject.toml`, `tool-gateway/pyproject.toml`).
- Per-product lockfiles: `products/*/uv.lock` (e.g. `agent-platform/uv.lock`, which pins every transitive dependency to exact versions and SHA256 hashes).
- Shared Make fragments: `mk/python.mk` defines the canonical `sync` target that runs `uv sync --frozen`, enforcing lockfile fidelity; `mk/image.mk` builds container images using a shared base image.
- Root orchestrator: `Makefile` enumerates `PYTHON_PRODUCTS := agent-platform audit-service identity-broker incident-service platform-gateway skills-hub tool-gateway` and runs `make -C products/$p sync` for each.
- Frontend: `products/operator-portal/web-ui/app/package.json` + `package-lock.json` (npm, node `>=22`).
- Shared base image: `shared/base-images/base-uv/Dockerfile` plus `mk/defaults.mk` variables (`BASE_UV_*`) pin the uv and Python versions baked into images.
- `.python-version` at the repo root declares the Python version used by tools like uv.

## Architecture and conventions

1. **One `pyproject.toml` per service.** Every Python product declares itself as a standalone project with `[project]`, `dependencies`, optional `[dependency-groups] dev`, and `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` / `build-backend = "uv_build"`. No cross-product Python packages are referenced — services depend only on PyPI packages (and one internal-ish dependency, `agentscope-runtime`, which is published separately).

2. **Lockfiles are committed and frozen.** `mk/python.mk` runs `uv sync --frozen`, which refuses to resolve against the network and installs exactly what `uv.lock` records. The root `Makefile`'s `sync` target iterates all Python products and calls their per-product `sync`, so CI and local development always install from the committed lockfile.

3. **Version specifiers use caret-style ranges.** Across services, common dependencies are pinned with upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `cryptography>=43.0,<45.0`, `opentelemetry-sdk>=1.25,<2.0`, `uvicorn[standard]>=0.30,<1.0`, `psycopg[binary]>=3.2,<4.0`). This allows minor updates within a major while preventing breaking changes. Dev-only groups (`jsonschema`, `pytest`, `fakeredis`) follow the same pattern.

4. **Shared runtime surface is enforced by the build pipeline.** The root `Makefile` computes a single `IMAGE_TAG` from the root `VERSION` file and applies it to every product image via `make build IMAGE_TAG=...`. A `validate-version` target (via `shared/shared-contracts/scripts/validate_version.py`) enforces that the root `VERSION`, each product's `version`, and the portal version stay in lockstep. This coordinates releases across independently versioned packages.

5. **Container images are built from a shared base image.** `mk/image.mk` invokes `docker build` using a context per product, but the base image is built centrally from `shared/base-images/base-uv/Dockerfile` with `BASE_UV_*` and `BASE_UV_PYTHON_VERSION` variables. All Python services therefore run against the same uv and Python runtime.

6. **No vendoring of third-party code.** Dependencies are resolved from `https://pypi.org/simple` (visible in `uv.lock` entries) and installed into per-product `.venv` directories (present under each `products/*/`). There is no `vendor/` directory, no private PyPI registry configured in the checked-in config, and no `pip.conf` / `uv.toml` pinning a custom index.

7. **Frontend dependencies are separate.** The operator portal is a Node.js app under `products/operator-portal/web-ui/app/` with its own `package.json` and `package-lock.json`; it is not part of the Python uv dependency graph.

## Conventions and constraints

- **Every Python product must declare its own `pyproject.toml` and commit a matching `uv.lock`.** The `sync` target in `mk/python.mk` uses `--frozen`, so any drift between `pyproject.toml` and `uv.lock` will fail resolution.
- **Python version is pinned globally.** `.python-version` and the `requires-python = ">=3.11"` field in each `pyproject.toml` ensure all services target Python 3.11+; the base image is built with a specific `BASE_UV_PYTHON_VERSION`.
- **Dependency ranges must include an explicit upper bound.** Observed patterns consistently cap major versions (e.g. `<3.0`, `<1.0`, `<45.0`), preventing automatic upgrades to incompatible majors.
- **Dev dependencies are isolated in `[dependency-groups] dev`**, keeping production images lean; tests are run via `uv run pytest` after `uv sync --frozen`.
- **Cross-product coordination happens through the root `Makefile`, not through shared Python packages.** Services communicate over HTTP/gRPC and share JSON schemas under `shared/shared-contracts/schemas/`, but they do not import each other's Python code.
- **Policy YAMLs are synchronized from a canonical location** (`shared/shared-contracts/policies/policy-default.yaml`) via `make sync-policy`, mirroring the version lockstep approach used for Python dependencies.