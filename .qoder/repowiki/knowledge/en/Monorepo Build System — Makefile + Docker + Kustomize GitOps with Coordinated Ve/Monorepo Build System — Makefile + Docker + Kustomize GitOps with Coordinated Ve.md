---
kind: build_system
name: Monorepo Build System — Makefile + Docker + Kustomize GitOps with Coordinated Versioning
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
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## What system/approach is used

The repository uses a **Makefile-driven monorepo build system** layered on top of:
- **Docker** for container image builds, driven by shared `mk/image.mk` fragments included from each product's thin `Makefile`.
- **uv** (astral.sh) as the Python dependency manager and runner; every Python product declares `pyproject.toml` + `uv.lock`, and images install dependencies via `uv sync --frozen --no-dev`.
- **Kustomize** overlays under `shared/platform-ops/gitops/` for Kubernetes manifests; overlay rendering is part of the verification gate.
- A single root `VERSION` file (semver) as the **single source of truth** for all product versions, enforced at build time by `make validate-version`.

There are no CI workflow files in `.github/workflows`; the repo exposes a forge-agnostic `make verify` target intended to run identically locally and in any CI. The `.github/` directory only holds issue templates, a PR template, and `CODEOWNERS`.

## Key files and packages

- Root orchestrator: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), coordinated tag computation, policy sync, overlay validation, version validation, deploy, e2e, and clean targets.
- Shared build fragments in `mk/`:
  - `mk/defaults.mk` — overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
  - `mk/image.mk` — shared `build` / `push` / `lint` targets that produce `luban-aiops/<name>:<tag>` images and optional registry re-tagging.
  - `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `pytest` with OTel exporters disabled.
- Product Makefiles (e.g. `products/platform-gateway/Makefile`) are one-liners setting `IMAGE_NAME` and including both `mk/image.mk` and `mk/python.mk`.
- Base image: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal with pinned `uv` and non-root `app` user; built via `make base-images`.
- Version lockstep enforcement: `shared/shared-contracts/scripts/validate_version.py` checks `VERSION` against every `products/*/pyproject.toml`, `src/*/metadata.py` (`SERVICE_VERSION`), `src/*/__init__.py` (`__version__`), and verifies operator-portal Vite wiring reads the root `VERSION`.
- Deployment pipeline: `shared/platform-ops/gitops/dev-k8s/deploy.sh` calls `deploy-overlay.sh` then provisions secrets (delegation, audit, skills, incidents, sessions DB, OTel) and reconciles Keycloak realm/client.
- Image state bridge: `shared/platform-ops/gitops/dev-k8s/.images.env` — written by `make build` with `IMAGE_TAG` and per-service image refs consumed by the Kustomize overlay.
- Policy synchronization: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into `platform-gateway`, `tool-gateway`, and the Kustomize base.

## Architecture and conventions

### Per-product layout
Every backend service under `products/<name>/` follows the same shape: `src/<package>/`, `tests/`, `Dockerfile`, `Makefile`, `pyproject.toml`, `uv.lock`, `.python-version`. The product `Makefile` never contains build logic — it only sets `IMAGE_NAME` and includes the shared fragments. This makes adding a new product a matter of creating the directory plus a two-line `Makefile`.

### Coordinated tagging
The root `Makefile` computes a single `IMAGE_TAG` once per invocation using the pattern `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`, where semver comes from `VERSION`, prefix/profile come from `IMAGE_TAG_PREFIX`/`IMAGE_TAG_PROFILE`, and git SHA/dirty detection come from `git status`. All images produced by `make build` share this tag, and the resulting `.images.env` is read by the deploy script so every deployed service runs the exact same build.

### Base image strategy
All Python services inherit from `luban-aiops/base-uv:<tag>`, which pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` via build args. Products do not install a system Python; `uv` resolves the interpreter from each product's `.python-version` (or the `UV_PYTHON` env default). Images run as the non-root `app` user (uid 1000).

### Test & lint execution
- `make test` iterates `PYTHON_PRODUCTS` and runs each product's `uv sync --frozen && uv run pytest` with OTel exporters set to `none` so tracing tests pass without an active collector.
- `make lint` runs `hadolint` (with a docker-run fallback) on every product `Dockerfile`.
- `make verify` chains `test`, `overlays` (kustomize build check for all overlays), `validate-policy`, and `validate-version` — intended as the pre-commit/pre-push gate.

### Version lockstep
`make validate-version` enforces that `VERSION` matches every product's `pyproject.toml` `[project] version`, every `src/*/metadata.py` `SERVICE_VERSION`, and any `__version__` in package roots. It also asserts the operator-portal's Vite config still wires `PLATFORM_VERSION` by reading the root `VERSION` file at build time (SPEC-023). Drift causes the gate to fail.

### Policy distribution
Policy bundles live in `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies this canonical file into `platform-gateway`, `tool-gateway`, and the Kustomize base. `make validate-policy` runs `shared/shared-contracts/scripts/validate_policy.py` against it.

### Deploy flow
`make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which:
1. Calls `deploy-overlay.sh` to render and apply Kustomize overlays.
2. Runs a series of `sync-*` scripts to provision secrets (token delegation, audit ingestion, skills credentials, incident credentials, sessions DB, OTel ingest).
3. Optionally reconciles the Keycloak realm and portal OIDC client (`RECONCILE_OIDC_PORTAL_CLIENT=true` by default).

The `dev-k8s` overlay references image names/tags from `.images.env`, ensuring the deployed cluster consumes the images built by `make build`.

### Local kind integration
Setting `AUTO_LOAD_KIND=true` after `make build` auto-loads all built images into a `kind` cluster named by `KIND_CLUSTER_NAME`. `make e2e` then runs demo scripts against the deployed cluster (requires port-forwards for platform-gateway and identity-service).

## Conventions and constraints

- **GNU make required**: documented in the root `Makefile` header; all targets assume GNU make semantics.
- **No `latest` tags**: `mk/defaults.mk` comments explicitly state pinned values are defaults for reproducible builds — never `latest`.
- **Single source of truth for versions**: `VERSION` is the authoritative semver; `make validate-version` enforces lockstep across all products and the portal.
- **Frozen Python deps**: `uv sync --frozen` is used everywhere (build, test, dev); `uv.lock` must be committed alongside changes.
- **Image naming convention**: local images are always `luban-aiops/<product>:<tag>`; pushing requires setting `REGISTRY` to trigger re-tagging to `<REGISTRY>/luban-aiops/<product>:<tag>`.
- **Overlay validation is mandatory**: `make verify` fails if any Kustomize overlay does not render cleanly.
- **Policy must be synchronized**: consumers copy the canonical policy via `make sync-policy`; drift is caught by `validate-policy`.
- **Deploy is idempotent**: secret-sync scripts are designed to be re-run safely; the deployment script skips external-secret injection when `SKIP_*_SECRETS=true` (used in CI).
- **Products must follow the template**: new services should mirror the existing product layout and use the shared `mk/image.mk` + `mk/python.mk` fragments rather than defining custom build rules.