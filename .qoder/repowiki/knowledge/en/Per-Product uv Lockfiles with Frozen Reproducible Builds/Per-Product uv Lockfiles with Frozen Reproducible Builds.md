---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Reproducible Builds
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - Makefile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - shared/base-images/base-uv/Dockerfile
---

## Approach

The Luban workspace uses **uv** (the fast Python package manager) as the single dependency tool across all nine Python products. There is no `requirements.txt`, no Poetry, no pipenv, and no vendored third-party code. Each product under `products/<name>/` declares its runtime and dev dependencies in a per-package `pyproject.toml` and ships a committed `uv.lock` lockfile that pins every transitive dependency to an exact version + SHA-256 hash.

## Key Files

- `mk/python.mk` — shared `sync` / `test` targets that invoke `uv sync --frozen` and `uv run pytest`
- `mk/image.mk` — shared container build targets; images are built from each product's `Dockerfile`
- `mk/defaults.mk` — pinned base image defaults (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`) used by `shared/base-images/base-uv/Dockerfile`
- Root `Makefile` — orchestrates `make sync` / `make test` / `make build` across all products via `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists
- Per-product `pyproject.toml` (e.g. `products/agent-platform/pyproject.toml`, `products/platform-gateway/pyproject.toml`) — declares `[project] dependencies`, `[dependency-groups].dev`, and `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]`
- Per-product `uv.lock` (e.g. `products/agent-platform/uv.lock`) — full deterministic resolution against `https://pypi.org/simple` with `sha256` hashes for every sdist/wheel
- `.python-version` at root and per-product `.python-version` — pin the interpreter version

## Architecture and Conventions

1. **One lockfile per product.** Each of the eight Python services (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`) has its own `pyproject.toml` + `uv.lock`. The operator portal (`operator-portal/web-ui`) is a separate npm/Vitest SPA and is not part of the uv system.

2. **Dependency specifiers use upper-bound major-version caps.** Runtime deps follow the pattern `package>=X.Y,<Z.0` (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `agentscope>=2.0.4,<3.0`). Dev deps use the same style (`pytest>=8.3,<9.0`, `fakeredis>=2.26,<3.0`). This allows minor/patch upgrades while blocking breaking-major releases.

3. **Lockfiles are frozen at install time.** `mk/python.mk` runs `uv sync --frozen` for both `sync` and `test`; this rejects any deviation between `pyproject.toml` and `uv.lock`, so developers cannot silently update dependencies without committing the regenerated lockfile.

4. **Reproducible base image pins uv itself.** `mk/defaults.mk` sets `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; the root `make base-images` target builds `shared/base-images/base-uv` with these args, and product Dockerfiles layer on top of it. The comment in `defaults.mk` states: "Pinned values below are defaults for reproducible builds — never `latest`."

5. **Build backend is pinned.** Every `pyproject.toml` sets `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"`, ensuring the same uv-based build pipeline regardless of environment.

6. **No private registry or vendoring.** All packages resolve from `https://pypi.org/simple` (visible in every `[[package]]` entry's `source = { registry = "https://pypi.org/simple" }`). No `index-url`, `extra-index-url`, `pip.conf`, `UV_INDEX_URL`, or `GOPRIVATE` configuration exists anywhere in the repo. Private/internal packages would need to be published to PyPI or configured externally via uv config outside the repo.

7. **Cross-product coordination via Makefile.** The root `Makefile` defines `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and delegates `sync`, `test`, `lint`, `build`, `push` to each product's Makefile. A coordinated `IMAGE_TAG` is computed once and written into `.images.env` for GitOps deployment.

## Conventions and Constraints

- **Observed convention:** Runtime dependencies declare explicit lower bounds and `<major+1` upper bounds (e.g. `agentscope>=2.0.4,<3.0`). Dev dependencies are isolated under `[dependency-groups].dev`.
- **Enforced rule:** `uv sync --frozen` is the only supported way to install dependencies in CI and local development (enforced by `mk/python.mk`'s `sync` and `test` targets).
- **Enforced rule:** The base uv version and Python version inside container images are pinned through `mk/defaults.mk` (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`) and rebuilt via `make base-images`.
- **Enforced rule:** The build backend is locked to `uv_build>=0.8.14,<0.9.0` via `[build-system]` in every product's `pyproject.toml`.
- **Enforced rule:** The root `VERSION` file is the single source of truth for the platform release semver; `make validate-version` enforces lockstep between `VERSION`, each product's `pyproject.toml` version, and the portal (via `shared/shared-contracts/scripts/validate_version.py`).
- **Observed constraint:** No private PyPI index or authentication is configured in the repository; all resolutions go to pypi.org.