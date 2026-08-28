---
kind: build_system
name: Multi-Product Makefile + Docker Build System with Coordinated Versioning
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - VERSION
---

## What system/approach is used

The repository uses a **GNU make-based multi-product build** that coordinates Python packaging (via `uv`), container image builds (via `docker`), and GitOps overlay rendering (via `kustomize`). There is no CI pipeline file in `.github/`; the root `Makefile` defines a single verification gate (`make verify`) intended to run identically locally and under any CI, as documented in its header comment.

Key tools:
- `make` (GNU make) — orchestration layer at root and per-product level
- `uv` — Python dependency resolver and runner; all products use `uv sync --frozen` against a pinned `uv.lock`
- `docker` — container image builder for every product
- `kustomize` — renders GitOps overlays under `shared/platform-ops/gitops`
- `hadolint` — Dockerfile linting (with a docker-run fallback)
- A custom Python script `shared/shared-contracts/scripts/validate_version.py` — enforces version lockstep across the workspace

## Key files and packages

- Root orchestrator: `Makefile` — declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, computes a coordinated `IMAGE_TAG` from `VERSION` + git SHA + dirty flag, and delegates to per-product Makefiles via `$(MAKE) -C products/$$p ...`
- Shared fragments in `mk/`:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, etc.) included by both root and product builds
  - `mk/image.mk` — shared `build` / `push` / `lint` targets; resolves `IMAGE_REF` based on whether `REGISTRY` is set; requires each including Makefile to set `IMAGE_NAME`
  - `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` then `uv run pytest`
- Per-product Makefiles are minimal stubs that only set `IMAGE_NAME` and include the two fragments (e.g. `products/platform-gateway/Makefile`)
- Base image: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal with a pinned `uv` binary, non-root `app` user (uid 1000), and env vars pinning `UV_PYTHON=3.12` and install dir `/app/.python`
- Product Dockerfiles follow a uniform pattern: `FROM luban-aiops/base-uv:al2023`, copy `pyproject.toml` + `uv.lock` first, run `uv sync --frozen --no-dev`, then copy `src/` and `CMD ["uv", "run", "<entrypoint>"]`
- Version enforcement: `VERSION` (root semver), `shared/shared-contracts/scripts/validate_version.py` which checks it against every `products/*/pyproject.toml`, every `products/*/src/*/metadata.py` (`SERVICE_VERSION`), any `__version__` in package roots, and `operator-portal/web-ui/app.js` (`PLATFORM_VERSION`)
- Policy synchronization: `sync-policy` target copies `shared/shared-contracts/policies/policy-default.yaml` into `tool-gateway`, `platform-gateway`, and the GitOps base `policy.yaml`

## Architecture and conventions

1. **Two-level Makefile hierarchy.** The root `Makefile` owns cross-cutting concerns (image tagging, coordinated build/push, policy sync, overlay validation, deploy). Each product has a tiny Makefile that just sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. This lets you run `make -C products/<name>` standalone or `make test` / `make build` from the repo root.

2. **Coordinated image tagging.** `IMAGE_TAG` is computed once per invocation as `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`. The root `make build` passes this tag to every product so all images share one tag, then writes an `.images.env` state file consumed by `deploy.sh`.

3. **Single base image strategy.** All backend services derive from `luban-aiops/base-uv:al2023`, built via `make base-images`. The base image pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` via build args and environment variables, ensuring deterministic installs without a system Python.

4. **Frozen Python dependencies.** Every product uses `uv sync --frozen`, meaning `uv.lock` is the authoritative dependency graph and must be committed alongside changes. Tests also call `uv sync --frozen` before `uv run pytest`.

5. **GitOps-first deployment.** After `make build`, `make deploy` runs `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which reads the `.images.env` produced by the coordinated build. Overlay rendering is validated via `make overlays` (runs `kustomize build --load-restrictor LoadRestrictionsNone` for each overlay).

6. **Version lockstep enforced at build time.** `make validate-version` runs the shared script that parses `VERSION` and asserts every product's `pyproject.toml` version, `metadata.py` `SERVICE_VERSION`, optional `__version__`, and the portal's `PLATFORM_VERSION` match exactly. The root `verify` target chains `test`, `overlays`, `validate-policy`, and `validate-version` as the pre-commit/pre-push gate.

7. **Policy-as-code distribution.** The canonical policy bundle lives in `shared/shared-contracts/policies/policy-default.yaml`; `make sync-policy` copies it into consumer locations. `make validate-policy` validates it against the JSON schema in `shared/shared-contracts/scripts/validate_policy.py`.

## Conventions and constraints

- **Every product directory must contain**: a `Dockerfile`, a `Makefile` that sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`, a `pyproject.toml` with a `[project] version`, a `uv.lock`, and a `src/<package>/metadata.py` defining `SERVICE_VERSION`.
- **Image tags must never use `latest`**; `mk/defaults.mk` documents that pinned values are required for reproducible builds, and the root `IMAGE_TAG` computation always produces a sha-prefixed tag.
- **Build platform is configurable but defaults to `linux/amd64`**; override via `IMAGE_PLATFORM=linux/arm64` for native arm64/kind builds.
- **Registry push is opt-in**: `REGISTRY=` empty means images stay local; setting it causes `make build` to re-tag and `make push` to push the fully qualified reference.
- **Local kind integration**: `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` after `make build` auto-loads all images into the named kind cluster.
- **Verification gate**: `make verify` (and thus any pre-commit hook using it) must pass tests, kustomize overlay rendering, policy validation, and version lockstep — all four must succeed for a change to be considered verified.
- **Base image rebuild**: Changing `BASE_UV_UV_VERSION` or `BASE_UV_PYTHON_VERSION` in `mk/defaults.mk` requires rebuilding the base image via `make base-images` before building products.