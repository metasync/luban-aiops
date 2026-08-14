---
kind: dependency_management
name: Per-Product uv Lockfiles with Shared Base Image and Root Orchestration
category: dependency_management
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/audit-service/pyproject.toml
    - products/audit-service/uv.lock
    - products/identity-broker/pyproject.toml
    - products/identity-broker/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/platform-gateway/uv.lock
    - products/tool-gateway/pyproject.toml
    - products/tool-gateway/uv.lock
    - shared/base-images/base-uv/Dockerfile
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - Makefile
---

## What system/approach is used

The monorepo manages Python dependencies per product using **uv** (Astral) as the package manager, with one `pyproject.toml` + `uv.lock` pair under each product directory (`products/agent-platform`, `products/audit-service`, `products/identity-broker`, `products/platform-gateway`, `products/tool-gateway`). There is no workspace-level lockfile; each product pins its own dependency graph independently. The build system uses a shared Amazon Linux 2023 base image (`shared/base-images/base-uv`) that installs a pinned `uv` binary and runs as a non-root `app` user — containers never install a system Python, relying on uv to resolve interpreters from each product's `.python-version` file.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` declare runtime dependencies (FastAPI, Pydantic, httpx, PyJWT, cryptography, opentelemetry exporters, prometheus-client, uvicorn) plus a `[dependency-groups].dev` group for pytest/jsonschema/fakeredis.
- Per-product lockfiles: `products/*/uv.lock` pin exact transitive versions resolved by uv.
- Build backend: every product sets `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"`.
- Interpreter pinning: each product ships a `.python-version` file (e.g. `products/agent-platform/.python-version`) consumed by uv during sync/build.
- Shared Make fragments:
  - `mk/python.mk` — `sync` and `test` targets run `uv sync --frozen` then `uv run pytest`.
  - `mk/image.mk` — Docker build/push helpers that tag images under `luban-aiops/<name>:<tag>`.
  - `mk/defaults.mk` — single source of overridable defaults (IMAGE_PLATFORM, REGISTRY, BASE_UV_UV_VERSION=0.12.1, BASE_UV_PYTHON_VERSION=3.12).
- Root orchestrator: root `Makefile` defines `PYTHON_PRODUCTS := agent-platform audit-service identity-broker platform-gateway tool-gateway` and dispatches `make sync`, `make test`, `make lint`, `make build`, `make push` across all products in one pass.
- Container entrypoint: each product `Dockerfile` copies `pyproject.toml`, `uv.lock`, and `src/`, then runs `RUN uv sync --frozen --no-dev` and `CMD ["uv", "run", "<entrypoint>"]`.
- Base image: `shared/base-images/base-uv/Dockerfile` pins UV_VERSION=0.12.1 and PYTHON_VERSION=3.12 via build args and exports `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=<version>`, `UV_PYTHON_INSTALL_DIR=/app/.python`.

## Architecture and conventions

- **Per-product isolation**: Each service owns its own dependency manifest and lockfile; there are no cross-product Python package references between services. Shared code lives only as JSON schemas and YAML policies under `shared/shared-contracts/`, not as importable Python packages.
- **Frozen resolution everywhere**: Both development (`mk/python.mk`) and production builds use `uv sync --frozen`, guaranteeing that the lockfile is authoritative and cannot be silently drifted.
- **Shared base image strategy**: All backend services inherit from `luban-aiops/base-uv:al2023`, which is built once via `make base-images` and reused by every product Dockerfile. This centralizes the uv binary version and Python interpreter selection policy.
- **Coordinated image tagging**: The root `Makefile` computes a single `IMAGE_TAG` (prefix[-profile]-gitsha[-dirty-timestamp]) and writes it into `shared/platform-ops/gitops/dev-k8s/.images.env`, so all five Python services ship with the same gitsha tag for consistent deployments.
- **Dependency version ranges**: Runtime deps use caret-style upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`) to allow patch/minor updates while blocking major bumps; dev deps follow the same pattern.
- **No vendoring or private registries**: Dependencies are resolved from the public PyPI index; there is no `pip.conf`, `uv.toml`, `Pipfile`, `requirements.txt`, `go.mod`, `package.json`, or vendor directory in this repo.

## Conventions and constraints

- Every Python product must have a `pyproject.toml` with a `[build-system]` using `uv_build`; enforced implicitly because the root `make build` iterates over `IMAGE_PRODUCTS` and calls each product's `make build`, which invokes `docker build` against the product Dockerfile that depends on `uv sync`.
- Dependency changes must update the product's `uv.lock` via `uv sync` (not manually edited); the `--frozen` flag in both dev and prod paths enforces that the lockfile matches the manifest exactly.
- The Python interpreter version is pinned per product via `.python-version` and globally defaulted to 3.12 in the base image; changing the default requires updating `mk/defaults.mk` (`BASE_UV_PYTHON_VERSION`) and rebuilding the base image.
- Cross-cutting concerns (linting, testing, overlay rendering, policy validation) are orchestrated from the root `Makefile`; adding a new Python product requires listing it in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS`.
- Policy bundles under `shared/shared-contracts/policies/policy-default.yaml` are copied into each gateway product via `make sync-policy`, keeping policy configuration synchronized alongside dependency management.