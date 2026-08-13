---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management
category: dependency_management
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/uv.lock
    - products/tool-gateway/uv.lock
    - products/identity-broker/uv.lock
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - products/agent-platform/.python-version
    - products/platform-gateway/.python-version
    - products/tool-gateway/.python-version
    - products/identity-broker/.python-version
---

## System / Approach

The repository manages Python dependencies per product using **uv** (the fast Python package manager) with a `pyproject.toml` + `uv.lock` lockfile strategy. Each product under `products/` is an independent, self-contained Python application with its own dependency graph and frozen lockfile.

## Key Files

- Per-product manifests: `products/*/pyproject.toml` — declare runtime and dev dependencies, entry points, build backend.
- Per-product lockfiles: `products/*/uv.lock` — pinned, reproducible resolution produced by uv.
- Shared Makefile fragments:
  - `mk/python.mk` — defines `sync` (`uv sync --frozen`) and `test` targets that install from the frozen lockfile.
  - `mk/image.mk` — builds Docker images; products include this to standardize image targets.
- Per-product `.python-version` files pin the interpreter to `3.12` across all four services.
- Root-level `mk/defaults.mk` (included by `image.mk`) centralizes registry/tag defaults for container builds.

## Architecture & Conventions

- **One product = one dependency graph.** The four Python services (`agent-platform`, `platform-gateway`, `identity-broker`, `tool-gateway`) each have their own `pyproject.toml` and `uv.lock`. There is no monorepo-wide workspace or shared virtual environment; cross-service sharing happens via published packages (`agentscope`, `agentscope-runtime`) rather than path-based linking.
- **Frozen installs in CI/CD.** The `sync` target runs `uv sync --frozen`, which refuses to resolve against PyPI and instead uses the committed `uv.lock`. This enforces deterministic builds.
- **Build backend pinned to uv.** Every product sets `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"`, so packaging also goes through uv.
- **Python version pinned per product.** Each product declares `requires-python = ">=3.11"` in `pyproject.toml` and additionally pins `3.12` in `.python-version`, ensuring local and container tooling agree.
- **Dependency ranges are bounded.** Runtime deps use caret-style upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `cryptography>=43.0,<45.0`) to prevent accidental major-version upgrades while allowing minor/patch updates. Dev-only deps live under `[dependency-groups].dev` (pytest, jsonschema, fakeredis).
- **Shared third-party libraries are consumed as published packages**, not vendored source. All four services depend on common libraries like `fastapi`, `httpx`, `opentelemetry-*`, `prometheus-client`, `pydantic`, `PyJWT`, `uvicorn[standard]`; each service resolves its own compatible set via its lockfile.
- **Container images are built per product** via the shared `mk/image.mk` targets, which tag images as `luban-aiops/<IMAGE_NAME>:<TAG>` (or `<REGISTRY>/luban-aiops/<IMAGE_NAME>:<TAG>` when `REGISTRY` is set). The root `Makefile` drives these per-product builds.

## Conventions & Constraints

- **Lockfiles are authoritative.** `uv sync --frozen` is used everywhere; developers must commit updated `uv.lock` files when adding/changing dependencies (enforced by the `--frozen` flag).
- **No private registries or vendoring are configured.** Dependencies are resolved from the default PyPI index; there is no `uv.config.toml` with custom index URLs, no `vendor/` directories, and no `GOPRIVATE` equivalents.
- **Dev vs runtime separation.** Optional test/dev dependencies are isolated in `[dependency-groups].dev` rather than mixed into runtime `dependencies`, keeping production images lean.
- **Entry points are declared centrally.** Each product exposes CLI scripts via `[project.scripts]` (e.g. `agent-service`, `platform-gateway`, `tool-gateway`, `identity-service`) that invoke the service's `main:run` function.
- **Dockerfiles consume the uv-managed environment.** Each product ships a `Dockerfile` that builds on top of the shared `shared/base-images/base-uv` base image, relying on uv to install dependencies from the locked manifest inside the image build context.