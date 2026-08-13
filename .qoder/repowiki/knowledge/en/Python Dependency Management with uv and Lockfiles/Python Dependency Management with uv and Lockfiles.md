---
kind: dependency_management
name: Python Dependency Management with uv and Lockfiles
category: dependency_management
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/identity-broker/pyproject.toml
    - products/identity-broker/uv.lock
    - products/tool-gateway/pyproject.toml
    - products/tool-gateway/uv.lock
    - mk/python.mk
    - Makefile
---

The Luban AIOps workspace manages Python dependencies using the modern `uv` toolchain across all three Python products (agent-platform, identity-broker, tool-gateway). Each product maintains its own isolated dependency graph through a per-product `pyproject.toml` paired with a committed `uv.lock` file.

**Declaration and Versioning Strategy**
- Dependencies are declared in each product's `pyproject.toml` under `[project.dependencies]` with semver-style range specifiers (e.g., `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`).
- All products pin `requires-python = ">=3.11"` and use `.python-version` files set to `3.12` for local development consistency.
- Development-only dependencies are separated into `[dependency-groups].dev` sections (pytest, jsonschema, fakeredis).
- The build system is declared via `[build-system]` requiring `uv_build>=0.8.14,<0.9.0` as the build backend.

**Lockfile Enforcement**
- Each product ships a committed `uv.lock` file that pins every transitive dependency with exact versions and SHA256 hashes.
- The shared `mk/python.mk` Makefile fragment enforces deterministic installs via `uv sync --frozen`, which refuses to resolve or update the lockfile — ensuring CI and local environments match exactly.
- The root `Makefile` orchestrates this via `make sync` which iterates over all `PYTHON_PRODUCTS` and runs their individual `sync` targets.

**Registry and Resolution**
- All packages resolve from PyPI (`https://pypi.org/simple`) as recorded in the lockfiles; no private registries or vendoring are configured.
- The lockfiles include platform-specific resolution markers for Python 3.11–3.15 across Windows and non-Windows platforms.

**Cross-Product Coordination**
- There is no shared `requirements.txt` or monorepo-wide lockfile; each product independently manages its dependency tree.
- Common libraries (FastAPI, Pydantic, OpenTelemetry, Prometheus client) are pinned to compatible ranges across products but resolved independently per product.
- The root `Makefile` coordinates cross-cutting concerns like image building and deployment but does not unify dependency resolution.