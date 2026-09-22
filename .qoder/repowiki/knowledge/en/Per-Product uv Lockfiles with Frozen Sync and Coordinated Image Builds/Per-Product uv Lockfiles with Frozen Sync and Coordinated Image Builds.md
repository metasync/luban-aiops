---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Sync and Coordinated Image Builds
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
    - products/agent-platform/.python-version
    - products/agent-platform/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
---

## System overview

The Luban AIOps platform manages dependencies through a **per-product Python dependency model** built on `uv` (the fast Python package manager) with **frozen lockfiles**, coordinated container image builds, and a root-level Makefile that orchestrates sync, test, lint, and verification across all products. The operator-portal is the only non-Python surface; its Node.js dependencies are managed separately under `products/operator-portal/web-ui/`.

## How dependencies are declared

- Each product lives under `products/<name>/` and declares its own `pyproject.toml` plus a matching `.python-version` file (e.g. `3.12`).
- Runtime dependencies are listed in `[project].dependencies` using caret-style ranges (e.g. `fastapi>=0.115,<1.0`, `agentscope>=2.0.4,<3.0`, `pydantic>=2.8,<3.0`).
- Test-only dependencies live in the `[dependency-groups] dev = [...]` section (`pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`, `fakeredis>=2.26,<3.0`).
- The build backend is pinned to `uv_build>=0.8.14,<0.9.0` via `[build-system]`.
- The operator-portal uses a conventional Node.js setup (package.json / package-lock.json) — no `uv` involvement there.

## Locking and resolution strategy

- Every Python product ships a committed `uv.lock` file. The spec SPEC-042 requires each lock to carry the **latest stable version its range allows**; prereleases, betas, RCs, and dev builds are not adopted anywhere.
- Dependency installation always runs with `uv sync --frozen`, both in local development (`mk/python.mk`) and inside Docker images (`RUN uv sync --frozen --no-dev`). This pins the exact transitive tree recorded in `uv.lock` — no network resolution at runtime or build time.
- The shared base image `luban-aiops/base-uv:al2023` is built once from `shared/base-images/base-uv/Dockerfile` with a pinned `UV_VERSION` (default `0.12.1`) and `PYTHON_VERSION` (default `3.12`), then consumed by every product Dockerfile as `FROM luban-aiops/base-uv:al2023`.

## Version coordination across the workspace

- A single root `VERSION` file is the source of truth for the platform release tag. The root Makefile computes `IMAGE_TAG` from it and writes a coordinated `.images.env` listing every product image tagged identically.
- Per-product `pyproject.toml` versions must stay in lockstep with `VERSION`; this is enforced by `make validate-version`, which invokes `shared/shared-contracts/scripts/validate_version.py` against the repo root.
- Product metadata files (`src/*/metadata.py`, `__init__.py` literals) also carry the same version and are refreshed together with `uv.lock` re-locks during releases.

## Shared contracts and SDK boundary

- `shared/shared-contracts/` holds canonical schemas, policy bundles, and validation scripts used by multiple products. Policy YAMLs are copied from canonical locations into consumers via `make sync-policy`.
- `shared/shared-sdk/` is a placeholder module for future shared service clients, auth helpers, tracing utilities, and typed event producers/consumers — currently empty but intended as the reuse boundary for cross-product library code.

## Build and CI integration

- The root `Makefile` enumerates `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` and dispatches `sync`, `test`, `lint`, `build`, and `push` to each product's Makefile.
- `mk/python.mk` provides the shared `sync` and `test` targets that run `uv sync --frozen` then `uv run pytest` with OTLP exporters disabled so tests remain deterministic.
- `mk/image.mk` provides shared `build`/`push`/`lint` targets that produce images tagged `luban-aiops/<name>:<tag>` and optionally re-tag to a configured `REGISTRY`.
- `mk/defaults.mk` centralizes overridable defaults (image platform, registry, base image versions) so standalone product builds resolve the same configuration as root-driven builds.
- The `verify` target chains per-product tests, Kustomize overlay rendering, policy validation, scenario evaluation, version lockstep checks, secret-vocabulary validation, password-policy validation, and a local secret-delivery demo — serving as the pre-commit/pre-push gate.

## Conventions observed

- **Frozen sync everywhere**: production images and local dev both use `uv sync --frozen`; no ad-hoc `pip install` or unfrozen resolves.
- **Caret-capped ranges + latest-stable locks**: ranges allow minor/patch drift, but `uv.lock` is refreshed regularly to adopt the newest stable within those bounds (SPEC-042 R-5).
- **One base image, one uv version**: `BASE_UV_IMAGE`, `BASE_UV_TAG`, `BASE_UV_UV_VERSION`, and `BASE_UV_PYTHON_VERSION` in `mk/defaults.mk` are the single source of truth for the Python runtime environment.
- **No vendoring**: third-party packages are resolved from PyPI via `uv` lockfiles; nothing is vendored into the repo.
- **Private registries**: none are configured in the checked-in files; `REGISTRY` is an override variable for pushing to an external registry when desired.
- **Portal Node.js deps** are isolated under `products/operator-portal/web-ui/` and do not participate in the `uv` workflow.