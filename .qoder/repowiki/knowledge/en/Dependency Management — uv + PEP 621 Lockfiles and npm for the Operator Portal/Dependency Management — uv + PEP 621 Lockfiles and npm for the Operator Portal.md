---
kind: dependency_management
name: Dependency Management — uv + PEP 621 Lockfiles and npm for the Operator Portal
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

# Dependency Management

## Approach

The Luban workspace is a multi-product Python monorepo plus one operator SPA. Dependency management is split by language:

- **Python products** (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) use **uv** as both the package manager and build backend (`uv_build`), with per-product `pyproject.toml` declarations and a committed `uv.lock` lockfile.
- **Operator portal** (`products/operator-portal/web-ui/app`) uses **npm** / **Vite** / **Vitest**, declared in `package.json`; there is no `package-lock.json` visible in the tree, so versions are resolved from the caret ranges at install time.

There is no vendoring of third-party source code; all dependencies are resolved from PyPI (and npm registry). No private registries or `GOFLAGS`/`GOPRIVATE`-style overrides appear in the Makefiles or Dockerfiles.

## Key Files

- Per-product manifests: `products/*/pyproject.toml`, `products/*/uv.lock`
- Root-level coordination: `Makefile`, `mk/python.mk`, `mk/defaults.mk`
- Node manifest: `products/operator-portal/web-ui/app/package.json`
- Policy document: `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` (SPEC-042)
- Base image defaults: `shared/base-images/base-uv/Dockerfile`, `mk/defaults.mk` (pins `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`)

## Architecture and Conventions

### Python dependency model

Each product's `pyproject.toml` follows PEP 621:

- `[project]` declares runtime `dependencies` with upper-bound major-version caps (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=5.0,<7.0`).
- `[dependency-groups.dev]` holds test-only packages (`pytest`, `fakeredis`, `jsonschema`).
- `[build-system]` pins `uv_build>=0.8.14,<0.9.0` as the build backend.
- A committed `uv.lock` pins exact transitive resolutions.
- `.python-version` files co-locate with each product to pin the interpreter (e.g. `products/agent-platform/.python-version`).

The shared fragment `mk/python.mk` defines the canonical targets:

```make
sync: ## Install/refresh this product's dependencies (frozen lock)
	uv sync --frozen

test: ## Run this product's test suite
	uv sync --frozen
	OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none \
		uv run pytest
```

The root `Makefile` aggregates these across all eight Python products via `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`, so `make sync` and `make test` operate on every product uniformly.

### Build reproducibility

- `uv sync --frozen` is used everywhere (both `mk/python.mk` and integration tests under `make audit-contract-test`, `make delegated-custody-test`, etc.), forcing resolution against `uv.lock` only — no network drift during CI.
- The base image `shared/base-images/base-uv` is built with pinned `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12` from `mk/defaults.mk`, and the root `make base-images` target passes them as `--build-arg`s.
- Image tags are computed deterministically from `VERSION` plus git SHA/dirty timestamp; the same tag is propagated to all product images via the coordinated `IMAGE_TAG` variable.

### Frontend dependency model

The operator portal's `package.json` declares:

- Runtime deps: `antd ^6.6.2`, `react ^19.2.8`, `react-dom ^19.2.8`, `@ant-design/x ^2.9.0`, `dayjs ^1.11.23`, `@ant-design/icons ^6.0.0`.
- Dev deps: `typescript ~5.9.3`, `vite ^8.2.2`, `vitest ^4.1.11`, `@vitejs/plugin-react ^6.1.1`, `jsdom ^30.0.1`, `@testing-library/react ^16.3.3`, `@types/*`.
- `engines.node >=22.22.2`.

The release note for SPEC-042 documents the adopt set (React 19, antd deprecation fixes, jsdom 30, TypeScript 5.9.x parked below 7.x native tsgo).

### Version policy

The SPEC-042 release note codifies the adopted posture:

- **Latest stable only** for upgrades — no alpha, beta, RC, or dev builds.
- OpenTelemetry instrumentation packages stay on their permanent `0.xb` channel paired with the locked SDK version (the single recorded exception to latest-stable).
- Redis client stays `<7.0` because the deployed server is 7.2 and client majors 7/8 were API-removal releases; Elasticsearch stays `<9.0` because no ES server is deployed in dev.
- Cryptography caps were adjudicated up from `<45.0` to `<51.0` after call-site review found only long-stable surfaces unchanged through 50.x.

### Cross-cutting verification

`make verify` is the pre-commit/pre-push gate and includes product test suites, GitOps overlay checks, dashboard validation, policy validation, secret-vocabulary validation, password-policy validation, portal Vitest + production build, and several integration proofs. Dependency regressions surface here because `test` runs `uv sync --frozen` against the committed lockfile.

## Conventions and Constraints

Observed conventions (descriptive):

- Every Python product has its own `pyproject.toml` + `uv.lock` pair; there is no workspace-level `pyproject.toml` aggregating dependencies.
- Runtime dependencies use broad lower bounds with hard upper bounds on the next major version (e.g. `<1.0`, `<3.0`, `<7.0`).
- Test-only dependencies live in `[dependency-groups.dev]` rather than top-level `dependencies`.
- `uv sync --frozen` is the universal invocation pattern — never bare `pip install` or `uv pip install` without `--frozen`.
- The base image pins `uv` and `python` versions centrally in `mk/defaults.mk` and propagates them into the `base-uv` Docker image.
- The operator portal pins `node >=22.22.2` in `engines` and uses caret ranges in `package.json`.
- Upgrades go through SPEC-driven delivery (SPEC-042) with a documented adopt set and post-release verification in the release notes.

Enforced rules (source cited):

- **Lockfile-frozen installs**: `mk/python.mk` calls `uv sync --frozen` for both `sync` and `test`; root `Makefile` integration targets also pass `--frozen` to `uv run`. This enforces that CI and local development resolve against the committed `uv.lock`.
- **Build backend pinned**: every Python product's `pyproject.toml` sets `build-backend = "uv_build"` with `uv_build>=0.8.14,<0.9.0` in `[build-system].requires`, preventing arbitrary setuptools/pip backends.
- **Base image versions pinned**: `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; the root `make base-images` target passes them as Docker build args, so the shared base image cannot drift to an unpinned version.
- **Node engine floor enforced**: `products/operator-portal/web-ui/app/package.json` declares `"engines": { "node": ">=22.22.2" }`, matching the jsdom 30 requirement documented in SPEC-042.
- **Version lockstep**: `make validate-version` delegates to `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file, product versions, and portal version stay in lockstep (root `Makefile` line 178).
- **No behavior change on dep bumps**: SPEC-042 release notes state the v0.24.0 release is "dependency-only — no new routes, actions, event types, or execution paths", and the verification gate requires all product suites green under frozen sync before merge.