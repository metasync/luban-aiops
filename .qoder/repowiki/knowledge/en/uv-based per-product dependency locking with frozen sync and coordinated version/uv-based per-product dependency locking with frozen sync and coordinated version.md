---
kind: dependency_management
name: uv-based per-product dependency locking with frozen sync and coordinated version hygiene
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/agent-platform/.python-version
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## What system/approach is used

The repository manages dependencies exclusively through **Python uv** (the Astral toolchain) at the individual product level. Each Python service under `products/<name>/` declares its own `pyproject.toml` with explicit dependency ranges and a companion `uv.lock` lockfile. The root build orchestration (`Makefile`, `mk/python.mk`) drives every product via `uv sync --frozen`, which pins installs to the committed lockfile and rejects drift — there is no loose `pip install -r requirements.txt` path.

Container images are built from a shared base image in `shared/base-images/base-uv/Dockerfile` that installs a pinned `uv` version (default `0.12.1`) into `/usr/local/bin` and sets `UV_NO_SYNC=1` so runtime containers never re-resolve; the Python interpreter itself is resolved by uv from each product's `.python-version` file (e.g. `3.12`).

The frontend portal (`operator-portal/web-ui`) uses a standard Node.js toolchain (Vite, Vitest, TypeScript, antd) with its own package manager lockfile, but the backend side of this workspace is uniformly uv-driven.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` declare `[project]` dependencies with upper-major caps (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `cryptography>=43.0,<51.0`, `agentscope>=2.0.4,<3.0`, `agentscope-runtime>=1.1,<2.0`).
- Per-product lockfiles: `products/*/uv.lock` — committed, consumed by `uv sync --frozen`.
- Shared build fragments: `mk/python.mk` (`uv sync --frozen`, test runner), `mk/image.mk` (docker build/push/lint), `mk/defaults.mk`.
- Base image: `shared/base-images/base-uv/Dockerfile` pins `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, runs as non-root user `app`.
- Product interpreter pin: `products/*/.python-version` (e.g. `3.12`).
- Root orchestrator: `Makefile` enumerates `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and runs `sync`, `test`, `build`, `push` across all of them.
- Version coordination: `VERSION` at repo root is the single source of truth for the platform release number; `make validate-version` enforces lockstep between it and every product's declared version.
- Dependency hygiene policy document: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` codifies the adoption posture.

## Architecture and conventions

1. **Per-product isolation.** Each service owns its own dependency graph; there is no monorepo-wide `requirements.txt` or shared `pyproject`. Cross-cutting concerns (policy YAMLs, JSON schemas, scripts) live in `shared/shared-contracts/` and are invoked via `uv run python ...` from within a product directory so they resolve against that product's environment.

2. **Range-declared + lockfile-frozen workflow.** Dependencies use PEP 440 ranges with an upper-major cap to allow patch/minor updates while blocking breaking changes. The lockfile is the source of truth for reproducible installs; `uv sync --frozen` is the only supported install path in CI and local dev.

3. **Build-time resolution, not vendoring.** No `vendor/` directories or checked-in wheels exist. Resolution happens at image build time inside the base image using the pinned uv binary. Runtime containers set `UV_NO_SYNC=1` so they do not attempt network access on start.

4. **Shared base image strategy.** All backend services inherit from `luban-aiops/base-uv:<tag>` built from `shared/base-images/base-uv/Dockerfile`. The base image pins both uv and Python versions via build args, and the root `make base-images` target controls those defaults.

5. **Coordinated multi-product builds.** The root `Makefile` computes a single `IMAGE_TAG` derived from `VERSION` plus git SHA and writes it into `shared/platform-ops/gitops/dev-k8s/.images.env`; all product images share this tag so deployments stay consistent.

6. **Adoption posture.** The dependency-hygiene release note states the adopted policy: "latest stable only" — no alpha, beta, RC, or dev builds. OpenTelemetry instrumentation packages are the recorded exception because upstream ships them on a permanent `0.xb` channel and they stay paired with their locked SDK version.

7. **Dev vs prod separation.** Optional `[dependency-groups].dev` sections in each `pyproject.toml` list test-only packages (`pytest`, `jsonschema`, `fakeredis`); these are installed alongside production deps during `uv sync` but are not expected to ship to production images.

## Conventions and constraints

- **Upper-major caps on every dependency.** Every third-party dep in `pyproject.toml` specifies a `<X.0` ceiling (e.g. `fastapi>=0.115,<1.0`, `redis>=6.2,<7.0`, `elasticsearch>=8.0,<9.0`, `kubernetes>=30.0,<33.0`, `playwright>=1.48,<2.0`). This is enforced by code review rather than a linter; the release notes show deliberate decisions to keep Redis capped at `<7.0` and Elasticsearch at `<9.0` because deployed server versions constrain client compatibility.
- **Frozen installs everywhere.** `mk/python.mk` invokes `uv sync --frozen` for both `sync` and `test` targets; any lockfile drift fails the build. The same pattern applies to per-product Makefiles that include `../../mk/python.mk`.
- **Single Python version per product.** Each product pins its interpreter in `.python-version` (currently `3.12`), and the base image sets `UV_PYTHON=3.12` as the deterministic fallback.
- **No private registry configured at the workspace level.** There is no `.pypirc`, `PYPI_URL`, or `uv` config file in the tree; packages are resolved from PyPI (and ECR for the base image). Private registries would need to be injected via environment or uv configuration outside this repo.
- **Version lockstep enforced by CI gate.** `make validate-version` calls `shared/shared-contracts/scripts/validate_version.py` to verify that the root `VERSION` matches every product's declared version; this is part of the `verify` target, making it a pre-commit/pre-push requirement.
- **Secret vocabulary lockstep enforced similarly.** `make validate-secret-vocabulary` ensures the redaction vocabulary stays synchronized between `agent-platform` and `tool-gateway`.
- **Policy bundles are copied, not imported.** Canonical policies in `shared/shared-contracts/policies/` are duplicated into consumers via `make sync-policy`; this is a deployment-time contract, not a Python import dependency.
- **Frontend deprecation guard.** The portal's vitest suite intercepts `console.error`/`console.warn` and fails teardown on any `[antd: …] deprecated` warning, providing a zero-tolerance regression guard for UI dependency upgrades.