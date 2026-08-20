---
kind: dependency_management
name: Per-Product uv-Based Python Dependency Management with Frozen Lockfiles
category: dependency_management
scope:
    - '**'
source_files:
    - products/incident-service/pyproject.toml
    - products/incident-service/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/agent-platform/pyproject.toml
    - mk/python.mk
    - Makefile
    - shared/base-images/base-uv/Dockerfile
---

## What system/approach is used

The repository manages Python dependencies per product using **uv** (a fast Python package manager) with **PEP 621 `pyproject.toml` manifests** and a per-product **`uv.lock` lockfile**. Each service under `products/` is an independent uv project with its own dependency graph, dev-only extras via `[dependency-groups]`, and a pinned build backend (`uv_build`). There is no monorepo-level `requirements.txt`, no shared `pip` virtualenv, and no vendored third-party source — all packages are resolved from PyPI at install time.

## Key files and packages

- Per-product dependency declarations: `products/*/pyproject.toml` (e.g. `incident-service/pyproject.toml`, `platform-gateway/pyproject.toml`, `agent-platform/pyproject.toml`). These declare runtime dependencies (FastAPI, httpx, Pydantic, PyJWT, PyYAML, cryptography, psycopg[binary], OpenTelemetry exporters/instrumentation, prometheus-client, uvicorn) and dev dependencies (`jsonschema`, `pytest`, plus `agentscope`/`redis` for the agent platform).
- Per-product lockfiles: `products/*/uv.lock` — fully pinned transitive dependency tree with checksums and wheel URLs sourced from `https://pypi.org/simple`.
- Shared Make targets: `mk/python.mk` defines `sync` (`uv sync --frozen`) and `test` (`uv sync --frozen && uv run pytest`), enforcing that installs use the locked versions.
- Root orchestrator: root `Makefile` lists `PYTHON_PRODUCTS := agent-platform audit-service identity-broker incident-service platform-gateway skills-hub tool-gateway` and runs `make -C products/$$p sync` across them; `verify` depends on `test` which invokes the frozen sync.
- Python version pinning: each product ships `.python-version` (e.g. `3.12`) alongside `requires-python = ">=3.11"` in `pyproject.toml`.
- Container base image: `shared/base-images/base-uv/Dockerfile` provides a uv-based image used by product Dockerfiles, ensuring the same resolver is available in CI/build.

## Architecture and conventions

1. **One manifest + one lockfile per product.** Every Python product has its own `pyproject.toml` and `uv.lock`; there is no workspace-level dependency file. This keeps each service's dependency surface explicit and independently updatable.
2. **Frozen installs in CI and local workflows.** The `sync` target uses `uv sync --frozen`, meaning the lockfile must be committed and any change requires regenerating it (via `uv lock`) before committing. This prevents drift between developer environments and CI.
3. **Version ranges are bounded but not pinned to exact versions in `pyproject.toml`.** Dependencies use caret-style or `<major` upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`). The actual resolved versions live only in `uv.lock`, giving flexibility during development while guaranteeing reproducibility at install time.
4. **Dev vs runtime separation via `[dependency-groups]`.** Test-only tools (`pytest`, `jsonschema`, `fakeredis`) are declared under `[dependency-groups] dev` rather than mixed into runtime dependencies, keeping production images lean.
5. **Build backend pinned to `uv_build`.** All products set `[build-system].requires = ["uv_build>=0.8.14,<0.9.0"]` and `build-backend = "uv_build"`, so packaging is also handled by uv and consistent across products.
6. **No private registry configuration found.** All `uv.lock` entries resolve from `registry = "https://pypi.org/simple"`; there is no `PYPI_INDEX_URL`, `PIP_INDEX_URL`, or uv `--index-url` override visible in the checked-in configuration.
7. **Cross-cutting policy bundles are NOT Python packages.** Policy definitions live as YAML in `shared/shared-contracts/policies/policy-default.yaml` and are copied into consumers via `make sync-policy`; this is a data contract strategy, not a Python dependency.

## Conventions and constraints

- **Every Python product must have a `pyproject.toml` and a committed `uv.lock`** — enforced by `make verify` → `test` → `uv sync --frozen`, which fails if the lockfile is missing or out of date.
- **Runtime dependencies must stay within their declared major version bounds** (e.g. FastAPI < 1.0, Pydantic < 3.0); bumping a major version requires updating both `pyproject.toml` and regenerating `uv.lock`.
- **Python version is coordinated**: `requires-python = ">=3.11"` in manifests and `.python-version = 3.12` pins the active interpreter; changing either should be accompanied by lockfile regeneration.
- **Shared contracts are kept separate from code dependencies**: `shared/shared-contracts/` holds JSON schemas and policy YAML consumed by multiple services without being installed as a Python package, avoiding tight coupling.
- **Container images inherit the same resolver**: product `Dockerfile`s build on the shared `base-uv` image, so `uv sync --frozen` inside the container resolves against the same PyPI index and lockfile used locally.