---
kind: dependency_management
name: Per-Product uv Lockfiles with Shared Base Image and npm Lockfile
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
    - products/agent-platform/Dockerfile
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/package-lock.json
    - Makefile
---

## System / Approach

The monorepo uses a **per-product dependency management** model built on two package managers:

- **Python**: `uv` (Astral) with per-product `pyproject.toml` + `uv.lock` files. There is no workspace-level lockfile; each product under `products/<name>/` declares its own dependencies, dev-dependencies, and pinned resolution.
- **Frontend (operator portal)**: `npm` with a single `package.json` + `package-lock.json` under `products/operator-portal/web-ui/app/`.

There are no vendored third-party packages, no private PyPI registry configured in the repo, and no `requirements.txt` files anywhere. All Python dependencies resolve from `https://pypi.org/simple` as recorded in the generated lockfiles.

## Key Files

- `mk/python.mk` — shared Make targets that invoke `uv sync --frozen` and `uv run pytest`, enforcing locked installs for every Python product.
- `mk/image.mk` — shared Docker build/push targets used by all Python services.
- `mk/defaults.mk` — pins the base image defaults (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`).
- `shared/base-images/base-uv/Dockerfile` — builds the shared `luban-aiops/base-uv:al2023` image that ships a pinned `uv` binary and sets `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=<version>`, `UV_PYTHON_INSTALL_DIR=/app/.python` so runtime installs are deterministic and non-root.
- Per-product `Dockerfile`s (e.g. `products/agent-platform/Dockerfile`) copy only `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, and `src/`, then run `RUN uv sync --frozen --no-dev` to bake a read-only dependency tree into the image.
- Root `Makefile` — defines `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway` and exposes `make sync` / `make test` which iterate over every product's Makefile.
- `products/operator-portal/web-ui/app/package.json` + `package-lock.json` — the sole frontend dependency manifest.
- `VERSION` file — single source of truth for the coordinated platform version; enforced via `make validate-version` which runs `shared/shared-contracts/scripts/validate_version.py` against products and the portal.

## Architecture and Conventions

1. **Frozen installs everywhere.** Both development (`uv sync --frozen`) and production images (`uv sync --frozen --no-dev`) use `--frozen`, meaning any change to `pyproject.toml` must be followed by regenerating the `uv.lock` (via `uv lock`) before committing. The CI verification gate (`make verify`) depends on this determinism.

2. **No cross-product Python dependencies.** Each service is self-contained; there is no shared Python package referenced between products at install time. Cross-cutting contracts live as JSON schemas under `shared/shared-contracts/schemas/` and YAML policies under `shared/shared-contracts/policies/`, not as importable Python packages.

3. **Shared base image strategy.** All Python services inherit from `luban-aiops/base-uv:al2023`, which contains a pinned `uv` (default `0.12.1`) and a pinned Python interpreter default (`3.12`). Product `.python-version` files select the exact interpreter per service; `uv` resolves it during sync. This isolates Python version drift from the package manager version.

4. **Dev vs prod separation.** `pyproject.toml` `dependency-groups.dev` lists test/dev-only packages (e.g. `pytest`, `fakeredis`, `jsonschema`); production images pass `--no-dev` to exclude them.

5. **Version lockstep across the monorepo.** The root `VERSION` semver is propagated to every product image tag via the root `Makefile`'s computed `IMAGE_TAG`. A `make validate-version` target runs a script that asserts the product versions stay in lockstep with the platform version.

6. **Policy bundling is synchronized centrally.** The canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`; `make sync-policy` copies it into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. Consumers do not pin policy versions independently.

7. **Frontend dependencies are isolated.** Only the operator portal uses npm; backend services have no Node.js dependencies. The portal pins Node via `engines.node = ">=22"` and an `.nvmrc` file.

## Conventions and Constraints

- **Every Python product must ship a `pyproject.toml` and a committed `uv.lock`.** The root `sync` target iterates over `PYTHON_PRODUCTS` and calls each product's `make sync`, which runs `uv sync --frozen`; a missing or stale lockfile will fail the gate.
- **Dependencies are declared with upper-bound major-version caps** (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `agentscope>=2.0.4,<3.0`). This prevents automatic major-version upgrades from breaking builds.
- **No private registries or pip config.** All sources resolve to `https://pypi.org/simple` as recorded in the lockfiles; no `PIP_INDEX_URL`, `pip.conf`, or `uv.config.toml` exists in the repo.
- **Base image versions are pinned in `mk/defaults.mk`**, not in individual Dockerfiles. Overriding `BASE_UV_UV_VERSION` or `BASE_UV_PYTHON_VERSION` requires changing the central defaults.
- **Image tags are derived from the root `VERSION` plus git SHA and dirty-state timestamp**; the root `Makefile` writes the resulting tag into `shared/platform-ops/gitops/dev-k8s/.images.env` so GitOps overlays reference exactly one coordinated image set.
- **Dockerfiles linted via hadolint** (with a docker-run fallback) through `make lint`, ensuring consistent container-layer dependency installation patterns.