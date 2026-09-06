---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Sync and Coordinated Image Tags
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
    - shared/shared-contracts/scripts/validate_version.py
---

## What system/approach is used

The repository manages Python dependencies per product using **uv** (the Astral package manager) with a `pyproject.toml` + `uv.lock` pair in every backend product under `products/`. Each product declares its runtime and dev dependencies with bounded version ranges, and the lockfile pins every transitive dependency to exact versions and hashes from PyPI. The workspace also ships a shared base image (`shared/base-images/base-uv/Dockerfile`) that installs a pinned `uv` version and a pinned Python interpreter so builds are deterministic across environments.

There is no monorepo-level `uv.lock`; instead each product owns its own lockfile, and the root Makefile orchestrates them uniformly via `make sync`, `make test`, and `make build`.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` — declare `[project]` dependencies, `[dependency-groups].dev`, `[build-system]` using `uv_build`, and entry-point scripts.
- Per-product lockfiles: `products/*/uv.lock` — full resolution of all transitive dependencies, including source registry URLs and SHA256 hashes for wheels/sdists.
- Shared build fragments:
  - `mk/python.mk` — defines `sync` (`uv sync --frozen`) and `test` targets consumed by every product Makefile.
  - `mk/image.mk` — Docker build/push helpers; images are tagged `luban-aiops/<name>:<IMAGE_TAG>` where `IMAGE_TAG` comes from the root Makefile's coordinated tag computation.
  - `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal image with pinned `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`, running as non-root user `app`.
- Root orchestration: `Makefile` — lists `PYTHON_PRODUCTS`, runs `make -C products/$p sync|test|build|push` in loop, computes a single `IMAGE_TAG` derived from `VERSION` plus git sha/dirty timestamp, and writes `.images.env` consumed by GitOps overlays.
- Version coordination: `VERSION` file at repo root; enforced by `make validate-version` which calls `shared/shared-contracts/scripts/validate_version.py` against all products.
- Dependency hygiene record: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` documents the adopted policy of "latest stable only" with one recorded exception for OpenTelemetry instrumentation packages on their permanent `0.xb` channel.

## Architecture and conventions

1. **Per-product isolation**: Each service has its own `pyproject.toml` and `uv.lock`. Dependencies are not shared via a workspace-level resolver; cross-cutting code lives in `shared/shared-contracts/` (JSON schemas, policy YAMLs, validation scripts) but is not installed as a Python package dependency.

2. **Frozen installs everywhere**: `mk/python.mk` runs `uv sync --frozen` for both `sync` and `test`, meaning the lockfile is authoritative — it cannot be updated without explicitly regenerating the lockfile. This guarantees reproducible CI and local builds.

3. **Bounded version ranges**: Runtime dependencies use upper-bound major caps (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`, `cryptography>=43.0,<51.0`). Dev dependencies follow the same pattern (e.g. `pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`).

4. **Single source of truth for Python version**: `.python-version` per product plus `requires-python = ">=3.11"` in each manifest; the base image pins `UV_PYTHON=3.12` and `UV_PYTHON_INSTALL_DIR=/app/.python` so the resolved interpreter is cached in the image.

5. **Coordinated image tagging**: The root `Makefile` computes one `IMAGE_TAG` (semver prefix from `VERSION` + git short sha + optional profile + `-dirty` suffix if uncommitted changes exist) and applies it to every product image. The resulting list is written to `shared/platform-ops/gitops/dev-k8s/.images.env` and consumed by the GitOps deploy overlay.

6. **No vendoring or private registry**: All packages resolve from `https://pypi.org/simple` (visible in `uv.lock` entries). No `index-url`, `extra-index-url`, `UV_DEFAULT_SOURCE`, or `PIP_INDEX_URL` configuration was found anywhere in the repo.

7. **Build backend pinning**: Every product uses `uv_build>=0.8.14,<0.9.0` as its build backend, keeping the build toolchain itself locked.

## Conventions and constraints

- **Latest-stable-only adoption policy**: Stated in the dependency-hygiene release note — bumps go to the latest stable release; alpha/beta/RC/dev builds are excluded except for OpenTelemetry instrumentation packages, which stay paired with their SDK on the permanent `0.xb` channel.
- **Lockstep versioning enforced**: `make validate-version` (invoked by `make verify`) runs `shared/shared-contracts/scripts/validate_version.py` to assert that the root `VERSION` file matches every product's declared version. This is part of the pre-commit/pre-push gate.
- **Frozen sync required**: `uv sync --frozen` is the only supported install mode in the shared Makefile targets; developers must regenerate lockfiles explicitly when updating dependencies.
- **Uniform product surface**: All eight Python products (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`) follow the same structure: `pyproject.toml` + `uv.lock` + `Dockerfile` + `Makefile` including `../../mk/python.mk` and `../../mk/image.mk`.
- **Container image naming convention**: Images are always tagged `luban-aiops/<product-name>:<IMAGE_TAG>`; pushing requires setting `REGISTRY` to re-tag before push.
- **Dependency cap discipline**: Major-version upper bounds are consistently applied to avoid breaking upgrades (e.g. `<1.0` for FastAPI, `<3.0` for Pydantic, `<7.0` for Redis, `<9.0` for Elasticsearch client). The dependency-hygiene note records deliberate decisions to keep certain caps parked (Redis <7.0, Elasticsearch <9.0) based on server compatibility.