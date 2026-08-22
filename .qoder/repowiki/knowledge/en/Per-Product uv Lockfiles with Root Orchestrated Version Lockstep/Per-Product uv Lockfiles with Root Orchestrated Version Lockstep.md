---
kind: dependency_management
name: Per-Product uv Lockfiles with Root Orchestrated Version Lockstep
category: dependency_management
scope:
    - '**'
source_files:
    - Makefile
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/audit-service/pyproject.toml
    - products/incident-service/pyproject.toml
    - products/identity-broker/pyproject.toml
    - products/skills-hub/pyproject.toml
---

## System / Approach

The monorepo manages Python dependencies per product using **uv** (the fast Python package installer and resolver) with PEP 621 `pyproject.toml` manifests and per-product `uv.lock` lockfiles. There is no workspace-level lockfile; each product under `products/<name>/` declares its own dependency graph, and the root Makefile orchestrates them uniformly.

## Key Files

- Per-product dependency manifests: `products/*/pyproject.toml` — declare runtime dependencies, dev dependency groups (`[dependency-groups] dev = [...]`), entry-point scripts (`[project.scripts]`), and build backend (`uv_build`).
- Per-product lockfiles: `products/*/uv.lock` — fully pinned transitive resolution from PyPI (`https://pypi.org/simple`); includes hash digests for every wheel/sdist so installs are reproducible.
- Shared uv invocation: `mk/python.mk` — defines `sync` and `test` targets that run `uv sync --frozen` (refusing any drift between `pyproject.toml` and `uv.lock`) and then `uv run pytest` with OTel exporters disabled in tests.
- Root orchestration: `Makefile` — lists `PYTHON_PRODUCTS := agent-platform audit-service identity-broker incident-service platform-gateway skills-hub tool-gateway`, runs `make -C products/$p sync` and `test` across all of them, and exposes `make verify` as the pre-commit/pre-push gate.
- Version lockstep enforcement: `shared/shared-contracts/scripts/validate_version.py` + `VERSION` at repo root — a single source-of-truth semver checked against every `products/*/pyproject.toml` `[project] version`, every `src/*/metadata.py` `SERVICE_VERSION`, optional `__version__` dunders, and `operator-portal/web-ui/app.js` `PLATFORM_VERSION`; invoked via `make validate-version`.
- Container image pipeline: `mk/image.mk` — builds Docker images per product using a shared base image `shared/base-images/base-uv` built from `shared/base-images/base-uv/Dockerfile`; tags are coordinated by the root `Makefile` into `.images.env` and deployed via Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/`.

## Architecture and Conventions

- **One manifest per product**: Each service owns its own `pyproject.toml` and `uv.lock`. Dependencies are declared with upper-bound major-version caps (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`) to prevent automatic major upgrades while allowing patch/minor refreshes.
- **Frozen installs everywhere**: `uv sync --frozen` is used in both local development (`make sync`) and CI (`make test`), meaning the lockfile is authoritative and cannot be silently drifted during install.
- **Dev vs runtime separation**: Runtime deps live under `[project].dependencies`; testing-only packages (`pytest`, `jsonschema`, `fakeredis`) live under `[dependency-groups] dev = [...]` and are only installed when requested by `uv run` or explicitly selected.
- **No vendoring / no private registry**: All packages resolve from `https://pypi.org/simple`; there is no `pip.conf`, `uv.config.toml`, `--index-url`, `GOFLAGS=-insecure`, or vendor directory. The lockfile pins exact versions and hashes instead.
- **Shared base image strategy**: Instead of sharing Python packages across containers, each product's Dockerfile pulls a common `base-uv` image (built once via `make base-images`) that contains a known Python + uv installation; `uv sync --frozen` then installs the locked deps inside the image.
- **Coordinated release versioning**: The root `VERSION` file is the single source of truth. `make validate-version` (part of `make verify`) fails if any product's `pyproject.toml` version, metadata module, or portal JS constant diverges from it, enforcing lockstep releases across all services.
- **Policy-as-code co-location**: Policy bundles are also centrally managed — `shared/shared-contracts/policies/policy-default.yaml` is copied to consumers via `make sync-policy`, mirroring the dependency-management pattern of a canonical source plus generated copies.

## Conventions and Constraints

- Every Python product must include `include ../../mk/python.mk` and `include ../../mk/image.mk` to inherit the standardized `sync`, `test`, `build`, `push`, `lint` targets.
- Dependency specifiers must use caret-style ranges with an explicit upper bound on the major version (observed consistently across all `pyproject.toml` files).
- `uv.lock` must be committed alongside `pyproject.toml`; `uv sync --frozen` will fail if the lockfile does not match the manifest, preventing accidental drift.
- New products must register themselves in the root `Makefile`'s `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists to participate in the coordinated `sync`, `test`, `build`, `push`, and `verify` gates.
- The `validate_version.py` script enforces that `VERSION`, all product `pyproject.toml` versions, `SERVICE_VERSION` constants in `src/*/metadata.py`, optional `__version__` entries, and the operator portal's `PLATFORM_VERSION` stay identical; `make validate-version` is part of the `verify` target, making this a hard gate before merge/deploy.
- Tests run with OpenTelemetry exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) to keep output clean while keeping the SDK active for tracing assertions.