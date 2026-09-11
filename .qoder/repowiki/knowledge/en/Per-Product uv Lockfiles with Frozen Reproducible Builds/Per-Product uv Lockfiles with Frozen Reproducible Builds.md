---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Reproducible Builds
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - Makefile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/uv.lock
    - products/agent-platform/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## What system/approach is used

The repository manages Python dependencies per product using **uv** (the fast Python package installer/resolver) together with PEP 621 `pyproject.toml` manifests and per-product `uv.lock` lockfiles. There is no monorepo-level dependency manifest; each service under `products/<name>/` declares its own runtime and dev dependencies, and the root orchestrates them via shared Makefile fragments in `mk/`.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` — declare `[project]` dependencies, `[dependency-groups].dev`, entry-point scripts, and a `build-system` that pins `uv_build>=0.8.14,<0.9.0` as the build backend.
- Per-product lockfiles: `products/*/uv.lock` — fully pinned transitive resolution from `https://pypi.org/simple`, including wheel URLs and sha256 hashes for every resolved package.
- Shared build helpers: `mk/python.mk` exposes `sync` (`uv sync --frozen`) and `test` targets consumed by each product's Makefile; `mk/image.mk` builds Docker images that copy only `pyproject.toml` + `uv.lock` into the image and run `uv sync --frozen --no-dev` at build time; `mk/defaults.mk` pins the shared base image toolchain (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`).
- Root orchestration: `Makefile` enumerates `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS`, then delegates `sync`, `test`, `lint`, `build`, and `push` to each product.
- Container images: each product's `Dockerfile` uses the shared `luban-aiops/base-uv:al2023` image and installs deps with `uv sync --frozen --no-dev`.
- Version coordination: `VERSION` at the repo root plus `shared/shared-contracts/scripts/validate_version.py` enforce that every product's `pyproject.toml` version stays in lockstep with the platform release.
- Dependency hygiene policy: documented in `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` — adoption policy is "latest stable only" (no alpha/beta/RC/dev), with one recorded exception for OpenTelemetry instrumentation packages on their permanent `0.xb` channel.

## Architecture and conventions

- **Per-product isolation**: each product has its own `pyproject.toml` and `uv.lock`; there are no cross-package workspace links between products. Dependencies are duplicated intentionally so each service ships an independent, reproducible environment.
- **Frozen installs everywhere**: both development (`make sync`, `make test`) and production container builds use `uv sync --frozen`, which refuses to resolve anything not already present in `uv.lock`. This makes CI and container images deterministic.
- **Pinned ranges, locked versions**: runtime dependencies use semver-compatible ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `cryptography>=43.0,<51.0`, `redis>=6.2,<7.0`, `elasticsearch>=8.0,<9.0`) while the lockfile pins exact versions. Major-version caps prevent accidental breaking upgrades.
- **Shared base image**: `shared/base-images/base-uv/Dockerfile` builds a minimal `al2023` image with a pinned `uv` and `python:3.12`, referenced by `mk/defaults.mk` as `BASE_UV_IMAGE=luban-aiops/base-uv` / `BASE_UV_TAG=al2023` / `BASE_UV_UV_VERSION=0.12.1`. All product images inherit this baseline.
- **Coordinated tagging**: the root `Makefile` computes a single `IMAGE_TAG` from `VERSION` + git SHA (+ optional profile/dirty suffix) and writes it into `.images.env`; all product images are tagged with the same coordinated tag and pushed/pulled as a unit.
- **No vendoring or private registry**: all packages resolve from `https://pypi.org/simple` (visible in every `uv.lock` `source` field). No `uv.config.toml`, `index-url`, `private-registry`, or `GOFLAGS` configuration was found — the workspace relies entirely on public PyPI.

## Conventions and constraints

- Every Python product must declare dependencies in `pyproject.toml` under `[project].dependencies` and keep `uv.lock` committed; `make verify` runs `uv sync --frozen` through each product's Makefile, so a stale lockfile breaks the gate.
- Runtime dependencies use upper major-version caps (e.g. `<3.0`, `<1.0`, `<7.0`, `<9.0`) to block automatic major bumps; new dependencies must follow the same range pattern.
- Dev-only tools go in `[dependency-groups].dev` (pytest, jsonschema, fakeredis) and are excluded from container images via `--no-dev`.
- The build backend itself is pinned: `uv_build>=0.8.14,<0.9.0` in every product's `[build-system]`.
- The shared base image toolchain is centrally pinned in `mk/defaults.mk` (`BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`) and rebuilt via `make base-images` before `make build`.
- Product versions must stay synchronized with the root `VERSION` file; `make validate-version` enforces this via `shared/shared-contracts/scripts/validate_version.py`.
- The adopted upgrade posture is "latest stable only" — pre-release channels are explicitly rejected except for OpenTelemetry instrumentation packages, which remain on upstream's permanent `0.xb` channel paired with their SDK version.