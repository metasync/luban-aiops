---
kind: dependency_management
name: uv-based per-product dependency management with frozen lockfiles and shared base image
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - Makefile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/agent-platform/Dockerfile
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
---

## System / Approach

The monorepo manages Python dependencies with **uv** (Astral) at the product level. Each service under `products/<name>/` is an independent uv-managed project declared in its own `pyproject.toml`, with a co-located `uv.lock` pinning every transitive resolution. There is no workspace-level `pyproject.toml`; instead, the root `Makefile` orchestrates per-product `make sync` / `make test` calls that delegate to `mk/python.mk`, which runs `uv sync --frozen` inside each product directory so the lockfile is authoritative.

Container images are built from a shared base image (`shared/base-images/base-uv/Dockerfile`) that installs a pinned version of uv (`UV_VERSION=0.12.1`) on Amazon Linux 2023 minimal and sets `UV_PYTHON_INSTALL_DIR=/app/.python`. Product Dockerfiles copy only `pyproject.toml`, `uv.lock`, `.python-version`, and `src/`, then run `uv sync --frozen --no-dev` during build — this guarantees production images contain exactly the locked versions and nothing extra.

## Key Files

- Per-product manifests: `products/*/pyproject.toml`, `products/*/uv.lock`, `products/*/.python-version`
- Shared uv targets: `mk/python.mk` (`sync`, `test` targets using `uv sync --frozen`)
- Shared image targets: `mk/image.mk`, `mk/defaults.mk`
- Base image: `shared/base-images/base-uv/Dockerfile` (pins uv and Python via build args)
- Root orchestration: `Makefile` (lists `PYTHON_PRODUCTS`, iterates them for `sync`/`test`/`build`/`push`)
- Product Dockerfiles (e.g. `products/agent-platform/Dockerfile`) that copy `uv.lock` and run `uv sync --frozen --no-dev`

## Architecture & Conventions

- **Per-product isolation**: each service declares its own `dependencies` list and optional `[dependency-groups].dev` group; there is no shared Python package vendored into the repo. Cross-cutting code lives as separate products (e.g. `shared/shared-contracts`, `shared/platform-ops`) consumed via runtime HTTP/contract files rather than Python imports.
- **Version ranges**: dependencies use caret-style ranges (e.g. `fastapi>=0.115,<1.0`, `agentscope>=2.0.4,<3.0`) to allow patch/minor updates while blocking major bumps. Dev-only tooling (pytest, jsonschema, fakeredis) is isolated in `[dependency-groups].dev`.
- **Frozen resolution**: both development (`uv sync --frozen`) and container builds (`uv sync --frozen --no-dev`) require the lockfile to match the source tree exactly; any drift fails the command. This is the enforcement mechanism for reproducibility.
- **Python version pinning**: each product has a `.python-version` file; the base image exposes it via `UV_PYTHON` and `UV_PYTHON_INSTALL_DIR` so uv installs the interpreter deterministically into `/app/.python`.
- **No vendoring or private registry config in-tree**: there is no `requirements.txt`, no `pip.conf`/`pip.ini`, no `Pipfile`, no `vendor/` directory, and no `PYPI_*` environment variables checked in. Dependencies resolve against the default PyPI index unless overridden by environment at build time.
- **Coordinated release surface**: although Python deps are per-product, the platform release version is centralized in the root `VERSION` file and enforced across all product packages via `make validate-version` (which invokes `shared/shared-contracts/scripts/validate_version.py`).

## Conventions & Constraints

- Every Python product must have a `pyproject.toml` with a `[project]` section declaring `dependencies` and a matching `uv.lock` committed alongside it.
- Dependency upgrades go through `uv lock` within the product directory; the resulting `uv.lock` diff is reviewed like any other source change because `uv sync --frozen` will fail if the lockfile does not match the working tree.
- Production images never install dev dependencies: Dockerfiles pass `--no-dev` to `uv sync`, and tests are run separately via `uv run pytest` with OTLP exporters disabled.
- The root Makefile enumerates `PYTHON_PRODUCTS := agent-platform audit-service identity-broker incident-service platform-gateway skills-hub tool-gateway`; adding a new product requires registering it there for `make sync`/`make test`/`make build` to apply.
- Container image tagging is coordinated: the root `IMAGE_TAG` computed from `VERSION` + git SHA is propagated to every product image via `make build`, keeping the Python dependency surface tied to a single immutable release tag.