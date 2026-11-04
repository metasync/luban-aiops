---
kind: dependency_management
name: uv-based Per-Product Dependency Locking with Latest-Stable Adoption Policy
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/defaults.mk
    - products/agent-platform/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
    - docs/agentic-aiops-platform/release-notes/2026-10-31-dependency-refresh-agentscope-2-0-11.md
---

# Dependency Management in the Luban Agentic AIOps Platform

## Approach

The workspace is a multi-product Python monorepo (nine services plus an operator-portal SPA). Each product owns its own `pyproject.toml` and a vendored `uv.lock`, resolved through **uv** — not pip, Poetry, or Pipenv. The root `Makefile` delegates dependency installation to each product via `make sync`, which invokes `mk/python.mk`'s `sync` target that runs `uv sync --frozen`. Tests also run under `uv run pytest`, so every developer and CI step resolves against the committed lockfile.

The shared base image (`shared/base-images/base-uv/Dockerfile`) is built from `mk/defaults.mk`, which pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; the root Makefile passes these as `--build-arg UV_VERSION` / `PYTHON_VERSION` when building the base image. This makes the uv binary itself reproducible across environments.

## Key Files

- `mk/python.mk` — shared `sync` and `test` targets; enforces `uv sync --frozen`.
- `mk/defaults.mk` — single source of truth for `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION`.
- `products/<product>/pyproject.toml` — per-product dependency declarations (e.g. `agent-platform/pyproject.toml`, `tool-gateway/pyproject.toml`).
- `products/<product>/uv.lock` — per-product lockfiles (one per Python product).
- `shared/base-images/base-uv/Dockerfile` — reproducible uv+python base image.
- `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` — codifies the adoption posture.
- `docs/agentic-aiops-platform/release-notes/2026-10-31-dependency-refresh-agentscope-2-0-11.md` — example of a routine re-lock release note.

## Architecture and Conventions

### Declaration style
Dependencies are declared as PEP 508 version ranges in `[project].dependencies`, using caret-style upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=5.0,<7.0`). Dev-only packages live in `[dependency-groups].dev` (pytest, fakeredis, jsonschema). The build backend is pinned to `uv_build>=0.8.14,<0.9.0` via `[build-system]`.

### Version policy
The adoption posture documented in SPEC-042's release notes is **"latest stable only"**: bumps land at the latest stable release inside the existing range; alpha, beta, RC, and dev builds are excluded. The sole recorded exception is the OpenTelemetry instrumentation packages, which ship on a permanent `0.xb` channel and stay paired with their locked SDK (e.g. `opentelemetry-instrumentation-*>=0.46b0` with `opentelemetry-sdk>=1.25,<2.0`).

### Range caps and deliberate parking
Major-version caps are intentional:
- Redis client `<7.0` because the deployed server is 7.2 and client majors 7/8 were API-removal releases.
- Elasticsearch client `<9.0` because no ES server is deployed and the client major follows the server major.
- Kubernetes client `<33.0` (locked 32.0.1) in tool-gateway.
- `cryptography <51.0` (locked 50.0.1); 51.0.0 was unreleased `-dev1` at the time of the last refresh.
These decisions are explicitly justified in the release notes rather than being ad hoc.

### Cross-product harmonization
Shared dependencies are kept in lockstep across products: PyJWT was harmonized from mixed 2.13.0/2.15.1 to 2.15.1 across all eight backend products in the agentscope 2.0.11 refresh. The root `Makefile` also orchestrates other cross-cutting validations (`validate-version`, `validate-secret-vocabulary`, `validate-password-policy`) that enforce contract-level lockstep between products and shared contracts.

### Operator portal (non-Python)
The operator portal under `products/operator-portal/web-ui/` is a TypeScript/Vite SPA managed by npm/pnpm (not uv). Its dependency hygiene is handled separately (antd 6 migration, React 19 upgrade, vitest deprecation guard), but it is not part of the uv lockfile system.

## Conventions and Constraints

- **Frozen resolution everywhere.** `mk/python.mk` runs `uv sync --frozen` for both `sync` and `test`; there is no path in the standard workflow that allows non-frozen resolution.
- **One manifest + one lockfile per Python product.** Dependencies are declared in `products/<name>/pyproject.toml`; versions are pinned in the co-located `uv.lock`. There are no top-level `requirements.txt`, `Pipfile`, or Poetry files.
- **Latest-stable adoption policy.** As stated in the release notes for SPEC-042: "the adoption policy throughout is latest stable only — no alpha, beta, RC, or dev builds," with the OpenTelemetry instrumentation packages as the only documented exception.
- **Upper-bound major caps on volatile clients.** Redis `<7.0`, Elasticsearch `<9.0`, Kubernetes `<33.0`, cryptography `<51.0` are deliberately parked and justified in release notes; they are not accidental omissions.
- **Reproducible base uv binary.** `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; the root Makefile passes them into `shared/base-images/base-uv/Dockerfile` so the uv executable used in images matches the one used locally.
- **Dependency changes require a release note.** Routine re-locks are documented as standalone release notes (e.g. `2026-08-28-dependency-hygiene.md`, `2026-10-31-dependency-refresh-agentscope-2-0-11.md`) that enumerate every bumped package, product affected, and verification results.
- **No private registry configuration observed.** No `PYPI_URL`, `UV_INDEX_URL`, `pip.conf`, `setup.cfg`, or `~/.config/uv/uv.toml` patterns appear in the checked-in code; dependencies resolve from the public index.