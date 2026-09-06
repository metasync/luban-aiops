---
kind: dependency_management
name: uv-based per-product Python dependency locking with stable-channel policy
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - shared/base-images/base-uv/Dockerfile
---

# Dependency Management in the Luban AIOps Platform

## System Overview

The repository uses **uv** (a fast Python package manager) as the single tool for declaring, resolving, and locking dependencies across every backend product. Each product under `products/` is an independent Python package with its own `pyproject.toml` and a committed `uv.lock` lockfile. There is no monorepo workspace file — each product manages its own dependency graph independently.

The build system is orchestrated by a root `Makefile` that delegates to per-product Makefiles, which include shared fragments from `mk/python.mk` and `mk/image.mk`. The shared `python.mk` defines `sync` and `test` targets that run `uv sync --frozen`, enforcing that builds use exactly the versions pinned in `uv.lock` rather than allowing resolution drift.

## Key Files

- Per-product manifests: `products/*/pyproject.toml` — declares runtime dependencies, dev dependency groups (`[dependency-groups] dev = [...]`), entry-point scripts (`[project.scripts]`), `requires-python = ">=3.11"`, and the build backend `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]`.
- Per-product lockfiles: `products/*/uv.lock` — frozen resolution of every transitive dependency with SHA256 hashes, sourced from `https://pypi.org/simple`.
- Shared build fragments: `mk/python.mk` (defines `uv sync --frozen` and test runner with OTel exporters disabled), `mk/image.mk` (container image build/push/lint), `mk/defaults.mk`.
- Root orchestration: `Makefile` lists `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and runs `make -C products/$$p sync` / `test` across all of them.
- Policy document: `docs/specs/SPEC-042-dependency-hygiene/spec.md` codifies the adopted version policy.

## Architecture and Conventions

### Version ranges and pinning strategy

Every runtime dependency is declared as a **bounded range** in `pyproject.toml` using `>=X.Y,<Z.0` style constraints (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `cryptography>=43.0,<51.0`, `redis>=6.2,<7.0`). The upper bound is always a major-version cap, ensuring that only semver-compatible updates are pulled in automatically. Dev-only packages live under `[dependency-groups] dev = [...]` and are not installed at runtime.

The actual resolved versions are captured in `uv.lock` and consumed via `uv sync --frozen`, so CI and production images install exactly the versions checked into source control. No floating installs occur after the initial lock.

### Stable-channel-only adoption policy

SPEC-042 formally adopts a **latest-stable-only** policy for both backend and portal dependencies: no alpha, beta, release candidate, or dev builds are adopted. The spec records explicit adjudications for edge cases:

- OpenTelemetry instrumentation packages (`opentelemetry-instrumentation-fastapi`, `-httpx`, `-logging`) stay on their permanent `0.xb` channel because upstream has no stable release line — this is recorded as a one-off exception.
- Redis client is capped `<7.0` and Elasticsearch client `<9.0` because those majors were API-removal releases and the deployed server versions do not require the newer clients.
- `agentscope` floats inside `>=2.0.4,<3.0` and is treated like a kernel bump — re-locking it carries the full `make verify` gate plus a live check of chat/HITL/mutating paths.

### Cross-cutting enforcement

- `make verify` aggregates `test`, overlay rendering, policy validation, scenario validation, and `validate-version` (which checks that the root `VERSION` file, product `pyproject.toml` versions, and portal versions stay in lockstep).
- `make sync` iterates over all `PYTHON_PRODUCTS` and runs each product's `uv sync --frozen`; any mismatch between `pyproject.toml` ranges and `uv.lock` fails the step.
- Container images are built from per-product Dockerfiles that layer on a shared `shared/base-images/base-uv` image; the base image pins the exact `UV_VERSION` and `PYTHON_VERSION` used to resolve the lock.

### Frontend dependencies

The operator portal lives under `products/operator-portal/web-ui/` and uses npm-style dependencies managed separately from the Python stack. SPEC-042 also governs its upgrade cadence (vite, vitest, TypeScript, React, antd) and enforces a zero-tolerance deprecation guard in the vitest suite.

## Conventions and Constraints

| Convention | Where enforced | Detail |
|---|---|---|
| One `pyproject.toml` + one `uv.lock` per product | Source tree structure | Every product under `products/` is self-contained; there is no shared workspace manifest. |
| Bounded major-version ranges | `pyproject.toml` `dependencies` | All runtime deps use `>=X,<Y` caps; new major bumps require explicit range edits. |
| Frozen installs in CI and images | `mk/python.mk` (`uv sync --frozen`) | Lockfiles must be regenerated before committing; `--frozen` rejects out-of-date locks. |
| Latest stable only | SPEC-042 design decisions | Prereleases/betas/RCs are rejected; documented exceptions (OTel instrumentation `0.xb`) are recorded. |
| Dev vs runtime separation | `[dependency-groups] dev` | Test-only packages are isolated and never installed in production images. |
| Coordinated versioning | Root `Makefile` `validate-version` target | Product versions and the root `VERSION` file must stay synchronized. |
| Base image reproducibility | `shared/base-images/base-uv/Dockerfile` + `mk/image.mk` | `UV_VERSION` and `PYTHON_VERSION` are pinned as build args. |

## Notable Dependencies

Common cross-product runtime dependencies include FastAPI, Pydantic, Uvicorn, PyJWT, cryptography, httpx, psycopg[binary], redis, prometheus-client, and the OpenTelemetry SDK/exporter/instrumentation packages. Product-specific dependencies include `agentscope` and `agentscope-runtime` (agent-platform), `playwright` and `elasticsearch` (tool-gateway), `kubernetes` (tool-gateway), and `apscheduler` (agent-platform).