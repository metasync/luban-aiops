---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Sync and Shared Base Image
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
    - products/agent-platform/Dockerfile
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## System Overview

The Luban Agentic AIOps Platform uses **uv** as the Python dependency manager across every backend product. Each product under `products/<name>/` is an independent PEP 621 package declared in its own `pyproject.toml`, with a co-located `uv.lock` that pins every transitive resolution. There is no workspace-level lockfile — the root Makefile orchestrates per-product `uv sync --frozen` invocations, and container images are built from a shared base image that installs a pinned `uv` version.

## Key Files

- Per-product manifests: `products/*/pyproject.toml` (dependency declarations, scripts, dev groups) and `products/*/uv.lock` (frozen resolution).
- Root orchestration: `Makefile` (lists `PYTHON_PRODUCTS`, runs `sync`/`test`/`build` across all of them), `mk/python.mk` (`sync` target runs `uv sync --frozen`; `test` target re-syncs frozen then runs pytest with OTel exporters disabled).
- Container build: each product `Dockerfile` copies `.python-version`, `pyproject.toml`, `uv.lock`, and `src/`, then runs `uv sync --frozen --no-dev` to bake only runtime deps into the image.
- Shared base image: `shared/base-images/base-uv/Dockerfile` installs a pinned `uv` (ARG `UV_VERSION=0.12.1`) on Amazon Linux 2023 minimal, sets `UV_PYTHON`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, and runs as non-root user `app`.
- Version policy documentation: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` codifies the adoption posture.

## Architecture and Conventions

### Per-package isolation
Each product declares its own dependencies explicitly; there are no cross-product Python package references between services. The monorepo structure is purely organizational — dependency resolution happens independently per product directory.

### Frozen resolutions
All `uv sync` calls use `--frozen`, which rejects any deviation from `uv.lock`. This means:
- Dependencies cannot drift at install time; the lockfile is the source of truth.
- CI and local environments must regenerate the lockfile explicitly via `uv lock` before committing changes.
- Docker builds also use `--frozen --no-dev`, so production images contain only runtime dependencies.

### Version ranges + latest stable policy
Dependency specifiers in `pyproject.toml` use bounded ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `cryptography>=43.0,<51.0`). The release notes for SPEC-042 document an explicit **"latest stable only"** adoption policy — no alpha, beta, RC, or dev builds — with one recorded exception: OpenTelemetry instrumentation packages stay on their permanent `0.xb` channel paired with the locked SDK version. Major version caps are intentionally set conservatively (Redis `<7.0`, Elasticsearch `<9.0`) based on server compatibility assessments rather than upstream stability alone.

### Shared base image strategy
The `luban-aiops/base-uv` image pins both `uv` and `PYTHON_VERSION` via build args, installs no system Python, and lets `uv` resolve the interpreter from each product's `.python-version` file. Environment variables `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, and `UV_PYTHON_INSTALL_DIR=/app/.python` ensure deterministic, layer-cacheable installs.

### Coordinated build and deploy
The root `Makefile` enumerates `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and iterates over them for `sync`, `test`, `lint`, `build`, and `push`. The coordinated `build` target writes a single `IMAGE_TAG` derived from `VERSION` plus git SHA/dirty state into `shared/platform-ops/gitops/dev-k8s/.images.env`, which is consumed by the GitOps overlay deployment. All images share this tag, ensuring version lockstep across the platform.

## Conventions and Constraints

- **Every Python product must have a `pyproject.toml` and `uv.lock`**: enforced by the root `Makefile`'s iteration over `PYTHON_PRODUCTS` and the Dockerfile pattern that requires these files at build time.
- **Dependencies must be declared in `pyproject.toml` under `[project]`**: not via `requirements.txt`; the build system reads PEP 621 metadata exclusively.
- **Dev-only dependencies go in `[dependency-groups] dev`**: used by tests but excluded from images via `--no-dev`.
- **No vendored third-party code**: all dependencies are resolved from PyPI registries (the lockfiles show `source = { registry = "https://pypi.org/simple" }`); there is no `vendor/` directory or private registry configuration in this repository.
- **Python version pinning per product**: each product ships a `.python-version` file consumed by the shared base image's `UV_PYTHON` environment variable.
- **Version lockstep enforced by `make validate-version`**: a script under `shared/shared-contracts/scripts/validate_version.py` checks that the root `VERSION` file matches product versions and portal versions.
- **Policy bundles are synchronized separately from Python deps**: `make sync-policy` copies the canonical policy YAML from `shared/shared-contracts/policies/policy-default.yaml` into each consumer location, analogous to how Python dependencies are managed.