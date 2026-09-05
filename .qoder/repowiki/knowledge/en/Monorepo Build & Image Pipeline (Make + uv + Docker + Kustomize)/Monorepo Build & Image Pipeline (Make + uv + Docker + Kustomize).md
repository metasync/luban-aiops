---
kind: build_system
name: Monorepo Build & Image Pipeline (Make + uv + Docker + Kustomize)
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
---

## What system/approach is used

The Luban AIOps platform is built as a Python microservices monorepo with a **Make-driven orchestration layer** on top of three core tools:

- **`uv`** for per-product dependency resolution and test execution (`uv sync --frozen`, `uv run pytest`).
- **Docker** for container image builds, using a shared base image `luban-aiops/base-uv:al2023`.
- **Kustomize** for rendering GitOps overlays under `shared/platform-ops/gitops/`.

There is no CI configuration in this repository; the root `Makefile` explicitly states it is "Forge-agnostic" and intended to run identically locally and under any CI via `make verify`.

## Key files and packages

- Root orchestrator: `Makefile` — defines product lists, coordinated image tagging, policy sync, overlay validation, deploy, e2e, and the `verify` gate.
- Shared build fragments in `mk/`:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
  - `mk/image.mk` — reusable `build` / `push` / `lint` targets that every product Makefile includes.
  - `mk/python.mk` — reusable `sync` / `test` targets that freeze deps via `uv sync --frozen` and run pytest with OTel exporters disabled.
- Per-product entry points: each product under `products/<name>/` has a minimal `Makefile` that sets `IMAGE_NAME` and includes both `../../mk/image.mk` and `../../mk/python.mk`; a `Dockerfile` based on `luban-aiops/base-uv:al2023`.
- Version lockstep enforcer: `shared/shared-contracts/scripts/validate_version.py` — reads the single-source `VERSION` file and asserts every product's `pyproject.toml` version, `src/*/metadata.py` `SERVICE_VERSION`, and portal Vite wiring match it.
- Deployment script: `shared/platform-ops/gitops/dev-k8s/deploy.sh` — renders the dev overlay and provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) before reconciling the portal OIDC client.
- Base image definition: `shared/base-images/base-uv/Dockerfile`.

## Architecture and conventions

1. **Product list is centralized.** The root `Makefile` declares `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` tuples; all cross-product commands iterate over them. Adding a new service requires adding it to these lists plus providing a `products/<name>/Makefile`, `Dockerfile`, and `pyproject.toml`.

2. **Coordinated image tagging.** The root computes one `IMAGE_TAG` per invocation using the formula `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` when the working tree has uncommitted changes). All images are built with that tag, then an `.images.env` state file is written at `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy step references exactly the images just built.

3. **Single source of truth for versions.** `VERSION` at the repo root is the canonical semver. `make validate-version` runs `validate_version.py` which checks:
   - Every `products/*/pyproject.toml` `[project] version`.
   - Every `products/*/src/*/metadata.py` `SERVICE_VERSION = ...`.
   - Any `__version__` in package roots.
   - Portal Vite wiring reads the root `VERSION` file at build time.

4. **Policy bundle synchronization.** The canonical policy lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it into `tool-gateway`, `platform-gateway`, and the dev-k8s base overlay. `make validate-policy` and `make validate-policy-scenarios` exercise both engines against the bundle.

5. **Per-product isolation.** Each product owns its own `pyproject.toml` + `uv.lock`, `src/`, `tests/`, `Dockerfile`, and `Makefile`. The root never touches product internals directly — it delegates via `$(MAKE) -C products/$$p <target>`.

6. **Local kind integration.** Setting `AUTO_LOAD_KIND=true` after `make build` auto-loads all nine images into a `kind` cluster named by `KIND_CLUSTER_NAME`.

7. **GitOps overlay validation.** `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` over `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, and `runtime-profiles/browser-dev`.

## Conventions and constraints

- **GNU make required.** The root `Makefile` comments require GNU make; macOS/Linux default shells are assumed.
- **Frozen dependencies.** All Python products use `uv sync --frozen` (no network, no lock drift); tests also re-run `uv sync --frozen` before invoking pytest.
- **No `latest` tags.** `mk/defaults.mk` pins `BASE_UV_TAG=al2023` and `BASE_UV_UV_VERSION=0.12.1`; the comment says pinned values are defaults for reproducible builds — never `latest`.
- **Image platform default is `linux/amd64`**, with `linux/arm64` supported via override for native local/kind builds.
- **Registry push is opt-in.** `REGISTRY` must be set for `docker tag` + `docker push` to execute; otherwise images stay local under `luban-aiops/<name>:<tag>`.
- **Secret provisioning is guarded by skip flags.** `deploy.sh` sources scripts for each secret category and honors `SKIP_*_SECRETS=true` environment variables so CI can bypass local-only provisioning.
- **Verification gate is uniform.** `make verify` runs `test` + `overlays` + `validate-policy` + `validate-policy-scenarios` + `validate-version`; the root Makefile documents it as the pre-commit/pre-push gate.