---
kind: dependency_management
name: uv-based Per-Product Dependency Lockfiles with Frozen Reproducible Builds
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - .python-version
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - shared/base-images/base-uv/Dockerfile
    - docs/workspace/python-container-strategy.md
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
---

## Approach

The Luban workspace is a Python monorepo whose dependency management is built on **uv** (Astral's fast Python package manager). Each product under `products/<name>/` is an independent PEP 621 project declared in its own `pyproject.toml`, with a co-located `uv.lock` pinning every transitive resolution. There is no shared `requirements.txt`, no Poetry, no pipenv, and no vendored third-party source trees — dependencies are resolved at build time from PyPI against the lockfile.

The root `.python-version` pins the workspace interpreter to `3.12`; each product also carries its own `.python-version` (e.g. `3.12`) so `uv sync` resolves the managed interpreter deterministically. The root `Makefile` aggregates per-product `sync`/`test` targets across eight Python products (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`).

## Key Files

- Root: `Makefile` (aggregates `sync`, `test`, `build`, `push`), `.python-version`, `mk/python.mk` (shared `uv sync --frozen` + pytest target), `mk/image.mk`, `mk/defaults.mk`
- Base image: `shared/base-images/base-uv/Dockerfile` (pinned uv install)
- Product manifests: `products/*/pyproject.toml` (PEP 621 deps + `[dependency-groups] dev = [...]`), `products/*/uv.lock` (frozen resolution)
- Container strategy doc: `docs/workspace/python-container-strategy.md`
- Release note documenting policy: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` (SPEC-042)

## Architecture and Conventions

### Declaration style
Each `pyproject.toml` uses PEP 621 `[project.dependencies]` with **upper-capped ranges** (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `cryptography>=43.0,<51.0`, `redis>=6.2,<7.0`, `elasticsearch>=8.0,<9.0`). Dev-only packages live in `[dependency-groups].dev` (pytest, fakeredis, jsonschema). The build backend is pinned to `uv_build>=0.8.14,<0.9.0` via `[build-system]`. All eight Python products declare `requires-python = ">=3.11"`.

### Resolution and reproducibility
The shared Makefile fragment `mk/python.mk` runs `uv sync --frozen` for both `sync` and `test`, meaning the lockfile is authoritative — no floating to newer versions during CI or local development. The root `make sync` loops over all Python products and invokes their per-product `sync` target.

### Containerization
The base image `shared/base-images/base-uv` installs a pinned version of uv (via `UV_VERSION` ARG, default pinned — never `latest`) and sets environment variables `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON`, `UV_PYTHON_INSTALL_DIR=/app/.python`. Product Dockerfiles inherit this base; because `UV_NO_SYNC=1` is set at the image level, runtime containers do not re-resolve dependencies — they rely on the pre-built frozen environment baked into the image by `make build`.

### Versioning discipline
The release note for SPEC-042 documents an explicit adoption policy: **latest stable only** — no alpha, beta, RC, or dev builds. Exceptions are recorded explicitly (OpenTelemetry instrumentation packages ship on a permanent `0.xb` channel and stay paired with their locked SDK). Major caps are deliberately parked where server compatibility dictates them (Redis `<7.0` aligned with deployed Redis 7.2; Elasticsearch `<9.0` since no ES server is deployed in dev).

### Cross-cutting verification
`make verify` is the pre-commit/pre-push gate and includes `test overlays validate-dashboards validate-policy validate-policy-scenarios validate-version validate-secret-vocabulary validate-password-policy secret-delivery-demo portal-test execution-failure-test`. While it does not run a dedicated `uv export` or `uv tree` audit, the frozen-lock approach plus the full test suite serves as the enforcement mechanism.

## Conventions and Constraints

- **One `pyproject.toml` + one `uv.lock` per product** under `products/<name>/`; there is no workspace-level dependency manifest.
- **Dependencies use upper-capped ranges** (e.g. `<1.0`, `<3.0`, `<51.0`) rather than exact pins in `pyproject.toml`; exact versions live only in `uv.lock`.
- **`uv sync --frozen` is enforced** by `mk/python.mk`, which is included by every Python product's `Makefile`; CI and local `make test` always resolve against the committed lockfile.
- **Runtime containers disable sync** via `UV_NO_SYNC=1` inherited from the base image, making the container image itself the single source of truth for installed packages.
- **Interpreter pinning**: root `.python-version` declares `3.12`; each product has its own `.python-version` so `uv sync` resolves the managed interpreter deterministically without relying on system Python.
- **Build tool pinning**: `[build-system].requires = ["uv_build>=0.8.14,<0.9.0"]` is uniform across products.
- **Adoption policy** (from SPEC-042 release notes): upgrades target latest stable only; exceptions (OTel instrumentation `0.xb` channel) are documented explicitly.
- **Major cap parking**: Redis capped at `<7.0` to match the deployed Redis 7.2 server; Elasticsearch capped at `<9.0` because no ES server is deployed in dev — these are deliberate compatibility constraints, not omissions.
- **No private registry configuration** was found in any `pyproject.toml`, `uv.lock`, `mk/*.mk`, or Dockerfile; dependencies are resolved from the default PyPI index.