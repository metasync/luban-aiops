---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management with Coordinated Versioning
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - Makefile
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/agent-platform/uv.lock
    - shared/shared-contracts/scripts/validate_version.py
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## What system/approach is used

The repository manages Python dependencies per product using **uv** (the fast Python package manager) with PEP 621 `pyproject.toml` manifests and a per-product `uv.lock` lockfile. There are no `requirements.txt`, Poetry, Pipenv, or pip-based workflows. The build backend is `uv_build` (`[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]`). Each of the eight Python products under `products/` (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) ships its own `pyproject.toml` and `uv.lock`. A shared Makefile fragment in `mk/python.mk` exposes `sync` and `test` targets that run `uv sync --frozen` inside each product directory, pinning installs to the committed lockfile.

The root-level `Makefile` orchestrates cross-cutting operations: `make sync` iterates all `PYTHON_PRODUCTS` and invokes each product's `sync`; `make test` runs every product suite; `make verify` chains tests, overlay checks, policy validation, version validation, and secret-vocabulary validation. Container images are built from a shared base image `shared/base-images/base-uv` whose tag is driven by `BASE_UV_*` variables in `mk/defaults.mk`, ensuring the same uv and Python versions across all product Dockerfiles.

## Key files and packages

- Per-product dependency manifests: `products/*/pyproject.toml` — declare runtime `dependencies`, `[dependency-groups].dev`, entry-point scripts, and `requires-python = ">=3.11"`.
- Per-product lockfiles: `products/*/uv.lock` — frozen resolution with pinned hashes for every transitive dependency, sourced from `https://pypi.org/simple`.
- Shared uv workflow: `mk/python.mk` — defines `sync: uv sync --frozen` and `test` which re-syncs then runs pytest with OTel exporters disabled so tracing tests stay green without network noise.
- Root orchestration: `Makefile` — lists `PYTHON_PRODUCTS`, dispatches `sync`/`test`/`build`/`push`, builds the shared `base-uv` image, and writes coordinated image tags into `.images.env`.
- Base image definition: `shared/base-images/base-uv/Dockerfile` — pins the uv and Python versions baked into every product image.
- Version lockstep enforcement: `shared/shared-contracts/scripts/validate_version.py` invoked via `make validate-version` ensures the root `VERSION` file matches every product's `pyproject.toml` version.
- Dependency hygiene spec: `docs/specs/SPEC-042-dependency-hygiene/spec.md` and release note `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` codify the adoption posture.

## Architecture and conventions

- **One manifest per product**: each service owns its own `pyproject.toml`; there is no monorepo-wide workspace dependency graph. Cross-product sharing happens through internal contracts (`shared/shared-contracts`) and a planned `shared/shared-sdk` module, not through a shared virtual environment.
- **Version ranges with upper bounds**: runtime dependencies use caret-style lower bounds with explicit major-cap upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`, `cryptography>=43.0,<51.0`). This allows patch/minor updates while preventing breaking-major upgrades automatically.
- **Lockfile-first installs**: development and CI always use `uv sync --frozen`, meaning the committed `uv.lock` is the source of truth for reproducible builds. Changes to dependency versions require regenerating the lockfile (`uv lock`) and committing it alongside the manifest change.
- **Coordinated multi-product releases**: the root `Makefile` treats all eight Python products as a single release train. `make build` builds every container image with one coordinated `IMAGE_TAG` derived from the root `VERSION` file, and `make push` pushes them all. Product versions must stay in lockstep with `VERSION` (enforced by `validate-version`).
- **Shared base image for reproducibility**: `make base-images` builds `shared/base-images/base-uv` with pinned `UV_VERSION` and `PYTHON_VERSION` from `mk/defaults.mk`; every product `Dockerfile` uses this base, so the uv binary and Python interpreter are identical across environments.
- **Dependency hygiene posture**: the adopted policy (SPEC-042) is "latest stable only" — no alpha, beta, RC, or dev builds. The OpenTelemetry instrumentation packages are the documented exception because upstream ships on a permanent `0.xb` channel; they stay paired with their locked SDK version rather than being chased.
- **Dev vs runtime separation**: optional extras like `uvicorn[standard]`, `psycopg[binary]`, and `redis` extras are declared inline; test-only packages live under `[dependency-groups].dev` (pytest, jsonschema, fakeredis) and are not installed in production builds.
- **Private registry / vendoring**: none observed. All resolved packages resolve from `registry = "https://pypi.org/simple"` in the lockfiles. No `vendor/` directories, no `Pipfile.lock`, no private index configuration was found in the scanned files.

## Conventions and constraints

- Every new Python product must ship a `pyproject.toml` with `requires-python = ">=3.11"`, a `uv.lock`, and an entry point script under `[project.scripts]` — enforced by the uniform scaffolding pattern across all eight products.
- Dependencies must be declared with an upper major bound to prevent automatic breaking upgrades; when a cap needs widening (e.g. cryptography `<45.0` → `<51.0`), it must be justified by a call-site review of the changed surface, as demonstrated in the dependency-hygiene release notes.
- `uv sync --frozen` is the required install command in both local development and CI; `uv sync` without `--frozen` is not used in any documented workflow.
- The root `VERSION` file is the single source of truth for the platform release number; `make validate-version` enforces that every product `pyproject.toml` version matches it.
- Transitive dependency refreshes go through SPEC-driven change records (SPEC-042) and produce a release note describing the adopt set, verification steps, and any behavioral impact — the process is codified rather than ad hoc.
- Container images are built with `uv sync --frozen --no-dev` (per SPEC-038 task list), so production images exclude dev dependencies.