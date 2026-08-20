---
kind: dependency_management
name: Per-Product uv Lockfiles with Coordinated Versioning
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/policies/policy-default.yaml
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/platform-gateway/uv.lock
    - products/audit-service/pyproject.toml
    - products/audit-service/uv.lock
    - products/tool-gateway/pyproject.toml
    - products/tool-gateway/uv.lock
    - shared/base-images/base-uv/Dockerfile
---

## System Overview

The repository uses **uv** (a fast Python package manager) as the sole dependency-management tool. Each product under `products/` is an independent Python package declared in its own `pyproject.toml`, and each maintains a per-product `uv.lock` lockfile that pins every transitive dependency to exact versions. There is no monorepo-level workspace file — dependencies are managed per product, not globally.

## Key Files and Packages

- Per-product manifests: `products/*/pyproject.toml` declare `[project]` dependencies, `[dependency-groups.dev]` for test-only packages, and `[build-system]` pinning `uv_build>=0.8.14,<0.9.0` as the build backend.
- Per-product lockfiles: `products/*/uv.lock` (e.g. `products/agent-platform/uv.lock`) provide deterministic resolution.
- Shared Python tooling: `mk/python.mk` exposes `sync` and `test` targets that invoke `uv sync --frozen` and `uv run pytest`, enforcing locked installs across all products.
- Root Makefile (`Makefile`) lists `PYTHON_PRODUCTS := agent-platform audit-service identity-broker incident-service platform-gateway skills-hub tool-gateway` and runs `make -C products/$p sync` / `test` for each.
- Container images: `mk/image.mk` builds Docker images per product using the pinned environment; base image `shared/base-images/base-uv/Dockerfile` is built with a pinned `UV_VERSION` build arg.
- Version coordination: `shared/shared-contracts/scripts/validate_version.py` enforces that every product's `pyproject.toml` version matches the root `VERSION` file, plus `src/*/metadata.py` `SERVICE_VERSION` and `operator-portal/web-ui/app.js` `PLATFORM_VERSION`.
- Policy bundle: `shared/shared-contracts/policies/policy-default.yaml` is the canonical policy source; `make sync-policy` copies it into `products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.

## Architecture and Conventions

1. **Per-package isolation**: Each service owns its own `pyproject.toml` and `uv.lock`. Dependencies are not shared via a workspace or `requirements.txt`; cross-cutting concerns live in `shared/` as code or schemas, not as installable packages.
2. **Frozen installs**: The `sync` target always runs `uv sync --frozen`, meaning CI and local environments must use exactly the versions recorded in `uv.lock`. No runtime resolution against PyPI is allowed during install.
3. **Python version pinning**: Each product declares `requires-python = ">=3.11"` in `pyproject.toml` and ships a `.python-version` file (e.g. `3.12`) for IDE/SDK managers.
4. **Dependency ranges**: All third-party dependencies use bounded semver ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`). This allows minor updates while preventing breaking major upgrades.
5. **Dev vs runtime separation**: Test-only packages (pytest, fakeredis, jsonschema) are placed in `[dependency-groups] dev` rather than the main `dependencies` list.
6. **Build system pinning**: Every product pins `uv_build>=0.8.14,<0.9.0` as its build backend, ensuring reproducible sdist/wheel builds.
7. **Coordinated release**: The root `VERSION` file is the single source of truth. `make validate-version` (via `validate_version.py`) fails if any product's `pyproject.toml` version drifts from it. The root `Makefile` also writes coordinated image tags into `shared/platform-ops/gitops/dev-k8s/.images.env` so all services ship together.
8. **No vendoring**: There is no `vendor/` directory or `pip freeze > requirements.txt` artifact. Resolution happens through uv's native lockfile mechanism.
9. **Private registry / auth**: No `uv config` or `PYPI_*` credentials are present in the repo; dependencies resolve against the public PyPI index. Authentication for container registries is handled separately via `REGISTRY` env var in the image build layer.

## Conventions and Constraints

- **Enforced by scripts**:
  - `uv sync --frozen` (in `mk/python.mk`) forbids resolving new versions at install time; the lockfile is authoritative.
  - `make validate-version` rejects any product whose `pyproject.toml` version does not equal the root `VERSION` file.
  - `make sync-policy` copies the canonical policy from `shared/shared-contracts/policies/policy-default.yaml` into every consumer location; consumers should not edit their copy directly.
  - `make overlays` runs `kustomize build` on every GitOps overlay, catching configuration drift before deploy.
- **Observed conventions**:
  - All Python services share the same core dependency set (FastAPI, Pydantic, httpx, OpenTelemetry exporters/instrumentations, Prometheus client, uvicorn), kept in lockstep via matching version ranges.
  - Service-specific dependencies (e.g. `agentscope`, `elasticsearch`, `kubernetes`, `redis`, `psycopg[binary]`) are added only where needed.
  - Dockerfiles reference the product's entry point via the console script defined in `[project.scripts]` of each `pyproject.toml`.