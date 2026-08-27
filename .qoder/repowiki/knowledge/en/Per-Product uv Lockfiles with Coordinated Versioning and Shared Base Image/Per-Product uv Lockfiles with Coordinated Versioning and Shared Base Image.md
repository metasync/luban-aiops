---
kind: dependency_management
name: Per-Product uv Lockfiles with Coordinated Versioning and Shared Base Image
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/agent-platform/.python-version
    - products/platform-gateway/.python-version
    - products/operator-portal/web-ui/app/package.json
---

## What system/approach is used

The workspace uses **uv** as the Python package manager across all backend products. Each product under `products/` is an independent uv project declared in its own `pyproject.toml`, with a per-product `uv.lock` file that pins every transitive dependency to exact versions. The root Makefile orchestrates dependency synchronization via `make sync`, which iterates over the seven Python products (`agent-platform`, `audit-service`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`) and runs each product's `make sync` target — itself a thin wrapper around `uv sync --frozen`. Development dependencies are isolated via PEP 735 `[dependency-groups] dev = [...]` rather than separate files.

For the Node.js frontend (`operator-portal/web-ui/app`), npm is used with `package.json` + `package-lock.json`; there is no shared lockfile at the workspace root for JS dependencies.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` declare runtime `dependencies` (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`, `httpx>=0.27,<1.0`, `cryptography>=43.0,<45.0`) plus optional extras like `psycopg[binary]` and `uvicorn[standard]`.
- Per-product lockfiles: `products/*/uv.lock` (one per product) — these are the immutable artifacts consumed by CI and images.
- Root orchestration: `Makefile` lists `PYTHON_PRODUCTS` and exposes `sync`, `test`, `build`, `push`; `mk/python.mk` provides the shared `sync` / `test` targets that invoke `uv sync --frozen` and `uv run pytest`.
- Container base image: `shared/base-images/base-uv/Dockerfile` builds a minimal Amazon Linux 2023 image with a pinned `uv` version; product Dockerfiles build from `luban-aiops/base-uv:al2023` and run `uv sync --frozen --no-dev` inside the image.
- Python version pinning: each product ships a `.python-version` file (e.g. `3.12`); the container strategy resolves the interpreter from this file during `uv sync`, with `UV_PYTHON` as a deterministic fallback.
- Version coordination: `VERSION` at the repo root is the single source of truth; `shared/shared-contracts/scripts/validate_version.py` enforces that every `products/*/pyproject.toml [project] version`, every `src/*/metadata.py SERVICE_VERSION`, and any `__version__` in package roots match it, and asserts the operator portal's Vite wiring reads the root `VERSION` at build time.

## Architecture and conventions

- **Isolated per-product environments**: No shared `requirements.txt` or monorepo-level `pyproject.toml`. Each product manages its own dependency graph independently, which lets services pick different major/minor ranges (e.g. `agentscope>=2.0.4,<3.0` vs `kubernetes>=30.0,<33.0`).
- **Frozen installs everywhere**: Both development (`mk/python.mk`) and production (container builds) use `uv sync --frozen`, guaranteeing bit-for-bit reproducibility from the committed `uv.lock`.
- **Dev/runtime separation**: Runtime deps live in `project.dependencies`; test-only tools (`pytest`, `jsonschema`, `fakeredis`) live in `[dependency-groups] dev` and are excluded from images via `--no-dev`.
- **Shared observability baseline**: All Python products import the same OpenTelemetry stack (`opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi/httpx/logging`, `opentelemetry-sdk`, `prometheus-client`) with aligned version ranges, ensuring consistent telemetry behavior across services.
- **Container strategy**: Product Dockerfiles only copy sources, `pyproject.toml`, `.python-version`, and `uv.lock`, then run `uv sync --frozen --no-dev`. The shared base image carries the env contract and non-root `app` user (uid 1000). The root `make build` tags all images with a coordinated `<semver>-<prefix>[-<profile>]-<gitsha>` tag written into `shared/platform-ops/gitops/dev-k8s/.images.env`.
- **Frontend isolation**: The web UI lives under `products/operator-portal/web-ui/app` with its own `package.json` + `package-lock.json`; it is built separately and pushed as `web-ui` alongside the Python services.

## Conventions and constraints

- **Constraint enforced by tooling**: `make verify` (the pre-commit/pre-push gate) runs `make validate-version`, which executes `validate_version.py` against the repo root; any drift between `VERSION` and product/package versions causes failure. This is the hard enforcement mechanism for version lockstep.
- **Constraint enforced by tooling**: `make sync` and per-product `make sync` both call `uv sync --frozen`; adding a dependency requires updating `pyproject.toml` and regenerating `uv.lock` so CI remains deterministic.
- **Convention observed across products**: Runtime dependencies use upper-bound major-version caps (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`) to allow patch/minor updates while blocking breaking changes.
- **Convention observed across products**: Dev dependencies are placed exclusively in `[dependency-groups] dev` and never in `project.dependencies`, keeping production images lean.
- **Convention observed across products**: Each service exposes entry points via `[project.scripts]` in `pyproject.toml` (e.g. `agent-service`, `platform-gateway`, `tool-gateway`) rather than ad-hoc CLI scripts.
- **No vendoring of third-party Python packages**: Dependencies are resolved from PyPI (or configured registries) at sync/build time; there is no `vendor/` directory for Python packages in this repository.