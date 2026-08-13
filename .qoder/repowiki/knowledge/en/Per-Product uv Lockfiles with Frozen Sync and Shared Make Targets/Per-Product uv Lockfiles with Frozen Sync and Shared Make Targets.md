---
kind: dependency_management
name: Per-Product uv Lockfiles with Frozen Sync and Shared Make Targets
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - Makefile
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/platform-gateway/uv.lock
    - products/identity-broker/pyproject.toml
    - products/identity-broker/uv.lock
    - products/tool-gateway/pyproject.toml
    - products/tool-gateway/uv.lock
    - products/agent-platform/.python-version
    - shared/base-images/base-uv/Dockerfile
---

## Dependency Management Approach

The repository is a multi-product Python workspace (agent-platform, identity-broker, platform-gateway, tool-gateway) that uses **uv** as the sole package manager. Each product declares its own `pyproject.toml` and ships a committed `uv.lock` lockfile under `products/<product>/`. There is no monorepo-level dependency manifest; each product manages its dependencies independently.

### Version pinning strategy

- All products declare `requires-python = ">=3.11"` in their `pyproject.toml`, but the per-product `.python-version` files pin to `3.12` (e.g. `products/agent-platform/.python-version`).
- Dependencies use **pessimistic range constraints** (`>=X,<Y`) rather than exact pins — for example `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`, `cryptography>=43.0,<45.0`. This allows patch/minor updates while blocking major-version breaks.
- Internal packages are treated like third-party ones: `agentscope>=2.0.4,<3.0` and `agentscope-runtime>=1.1,<2.0` are declared as runtime dependencies of `agent-service`.
- Dev-only dependencies live in `[dependency-groups] dev = [...]` (pytest, jsonschema, fakeredis), keeping them separate from runtime requirements.
- The build system itself is pinned via `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"` across all four products.

### Lockfiles and reproducibility

Each product directory contains a committed `uv.lock` file (e.g. `products/agent-platform/uv.lock`, `products/platform-gateway/uv.lock`, `products/identity-broker/uv.lock`, `products/tool-gateway/uv.lock`). These lockfiles pin every transitive dependency to an exact version, ensuring deterministic installs.

The shared Make target in `mk/python.mk` enforces frozen installs:
```
sync: ## Install/refresh this product's dependencies (frozen lock)
	uv sync --frozen
```
The `--frozen` flag causes `uv sync` to fail if the lockfile does not match the current `pyproject.toml`, preventing accidental drift between manifests and lockfiles.

### Workspace orchestration

The root `Makefile` defines `PYTHON_PRODUCTS := agent-platform identity-broker platform-gateway tool-gateway` and exposes top-level targets that iterate over every product:
- `make sync` — runs `make -C products/<p> sync` for each Python product, invoking `uv sync --frozen` per product.
- `make test` — runs `make -C products/<p> test` which first re-syncs frozen deps then runs `uv run pytest`.

This means CI or a developer running `make verify` at the repo root will install and test every product against its locked dependency set.

### Container builds

Products ship Dockerfiles that layer on a shared base image built from `shared/base-images/base-uv/Dockerfile`. The root `Makefile` has a `base-images` target that builds this image using `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION` variables defined in `mk/defaults.mk`. The container images are tagged with a coordinated tag computed from git SHA and written into `shared/platform-ops/gitops/dev-k8s/.images.env`, so deployment manifests reference a single consistent image tag across all services.

### Private registries and vendoring

No private PyPI registry configuration, `pip.conf`, `pip.ini`, `Pipfile`, `requirements.txt`, `go.mod`, `package.json`, or vendored `vendor/` directories were found. Dependencies resolve exclusively from the public PyPI index via uv. There is no `GOPRIVATE`, no npm registry config, and no vendoring strategy — the project relies entirely on uv's lockfile-based resolution against the default index.

### Conventions observed

1. Every Python product lives under `products/<name>/` with its own `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, and `Makefile`.
2. Runtime dependencies use upper-bound major-version caps (`<1.0`, `<2.0`, `<3.0`, `<45.0`) to allow safe minor/patch upgrades.
3. Dev dependencies are isolated in `[dependency-groups] dev` and never shipped to production images.
4. `uv sync --frozen` is the canonical way to install deps; it is invoked by both per-product Makefiles and the root orchestrator.
5. The build backend is uniformly `uv_build` across all products.
6. The root Makefile enumerates which products participate in `sync`, `test`, `lint`, and `build`; adding a new Python product requires registering it in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS`.