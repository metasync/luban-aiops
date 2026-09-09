---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management with Coordinated Release Hygiene
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - Makefile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/execution-runtime/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/agent-platform/uv.lock
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
    - shared/shared-sdk/README.md
---

## System Overview

The Luban AIOps Platform uses a per-product dependency management strategy built on **uv** (Python package manager) with `pyproject.toml` declarations and per-product `uv.lock` lockfiles. There is no monorepo-level workspace or shared `requirements.txt`; each service under `products/` is an independently versioned, independently buildable Python package.

## Key Files and Packages

- Per-product manifests: `products/*/pyproject.toml` — declare runtime dependencies, dev dependency groups (`[dependency-groups] dev = [...]`), entry points (`[project.scripts]`), and the build backend.
- Per-product lockfiles: `products/*/uv.lock` — pin every transitive dependency to exact versions and hashes; sourced from `https://pypi.org/simple`.
- Shared Makefile fragments: `mk/python.mk` defines the canonical `sync` target that runs `uv sync --frozen`, enforcing deterministic installs in CI and local dev.
- Root orchestrator: `Makefile` enumerates `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and dispatches `make -C products/$$p sync` / `test` across all of them.
- Version lockstep enforcement: `shared/shared-contracts/scripts/validate_version.py` is invoked via `make validate-version` to ensure every product's `pyproject.toml` version matches the root `VERSION` file.
- Frontend: the operator portal lives under `products/operator-portal/web-ui/` and manages its own Node.js dependencies (npm/yarn/pnpm not shown here); release notes document React 19, antd 6, TypeScript, Vite upgrades.
- Docker base image: `shared/base-images/base-uv/Dockerfile` plus `mk/image.mk` bake a consistent `uv` + Python environment into images.

## Architecture and Conventions

1. **One manifest per product.** Each service declares its own `[project]` name, `version`, `requires-python = ">=3.11"`, and explicit dependency ranges. No cross-package imports between products are expressed as Python packages; inter-product communication is over HTTP/gRPC contracts defined in `shared/shared-contracts/schemas/`.
2. **Lockfiles are committed and frozen.** The `sync` target always runs `uv sync --frozen`, so builds never resolve against a mutable index — reproducibility is enforced at the make layer.
3. **Dependency ranges use caret-style upper bounds.** Typical patterns observed: `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`, `cryptography>=43.0,<51.0`. Major-version caps prevent breaking upgrades until reviewed.
4. **Dev vs runtime separation via dependency groups.** Test-only packages (pytest, fakeredis, jsonschema) live in `[dependency-groups] dev = [...]` rather than top-level `dependencies`, keeping production images lean.
5. **Build backend pinned to uv_build.** Every `pyproject.toml` sets `build-system.requires = ["uv_build>=0.8.14,<0.9.0"]` and `build-backend = "uv_build"`, ensuring deterministic sdist/wheel generation.
6. **Coordinated release hygiene.** A dedicated release note (`docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md`) codifies the adoption policy: "latest stable only — no alpha, beta, RC, or dev builds", with one recorded exception for OpenTelemetry instrumentation packages which stay on their permanent `0.xb` channel paired to a locked SDK version. Upgrades are applied uniformly across all eight Python products in a single pass.
7. **Shared SDK placeholder.** `shared/shared-sdk/README.md` documents the intended boundary for reusable clients/auth/tracing helpers that will be consumed by multiple products once extracted — currently a placeholder, not yet a published package.

## Conventions and Constraints

- **Frozen installs are mandatory**: `uv sync --frozen` is the only supported install path in `mk/python.mk`; any deviation bypasses the lockfile guarantee.
- **Python version pinned per product**: each product ships a `.python-version` file (e.g., `3.12` in `agent-platform/.python-version`) alongside the `requires-python = ">=3.11"` constraint in `pyproject.toml`.
- **Version lockstep is enforced**: `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root, ensuring the root `VERSION` and every product's declared version stay synchronized.
- **Secret vocabulary lockstep**: `make validate-secret-vocabulary` ensures redaction vocabularies in `agent-platform` and `tool-gateway` stay aligned via `shared/shared-contracts/scripts/validate_secret_vocabulary.py`.
- **No vendoring of third-party code**: all dependencies resolve from PyPI (`source = { registry = "https://pypi.org/simple" }` in lockfiles); there is no `vendor/` directory or private registry configured in the checked-in files.
- **Docker images consume the same lockfiles**: the `base-uv` image and per-product Dockerfiles rely on `uv` to honor `uv.lock`, so container builds reproduce the same dependency tree as local `make sync`.
- **Frontend dependency updates follow the same latest-stable posture**, documented in the same release note (React 19, antd 6, TypeScript 5.9.x, Vite 8.x, Vitest 4.x).

## Enforcement Surface

| Mechanism | What it enforces | Location |
|---|---|---|
| `uv sync --frozen` | Deterministic install from `uv.lock` | `mk/python.mk` |
| `make verify` | Runs tests, overlays, policy validation, version & secret-vocabulary checks | `Makefile` |
| `make validate-version` | Product versions match root `VERSION` | `shared/shared-contracts/scripts/validate_version.py` |
| `make validate-secret-vocabulary` | Redaction vocabularies in agent-platform/tool-gateway match | `shared/shared-contracts/scripts/validate_secret_vocabulary.py` |
| Release-note policy | Adoption of "latest stable only" with recorded exceptions | `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` |

This approach keeps each microservice self-contained while coordinating upgrades through a single release process and a set of cross-cutting validation targets.