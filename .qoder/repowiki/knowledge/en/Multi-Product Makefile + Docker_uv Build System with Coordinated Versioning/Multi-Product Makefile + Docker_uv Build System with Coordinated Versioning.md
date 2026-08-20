---
kind: build_system
name: Multi-Product Makefile + Docker/uv Build System with Coordinated Versioning
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/incident-service/Makefile
    - products/incident-service/Dockerfile
    - products/incident-service/pyproject.toml
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - VERSION
---

## What system/approach is used

The repository uses a **GNU Make-based multi-product build orchestration** layered on top of **Docker images built from per-product `Dockerfile`s**, with Python dependency management via **`uv`** (lockfile-driven, `uv sync --frozen`). A root `Makefile` delegates to per-product `Makefile`s and coordinates cross-cutting concerns: shared base image builds, coordinated image tagging, GitOps overlay validation, policy/version checks, and deployment. There is no CI configuration in the repo; the root Makefile's `verify` target (`test`, `overlays`, `validate-policy`, `validate-version`) is designed as the pre-commit/pre-push gate that runs identically locally and under any CI.

## Key files and packages

- `Makefile` — workspace root orchestrator. Declares `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists, computes a coordinated `IMAGE_TAG` from `VERSION` + git SHA (+ `-dirty-<timestamp>` for dirty trees), drives `make -C products/<name>` for each product, writes `.images.env` state consumed by deploy, and exposes `sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `clean`.
- `mk/defaults.mk` — single source of overridable build settings: `IMAGE_PLATFORM`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*` versions, tag prefix/profile defaults.
- `mk/image.mk` — shared container-image targets (`help`, `build`, `push`, `lint`) included by every product Makefile; resolves `IMAGE_REF` against `luban-aiops/*` registry.
- `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` then `uv run pytest`.
- Per-product `products/<name>/Makefile` — minimal, only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`.
- Per-product `Dockerfile` — all follow the same pattern: `FROM luban-aiops/base-uv:al2023`, copy `pyproject.toml`/`uv.lock`/`src`, run `uv sync --frozen --no-dev`, expose 8000, `CMD ["uv", "run", "<entrypoint>"]`.
- `shared/base-images/base-uv/Dockerfile` — shared base image built via `make base-images`.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — wraps `deploy-overlay.sh` and sequentially provisions secrets (delegation, audit, skills, incident, sessions DB, OTel) and reconciles Keycloak portal client.
- `shared/shared-contracts/scripts/validate_version.py` — enforces that `VERSION` at repo root matches every `products/*/pyproject.toml` `[project] version`, every `src/*/metadata.py` `SERVICE_VERSION`, optional `__version__`, and `operator-portal/web-ui/app.js` `PLATFORM_VERSION`.
- `shared/shared-contracts/scripts/validate_policy.py` — validates canonical policy bundle against JSON schema.
- `VERSION` — single semver source of truth read by root Makefile and validated by `validate_version.py`.

## Architecture and conventions

1. **Two-level Makefile hierarchy**: The root `Makefile` owns cross-product coordination; each product Makefile is a thin wrapper that includes shared fragments from `mk/`. This lets you run `make -C products/<name> <target>` standalone or `make <target>` from the repo root to operate on all products.
2. **Coordinated image tagging**: `IMAGE_TAG` is computed once at the root level as `<semver>-<prefix>[-<profile>]-<gitsha>` (or `<prefix>-<gitsha>-dirty-<timestamp>` for uncommitted changes). All images are tagged with this same tag and written into `shared/platform-ops/gitops/dev-k8s/.images.env`, which `deploy.sh` consumes.
3. **Base image strategy**: A single `base-uv` image (AL2023 + pinned `uv` + Python 3.12) is built first (`make base-images`) and reused by every product Dockerfile. Versions are pinned in `mk/defaults.mk` (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`).
4. **Frozen dependencies**: Every product pins exact dependency versions via `uv.lock`; `sync` and `test` use `uv sync --frozen`, ensuring reproducible installs.
5. **Platform abstraction**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64` for native kind builds); `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME` auto-loads built images into a local kind cluster after `make build`.
6. **GitOps overlays as verification**: `make overlays` runs `kustomize build` against every overlay under `shared/platform-ops/gitops/` (`dev-k8s`, `runtime-profiles/dashscope|deepseek|openai`) to fail early on manifest drift.
7. **Version lockstep enforcement**: `make validate-version` calls `validate_version.py`, which reads `VERSION` and asserts it matches every product's `pyproject.toml` version, `metadata.py` `SERVICE_VERSION`, optional `__version__`, and the operator portal's `PLATFORM_VERSION`. Any mismatch causes failure.
8. **Policy synchronization**: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into both gateway consumers and the deployed `policy.yaml`, keeping them in sync.
9. **Deploy flow**: `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders the kustomize overlay and then runs secret-provisioning scripts (skippable via `SKIP_*_SECRETS=true` for CI environments).

## Conventions and constraints

- **Every Python product must declare itself** in the root `Makefile`'s `PYTHON_PRODUCTS` and/or `IMAGE_PRODUCTS` list to participate in `make test` / `make build` / `make push`.
- **Image names** follow the `luban-aiops/<product-name>:<tag>` convention; setting `REGISTRY` re-tags to `$REGISTRY/luban-aiops/<product-name>:<tag>` before pushing.
- **Dockerfiles must use the shared base image** `luban-aiops/base-uv:al2023` and install deps via `uv sync --frozen --no-dev`; they should not pin Python or uv versions themselves.
- **Products must keep their `pyproject.toml` version in lockstep** with the root `VERSION` file; `make validate-version` enforces this across all products and the portal UI.
- **Service metadata modules** must define `SERVICE_VERSION = "<semver>"` matching `VERSION`; `validate_version.py` scans `src/*/metadata.py` for this symbol.
- **Build reproducibility**: No `latest` tags are used anywhere in the build chain — base image tag, uv version, and python version are all pinned in `mk/defaults.mk`.
- **Cross-platform builds**: Use `IMAGE_PLATFORM=linux/arm64` (or other) to target non-amd64; the default is `linux/amd64` because deployments target amd64.
- **Secret provisioning during deploy** is opt-out via environment variables (`SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_SKILLS_SECRETS`, `SKIP_INCIDENT_SECRETS`, `SKIP_OTEL_SECRETS`) so CI pipelines can skip steps where secrets are injected externally.