---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Sync and Managed Upgrade Policy
category: dependency_management
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/agent-platform/uv.lock
    - mk/python.mk
    - mk/image.mk
    - Makefile
    - docs/workspace/python-container-strategy.md
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
    - products/operator-portal/web-ui/app/package.json
    - shared/base-images/base-uv/Dockerfile
---

## What system/approach is used

The repository manages dependencies through two parallel, per-product package managers:

- **Python services** (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) use **uv** as the interpreter and package manager. Each product has its own `pyproject.toml` declaring runtime and dev dependency ranges, plus a committed `uv.lock` that pins every transitive resolution.
- **Operator portal web UI** (`products/operator-portal/web-ui/app`) uses **npm** via `package.json` + `package-lock.json`, built with Vite/Ts/React.

There are no vendored third-party packages in this repo; all dependencies are resolved from public registries (PyPI for Python, npm registry for the portal). No private PyPI or npm registry is configured — the lockfiles resolve exclusively from `https://pypi.org/simple`.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` (runtime deps, `[dependency-groups]` dev deps, `[build-system]` using `uv_build`).
- Per-product lockfiles: `products/*/uv.lock` — committed, frozen at build time.
- Shared Makefile fragments: `mk/python.mk` (defines `sync` → `uv sync --frozen`, `test` → `uv sync --frozen && uv run pytest`), `mk/image.mk` (container build/push/lint targets).
- Root orchestrator: `Makefile` lists `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and runs `make -C products/$p sync|test` across them.
- Container strategy doc: `docs/workspace/python-container-strategy.md` codifies the `uv sync --frozen --no-dev` image build pattern and the shared `luban-aiops/base-uv:al2023` base image.
- Portal manifest: `products/operator-portal/web-ui/app/package.json` declares React 19, antd 6.x, vite 8.x, vitest 4.x, TypeScript ~5.9.x.
- Dependency hygiene spec: `docs/specs/SPEC-042-dependency-hygiene/spec.md` records the adopted upgrade policy and adjudications.

## Architecture and conventions

### Python: per-product isolation with frozen locks

Each Python product owns its own dependency graph. The root Makefile does not aggregate `pyproject.toml` files — it delegates to each product's Makefile, which includes `../../mk/python.mk`. The `sync` target always runs `uv sync --frozen`, meaning the committed `uv.lock` is the single source of truth for installed versions. Dev-only dependencies live under `[dependency-groups].dev` and are excluded from production images by `--no-dev` in container builds.

### Version ranges vs pinned resolutions

`pyproject.toml` declares **ranges**, not exact pins (e.g. `fastapi>=0.115,<1.0`, `agentscope>=2.0.4,<3.0`, `cryptography>=43.0,<51.0`, `redis>=6.2,<7.0`, `elasticsearch>=8.0,<9.0`). The `uv.lock` then captures the latest stable version within those ranges at re-lock time. This is intentional: ranges keep the manifest readable while the lockfile guarantees determinism.

### Build-time determinism

Container images copy only `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, and `src/` into the image, then run `uv sync --frozen --no-dev`. The base image sets `UV_NO_SYNC=1` so the runtime does not re-resolve. The shared base image `shared/base-images/base-uv/Dockerfile` installs a pinned `uv` version via a versioned installer URL (`https://astral.sh/uv/${UV_VERSION}/install.sh`) and creates a non-root `app` user (uid 1000). All Python products build from `luban-aiops/base-uv:al2023`, built via `make base-images`.

### Frontend: managed refresh policy

The portal follows a separate but equally strict policy documented in SPEC-042: upgrades must be **latest stable only** (no alpha/beta/RC/dev), with every adoption recorded in the spec. Deprecation warnings in the test suite are treated as failures (R-2 guard), so new deprecations surface immediately rather than being allow-listed.

### Cross-cutting enforcement

- `make verify` aggregates `test`, overlay rendering, policy validation, version validation, and secret-vocabulary validation — it is the pre-commit/pre-push gate.
- `make validate-version` enforces that the root `VERSION` file matches every product's `pyproject.toml` version and metadata literals.
- `make validate-secret-vocabulary` enforces that secret-literal declarations stay in lockstep between agent-platform, tool-gateway, and skills-hub.
- Policy bundles are copied from a canonical location (`shared/shared-contracts/policies/policy-default.yaml`) into consumers via `make sync-policy`, ensuring a single source of truth.

## Conventions and constraints

Observed conventions (descriptive):

- Every Python product has a `pyproject.toml` with explicit upper bounds on major versions (e.g. `<3.0`, `<1.0`, `<7.0`, `<9.0`) to prevent accidental major bumps.
- Dependencies are split into runtime (`dependencies`) and development (`[dependency-groups].dev`) — only runtime deps ship in images.
- The workspace uses a single Python minor line enforced by `.python-version` files (root and per-product); the base image pins `UV_PYTHON` to align with it.
- Lockfiles are committed alongside code changes — release notes repeatedly reference "per-product `uv.lock` files refreshed" as part of delivery.
- Upgrades follow a managed process: SPEC-042 documents an "adopt set" table, records reasons for parked majors (redis client `<7.0`, elasticsearch client `<9.0`), and requires live checks for kernel-level bumps like agentscope.
- The OpenTelemetry instrumentation packages (`opentelemetry-instrumentation-fastapi/httpx/logging`) are explicitly exempted from the "stable only" rule because upstream publishes them on a permanent `0.xb` channel; they stay paired with their SDK versions.
- The portal's Node engine is pinned to `>=22.22.2` in `package.json` and matched by the Dockerfile's node base image.

Rules enforced by tooling or specs:

- `uv sync --frozen` is mandatory in both local `make sync` and container `RUN` steps — any drift between `pyproject.toml` and `uv.lock` fails the build.
- `make verify` must pass before push (documented as the pre-commit/pre-push gate in the root Makefile comments).
- `make validate-version` enforces lockstep between `VERSION`, every `pyproject.toml`, and metadata literals.
- SPEC-042 R-2 makes antd deprecation warnings a test failure, enforcing zero-tolerance deprecation accumulation in the portal.
- SPEC-042 R-5 mandates that every backend `uv.lock` carries the latest stable version its range allows, with no prerelease/beta/RC resolution.
- Image builds must use `--no-dev` and `UV_NO_SYNC=1` per the python-container-strategy document.