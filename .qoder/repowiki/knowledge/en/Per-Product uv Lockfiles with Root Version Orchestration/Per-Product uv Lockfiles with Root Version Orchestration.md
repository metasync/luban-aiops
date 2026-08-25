---
kind: dependency_management
name: Per-Product uv Lockfiles with Root Version Orchestration
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - Makefile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/policies/policy-default.yaml
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
---

## System Overview

The Luban AIOps platform is a Python monorepo of microservices plus a TypeScript web portal. Dependency management is **per-product**, not workspace-wide: each service under `products/` declares its own dependencies in a `pyproject.toml` and pins them via a per-package `uv.lock` file. The root build system orchestrates dependency installation, testing, and image building across all products.

### Package Manager and Locking

- **Python**: All Python services use [uv](https://docs.astral.sh/uv/) as the package manager and resolver. Each product has:
  - `pyproject.toml` declaring runtime dependencies (e.g. `fastapi`, `httpx`, `opentelemetry-*`, `pydantic`, `uvicorn`) with upper-bound constraints (e.g. `>=0.115,<1.0`).
  - `uv.lock` — a committed lockfile that pins every transitive dependency to an exact version.
  - `build-system.requires = ["uv_build>=0.8.14,<0.9.0"]` so builds are reproducible.
  - Optional `[dependency-groups].dev` for test-only packages (`pytest`, `jsonschema`, `fakeredis`).
- **Node.js**: The operator portal's web UI (`products/operator-portal/web-ui/app/package.json`) uses npm/yarn-style `package.json` + `package-lock.json` for React/AntD/Vite dependencies; no workspace-level Node config exists.

### Installation and Reproducibility Conventions

- The shared Makefile target `make sync` iterates over `PYTHON_PRODUCTS` and runs `make -C products/<name> sync`, which invokes `uv sync --frozen` (defined in `mk/python.mk`). The `--frozen` flag forces resolution strictly against `uv.lock`, disallowing any drift from the committed lockfile.
- Tests run via `uv run pytest` inside the synced environment, with OpenTelemetry exporters disabled via env vars to keep CI output clean.
- There is **no** global `requirements.txt`, `Pipfile`, or workspace-level `pyproject.toml`; each product owns its own dependency surface.

### Version Coordination Across Products

A single source of truth governs release versions:
- The root `VERSION` file holds the platform semver (e.g. `0.13.0`).
- Every product's `pyproject.toml[project].version` must match it.
- Each product's `src/*/metadata.py` exposes `SERVICE_VERSION` set to the same value.
- The script `shared/shared-contracts/scripts/validate_version.py` is invoked by `make validate-version` (part of `make verify`) and fails if any product drifts from `VERSION`. It also checks that the portal's Vite build reads `VERSION` at build time rather than hardcoding a literal.

This enforces **lockstep releases**: all Python services ship together with one coordinated image tag computed by the root `Makefile` and written into `shared/platform-ops/gitops/dev-k8s/.images.env`.

### Private Registries and Vendoring

- No private PyPI registry, `pip.conf`, `UV_INDEX_URL`, or `PYPI_TOKEN` configuration was found in the repository. Dependencies resolve against the public PyPI index.
- No vendored third-party code (no `vendor/`, `third_party/`, or submodules). All third-party code enters through uv's resolver and is captured in `uv.lock`.
- Container images are built with Dockerfiles that install dependencies via `uv sync --frozen`, ensuring production containers match the locked state.

### Shared Contracts vs. Runtime Dependencies

Cross-service contracts live in `shared/shared-contracts/schemas/*.schema.json` and `shared/shared-contracts/policies/policy-default.yaml`. These are **not** Python packages — they are JSON/YAML artifacts copied into consumers via `make sync-policy` (which copies the canonical policy to `platform-gateway` and `tool-gateway` policy directories). They are validated by `scripts/validate_policy.py` during `make validate-policy`.

### Key Files

- Per-product manifests: `products/*/pyproject.toml`, `products/*/uv.lock`
- Shared uv targets: `mk/python.mk` (defines `sync` → `uv sync --frozen`)
- Root orchestration: `Makefile` (`sync`, `test`, `build`, `verify`, `validate-version`)
- Version enforcement: `shared/shared-contracts/scripts/validate_version.py`
- Policy synchronization: `shared/shared-contracts/policies/policy-default.yaml` + `Makefile` `sync-policy` target
- Web UI deps: `products/operator-portal/web-ui/app/package.json`, `package-lock.json`
- Image base: `shared/base-images/base-uv/Dockerfile` (pins UV and Python versions used in all service images)