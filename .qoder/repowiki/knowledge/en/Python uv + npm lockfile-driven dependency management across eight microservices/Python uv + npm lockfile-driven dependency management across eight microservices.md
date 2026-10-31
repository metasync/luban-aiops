---
kind: dependency_management
name: Python uv + npm lockfile-driven dependency management across eight microservices
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/defaults.mk
    - Makefile
    - .python-version
    - products/agent-platform/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/agent-platform/uv.lock
    - products/tool-gateway/uv.lock
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## Approach

Luban is a multi-product Python workspace (eight FastAPI services under `products/`) plus an operator-portal SPA. Dependency management is split by language:

- **Python**: `uv` as the package manager, resolver, and virtualenv tool. Each product ships its own `pyproject.toml` with `[project.dependencies]` ranges and a committed `uv.lock` lockfile. The build backend is `uv_build`.
- **Node.js**: only the operator portal (`products/operator-portal/web-ui/app/package.json`) uses npm-style `package.json`; no lockfile is committed in the tree shown, so resolution is delegated to the installed npm/pnpm/yarn version.
- **No vendoring** of third-party source code — dependencies are resolved at install/build time from PyPI / npm registries.
- **No private registry configuration** was found: there are no `uv.toml`, `UV_INDEX_URL`, `UV_EXTRA_INDEX_URL`, or `.pypirc` files anywhere in the repository.

## Key files

- `mk/python.mk` — shared `sync` / `test` targets that invoke `uv sync --frozen` and `uv run pytest` for every Python product.
- `Makefile` — root orchestrator; `make sync` iterates `PYTHON_PRODUCTS` and delegates to each product's Makefile; `make verify` includes contract, policy, overlay, dashboard, and portal gates.
- `mk/defaults.mk` — pins `BASE_UV_UV_VERSION = 0.12.1` and `BASE_UV_PYTHON_VERSION = 3.12` for the shared base image `shared/base-images/base-uv`.
- Root `.python-version` declares `3.12`.
- Per-product manifests: `products/*/pyproject.toml` (dependencies + dev groups) and `products/*/uv.lock` (committed lockfiles).
- Portal frontend: `products/operator-portal/web-ui/app/package.json` (React 19, antd 6, Vite 8, Vitest 4, TypeScript ~5.9).
- Release note documenting the hygiene policy: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md`.

## Architecture and conventions

### Python products

Each of the eight Python products (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`) follows the same shape:

- `requires-python = ">=3.11"` declared in `pyproject.toml`.
- Runtime dependencies use **major-version caps** (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=5.0,<7.0`, `cryptography>=43.0,<51.0`).
- Dev-only dependencies live in `[dependency-groups].dev` (pytest, fakeredis, jsonschema).
- Entry points are declared under `[project.scripts]`.
- Build backend is pinned: `uv_build>=0.8.14,<0.9.0`.
- A committed `uv.lock` pins exact transitive versions; `make sync` and `make test` both run `uv sync --frozen`, so CI and local installs resolve deterministically from the lockfile.

The shared base image `shared/base-images/base-uv` is built via `make base-images` and carries the pinned `uv` and `python` versions from `mk/defaults.mk`. All product Dockerfiles layer on top of this image.

### Node.js (operator portal)

The portal is a Vite + React 19 + antd 6 SPA. Dependencies are declared with caret ranges in `package.json`; the release note records the adopt set (antd 6.6.2, react/react-dom 19.2.x, vite 8.2.2, vitest 4.1.11, jsdom 30.0.1, typescript ~5.9.3). An `engines.node >= 22.22.2` constraint matches jsdom 30's floor. Deprecation of antd APIs is guarded by a vitest setup that intercepts `console.error`/`console.warn` and fails teardown on any `[antd: …] deprecated` warning.

### Cross-cutting orchestration

The root `Makefile` aggregates per-product routines. `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` enumerates every Python product; `IMAGE_PRODUCTS` adds `operator-portal`. `make sync` loops over `PYTHON_PRODUCTS` and runs each product's `sync` target (`uv sync --frozen`). `make verify` is the pre-commit/pre-push gate and includes contract validation, policy checks, kustomize overlay rendering, dashboard validation, portal tests, and integration proofs.

## Conventions and constraints

- **Frozen resolution**: `mk/python.mk` runs `uv sync --frozen`; the lockfile is the single source of truth for reproducible installs. This is enforced by the Makefile targets used by CI.
- **Major-version caps on runtime deps**: all Python packages declare upper bounds on their major version (e.g. `<1.0`, `<3.0`, `<7.0`, `<51.0`), preventing accidental major upgrades during normal refreshes.
- **Latest-stable adoption policy**: documented in the dependency-hygiene release note — "latest stable only — no alpha, beta, RC, or dev builds", with one recorded exception for OpenTelemetry instrumentation packages which ship on a permanent `0.xb` channel and stay paired with their locked SDK.
- **OpenTelemetry instrumentation pairing exception**: OTel instrumentation packages (`opentelemetry-instrumentation-fastapi`, `-httpx`, `-logging`) stay at `0.46b0` paired with `opentelemetry-sdk>=1.25,<2.0`; the release note explicitly calls this out as the sole exception to the latest-stable rule.
- **Redis and Elasticsearch caps parked below next major**: `redis>=5.0,<7.0` and `elasticsearch>=8.0,<9.0` are intentionally capped because the deployed Redis server is 7.2 (client 6.x compatible; majors 7/8 removed APIs) and no Elasticsearch server is deployed in dev.
- **Cryptography cap adjudicated up**: six products share `cryptography>=43.0,<51.0` after a call-site review confirmed only long-stable surfaces (`rsa.generate_private_key`, PEM/DER serialization, PKCS8/SubjectPublicKeyInfo) were used.
- **Shared base image pins**: `mk/defaults.mk` pins `BASE_UV_UV_VERSION = 0.12.1` and `BASE_UV_PYTHON_VERSION = 3.12`; these values are passed as `--build-arg` when building `shared/base-images/base-uv`.
- **Root Python version pin**: `.python-version = 3.12` and each product's `requires-python = ">=3.11"` together constrain the interpreter surface.
- **Portal deprecation guard**: the portal's vitest suite fails on any `[antd: …] deprecated` console warning, enforcing zero-tolerance migration off deprecated antd v6 APIs.
- **No private index configured**: grep across the repo finds no `uv.toml`, `UV_INDEX_URL`, `UV_EXTRA_INDEX_URL`, or similar private registry settings; dependencies resolve from public PyPI/npm registries.