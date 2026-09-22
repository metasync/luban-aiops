---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Sync and Shared base-uv Image
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/agent-platform/Dockerfile
    - Makefile
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## What system/approach is used

The repository manages Python dependencies per product using **uv** (Astral's fast Python package manager) with `pyproject.toml` declarations and a committed `uv.lock` lockfile in each of the eight backend products under `products/`. The root Makefile enumerates the Python products (`PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`) and delegates `sync` / `test` into each product, which in turn call shared fragments from `mk/python.mk` that run `uv sync --frozen` and `uv run pytest`. Container images are built on top of a shared `shared/base-images/base-uv/Dockerfile` that installs a pinned `uv` version (default `0.12.1`) onto Amazon Linux 2023 minimal and sets `UV_PYTHON_INSTALL_DIR=/app/.python` so each product resolves its interpreter from its own `.python-version`.

The Node.js side (operator portal) lives under `products/operator-portal/web-ui/` and uses a conventional `node_modules/` tree; no lockfile was visible in the scanned tree, but it is treated as a separate product build via its own Dockerfile and Makefile.

## Key files and packages

- Per-product dependency manifests: `products/*/pyproject.toml` — declare runtime `dependencies`, optional `[dependency-groups].dev` for test-only packages, and a `[build-system]` pinning `uv_build>=0.8.14,<0.9.0` as the build backend.
- Per-product lockfiles: `products/*/uv.lock` — frozen resolution including transitive deps, source registry URLs (`https://pypi.org/simple`), and exact wheel/sdist hashes.
- Shared build fragments: `mk/python.mk` (`uv sync --frozen`, `uv run pytest` with OTLP exporters disabled), `mk/image.mk` (docker build/push/lint helpers), `mk/defaults.mk` (IMAGE_PLATFORM, REGISTRY, BASE_UV_*).
- Shared base image: `shared/base-images/base-uv/Dockerfile` — pins `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, installs curl-minimal + ca-certificates, creates non-root `app` user (uid 1000), exports `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=${PYTHON_VERSION}`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Product Dockerfiles (e.g. `products/agent-platform/Dockerfile`) copy only `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, and `src/`, then run `uv sync --frozen --no-dev` before `CMD ["uv", "run", "agent-service"]`.
- Root orchestration: `Makefile` lists `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, and exposes `make sync`, `make test`, `make build`, `make push`, `make verify`.
- Version lockstep enforcement: `shared/shared-contracts/scripts/validate_version.py` is invoked by `make validate-version`; release notes repeatedly reference re-locking all eight `uv.lock` files alongside `metadata.py` bumps.

## Architecture and conventions

- **One lockfile per product**: each service declares its own `pyproject.toml` and `uv.lock`; there is no workspace-level `uv.lock` or monorepo virtual environment. Cross-cutting scripts operate by iterating over the known product list.
- **Frozen installs everywhere**: both development (`mk/python.mk`) and production (`Dockerfile RUN uv sync --frozen --no-dev`) use `--frozen`, meaning the lockfile is the single source of truth — any change requires committing an updated `uv.lock`.
- **Latest-stable adoption policy**: per SPEC-042 (documented in `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md`), upgrades follow a "latest stable only" rule — no alpha, beta, RC, or dev builds. The OpenTelemetry instrumentation packages are the recorded exception because upstream ships them on a permanent `0.xb` channel; they stay paired with their locked SDK versions rather than being chased.
- **Version ranges cap majors**: dependencies use caret-style lower bounds with explicit upper major caps (e.g. `fastapi>=0.115,<1.0`, `redis>=6.2,<7.0`, `psycopg[binary]>=3.2,<4.0`, `agentscope>=2.0.4,<3.0`). Major-cap decisions are documented in release notes (e.g. cryptography caps moved from `<45.0` to `<51.0`; redis and elasticsearch clients remain parked below server-major boundaries).
- **Shared base image isolates toolchain**: the `base-uv` image pins `uv` and `python` versions at build time via `ARG UV_VERSION` / `ARG PYTHON_VERSION`, overridden through `BASE_UV_UV_VERSION` / `BASE_UV_PYTHON_VERSION` in `mk/defaults.mk`. Products do not install Python themselves — `uv sync` resolves the interpreter from `.python-version`.
- **No vendoring**: dependencies are resolved from PyPI (`source = { registry = "https://pypi.org/simple" }` in lockfiles). There is no `vendor/` directory or private registry configured in the scanned files.
- **Coordinated image tagging**: the root `Makefile` computes a single `IMAGE_TAG` and writes it into `shared/platform-ops/gitops/dev-k8s/.images.env`, so all product images share one tag — this couples deployment to the state of all `uv.lock` files simultaneously.

## Conventions and constraints

- **`uv sync --frozen` is the canonical install command** for both local dev and CI; `mk/python.mk` enforces it for every product's `sync` and `test` targets.
- **Lockfiles must be committed**: release notes consistently describe changes as "re-locking eight `uv.lock` files" alongside code changes, indicating that updating a dependency without committing the new lockfile is considered incomplete.
- **Python version pin per product**: each product has a `.python-version` file consumed by `uv` during `sync`; the base image defaults to `3.12` but can be overridden via `UV_PYTHON`.
- **Dev vs runtime separation**: runtime dependencies live under `dependencies` in `pyproject.toml`; test-only packages go into `[dependency-groups].dev` (e.g. `pytest`, `fakeredis`, `jsonschema`), keeping production images lean when `--no-dev` is used.
- **Build backend pinned**: `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` ensures deterministic builds regardless of the host's uv version.
- **Verification gate enforces consistency**: `make verify` runs `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, and a local secret-delivery demo — all of which depend on consistent dependency states across products.
- **Major-version caps are deliberate policy**: the release notes document why certain client libraries (redis, elasticsearch) are capped below their next major to match deployed server versions, showing that range caps are not accidental but reviewed decisions.