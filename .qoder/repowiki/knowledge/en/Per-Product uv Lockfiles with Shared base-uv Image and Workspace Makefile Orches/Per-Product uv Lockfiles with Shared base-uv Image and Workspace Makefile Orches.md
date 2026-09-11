---
kind: dependency_management
name: Per-Product uv Lockfiles with Shared base-uv Image and Workspace Makefile Orchestration
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - docs/workspace/python-container-strategy.md
    - products/agent-platform/pyproject.toml
    - products/agent-platform/.python-version
    - products/agent-platform/Dockerfile
    - Makefile
---

## What system/approach is used

The repository manages Python dependencies per product using **uv** as the package and environment manager. Each backend service under `products/<name>/` declares its runtime and dev dependencies in a local `pyproject.toml`, pins them to exact versions via a committed `uv.lock`, and installs them with `uv sync --frozen`. There is no workspace-level `pyproject.toml` or shared lockfile — dependency resolution is isolated per product.

Container images are built from a single shared base image `luban-aiops/base-uv:al2023` (built from `shared/base-images/base-uv/Dockerfile`) that ships a pinned `uv` binary and sets deterministic environment variables (`UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON`, `UV_PYTHON_INSTALL_DIR`). The root `Makefile` orchestrates cross-cutting build, test, lint, policy, and deploy steps across all products; per-product `make sync` / `make test` delegates to `mk/python.mk`, which runs `uv sync --frozen` then `uv run pytest`.

There is no vendoring of third-party packages into source control, no private PyPI registry configured at the workspace level, and no Go/Node dependency manifests — this is a pure Python + container image dependency strategy.

## Key files and packages

- Per-product dependency declarations: `products/*/pyproject.toml` (e.g. `products/agent-platform/pyproject.toml` lists `agentscope>=2.0.4,<3.0`, `fastapi>=0.115,<1.0`, `psycopg[binary]>=3.2,<4.0`, etc., plus `[dependency-groups] dev = [...]`).
- Per-product lockfiles: `products/*/uv.lock` (committed alongside each `pyproject.toml`; release notes repeatedly reference refreshing these).
- Per-product interpreter pin: `products/.python-version` and `products/*/Dockerfile` copy `.python-version` into the image so `uv` resolves the interpreter deterministically.
- Shared base image: `shared/base-images/base-uv/Dockerfile` — pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`, installs uv from `https://astral.sh/uv/${UV_VERSION}/install.sh`, creates non-root `app` user (uid 1000), exports `UV_*` env vars.
- Build orchestration: root `Makefile` (lists `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`, defines `sync`, `test`, `build`, `push`, `verify` targets) and `mk/python.mk` (defines `sync: uv sync --frozen`, `test: uv sync --frozen && OTEL_TRACES_EXPORTER=none ... uv run pytest`).
- Container strategy doc: `docs/workspace/python-container-strategy.md` documents the adopted Option B strategy (Amazon Linux 2023 minimal base + installed uv, frozen lockfiles, non-root user).
- Product Dockerfiles: e.g. `products/agent-platform/Dockerfile` uses `FROM luban-aiops/base-uv:al2023`, copies `.python-version pyproject.toml uv.lock`, runs `RUN uv sync --frozen --no-dev`, and executes via `CMD ["uv", "run", "agent-service"]`.

## Architecture and conventions

1. **One `pyproject.toml` + one `uv.lock` per product.** Dependencies are declared with upper-bound version ranges (e.g. `>=X,<Y`) in `pyproject.toml`; the exact resolved versions live only in `uv.lock`. Dev-only dependencies go under `[dependency-groups] dev`.
2. **Frozen installs everywhere.** Both development (`mk/python.mk`) and production builds use `uv sync --frozen --no-dev`, guaranteeing that the locked graph is reproduced exactly. The base image also sets `UV_NO_SYNC=1` so containers do not re-resolve on boot.
3. **Interpreter pinning via `.python-version`.** Each product pins its Python version (e.g. `3.12`); the base image exposes `UV_PYTHON` as a fallback but the convention is to keep `.python-version` present so `uv` selects the interpreter explicitly.
4. **Shared base image for supply-chain hygiene.** All Python services `FROM luban-aiops/base-uv:al2023`, built once by `make base-images` with pinned `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION`. This centralizes OS-level dependencies, the uv binary, and the non-root `app` user.
5. **Root Makefile as the single entry point.** `make sync`, `make test`, `make build`, `make verify` iterate over every product listed in `PYTHON_PRODUCTS` / `IMAGE_PRODUCTS`. New products must be added to those lists to participate in the workspace workflow.
6. **No private registries or vendoring.** Packages are resolved from the default PyPI index through uv; there is no `--index-url`, `PIP_INDEX_URL`, `PYPI_MIRROR`, or `vendor/` directory observed in the codebase.
7. **Version lockstep enforced externally.** The root `Makefile` target `validate-version` calls `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file, per-product versions, and portal versions stay in lockstep — this is separate from package dependency versions but part of the overall dependency/versioning discipline.

## Conventions and constraints

- **Use `uv sync --frozen`** for both development and production dependency installation. Observed in `mk/python.mk`, every product Dockerfile, and the root `Makefile`'s `sync` target. The frozen flag enforces that `uv.lock` is authoritative.
- **Pin dependencies with upper bounds** in `pyproject.toml` (e.g. `fastapi>=0.115,<1.0`, `agentscope>=2.0.4,<3.0`). Lower bounds are used to allow patch updates while preventing major-version drift.
- **Keep `.python-version` in every product root.** The container strategy doc states this as a rule; all existing products include it and Dockerfiles copy it into the image.
- **Build images from `luban-aiops/base-uv:al2023`**, never from an external base like `python:slim` or `ghcr.io/astral-sh/uv:*`. The strategy doc records this as the current workspace rule.
- **Do not install a system Python inside product images.** The base image has no system Python; `uv` manages the interpreter via `.python-version` / `UV_PYTHON`.
- **Run as non-root user `app` (uid 1000).** Enforced by the base image (`USER app`) and required by deployment `securityContext` (`runAsNonRoot`, `allowPrivilegeEscalation: false`).
- **New Python products must register themselves** in the root `Makefile`'s `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists to participate in `make sync`, `make test`, `make build`, and `make push`.
- **uv itself is pinned via ARG** (`UV_VERSION=0.12.1` in `shared/base-images/base-uv/Dockerfile` and overridden by `BASE_UV_UV_VERSION` in `mk/defaults.mk`); the strategy doc explicitly forbids defaulting to `latest`.
- **Dev dependencies are separated** into `[dependency-groups] dev` rather than top-level `dependencies`, keeping production images lean when `--no-dev` is passed.