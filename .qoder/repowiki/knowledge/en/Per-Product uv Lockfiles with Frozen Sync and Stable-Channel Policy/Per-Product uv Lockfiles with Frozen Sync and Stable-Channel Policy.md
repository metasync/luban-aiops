---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Sync and Stable-Channel Policy
category: dependency_management
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/platform-gateway/uv.lock
    - mk/python.mk
    - products/agent-platform/Dockerfile
    - .python-version
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
    - shared/shared-sdk/README.md
---

## What system/approach is used

The repository manages Python dependencies per product using **uv** (a fast Python package manager) with **PEP 621 `pyproject.toml` manifests** and a **per-product `uv.lock` lockfile**. Each product under `products/` declares its own dependency ranges, dev-only groups, and entry-point scripts. The build and CI use `uv sync --frozen` to enforce that the installed tree exactly matches the committed lockfile — no ad-hoc resolution at install time.

There is no monorepo workspace file; each product is an independent uv project resolved against PyPI (`https://pypi.org/simple`). No vendored third-party source trees or private registry configuration were found in the repo.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` (e.g. `products/agent-platform/pyproject.toml`, `products/platform-gateway/pyproject.toml`) declare `name`, `version`, `requires-python = ">=3.11"`, runtime `dependencies`, `[dependency-groups].dev`, and `[build-system]` pinning `uv_build>=0.8.14,<0.9.0` as the build backend.
- Per-product lockfiles: `products/*/uv.lock` record the exact resolved versions, hashes, and sources for every transitive dependency.
- Shared Make targets: `mk/python.mk` defines `sync` (`uv sync --frozen`) and `test` (re-syncs frozen, then runs `uv run pytest` with OTLP exporters disabled so tracing tests stay quiet).
- Docker images: each product's `Dockerfile` copies `.python-version`, `pyproject.toml`, `uv.lock`, and `src/`, then runs `uv sync --frozen --no-dev` to bake a deterministic image.
- Root-level `.python-version` pins the interpreter version consumed by all products.
- Spec governing policy: `docs/specs/SPEC-042-dependency-hygiene/spec.md` codifies the adoption rules.

## Architecture and conventions

- **Range-based versioning with locked resolutions.** Runtime dependencies are declared as semver-style ranges (e.g. `fastapi>=0.115,<1.0`, `agentscope>=2.0.4,<3.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`, `cryptography>=43.0,<51.0`). Dev dependencies live in `[dependency-groups].dev` (pytest, jsonschema, fakeredis) and are excluded from production images via `--no-dev`.
- **Frozen installs everywhere.** Both development (`make sync`, `make test`) and container builds invoke `uv sync --frozen`, which rejects any lockfile drift. This makes the committed `uv.lock` the single source of truth for what actually ships.
- **Stable-channel only policy.** SPEC-042 mandates "latest stable versions only — no betas, no RCs" across both backend and portal surfaces. The spec records one exception: OpenTelemetry instrumentation packages on their permanent `0.xb` channel may be adopted when paired with a stable SDK, but the portal intentionally stays on its existing pairing rather than chasing newer `0.xb` releases.
- **Adjudicated caps for risky majors.** Major bumps that could break deployed server contracts are explicitly parked with recorded reasons: Redis client capped `<7.0` because the deployed server is Redis 7.2 and clients 7/8 removed APIs; Elasticsearch client capped `<9.0` because the client major follows the server major and no ES server is deployed in dev. These caps are reviewed and raised only when the spec adjudicates them (e.g. cryptography was raised to `>=43.0,<51.0` after reviewing JWT/signing call sites).
- **Kernel dependency treated specially.** `agentscope` (the AgentScope kernel per ADR-0002) floats inside `>=2.0.4,<3.0`; bumping it requires not just unit tests but a full `make verify` plus a live check of chat, HITL confirmation, and mutating paths.
- **No shared Python package yet.** `shared/shared-sdk/README.md` describes a future shared SDK (service clients, auth helpers, tracing helpers) but currently contains only a placeholder README; cross-product reuse is expressed through shared JSON schemas in `shared/shared-contracts/schemas/` rather than a Python package import today.
- **Frontend toolchain (portal).** The operator portal uses npm/vite/vitest with `package.json` + `package-lock.json` and follows the same latest-stable-only policy documented in SPEC-042 (TypeScript 5.9.x, Vite 8.x, React 19.x, jsdom 30.x). It is separate from the Python uv workflow.

## Conventions and constraints

- Every product must keep its `uv.lock` committed and in sync with `pyproject.toml`; `uv sync --frozen` enforces this at build/test time.
- New dependencies must be added as ranges (not absolute pins) in `pyproject.toml`; the exact version is captured by re-running `uv lock`.
- Development-only tools belong in `[dependency-groups].dev` so they are never baked into production images.
- Upgrades follow SPEC-042: adopt the latest stable release within the declared range, document any cap decisions, and avoid prereleases/betas/RCs.
- Major version changes to server-facing clients (Redis, Elasticsearch) require explicit justification and are parked until the deployed server supports them.
- The agentscope kernel bump triggers additional verification beyond unit tests (full verify gate + live path checks).
- Container images are built reproducibly by copying only the lockfile and source, then running `uv sync --frozen --no-dev` — no network access at runtime and no mutable environment variables needed for dependency resolution.