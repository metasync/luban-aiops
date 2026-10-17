---
kind: dependency_management
name: Dependency Management via uv Lockfiles and Per-Product pyproject.toml
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/defaults.mk
    - .python-version
    - products/agent-platform/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/execution-runtime/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
    - docs/agentic-aiops-platform/release-notes/2026-09-27-dependency-refresh-agentscope-2-0-8.md
---

## Approach

The Luban workspace is a Python-first monorepo (nine product services plus an operator-portal SPA) that manages dependencies through:

- **uv** as the sole Python package manager, invoked from `mk/python.mk` (`uv sync --frozen`, `uv run pytest`) and from each product's `Makefile`.
- One `pyproject.toml` per Python product under `products/<name>/`, declaring runtime dependencies with caret ranges and a corresponding `uv.lock` lockfile committed in-tree.
- A single Node.js project for the operator portal SPA under `products/operator-portal/web-ui/app/package.json`, using npm/yarn/pnpm (the lockfile is not present in the tree; `node_modules/` is committed).
- Shared base image `shared/base-images/base-uv/Dockerfile` built from `mk/defaults.mk` with pinned `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`, consumed by every product Dockerfile.

No private PyPI registry, no `UV_DEFAULT_INDEX`, no `index-url` / `extra-index-url`, and no vendored Python packages were found — all third-party packages resolve from the public index.

## Key Files

- Root orchestration: `Makefile` (aggregates `sync`, `test`, `build`, `verify` across products), `mk/python.mk` (shared `sync`/`test` targets), `mk/defaults.mk` (pinned `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`).
- Per-product manifests: `products/*/pyproject.toml` + `products/*/uv.lock` (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway).
- Runtime pin: `.python-version` declares `3.12` at the repo root.
- Portal frontend: `products/operator-portal/web-ui/app/package.json` (React 19, antd 6, Vite 8, Vitest 4, TypeScript ~5.9).
- Policy documents: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` (SPEC-042 adoption posture), `docs/agentic-aiops-platform/release-notes/2026-09-27-dependency-refresh-agentscope-2-0-8.md` (routine re-lock example).

## Architecture and Conventions

### Python dependency ranges
Each `pyproject.toml` uses caret-ranged constraints on major versions, e.g. `agentscope>=2.0.4,<3.0`, `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`. The `<major` caps are deliberate compatibility boundaries documented in release notes (e.g. Redis client `<7.0` because deployed server is 7.2 and client majors 7/8 removed APIs; Elasticsearch client `<9.0` following the deployed server major; Kubernetes client `<33.0` in tool-gateway).

### Locked resolution
`mk/python.mk` runs `uv sync --frozen`, which refuses to install anything not already recorded in `uv.lock`. The root `Makefile` delegates `sync`/`test` to each product Makefile, so CI and local dev both use frozen locks.

### Build backend
Every Python product declares `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"` (observed in agent-platform; consistent across products).

### Frontend dependencies
The portal SPA pins React 19, antd 6, Vite 8, Vitest 4, jsdom 30, and TypeScript ~5.9.3 in `package.json`; `engines.node` is set to `>=22.22.2` (jsdom 30 floor). The SPA is not a uv product — it has its own `Makefile` targets `test` and `web-build` invoked from the root `make portal-test`.

### Base image strategy
`mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; `base-images` target builds `luban-aiops/base-uv:<tag>` from `shared/base-images/base-uv/Dockerfile`, and product images layer on top of this shared base.

### Adoption policy
Per SPEC-042 and the release notes: **latest stable only** — no alpha, beta, RC, or dev builds. The OpenTelemetry instrumentation packages are the single recorded exception, staying on their permanent `0.xb` channel paired with the locked SDK. New AgentScope capabilities are adopted only after passing the four-point adoption gate documented in `docs/workspace/agentscope-utilization-audit.md`.

### Version coordination
The root `VERSION` file is the single source of truth for the platform release version; `make validate-version` enforces lockstep between `VERSION`, every product's `pyproject.toml` version, and the portal version via `shared/shared-contracts/scripts/validate_version.py`.

## Conventions and Constraints

- **Frozen installs**: `uv sync --frozen` is used in both `sync` and `test` targets in `mk/python.mk`; any drift between `pyproject.toml` and `uv.lock` fails the build.
- **Major-version caps**: Python dependencies declare upper bounds on the next major (`<3.0`, `<1.0`, `<4.0`, etc.) to prevent automatic major upgrades; specific caps (Redis `<7.0`, Elasticsearch `<9.0`, Kubernetes `<33.0`) are justified in release notes.
- **Latest-stable-only adoption**: Stated explicitly in SPEC-042 release notes — pre-release channels (alpha/beta/RC/dev) are excluded except for OTel instrumentation's permanent `0.xb` channel.
- **Python version pinning**: `.python-version` = `3.12`; `mk/defaults.mk` pins `BASE_UV_PYTHON_VERSION=3.12`; product `pyproject.toml`s declare `requires-python = ">=3.11"`.
- **Node engine pinning**: `package.json` `engines.node` = `>=22.22.2`.
- **Build tool pinning**: `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1`; product `pyproject.toml`s pin `uv_build>=0.8.14,<0.9.0`.
- **No private registries**: No `uv.toml`, no `PYPI_*` environment variables, no `index-url`/`extra-index-url` configuration was found — all packages resolve from the public index.
- **Lockstep validation**: `make validate-version` enforces that the root `VERSION`, all product versions, and the portal version stay synchronized.
- **Portal deprecation guard**: The vitest setup intercepts `console.error`/`console.warn` and fails the suite on any `[antd: …] deprecated` warning (SPEC-042 R-2), preventing future antd API drift.