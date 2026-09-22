---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Sync and Centralized Version Policy
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - shared/shared-contracts/scripts/validate_version.py
    - VERSION
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/platform-gateway/uv.lock
    - products/audit-service/pyproject.toml
    - products/execution-runtime/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/operator-portal/web-ui/package.json
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## What system/approach is used

The Luban workspace manages dependencies through a per-product Python package model built on **uv** (the fast Python package manager). Each product under `products/` declares its own `pyproject.toml` with explicit dependency ranges and ships a committed `uv.lock` lockfile. The root Makefile orchestrates cross-cutting dependency operations (`make sync`, `make test`, `make build`) that delegate to each product's Makefile, which in turn runs `uv sync --frozen` — pinning installs to the exact versions recorded in `uv.lock`. There is no monorepo-level `requirements.txt` or shared `pyproject`; instead, every product is an independently versioned package.

The operator portal (`operator-portal/web-ui`) uses a conventional Node.js toolchain (Vite + TypeScript + Vitest) with its own `package.json` and `node_modules`, managed separately from the Python stack.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` declare `[project] dependencies`, optional `[dependency-groups.dev]`, and `[build-system]` using `uv_build` as the build backend.
- Per-product lockfiles: `products/*/uv.lock` are committed alongside each `pyproject.toml` and consumed by `uv sync --frozen`.
- Shared build fragments: `mk/python.mk` defines the canonical `sync` and `test` targets that enforce frozen installs; `mk/image.mk` builds container images for each product.
- Root orchestration: `Makefile` enumerates `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS`, then loops over them for `sync`, `test`, `build`, `push`, and the full `verify` gate.
- Version policy enforcement: `shared/shared-contracts/scripts/validate_version.py` asserts that every product's `pyproject.toml` version, `src/*/metadata.py` `SERVICE_VERSION`, any `__version__`, and the portal's Vite wiring all match the single source of truth at `VERSION`.
- Runtime Python version pinning: each product carries a `.python-version` file (e.g. `3.12`) so `uv` resolves the correct interpreter.
- Base image: `shared/base-images/base-uv/Dockerfile` plus `mk/defaults.mk` define the base image tag and `BASE_UV_*` variables used when building product images.
- Release notes documenting the policy: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` codifies the adoption posture.

## Architecture and conventions

- **One lockfile per product**: each service owns its own `uv.lock`, enabling independent refresh cycles while still being coordinated by `make verify`.
- **Frozen installs in CI and dev**: `uv sync --frozen` is the only supported install path in the shared Make targets, guaranteeing reproducible builds from the committed lockfile.
- **Dependency range policy**: dependencies use upper-bounded ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`, `cryptography>=43.0,<51.0`). The release note records the adopted posture as "latest stable only" — no alpha, beta, RC, or dev builds — with one documented exception: OpenTelemetry instrumentation packages stay pinned to their locked SDK pairing because upstream ships them on a permanent `0.xb` channel.
- **Python version alignment**: `requires-python = ">=3.11"` in pyproject files and `.python-version = 3.12` pins the runtime interpreter across products.
- **Build backend pinning**: all products declare `uv_build>=0.8.14,<0.9.0` as the build backend, keeping the build toolchain deterministic.
- **Coordinated image tagging**: the root `Makefile` computes a single `IMAGE_TAG` derived from `VERSION` plus git SHA and applies it uniformly to all product images via `make build`, then writes the resulting tags into `shared/platform-ops/gitops/dev-k8s/.images.env` for deployment.
- **Portal frontend**: the web UI under `operator-portal/web-ui` follows standard Node.js dependency management via `package.json`/`node_modules`; the release note documents a managed refresh (React 19, antd 6.6.2, Vite 8, Vitest 4, jsdom 30) gated by a vitest deprecation warning guard.

## Conventions and constraints

- **`uv sync --frozen` is enforced**: the shared `mk/python.mk` target runs `uv sync --frozen`, so any drift between `pyproject.toml` ranges and `uv.lock` fails the build. This is the primary mechanism preventing accidental transitive upgrades.
- **Single source of truth for version**: `VERSION` at the repo root must match every product's `pyproject.toml` version, every `SERVICE_VERSION` in `src/*/metadata.py`, and any `__version__` in package roots. `make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` and is part of the `verify` gate.
- **No vendoring of third-party code**: there is no `vendor/` directory or vendored libraries; all dependencies resolve from PyPI (or configured registries) at build time against the lockfile.
- **Private registry / auth**: not evident in the checked files; the Docker build/push flow uses `docker` commands with an optional `REGISTRY` override, but no explicit private registry configuration appears in the Makefiles or Dockerfiles shown.
- **Release cadence**: dependency updates are delivered as dedicated releases (e.g. v0.24.0 dependency-only slice) and validated end-to-end via `make verify` plus live demo scripts before merging.
- **Compatibility caps are intentional**: the release note explicitly records why certain major versions are capped (e.g. Redis `<7.0` because client majors 7/8 removed APIs; Elasticsearch `<9.0` because the server is not deployed in dev and the client major tracks the server major).
- **Verification gate**: `make verify` runs tests, kustomize overlay rendering, policy validation/scenarios, version lockstep, secret vocabulary validation, and e2e demos — any dependency change must pass this full gate.