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
    - products/agent-platform/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## Approach

The Luban AIOps Platform is a Python + TypeScript monorepo that manages dependencies through two parallel, per-product dependency manifests:

- **Python products** (`products/agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`) use **uv** as the package manager. Each product ships its own `pyproject.toml` (PEP 621) declaring runtime `dependencies`, optional `[dependency-groups].dev` groups, and a `[build-system]` pinning `uv_build>=0.8.14,<0.9.0`. The corresponding `uv.lock` file in each product directory pins every transitive resolution.
- **Operator portal** (`products/operator-portal/web-ui/app/package.json`) uses **npm** with pinned caret ranges for React 19 / antd 6 / Vite 8 / Vitest 4.

There is no workspace-level lockfile; each product resolves independently against PyPI and npm registries. No private registry or vendored third-party code is present — all packages are pulled from public indexes.

## Key Files

- Root orchestration: `Makefile` (aggregates per-product `sync`, `test`, `build`, `verify`), `mk/python.mk` (shared `uv sync --frozen` / `uv run pytest` targets), `mk/defaults.mk` (pins `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`).
- Per-product manifests: `products/*/pyproject.toml` plus matching `products/*/uv.lock`.
- Frontend manifest: `products/operator-portal/web-ui/app/package.json`.
- Policy document: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` (SPEC-042).

## Architecture and Conventions

1. **Frozen installs everywhere.** `mk/python.mk` runs `uv sync --frozen`; the root `Makefile` delegates to it for every Python product. This means the committed `uv.lock` is authoritative — developers cannot drift versions locally without committing an updated lockfile.
2. **Per-product isolation.** Each service owns its own `pyproject.toml` and `uv.lock`; there is no shared Python package consumed across products. Cross-product coupling goes through JSON schemas and policy bundles under `shared/shared-contracts/`, not through shared Python imports.
3. **Version range policy.** Runtime dependencies use broad major-version caps (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=5.0/<6.2,<7.0`, `cryptography>=43.0,<51.0`) so patch/minor updates flow automatically while breaking majors are blocked. Dev dependencies live in `[dependency-groups].dev` and are separated from runtime.
4. **Build-backend pinning.** Every `pyproject.toml` declares `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"`, ensuring reproducible sdist/wheel builds.
5. **Base image reproducibility.** `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; the shared base image `shared/base-images/base-uv/Dockerfile` is built with these exact versions, so container images never pull arbitrary Python/uv versions at build time.
6. **Frontend parity.** The operator portal's `package.json` pins Node `engines.node >=22.22.2` and uses caret ranges for libraries; the release note for SPEC-042 documents the adopt set (React 19, antd 6.6.2, Vite 8.2.2, Vitest 4.1.11, jsdom 30.0.1, TypeScript ~5.9.3).
7. **OTel instrumentation exception.** OpenTelemetry instrumentation packages ship on a permanent `0.xb` channel and stay at their locked SDK pairing (SDK 1.44.0 / instrumentation 0.65b0); this is the single recorded exception to the "latest stable only" posture documented in the dependency-hygiene release note.

## Conventions and Enforced Rules

- **Rule:** Dependency refreshes must stay inside declared version ranges and target "latest stable only" — no alpha, beta, RC, or dev builds. Enforced by the adoption policy stated in `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` (SPEC-042) and the frozen-lock workflow.
- **Rule:** All Python dependency changes go through `make verify`, which runs every product suite under `uv sync --frozen`; any lockfile drift causes `uv sync --frozen` to fail. Enforced by `mk/python.mk` and the root `Makefile`'s `verify` target.
- **Rule:** The base image's Python and uv versions are pinned centrally in `mk/defaults.mk` (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`) and referenced by `shared/base-images/base-uv/Dockerfile`; changing them requires rebuilding the base image before product images.
- **Convention:** Runtime dependencies use `<major>.x` caps (e.g. `<1.0`, `<3.0`, `<7.0`, `<51.0`) to allow minor/patch upgrades while blocking incompatible majors.
- **Convention:** Test-only packages are placed in `[dependency-groups].dev` rather than top-level `dependencies`, keeping production wheels lean.
- **Convention:** Major-version cap exceptions are explicitly justified in release notes (e.g. `cryptography` cap raised from `<45.0` to `<51.0` after call-site review of `rsa.generate_private_key` usage; Redis/Elasticsearch client majors kept parked because deployed server versions constrain compatibility).
- **Convention:** The operator portal treats deprecation warnings as failures — the vitest setup intercepts `console.error`/`console.warn` and fails teardown on any `[antd: …] deprecated` warning, providing a regression guard against future upstream deprecations.