---
kind: dependency_management
name: uv-based per-product dependency management with frozen lockfiles and shared base image
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - Makefile
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
---

## What system/approach is used

The monorepo manages Python dependencies with **uv** (Astral's Python package manager) on a per-product basis. Each service under `products/` declares its own `pyproject.toml` with explicit version ranges, and each product ships a committed `uv.lock` that pins every transitive dependency to an exact version and hash. The root Makefile orchestrates dependency operations across all Python products via the shared fragment `mk/python.mk`, which invokes `uv sync --frozen` — forcing resolution against the committed lockfile so builds are reproducible.

Python interpreter versions are pinned per product in `.python-version` files (e.g. `3.12`) and globally via the shared base image `shared/base-images/base-uv/Dockerfile`, which installs a pinned `uv` (`0.12.1`) and sets `UV_PYTHON=3.12` as the deterministic fallback. All backend services build on this Amazon Linux 2023 minimal image; there is no vendored source tree for third-party packages — everything is resolved from PyPI at build time using the lockfile.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` declare runtime and dev dependencies with bounded semver ranges (e.g. `fastapi>=0.115,<1.0`, `agentscope>=2.0.4,<3.0`).
- Per-product lockfiles: `products/*/uv.lock` pin every transitive dependency with source registry URLs and SHA256 hashes.
- Shared uv targets: `mk/python.mk` defines `sync` and `test` targets that run `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled for test output cleanliness.
- Root orchestration: `Makefile` lists `PYTHON_PRODUCTS := agent-platform audit-service identity-broker incident-service platform-gateway skills-hub tool-gateway` and runs `make -C products/$p sync` / `test` across them.
- Base image: `shared/base-images/base-uv/Dockerfile` pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`, installs uv into `/usr/local/bin`, and configures `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Build defaults: `mk/defaults.mk` centralizes overridable settings like `BASE_UV_UV_VERSION`, `IMAGE_PLATFORM`, and `REGISTRY`.
- Product Dockerfiles reference the base image and use `uv sync --frozen` during image build to install dependencies inside the container.

## Architecture and conventions

- **Per-product isolation**: Each service owns its own `pyproject.toml` and `uv.lock`; there is no workspace-level or monorepo-wide dependency manifest. Cross-cutting concerns (image building, policy validation, overlay rendering) live in the root `Makefile` and `mk/*.mk` fragments.
- **Bounded version ranges**: Runtime dependencies use upper-bound major-version caps (e.g. `<3.0` for pydantic, `<1.0` for fastapi, `<2.0` for opentelemetry-sdk) to allow patch/minor updates while preventing breaking changes. Dev-only dependencies are isolated under `[dependency-groups] dev = [...]`.
- **Frozen resolution**: Both development (`make sync`) and CI/test flows use `uv sync --frozen`, guaranteeing that the installed dependency graph matches exactly what was committed in `uv.lock`. No network resolution is allowed at build time.
- **Shared base image strategy**: Instead of installing Python system-wide, images derive from `luban-aiops/base-uv:al2023`, which pins uv and Python versions centrally. This ensures consistent interpreter selection across all products.
- **Coordinated image tagging**: The root `Makefile` computes a single `IMAGE_TAG` from the root `VERSION` file plus git sha and profile, then tags every product image uniformly (e.g. `luban-aiops/platform-gateway:<semver>-dev-k8s-<sha>`). A `.images.env` state file records the built image references for GitOps deployment.
- **No private registry configuration**: All packages resolve from `https://pypi.org/simple` as recorded in the lockfiles; no `PYPI_URL`, `pip.conf`, or `uv config` overrides were found in the repository.

## Conventions and constraints

- Every Python product must have a `pyproject.toml` with a `[build-system]` section declaring `uv_build` as the build backend and a matching `uv.lock` committed alongside it.
- Dependencies must specify both lower and upper bounds on major versions to avoid accidental breaking upgrades; this pattern is enforced by the existing declarations rather than a linter.
- Development-only tools (pytest, jsonschema, fakeredis) are declared exclusively in the `[dependency-groups] dev` section and never mixed into runtime dependencies.
- The `make verify` gate (used as pre-commit/pre-push) includes `test overlays validate-policy validate-version`, which runs `uv run pytest` against the frozen lockfile for every Python product, making lockfile drift detectable in CI.
- Container images inherit the shared base image and do not install Python or uv themselves; they rely on the base image's pinned versions and run `uv sync --frozen` during their own build stage.
- The root `VERSION` file is the single source of truth for the platform release version; `make validate-version` enforces that product versions stay in lockstep with it.