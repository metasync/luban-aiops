---
kind: dependency_management
name: Per-Product uv Lockfiles with Centralized Version & Policy Enforcement
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - shared/base-images/base-uv/Dockerfile
    - VERSION
    - shared/shared-contracts/scripts/validate_version.py
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/agent-platform/Dockerfile
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## What system/approach is used

The repository manages dependencies through **per-product Python packages** using `uv` as the package manager and resolver. Each product under `products/` declares its own `pyproject.toml` (PEP 621) and ships a committed `uv.lock` lockfile. There are no monorepo-level dependency manifests — instead, each product is an independent distribution pinned by its local lockfile, and container images are built from those same files.

The build toolchain is layered:
- `mk/python.mk` defines shared `sync` / `test` targets that invoke `uv sync --frozen`, forcing resolution strictly against the committed `uv.lock`.
- `mk/image.mk` provides shared Docker image targets; every product `Dockerfile` copies `pyproject.toml` and `uv.lock` into the image and runs `uv sync --frozen --no-dev` at build time.
- The root `Makefile` orchestrates cross-cutting concerns: `make sync` iterates all `PYTHON_PRODUCTS`, `make verify` runs tests, overlay checks, policy validation, version validation, and secret-vocabulary validation in one gate.

A dedicated base image (`shared/base-images/base-uv/Dockerfile`) pins the `UV_VERSION` and `PYTHON_VERSION` build args so all products share the same `uv` + Python runtime.

## Key files and packages

- Per-product declarations: `products/*/pyproject.toml` (e.g. `products/agent-platform/pyproject.toml`, `products/platform-gateway/pyproject.toml`) declare `[project]` dependencies with caret-style ranges (e.g. `fastapi>=0.115,<1.0`, `agentscope>=2.0.4,<3.0`, `cryptography>=43.0,<51.0`) and optional `[dependency-groups].dev` for test-only packages.
- Per-product lockfiles: `products/*/uv.lock` (committed alongside each product).
- Shared Makefile fragments: `mk/python.mk` (`uv sync --frozen`), `mk/image.mk` (image build/push/lint), `mk/defaults.mk` (registry, platform, base-image tags).
- Root orchestration: `Makefile` (`sync`, `build`, `push`, `verify`, `validate-version`).
- Base image: `shared/base-images/base-uv/Dockerfile`.
- Version enforcement: `shared/shared-contracts/scripts/validate_version.py` asserts that every product's `pyproject.toml` version, `src/*/metadata.py` `SERVICE_VERSION`, `src/*/__init__.py` `__version__`, and operator portal Vite wiring all match the single source of truth `VERSION` at the repo root.
- Policy document: `docs/specs/SPEC-042-dependency-hygiene/spec.md` codifies the adoption posture.

## Architecture and conventions

1. **One lockfile per product.** Each service owns its own `uv.lock`; there is no workspace-level lock. Reproducibility is enforced via `uv sync --frozen` everywhere (development Make targets, CI, and Docker builds).
2. **Dependency ranges are bounded but not pinned to exact versions.** Declarations use `>=X,<Y` ranges (typically major-version caps). The latest stable version within each range is resolved into `uv.lock` during refreshes, as documented in the release notes for SPEC-042.
3. **Adoption posture is "latest stable only"**. The SPEC-042 release notes state explicitly that alpha/beta/RC/dev builds are excluded, with one recorded exception: OpenTelemetry instrumentation packages stay on their permanent `0.xb` channel paired with the locked SDK version.
4. **Python version is centralized.** Every product has a `.python-version` file and requires `>=3.11` in `pyproject.toml`. The base image pins the exact Python and `uv` versions, so all containers run the same interpreter.
5. **Container images embed the lock.** Dockerfiles copy `pyproject.toml` and `uv.lock` into the image and install deps with `--no-dev`, ensuring production images match the developer environment exactly.
6. **Platform-wide version lockstep.** A single `VERSION` file at the repo root is the canonical semver. `make validate-version` (via `validate_version.py`) fails if any product `pyproject.toml`, `metadata.py`, or `__init__.py` drifts from it. This couples product releases to a coordinated multi-service version bump.
7. **Shared contracts are versioned separately.** JSON schemas and policies live in `shared/shared-contracts/` and are validated by scripts invoked from the root Makefile (`validate-policy`, `validate-policy-scenarios`, `policy-diff`). They are not Python dependencies but are treated as versioned artifacts consumed by multiple products.

## Conventions and constraints

- **Frozen installs everywhere.** Development (`mk/python.mk`), testing, and Docker builds all use `uv sync --frozen`, so uncommitted `uv.lock` changes will fail the build — this is the primary reproducibility invariant.
- **No vendored third-party code.** Dependencies are resolved from PyPI (or configured registries) at build time; there is no `vendor/` directory or checked-in wheels.
- **Dev vs. prod dependencies are separated.** Optional `[dependency-groups].dev` in `pyproject.toml` lists test-only packages (pytest, fakeredis, jsonschema); Docker builds pass `--no-dev` to exclude them.
- **Major-version caps are enforced in declarations.** Almost every dependency uses a `<N+1>` cap (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`), preventing accidental major upgrades without explicit review.
- **Cryptography and redis caps are intentionally parked.** The SPEC-042 release notes document why `redis<7.0` and `elasticsearch<9.0` remain capped despite newer majors being available — they track deployed server versions.
- **OpenTelemetry instrumentation stays on the `0.xb` channel.** The release notes record this as the sole exception to the "latest stable only" rule, because upstream publishes these packages on a permanent beta channel.
- **Version drift is a build failure.** `make validate-version` exits non-zero on any mismatch between `VERSION` and product metadata; it is part of the `make verify` gate.
- **Secret vocabulary is also centrally validated.** `make validate-secret-vocabulary` ensures redaction vocabularies stay in lockstep across agent-platform and tool-gateway, analogous to how dependency versions are coordinated.