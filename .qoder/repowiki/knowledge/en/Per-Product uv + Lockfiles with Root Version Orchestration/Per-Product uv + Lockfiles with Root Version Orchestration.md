---
kind: dependency_management
name: Per-Product uv + Lockfiles with Root Version Orchestration
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - VERSION
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/policies/policy-default.yaml
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/package-lock.json
---

## System / Approach

The repository is a Python monorepo of eight backend services plus an operator portal (React/TypeScript). Dependency management follows a **per-product lockfile** model built on **uv** (the fast Python package manager) for the backends and **npm** (`package.json` + `package-lock.json`) for the portal web UI. There is no workspace-level dependency manifest; each product under `products/<name>/` owns its own `pyproject.toml`, `.python-version`, and `uv.lock`. The root `Makefile` orchestrates cross-cutting operations — notably `make sync` runs `uv sync --frozen` in every Python product, and `make verify` adds policy and version checks.

## Key Files

- Per-product manifests: `products/*/pyproject.toml` declare `[project] dependencies`, optional `[dependency-groups.dev]` test deps, and a pinned `[build-system]` using `uv_build>=0.8.14,<0.9.0`.
- Per-product lockfiles: `products/*/uv.lock` are committed alongside each product and consumed via `uv sync --frozen` (see `mk/python.mk`).
- Per-product interpreter pin: `products/.python-version` (e.g. `3.12`) tells uv which CPython to resolve during install.
- Root orchestration: `Makefile` lists `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and exposes `sync`, `test`, `verify` targets that delegate into each product's Makefile.
- Shared base image: `shared/base-images/base-uv/Dockerfile` builds a minimal Amazon Linux 2023 image with a pinned `uv` binary; all product Dockerfiles build on top of it and run `uv sync --frozen --no-dev`.
- Version lockstep enforcement: `shared/shared-contracts/scripts/validate_version.py` reads the single source-of-truth `VERSION` file at the repo root and asserts that every `products/*/pyproject.toml [project] version`, every product's `src/*/metadata.py SERVICE_VERSION`, any `__version__` in package roots, and the operator portal's Vite wiring all match it exactly.
- Policy bundle validation: `shared/shared-contracts/scripts/validate_policy.py` validates the canonical policy YAML against `shared/shared-contracts/schemas/policy-rule.schema.json`; the Makefile target `sync-policy` copies the canonical bundle from `shared/shared-contracts/policies/policy-default.yaml` into each consumer location (`products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`).
- Portal frontend: `products/operator-portal/web-ui/app/package.json` declares runtime and dev dependencies; `package-lock.json` pins resolutions.

## Architecture and Conventions

- **Frozen installs everywhere.** All CI and local flows use `uv sync --frozen`, meaning the committed `uv.lock` is authoritative and no resolution may drift. The same pattern applies to container images, which run `uv sync --frozen --no-dev` to avoid installing dev-only extras.
- **Range-pinned, not exact-pinned, declarations.** Dependencies in `pyproject.toml` use caret ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `agentscope>=2.0.4,<3.0`) so `uv lock` can pick the latest stable within the range while still preventing major bumps. A dedicated SPEC-042 codifies a "latest stable only" adoption policy and records adjudications for caps that intentionally lag upstream (redis client `<7.0`, elasticsearch client `<9.0`, cryptography capped per call-site review).
- **Dev vs prod separation via dependency groups.** Test-only packages live under `[dependency-groups.dev]` (pytest, jsonschema, fakeredis) and are excluded from production images by `--no-dev`.
- **Single source of truth for versions.** The root `VERSION` file (currently `0.23.2`) is the canonical platform semver; `make validate-version` enforces that every product's `pyproject.toml` version and runtime metadata match it. This is separate from third-party dependency versions but part of the same release hygiene surface.
- **Shared contracts as a dependency boundary.** Cross-service schemas live in `shared/shared-contracts/schemas/*.schema.json` and policies in `shared/shared-contracts/policies/`. Consumers copy or reference them rather than redeclaring versions, keeping contract evolution centralized.
- **No vendoring of third-party code.** Dependencies are resolved from PyPI/npm registries at build time; there is no `vendor/` directory or private registry configuration in the checked-in tree.

## Conventions and Constraints

- Every Python product must have a `pyproject.toml`, `.python-version`, and `uv.lock` — new products scaffolded per SPEC-013/014/015 follow this layout.
- `uv sync --frozen` is the only supported way to install dependencies locally or in CI; non-frozen installs are not used in any documented flow.
- Container images must be based on the shared `luban-aiops/base-uv` image and must run `uv sync --frozen --no-dev` as their dependency installation step (enforced by the product Dockerfiles and the `base-uv` image strategy documented in `docs/workspace/python-container-strategy.md`).
- Third-party dependency updates must stay inside the declared ranges in `pyproject.toml`; major bumps require updating the range cap and passing `make verify`.
- The `validate_version.py` script is invoked via `make validate-version` and is part of the `make verify` gate; any drift between `VERSION` and product pyproject/metadata fails the build.
- Policy bundles are managed centrally: changes go to `shared/shared-contracts/policies/policy-default.yaml` and are propagated via `make sync-policy`; consumers cannot maintain independent copies without going through the canonical path.
- Frontend dependencies use standard npm conventions (`package.json` + `package-lock.json`) under `products/operator-portal/web-ui/app/`; the SPEC-042 plan documents a deliberate refresh cadence and requires `tsc --noEmit`, vitest, and the production build to pass after upgrades.