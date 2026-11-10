---
kind: dependency_management
name: uv-based Python Dependency Management with Frozen Lockfiles and Shared Base Image
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/defaults.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/agent-platform/Dockerfile
    - products/agent-platform/.python-version
---

# Dependency Management in the Luban Agentic AIOps Platform

## Approach

The repository uses **uv** (Astral) as the sole Python package manager across all nine backend products. There is no pip, Poetry, or PDM usage. Each product under `products/<name>/` declares its dependencies in a `pyproject.toml` using PEP 621 `[project]` / `[dependency-groups]` tables, and ships a committed `uv.lock` lockfile that pins every transitive dependency to an exact version plus SHA-256 hash.

There are no vendored third-party sources — packages resolve from PyPI (`https://pypi.org/simple`) as recorded in each `uv.lock` entry's `source.registry`. No private registry, mirror, or `UV_INDEX_URL`/`PIP_INDEX_URL` configuration was found in any `.mk`, Dockerfile, or Makefile; the build system does not set `PYPI_MIRROR` either.

## Key Files

- `Makefile` — root orchestrator; `make sync` iterates over `PYTHON_PRODUCTS` and delegates to each product's `sync` target.
- `mk/python.mk` — shared `sync` / `test` targets: `uv sync --frozen` and `uv run pytest`.
- `mk/defaults.mk` — pinned defaults for the shared base image (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`).
- `shared/base-images/base-uv/Dockerfile` — base image that installs a pinned uv binary and sets `UV_PYTHON=3.12`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Per-product `Dockerfile` — copies `.python-version pyproject.toml uv.lock` then runs `uv sync --frozen --no-dev`.
- Per-product `pyproject.toml` — PEP 621 dependency declarations (e.g. `agent-service`: `agentscope>=2.0.4,<3.0`, `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, etc.).
- Per-product `uv.lock` — deterministic lockfile with per-package `sha256` hashes and `source = { registry = "https://pypi.org/simple" }`.
- Per-product `.python-version` — e.g. `3.12` in `products/agent-platform/.python-version`.
- Root `.python-version` — also present at workspace root.

## Architecture and Conventions

### Version pinning strategy

Dependencies use **broad lower bounds with tight upper bounds** (e.g. `>=X.Y,<Z.0`), allowing patch/minor updates within a major version while blocking breaking changes. The `build-system.requires` field pins the build tool itself narrowly: `uv_build>=0.8.14,<0.9.0`. Dev-only dependencies live under `[dependency-groups].dev` (e.g. `pytest>=8.3,<9.0`, `fakeredis>=2.26,<3.0`) and are excluded from production images via `--no-dev`.

### Reproducibility

All install steps invoke `uv sync --frozen`, which refuses to resolve against the network and requires the committed `uv.lock` to be up-to-date. This is enforced both by:
- `mk/python.mk`'s `sync` target (`uv sync --frozen`)
- Every product `Dockerfile` (`RUN uv sync --frozen --no-dev`)
- Integration tests invoked through `make audit-contract-test`, `make delegated-custody-test`, etc., which use `uv run --frozen`

The base image pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` as build args, propagated via `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION` in `mk/defaults.mk`. Product `.python-version` files override the interpreter selection per product.

### Multi-product coordination

The root `Makefile` enumerates Python products in `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and loops over them for `sync`, `test`, and `lint`. The same list drives image builds via `IMAGE_PRODUCTS`.

### Container strategy

Product images inherit from `luban-aiops/base-uv:al2023`, built once by `make base-images` using `shared/base-images/base-uv/Dockerfile`. That image runs as non-root user `app` (uid 1000), has no system Python installed, and lets uv manage interpreters under `/app/.python`. The `UV_NO_SYNC=1` environment variable prevents accidental resolution at runtime; dependencies are baked into the image layer during build.

### Operator-portal frontend

The operator portal (`products/operator-portal/`) is a separate SPA (Vitest + TypeScript/Vite) and is not part of the Python/uv dependency graph. Its build is orchestrated by `make portal-test` and `make -C products/operator-portal web-build` from the root Makefile, but its own npm/yarn/pnpm lockfile is outside the scope of this card.

## Conventions and Constraints

- **Every Python product must have a `pyproject.toml` and a committed `uv.lock`** — enforced because `uv sync --frozen` fails without a lockfile and the Dockerfile copies `uv.lock` into the image.
- **Dependency ranges must use `<major.next>` upper bounds** — observed consistently across all `pyproject.toml` entries (e.g. `agentscope>=2.0.4,<3.0`, `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `redis>=6.2,<7.0`).
- **Dev dependencies go under `[dependency-groups].dev`**, not `[project.dependencies]** — seen in `agent-service` and mirrored across other products.
- **Production images exclude dev deps** via `uv sync --frozen --no-dev` in every product `Dockerfile`.
- **Interpreter versions are declared per-product** in `.python-version` and resolved by uv; the base image default is `3.12`.
- **No private PyPI registry or mirror is configured** — all lockfile entries point to `https://pypi.org/simple`; no `UV_INDEX_URL`, `PYPI_MIRROR`, or `PIP_INDEX_URL` appears in any build file.
- **The base uv binary and Python version are centrally pinned** in `mk/defaults.mk` (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`) and overridden only via `--build-arg` on `make base-images`.
- **Reproducible builds require a frozen lockfile** — `uv sync --frozen` is the universal invocation pattern in `mk/python.mk`, product Dockerfiles, and integration test wrappers.