---
kind: dependency_management
name: Per-Product uv + pyproject.toml with Locked Dependencies and Shared Base Image
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - Makefile
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/skills-hub/pyproject.toml
---

## System / Approach

The Luban AIOps platform manages Python dependencies using **uv** as the package manager, with each product under `products/<name>/` declaring its own isolated dependency graph via a `pyproject.toml` (PEP 621) plus a committed `uv.lock` lockfile. There is no monorepo-level `requirements.txt`, `Pipfile`, or shared `pyproject.toml`; instead every service owns its own manifest.

The build system enforces deterministic installs through `uv sync --frozen` in the shared Makefile fragment `mk/python.mk`, which means CI and local runs must use exactly the versions pinned in `uv.lock`. The root `Makefile` orchestrates per-product `sync`, `test`, `build`, and `push` targets across all six Python products (`agent-platform`, `audit-service`, `identity-broker`, `platform-gateway`, `skills-hub`, `tool-gateway`).

Container images are built from a shared base image `shared/base-images/base-uv/Dockerfile` that pins both the Python version and the `uv` binary version (via `BASE_UV_*` variables in `mk/defaults.mk`), so runtime dependency resolution happens against a known toolchain rather than whatever `uv` happens to be installed on the host.

## Key Files

- Per-product manifests: `products/*/pyproject.toml` — declare `dependencies`, `[dependency-groups] dev`, entry-point scripts, and `requires-python = ">=3.11"`.
- Per-product lockfiles: `products/*/uv.lock` — fully resolved dependency trees with source registry (`https://pypi.org/simple`) and SHA256 hashes for every wheel/sdist.
- Shared Makefile fragment: `mk/python.mk` — defines `sync` and `test` targets that run `uv sync --frozen` then `uv run pytest`.
- Root orchestration: `Makefile` — lists `PYTHON_PRODUCTS`, iterates over them for `sync`/`test`/`build`/`push`, and writes coordinated image tags into `shared/platform-ops/gitops/dev-k8s/.images.env`.
- Base image definition: `shared/base-images/base-uv/Dockerfile` — builds a minimal image with a pinned Python and uv version used by every product Dockerfile.
- Product Dockerfiles: `products/*/Dockerfile` — reference the base image and install deps via `uv sync --frozen` inside the image build.
- Root `.python-version` — declares the workspace Python version (consumed by uv).

## Architecture and Conventions

- **One manifest per product**: Each of the six services has an independent `pyproject.toml` listing only the packages it imports at runtime. Cross-cutting libraries (FastAPI, Pydantic, httpx, PyJWT, cryptography, OpenTelemetry exporters/instrumentation, prometheus-client, uvicorn) appear in multiple manifests with the same version ranges, keeping the platform's runtime surface consistent without sharing a common dependency file.
- **Version pinning style**: Runtime dependencies use caret-style ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`) to allow patch/minor updates while blocking major bumps. Dev-only dependencies live under `[dependency-groups] dev` (pytest, jsonschema, fakeredis) and are not installed in production images.
- **Lockfile-first workflow**: `mk/python.mk` uses `uv sync --frozen`, which refuses to resolve anything outside `uv.lock`. This makes the lockfile the single source of truth; developers update it via `uv add <pkg>` (which re-resolves and rewrites `uv.lock`) rather than editing it by hand.
- **No vendoring**: All third-party packages are pulled from the public PyPI index (`source = { registry = "https://pypi.org/simple" }` in the lockfiles). There is no `vendor/` directory, no private PyPI mirror configured in the manifests, and no `pip.conf`/`uv` config files checked in. Private registries would need to be supplied externally (e.g. via `uv` environment configuration or container registry mirrors).
- **Build backend**: Every product sets `build-system.requires = ["uv_build>=0.8.14,<0.9.0"]` and `build-backend = "uv_build"`, so packaging and installation go through uv's PEP 517 backend.
- **Shared policy assets are NOT Python dependencies**: Policy YAMLs (`policy-default.yaml`) are copied between locations via the `make sync-policy` target in the root `Makefile`; they are not managed as Python packages.

## Conventions and Constraints

- **Python version gate**: Every product requires `requires-python = ">=3.11"`; the base image pins a specific Python minor version, ensuring reproducible native extensions.
- **Deterministic installs enforced by make**: The `sync` and `test` targets in `mk/python.mk` always invoke `uv sync --frozen`; any drift between `pyproject.toml` and `uv.lock` will fail CI.
- **Dev vs prod separation**: Optional test-only tools (pytest, jsonschema, fakeredis) are declared in `[dependency-groups] dev` and are not part of the runtime `dependencies` list, so production images stay lean.
- **Consistent cross-cutting versions**: Across all six products, shared libraries are pinned to the same ranges (e.g. `fastapi>=0.115,<1.0`, `httpx>=0.27,<1.0`, `PyJWT>=2.8,<3.0`, `cryptography>=43.0,<45.0`, `opentelemetry-*` families), preventing version skew between gateway, broker, audit, skills hub, and agent platform.
- **Entry points declared in manifests**: Each product registers CLI entry points under `[project.scripts]` (e.g. `agent-service`, `platform-gateway`, `tool-gateway`, `audit-service`, `identity-service`, `skills-hub`) so the resulting wheels expose a uniform command-line interface.
- **Image tagging is coordinated but separate from dependency management**: The root `Makefile` computes a single `IMAGE_TAG` and writes all product image names into `shared/platform-ops/gitops/dev-k8s/.images.env`; this coordinates deployment but does not affect how Python packages are resolved.