---
kind: dependency_management
name: Per-Product uv Lockfiles with Shared Base Image and Coordinated Build
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/audit-service/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/execution-runtime/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/agent-platform/Dockerfile
    - Makefile
---

## System Overview

The Luban AIOps Platform monorepo manages Python dependencies using **uv** (Astral) as the package manager, with one `pyproject.toml` + `uv.lock` pair per product under `products/<name>/`. There is no workspace-level lockfile or shared dependency manifest — each service declares its own runtime and dev dependencies, but they are kept in lockstep through conventions enforced by shared build fragments.

## Key Files and Packages

- Per-product manifests: `products/*/pyproject.toml` declare `[project]`, `[dependency-groups]`, and `[build-system]` (`requires = ["uv_build>=0.8.14,<0.9.0"]`, `build-backend = "uv_build"`).
- Per-product lockfiles: `products/*/uv.lock` pin every transitive dependency to a specific version and SHA256 hash, sourced from `https://pypi.org/simple`.
- Shared Makefile fragments:
  - `mk/python.mk` — defines `sync` (`uv sync --frozen`) and `test` targets used by every Python product.
  - `mk/image.mk` — Docker image build/push/lint targets that invoke `uv sync --frozen --no-dev` during image builds.
  - `mk/defaults.mk` — pinned defaults for `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`.
- Shared base image: `shared/base-images/base-uv/Dockerfile` installs a pinned `uv` into Amazon Linux 2023 minimal, sets `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=<version>`, and runs as non-root user `app`.
- Root orchestration: root `Makefile` lists `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and dispatches `make sync` / `make test` across all of them.
- Product Dockerfiles (e.g. `products/agent-platform/Dockerfile`) copy only `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, and `src/`, then run `uv sync --frozen --no-dev`.

## Architecture and Conventions

1. **Frozen resolution everywhere.** Both development (`make sync` → `uv sync --frozen`) and production images (`uv sync --frozen --no-dev`) use `--frozen`, so the resolved tree must exactly match `uv.lock`. No network resolution is allowed at install time.
2. **One lockfile per product, not per workspace.** Each service has its own `uv.lock`; there is no monorepo-wide lockfile. Cross-product consistency is achieved by keeping dependency spec ranges aligned (see below).
3. **Pinned major/minor ranges, never loose pins.** All products constrain shared libraries with upper bounds: e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`, `prometheus-client>=0.20,<1.0`, `uvicorn[standard]>=0.30,<1.0`, `cryptography>=43.0,<51.0`, `PyJWT>=2.8,<3.0`, `httpx>=0.27,<1.0`, `psycopg[binary]>=3.2,<4.0`, `PyYAML>=6.0,<7.0`. This prevents an automatic upgrade from breaking inter-service contracts.
4. **Shared base image isolates uv and Python versions.** The base image pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` via build args; `UV_PYTHON_INSTALL_DIR=/app/.python` stores interpreter copies per product. Every product's `Dockerfile` starts from `luban-aiops/base-uv:al2023`.
5. **No vendoring, no private registry configured in code.** Dependencies resolve against PyPI (`source = { registry = "https://pypi.org/simple" }` in lockfiles). There is no `uv.config.toml`, `PIP_INDEX_URL`, `index-url`, or `pip.conf` anywhere in the repo — private registries would need to be injected via environment variables or uv configuration outside the repo.
6. **Dev-only extras isolated via `dependency-groups`.** Test-only packages (`pytest`, `jsonschema`, `fakeredis`) live under `[dependency-groups] dev = [...]` and are excluded from images via `--no-dev`.
7. **Coordinated image tagging ties products together.** The root `Makefile` computes a single `IMAGE_TAG` from `VERSION` plus git metadata and writes it into `.images.env`, then tags every product image with the same tag. This ensures a deployed cluster always runs a coordinated set of services, even though their Python dependencies are locked independently.

## Conventions and Constraints

- **Every Python product must include `../../mk/python.mk`** to inherit the `sync` and `test` targets that enforce `uv sync --frozen` (documented in `mk/python.mk` header).
- **Image builds must use `uv sync --frozen --no-dev`** so production containers contain only runtime deps and cannot reach PyPI at build time (enforced by the shared `mk/image.mk` fragment and every product Dockerfile).
- **Dependency ranges must include an upper bound** on shared libraries (FastAPI, Pydantic, OTel SDK, Prometheus client, etc.) to avoid accidental upgrades across services — this is a consistent convention observed across all eight product manifests.
- **Python version is pinned per product via `.python-version`** and selected by the base image's `UV_PYTHON` env var; changing the interpreter requires updating both the base image default and each product's `.python-version`.
- **Build tooling itself is pinned:** `uv_build>=0.8.14,<0.9.0` in every product's `[build-system]`, and `BASE_UV_UV_VERSION=0.12.1` in `mk/defaults.mk`.
- **No cross-product Python package references exist** — services communicate over HTTP/gRPC, not by importing shared Python packages, which is why each product maintains its own lockfile rather than sharing one.