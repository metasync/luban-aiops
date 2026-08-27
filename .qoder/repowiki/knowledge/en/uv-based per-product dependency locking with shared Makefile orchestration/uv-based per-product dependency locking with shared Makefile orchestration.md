---
kind: dependency_management
name: uv-based per-product dependency locking with shared Makefile orchestration
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
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/execution-runtime/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - VERSION
---

## What system/approach is used

The repository manages Python dependencies using **uv** (a fast Python package manager) with **PEP 621 `pyproject.toml` manifests** and **`uv.lock` lockfiles** at each product level. There is no monorepo-level workspace manifest; instead, every service under `products/` is an independent uv project with its own `pyproject.toml`, `uv.lock`, `.python-version`, and `.venv`. The root `Makefile` and shared fragments in `mk/python.mk` coordinate dependency synchronization across all products via the `sync` target, which iterates over the `PYTHON_PRODUCTS` list and invokes `make -C products/<name> sync`.

For the Node.js web UI (`products/operator-portal/web-ui`), dependencies are managed separately via `package.json` + `package-lock.json` — this is a distinct npm ecosystem from the Python services.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` declare runtime `dependencies`, optional `[dependency-groups] dev = [...]` for test-only packages, and a pinned `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` build backend.
- Lockfiles: `products/*/uv.lock` pin exact transitive versions for reproducible installs.
- Shared Makefile fragments:
  - `mk/python.mk` — defines the `sync` target that runs `uv sync --frozen`, enforcing installation from the lockfile without network resolution.
  - `mk/image.mk` — builds container images that embed the frozen uv environment.
  - Root `Makefile` — lists `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and exposes `make sync`, `make test`, `make verify` to operate on all of them uniformly.
- Runtime base image: `shared/base-images/base-uv/Dockerfile` provides a prebuilt uv+Python base image whose version is controlled by `mk/defaults.mk` variables (`BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`).
- Version coordination: root `VERSION` file plus `shared/shared-contracts/scripts/validate_version.py` enforce that every product's `pyproject.toml` version stays in lockstep with the platform release version.

## Architecture and conventions

- **Per-product isolation**: Each service declares its own dependency surface. Common observability stacks (OpenTelemetry exporters/instrumentation, Prometheus client, Pydantic, FastAPI, Uvicorn) are declared individually in each `pyproject.toml` rather than pulled through a shared workspace dependency, keeping each image self-contained.
- **Frozen installs in CI/CD**: `mk/python.mk` uses `uv sync --frozen` so builds never resolve or update the lockfile — only the committed `uv.lock` is accepted. This makes CI deterministic and prevents accidental drift.
- **Dev vs runtime separation**: Development-only tools (pytest, jsonschema, fakeredis) live in `[dependency-groups] dev = [...]` and are not part of the runtime image unless explicitly included.
- **Python version pinning**: Each product carries a `.python-version` file (e.g. `3.12.x`) and `requires-python = ">=3.11"` in `pyproject.toml`; the root also has `.python-version`.
- **Containerization**: Images are built with Docker using the shared `mk/image.mk` targets, tagging images as `luban-aiops/<service>:<IMAGE_TAG>` where `<IMAGE_TAG>` is derived from the root `VERSION` plus git SHA/dirty marker. The root `Makefile` writes a coordinated `.images.env` listing all built image references for GitOps deployment.
- **No vendoring**: Dependencies are resolved from PyPI (or a configured registry via uv configuration); there is no `vendor/` directory or inline source vendoring for Python packages.

## Conventions and constraints

- **Constraint: All Python products must use uv with `--frozen` sync.** Enforced by `mk/python.mk`'s `sync` target and invoked by the root `Makefile`; any deviation would break the standard `make sync` / `make test` flow.
- **Constraint: Lockfiles must be committed.** Because `uv sync --frozen` refuses to install without a matching `uv.lock`, changes to `pyproject.toml` require regenerating the lockfile before committing.
- **Constraint: Product versions stay synchronized with the root `VERSION` file.** Enforced by `make validate-version`, which runs `shared/shared-contracts/scripts/validate_version.py` against the repo tree.
- **Convention: Dependency ranges use caret-style upper bounds** (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`) to allow patch/minor updates while blocking major-version breaks.
- **Convention: Dev dependencies are isolated in `[dependency-groups] dev`** and kept out of runtime images.
- **Convention: Build backend is pinned to `uv_build>=0.8.14,<0.9.0`** in every product's `[build-system]`, ensuring consistent packaging behavior.
- **Node.js frontend is decoupled**: `products/operator-portal/web-ui/package.json` + `package-lock.json` are managed independently of the Python uv workflow.