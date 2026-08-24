---
kind: dependency_management
name: uv-based per-product dependency locking with coordinated platform versioning
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - VERSION
    - mk/python.mk
    - mk/image.mk
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/skills-hub/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/incident-service/pyproject.toml
    - shared/shared-contracts/scripts/validate_version.py
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/package-lock.json
---

## What system/approach is used

The workspace uses **uv** (a fast Python package installer and resolver) as the single dependency manager across all Python products. Each product under `products/<name>/` declares its own dependencies in a `pyproject.toml` using PEP 621 `[project.dependencies]`, and ships a committed `uv.lock` lockfile that pins every transitive dependency to an exact version plus SHA-256 hash, resolved from PyPI (`https://pypi.org/simple`). There is no monorepo-level `pyproject.toml` or shared lockfile — each product is an independent uv project.

The build toolchain is Make-driven: the root `Makefile` lists `PYTHON_PRODUCTS := agent-platform audit-service identity-broker incident-service platform-gateway skills-hub tool-gateway` and delegates `sync`, `test`, `build`, `push` to each product's Makefile via `mk/python.mk`, which runs `uv sync --frozen` (enforcing the lockfile). The `--frozen` flag guarantees that CI and local installs resolve exactly what is checked in, preventing drift between developer environments.

The Node.js web portal (`products/operator-portal/web-ui/app/`) uses npm with a committed `package-lock.json` and an `.nvmrc` pinning the Node runtime; it is not managed by uv.

## Key files and packages

- Per-product dependency manifests: `products/*/pyproject.toml` (e.g. `products/agent-platform/pyproject.toml`, `products/platform-gateway/pyproject.toml`, `products/tool-gateway/pyproject.toml`, `products/skills-hub/pyproject.toml`, `products/audit-service/pyproject.toml`, `products/identity-broker/pyproject.toml`, `products/incident-service/pyproject.toml`).
- Per-product lockfiles: `products/*/uv.lock` (e.g. `products/agent-platform/uv.lock`, `products/platform-gateway/uv.lock`, etc.).
- Shared Make fragments: `mk/python.mk` (defines `sync` → `uv sync --frozen`; `test` → `uv run pytest`), `mk/image.mk` (container image targets).
- Root orchestration: `Makefile` (aggregates per-product `sync`/`test`/`build`/`push`), `VERSION` (single source of truth for the platform semver).
- Version lockstep enforcement: `shared/shared-contracts/scripts/validate_version.py`, invoked via `make validate-version`.
- Build backend: `uv_build>=0.8.14,<0.9.0` declared in each product's `[build-system]`.
- Node portal: `products/operator-portal/web-ui/app/package.json` + `package-lock.json` + `.nvmrc`.

## Architecture and conventions

1. **Per-product isolation**: Each service owns its own `pyproject.toml` and `uv.lock`. Dependencies are not hoisted to a workspace root; this keeps each product independently installable and testable.

2. **Frozen resolution**: All installs use `uv sync --frozen` (see `mk/python.mk` line 12). This means the lockfile is authoritative — adding a new dependency requires running `uv add <pkg>` inside the product directory to regenerate the lockfile before committing.

3. **Version pinning style**: Runtime dependencies use caret-style ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`) to allow patch/minor updates while blocking major upgrades. Dev-only dependencies live in `[dependency-groups].dev` (PEP 735) and include `pytest`, `jsonschema`, and `fakeredis` where needed.

4. **Python version policy**: Every product sets `requires-python = ">=3.11"` in its `pyproject.toml`, and the root `.python-version` file pins the interpreter for the workspace.

5. **Coordinated platform release**: The root `VERSION` file is the single source of truth for the platform semver. `shared/shared-contracts/scripts/validate_version.py` asserts that every `products/*/pyproject.toml [project] version`, every `src/*/metadata.py SERVICE_VERSION`, any `__version__` in package roots, and the operator portal's Vite wiring all match the root `VERSION`. It is executed as part of `make verify` (which also runs tests, kustomize overlay rendering, and policy validation). This enforces lockstep releases across all services and the portal.

6. **Container images**: Images are built per product via `mk/image.mk` and tagged with a coordinated `IMAGE_TAG` derived from `VERSION` plus git sha/dirty marker. The root `Makefile` writes all image references into `shared/platform-ops/gitops/dev-k8s/.images.env` so GitOps overlays reference consistent versions.

7. **No vendoring / private registry**: Dependencies are pulled from the public PyPI index (`source = { registry = "https://pypi.org/simple" }` in lockfiles). There is no `vendor/` directory, no `pip.conf`/`uv.toml` pointing at a private registry, and no `requirements.txt` files. If a private registry is needed, it would be configured at the uv level (e.g. environment variables or `uv.toml`), but none is present in the repo.

## Conventions and constraints

- **Lockfiles must be committed**: Because `uv sync --frozen` is enforced in CI via `make verify`, any change to `pyproject.toml` must be accompanied by an updated `uv.lock`; otherwise the build fails.
- **Single platform version**: The root `VERSION` file is the only place you set the platform release number. `make validate-version` will fail if any product's `pyproject.toml` version, `SERVICE_VERSION`, or portal build-time version wiring diverges.
- **Dependency groups**: Development-only tools go in `[dependency-groups].dev` rather than the main `dependencies` list, keeping production images lean.
- **Major-version caps**: All runtime dependencies cap their major version (e.g. `<3.0` for pydantic, `<2.0` for opentelemetry-sdk, `<1.0` for fastapi), preventing automatic breaking upgrades.
- **Build backend pinned**: Every product pins `uv_build>=0.8.14,<0.9.0` in `[build-system]`, ensuring reproducible sdist/wheel builds.
- **Portal exception**: The web UI is the only non-Python artifact and is managed separately via npm (`package-lock.json`); it does not participate in the uv lockfile or `make sync` flow.