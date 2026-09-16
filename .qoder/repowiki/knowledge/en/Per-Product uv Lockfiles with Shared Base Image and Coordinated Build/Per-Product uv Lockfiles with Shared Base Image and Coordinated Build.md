---
kind: dependency_management
name: Per-Product uv Lockfiles with Shared Base Image and Coordinated Build
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/agent-platform/.python-version
    - products/agent-platform/Dockerfile
    - Makefile
    - docs/workspace/python-container-strategy.md
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
---

# Dependency Management

## What system/approach is used

The workspace uses **uv** (Astral) as the sole Python package manager across all backend products. Each product under `products/<name>/` declares its own `pyproject.toml` with explicit version ranges, a per-product `uv.lock` lockfile, and a `.python-version` file pinning the interpreter. The root Makefile orchestrates dependency synchronization (`make sync`) by invoking each product's `make sync`, which runs `uv sync --frozen` against that product's lockfile.

Container images are built from a shared base image `luban-aiops/base-uv:al2023` (built from `shared/base-images/base-uv/Dockerfile`) that installs a pinned `uv` binary on Amazon Linux 2023 minimal and exposes environment variables (`UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON`, `UV_PYTHON_INSTALL_DIR`). Product Dockerfiles copy only `.python-version`, `pyproject.toml`, `uv.lock`, and `src/`, then run `uv sync --frozen --no-dev` to install runtime-only dependencies deterministically.

There is no monorepo-level `uv.lock`; instead, each product maintains an independent lockfile. There is no vendored third-party source code — packages are resolved at build time from PyPI (or whatever registry uv is configured to use).

## Key files and packages

- `mk/python.mk` — shared `sync` and `test` targets that run `uv sync --frozen` and `uv run pytest` for every Python product.
- `mk/image.mk` — shared container-image targets; builds images using the product's `Dockerfile` and tags them under `luban-aiops/<IMAGE_NAME>:$(IMAGE_TAG)`.
- `mk/defaults.mk` — single source of overridable defaults including `BASE_UV_UV_VERSION` (default `0.12.1`) and `BASE_UV_PYTHON_VERSION` (default `3.12`); these pins propagate into the base image build via `make base-images`.
- `shared/base-images/base-uv/Dockerfile` — defines the shared base image with a pinned uv installer URL (`https://astral.sh/uv/${UV_VERSION}/install.sh`) and non-root `app` user (uid 1000).
- `products/*/pyproject.toml` — per-product dependency declarations with upper-bounded version ranges (e.g. `agentscope>=2.0.4,<3.0`, `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `psycopg[binary]>=3.2,<4.0`, `redis>=6.2,<7.0`, `uvicorn[standard]>=0.30,<1.0`).
- `products/*/uv.lock` — per-product lockfiles committed to the repo; consumed by `uv sync --frozen` in both development and image builds.
- `products/*/.python-version` — per-product Python interpreter pin (root also has one).
- `products/*/Dockerfile` — standard pattern: `FROM luban-aiops/base-uv:al2023`, copy lockfile + sources, `RUN uv sync --frozen --no-dev`, `CMD ["uv", "run", "<entrypoint>"]`.
- Root `Makefile` — lists `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and iterates over them for `sync`, `test`, `build`, `push`.
- `docs/workspace/python-container-strategy.md` — documents the adopted strategy and rules governing uv usage, base image selection, and interpreter resolution.
- `docs/specs/SPEC-042-dependency-hygiene/spec.md` — codifies dependency hygiene requirements including lockfile re-locking and range policies.

## Architecture and conventions

1. **Per-product isolation**: Each service owns its own `pyproject.toml` and `uv.lock`. There is no shared Python package or workspace-level dependency declaration. Cross-cutting concerns (policy validation scripts, JSON schemas) live under `shared/shared-contracts/` and are invoked via `uv run python ...` from product directories rather than installed as dependencies.

2. **Frozen lockfiles everywhere**: Both local development (`uv sync --frozen`) and production image builds (`uv sync --frozen --no-dev`) require the lockfile to be present and exact. No `--upgrade` or editable installs in production images.

3. **Interpreter pinning via `.python-version`**: The base image sets `UV_PYTHON` as a fallback, but each product explicitly pins its interpreter in `.python-version` so `uv` resolves it deterministically during `uv sync`. The root `.python-version` is `3.12`.

4. **Shared base image for supply-chain control**: All Python services build from `luban-aiops/base-uv:al2023`, built once via `make base-images` and reused by every product image. This centralizes OS-level dependencies (curl-minimal, ca-certificates, shadow-utils), the uv binary version, and the non-root `app` user.

5. **Coordinated tagging**: The root `VERSION` file is the single source of truth for the platform release version. The root `Makefile` computes a coordinated `IMAGE_TAG` (semver + git sha + optional profile/dirty marker) and writes it into `.images.env`, which is consumed by GitOps overlays. A `validate-version` target enforces lockstep between `VERSION`, product versions, and portal metadata.

6. **No private registry configuration in this repo**: Dependencies are declared as plain PyPI specifiers. Private registries would be configured externally (e.g., via uv config or CI credentials), not checked into the repository.

## Conventions and constraints

- **Version ranges are upper-bounded**: Every dependency in `pyproject.toml` files uses a `<major>` cap (e.g. `<3.0`, `<1.0`, `<4.0`) to prevent automatic major-version upgrades. This is enforced by convention and documented in SPEC-042 dependency hygiene.
- **Lockfiles must be committed**: `uv.lock` is part of the source tree and consumed with `--frozen`. Release notes repeatedly reference re-locking `uv.lock` files as part of changes.
- **Dev vs prod dependencies are separated**: `dependency-groups.dev` in `pyproject.toml` holds test/dev-only packages (`fakeredis`, `jsonschema`, `pytest`); production images pass `--no-dev` to exclude them.
- **Base toolchain versions are pinned, never `latest`**: `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION` in `mk/defaults.mk` default to specific versions; the documentation explicitly states they must never default to `latest`.
- **Non-root execution**: The base image creates a non-root `app` user (uid 1000) and sets `USER app`; deployment security contexts enforce `runAsNonRoot`, `runAsUser`, `allowPrivilegeEscalation: false`, and `seccompProfile: RuntimeDefault`.
- **Single build entry point**: Developers should use `make sync`, `make test`, `make build`, `make push` from the repo root rather than running uv directly per product; the root Makefile delegates to per-product Makefiles that include `mk/python.mk` and `mk/image.mk`.
- **Image tag coordination**: The root `make build` computes one `IMAGE_TAG` and applies it uniformly to all eight Python services plus the web UI, ensuring all deployed components share a coordinated version.
- **Supply-chain note**: uv itself is installed from the pinned-version installer URL (`https://astral.sh/uv/${UV_VERSION}/install.sh`) rather than a checksummed tarball; this is an accepted decision documented in the container strategy.