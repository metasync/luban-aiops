---
kind: dependency_management
name: Per-Product uv Lockfiles with Centralized Version and Build Orchestration
category: dependency_management
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/platform-gateway/uv.lock
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/package-lock.json
    - shared/shared-contracts/scripts/validate_version.py
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - Makefile
    - shared/base-images/base-uv/Dockerfile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## System Overview

The Luban AIOps workspace manages dependencies across eight Python services and one React/TypeScript portal using a **per-product lockfile strategy** driven by `uv` (Python) and `npm` (portal), orchestrated from a root Makefile that enforces version lockstep and frozen resolution.

### Python dependency management

Each product under `products/<name>/` declares its own `pyproject.toml` with explicit dependency ranges and a co-located `uv.lock` pinning every transitive to a specific version and hash. The lockfiles resolve against the public PyPI registry (`https://pypi.org/simple`) — no private index or vendored packages are used. Dependency ranges follow a consistent pattern: major-version caps for fast-moving libraries (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`, `cryptography>=43.0,<51.0`) while keeping critical runtime kernels like `agentscope>=2.0.4,<3.0` and `agentscope-runtime>=1.1,<2.0` pinned to their own major boundaries. OpenTelemetry instrumentation packages intentionally stay on the upstream `0.xb` channel (`opentelemetry-instrumentation-*>=0.46b0`) as documented in SPEC-042's release notes, which is the only recorded exception to the "latest stable only" posture.

Dev-only tooling is isolated via PEP 735 `dependency-groups`: each product groups `pytest`, `jsonschema`, `fakeredis` etc. under `[dependency-groups].dev` rather than mixing them into runtime requirements.

Resolution is enforced as **frozen**: the shared `mk/python.mk` fragment runs `uv sync --frozen` for both `sync` and `test` targets, so any drift between `pyproject.toml` ranges and `uv.lock` fails the build. The root Makefile exposes `make sync` and `make test` that iterate over all eight Python products (`PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`).

### Frontend dependency management

The operator portal lives under `products/operator-portal/web-ui/app/` with a standard `package.json` + `package-lock.json` setup. Dependencies use caret ranges (`^6.6.2` for antd, `^19.2.8` for react/react-dom, `~5.9.3` for typescript). Node engine is pinned to `>=22.22.2` in `engines.node`. Tests run via vitest; deprecation warnings from antd are treated as failures through a vitest teardown guard that intercepts `console.error`/`console.warn` and fails the suite on any `[antd: …] deprecated` message — this is the enforcement mechanism for the frontend's deprecation policy.

### Version lockstep and single source of truth

The root `VERSION` file is the single source of truth for the platform semver. A dedicated script `shared/shared-contracts/scripts/validate_version.py` is invoked by `make validate-version` (part of `make verify`) and asserts that:
- Every `products/*/pyproject.toml` `[project] version` matches `VERSION`
- Every `products/*/src/*/metadata.py` `SERVICE_VERSION = ...` matches `VERSION`
- Any `__version__` in package roots matches `VERSION`
- The portal's Vite build wiring reads `VERSION` at build time (regex checks for the URL import and `__PLATFORM_VERSION__` define)

Drift causes the verification gate to fail.

### Build and image orchestration

Shared build fragments live in `mk/`:
- `mk/defaults.mk` pins reproducible defaults including `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12` for the shared base image `shared/base-images/base-uv/Dockerfile`.
- `mk/image.mk` provides `build`/`push`/`lint` targets that tag images as `luban-aiops/<name>:<tag>` and optionally re-tag/push to a configured `REGISTRY`.
- The root `Makefile` computes a coordinated `IMAGE_TAG` from `VERSION` + git SHA (+ `-dirty-<timestamp>` for dirty trees) and writes `.images.env` so all products ship the same tag per release.

### Update cadence and governance

SPEC-042 and its release note (`docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md`) codify the update posture: **"latest stable only"** — no alpha, beta, RC, or dev builds — applied uniformly across backend and portal. Updates are delivered as dependency-only releases (no route/action/event changes) and verified by running all product suites under `uv sync --frozen` plus the full `make verify` gate (tests, kustomize overlay rendering, policy validation, scenario validation, version lockstep).

## Key Files

- `products/*/pyproject.toml` — per-product dependency declarations and ranges
- `products/*/uv.lock` — fully resolved, hashed lockfiles for each Python product
- `products/operator-portal/web-ui/app/package.json` — portal frontend dependencies
- `products/operator-portal/web-ui/app/package-lock.json` — locked frontend tree
- `shared/shared-contracts/scripts/validate_version.py` — enforces VERSION lockstep
- `mk/python.mk` — `uv sync --frozen` and pytest invocation
- `mk/image.mk` — shared Docker image build/push targets
- `mk/defaults.mk` — pinned base image versions (`BASE_UV_*`)
- `Makefile` — root orchestration (`sync`, `verify`, `build`, `validate-version`)
- `shared/base-images/base-uv/Dockerfile` — pinned uv/python base image
- `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` — published update posture and adopt set

## Conventions and Constraints

- Every Python product has its own `pyproject.toml` + `uv.lock`; there is no monorepo-wide `requirements.txt` or shared `pyproject` for third-party deps.
- All Python dependencies resolve from `https://pypi.org/simple`; no private registries or vendored wheels are present.
- Runtime dependencies declare upper-major-version caps (e.g. `<1.0`, `<3.0`, `<7.0`) to allow patch/minor refreshes without breaking CI.
- Dev dependencies are isolated in `[dependency-groups].dev` and never mixed into runtime `dependencies`.
- `uv sync --frozen` is mandatory for install/test; non-frozen installs are not part of the build surface.
- The root `VERSION` file must match every product's declared version; `make validate-version` enforces this at the verification gate.
- Container images for all Python products are tagged with the same coordinated `IMAGE_TAG` derived from `VERSION` + git SHA.
- Frontend updates follow a "latest stable only" posture enforced by a vitest teardown guard that fails on antd deprecation warnings.
- OpenTelemetry instrumentation packages are explicitly exempted from the latest-stable rule because upstream ships them on a permanent `0.xb` channel.