---
kind: dependency_management
name: uv-based per-product dependency management with frozen lockfiles
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - Makefile
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/agent-platform/Dockerfile
    - products/agent-platform/.python-version
    - docs/workspace/python-container-strategy.md
    - docs/workspace/backend-service-layout-convention.md
---

## System / Approach

The repository uses **uv** (Astral) as the sole Python package manager across all seven backend microservices. Each product under `products/` is an independent uv project declared in its own `pyproject.toml`, and every product ships a committed `uv.lock` lockfile that pins exact transitive versions. The workspace-level Makefile orchestrates dependency sync, test runs, and image builds for all products uniformly.

There is no shared `requirements.txt`, no vendored `site-packages`, and no pip configuration files — dependency resolution is entirely delegated to uv via PEP 621 metadata.

## Key Files

- Per-product manifests: `products/*/pyproject.toml` — declare runtime dependencies, dev dependency groups (`[dependency-groups] dev = [...]`), entrypoint scripts (`[project.scripts]`), and build system.
- Per-product lockfiles: `products/*/uv.lock` — committed, deterministic pin of every transitive dependency.
- Shared build fragment: `mk/python.mk` — defines `sync` (`uv sync --frozen`) and `test` targets used by every product Makefile.
- Root orchestrator: `Makefile` — lists `PYTHON_PRODUCTS := agent-platform audit-service identity-broker platform-gateway skills-hub tool-gateway` and runs `make -C products/$p sync` / `test` for each.
- Base image: `shared/base-images/base-uv/Dockerfile` — installs a pinned `uv` (0.12.1) into Amazon Linux 2023 minimal, sets `UV_PYTHON=3.12`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, and runs as non-root user `app` (uid 1000).
- Product Dockerfiles (e.g. `products/agent-platform/Dockerfile`) — copy `.python-version`, `pyproject.toml`, `uv.lock`, then run `uv sync --frozen --no-dev` inside the image.
- Version pinning file: `products/<product>/.python-version` (e.g. `3.12`) — tells uv which interpreter to use; also copied into images.
- Documentation codifying the strategy: `docs/workspace/python-container-strategy.md` and `docs/workspace/backend-service-layout-convention.md` explicitly prescribe `uv.lock` + `uv sync --frozen` in deterministic build paths.

## Architecture & Conventions

1. **Per-product isolation**: Each service declares only its own runtime and dev dependencies. There are no cross-package imports between services at the Python level; inter-service communication happens over HTTP/gRPC via shared JSON schemas in `shared/shared-contracts/schemas/`.
2. **Version ranges**: Runtime dependencies use caret-style ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`). Dev dependencies follow the same pattern (e.g. `pytest>=8.3,<9.0`, `jsonschema>=4.23,<5.0`). This allows minor/patch updates while blocking major bumps.
3. **Deterministic installs**: Both development (`make sync`) and container builds invoke `uv sync --frozen`, which refuses to resolve or modify the lockfile — the lockfile is the source of truth.
4. **No dev deps in images**: Container images install with `--no-dev`, so production images contain only runtime dependencies.
5. **Shared base image**: All product images derive from `luban-aiops/base-uv:al2023`, which pins the uv binary version and Python interpreter version via build args (`BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION` defined in `mk/defaults.mk`).
6. **Registry/source**: No private PyPI index or `pip.conf` is configured anywhere in the repo. Dependencies are resolved against the public PyPI (and any registry configured on the host running uv). The root `Makefile` does not set `UV_INDEX_URL` or similar environment variables.
7. **Build backend**: Every product uses `uv_build` (`build-system.requires = ["uv_build>=0.8.14,<0.9.0"]`) — no setuptools or poetry involved.

## Conventions & Constraints

- **Every Python product must have**: a `pyproject.toml` with `[project]` dependencies, a committed `uv.lock`, a `.python-version` file, and a `Dockerfile` that copies those three files before running `uv sync --frozen --no-dev`. (Enforced by the shared `mk/python.mk` targets and the root Makefile's product list.)
- **Lockfiles must stay in sync with `pyproject.toml`**: `uv sync --frozen` will fail if the lockfile drifts, making it a CI gate. The root `verify` target chains `test` (which calls `uv sync --frozen`) and overlay/policy checks.
- **Python version is pinned per product**: `.python-version` files (currently `3.12`) are copied into images and drive interpreter selection; the base image defaults to `UV_PYTHON=3.12` but respects per-project overrides.
- **Dev-only packages go in `[dependency-groups] dev`**: Test and linting tools (pytest, jsonschema, fakeredis) are isolated from runtime dependencies and excluded from images via `--no-dev`.
- **No vendoring**: The repo contains no `vendor/` directories or checked-in wheels; all third-party code comes through uv's resolver against the lockfile.
- **Policy artifacts are separate from Python deps**: Policy YAML bundles live under `shared/shared-contracts/policies/` and are synced to consumers via `make sync-policy`; they are not managed as Python packages.