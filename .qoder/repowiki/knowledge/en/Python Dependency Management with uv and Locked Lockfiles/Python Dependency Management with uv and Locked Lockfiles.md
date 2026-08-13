---
kind: dependency_management
name: Python Dependency Management with uv and Locked Lockfiles
category: dependency_management
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/tool-gateway/pyproject.toml
    - products/tool-gateway/uv.lock
    - products/identity-broker/pyproject.toml
    - products/identity-broker/uv.lock
    - mk/python.mk
    - Makefile
---

This repository manages Python dependencies per product using **uv** as the package manager, with **pyproject.toml** declaring runtime and dev dependencies and a committed **uv.lock** file pinning every transitive dependency to exact versions and hashes. The approach is deterministic across environments and CI.

### System and tools
- **Package manager**: `uv` (invoked via `uv sync --frozen` and `uv run pytest`).
- **Build backend**: `uv_build>=0.8.14,<0.9.0` declared in each product's `[build-system]`.
- **Lockfiles**: `uv.lock` committed alongside each `pyproject.toml`; all install/test commands use `--frozen` so builds fail if the lockfile drifts from `pyproject.toml`.
- **Registry**: All packages resolve from `https://pypi.org/simple` (no private registry or vendoring observed).
- **Python version**: Each product pins `requires-python = ">=3.11"` and ships a `.python-version` file.

### Where declarations live
- Runtime and dev dependencies are declared per-product in `products/<name>/pyproject.toml` under `[project.dependencies]` and `[dependency-groups].dev`.
- Deterministic resolution is captured in `products/<name>/uv.lock`.
- Shared Make targets orchestrate dependency operations across products:
  - `make sync` runs `uv sync --frozen` for every Python product.
  - `make test` re-syncs then runs `uv run pytest` per product.
- Shared fragment `mk/python.mk` centralizes the `sync` and `test` targets used by each product Makefile.

### Conventions and constraints
- **Per-product isolation**: Each service (`agent-platform`, `identity-broker`, `tool-gateway`) has its own `pyproject.toml` and `uv.lock`; there is no workspace-level `pyproject.toml` aggregating dependencies.
- **Version pinning style**: Dependencies use semver-compatible ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`) rather than exact pins in `pyproject.toml`; exact pins are enforced through the committed `uv.lock`.
- **Frozen installs**: Both development and CI flows use `uv sync --frozen`, ensuring reproducible environments and preventing accidental drift.
- **Dev vs runtime separation**: Test-only packages (`pytest`, `jsonschema`, `fakeredis`) are placed under `[dependency-groups].dev` and are not included in production images.
- **Container strategy**: Dockerfiles copy only `.python-version`, `pyproject.toml`, `uv.lock`, and `README.md` into the build context, then rely on `uv sync --frozen` inside the image — no `pip install -r requirements.txt` or `pip freeze` usage.
- **No vendoring or private registries**: No `vendor/` directories, no `Pipfile.lock`, no `poetry.lock`, and no `GONOSUMDB`/`GOPRIVATE` equivalents; all third-party code comes from PyPI.