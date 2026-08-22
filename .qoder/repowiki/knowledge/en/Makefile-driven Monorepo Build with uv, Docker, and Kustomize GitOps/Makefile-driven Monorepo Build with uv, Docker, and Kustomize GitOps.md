---
kind: build_system
name: Makefile-driven Monorepo Build with uv, Docker, and Kustomize GitOps
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
    - products/agent-platform/Dockerfile
    - products/agent-platform/pyproject.toml
    - shared/platform-ops/gitops/deploy-overlay.sh
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - VERSION
---

## What system/approach is used

The repository uses a **Makefile-centric monorepo build system** that orchestrates three layers:

1. **Python packaging & testing via `uv`** — each product under `products/<name>/` declares its own `pyproject.toml` + `uv.lock`, and the shared fragment `mk/python.mk` provides `sync`/`test` targets that run `uv sync --frozen` then `uv run pytest` with OTLP exporters disabled.
2. **Container image builds via Docker** — every product ships a minimal `Dockerfile` based on a shared base image (`shared/base-images/base-uv/Dockerfile`) built from Amazon Linux 2023 with a pinned `uv` (0.12.1) and Python 3.12; images are tagged `luban-aiops/<service>:<IMAGE_TAG>` and optionally re-tagged to a `REGISTRY`.
3. **Kubernetes deployment via Kustomize overlays** — `shared/platform-ops/gitops/dev-k8s/` holds the base overlay plus runtime-profile overlays (dashscope, deepseek, openai, mutating-dev); deployment is driven by `shared/platform-ops/gitops/deploy-overlay.sh`, which renders overlays with `kubectl kustomize --load-restrictor LoadRestrictionsNone`, applies them, and then `kubectl set image` for every service using coordinated tags written by `make build`.

There is no CI configuration in this snapshot (no `.github/workflows`), so the build surface exposed here is the local Makefile gate.

## Key files and packages

- Root orchestration: `Makefile` — defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`, computes a coordinated `IMAGE_TAG` from `VERSION` + git SHA (+ `-dirty-<timestamp>` for dirty trees), and dispatches per-product make invocations.
- Shared fragments: `mk/defaults.mk` (all overridable defaults like `IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`), `mk/image.mk` (per-product `build`/`push`/`lint` targets), `mk/python.mk` (`sync`/`test`).
- Base image: `shared/base-images/base-uv/Dockerfile` — single source of truth for the Python runtime layer; built via `make base-images`.
- Product manifests: each `products/<name>/Makefile` sets `IMAGE_NAME` and includes both `../../mk/image.mk` and `../../mk/python.mk`; `pyproject.toml` pins versions and entry points.
- Deployment scripts: `shared/platform-ops/gitops/deploy-overlay.sh` (renders overlay, applies, restarts deployments when ConfigMaps change), `dev-k8s/deploy.sh` (orchestrates secret provisioning and OIDC client reconciliation).
- Version lock: root `VERSION` file (currently `0.8.0`) is the single source of truth; `make validate-version` enforces it matches every product's `pyproject.toml` version via `shared/shared-contracts/scripts/validate_version.py`.
- Policy sync: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.

## Architecture and conventions

- **Two-level Makefile**: the root `Makefile` owns cross-cutting concerns (coordinated tagging, policy sync, overlay validation, e2e demos) and delegates per-product work to `make -C products/<name>`. Each product Makefile is a thin shim that only sets `IMAGE_NAME` and includes shared fragments.
- **Coordinated image tagging**: `IMAGE_TAG` is computed once at the root as `<semver>-<prefix>[-<profile>]-<gitsha>` (or `<prefix>-<gitsha>-dirty-<timestamp>` for dirty trees). The same tag is applied to all eight services (`agent-service`, `platform-gateway`, `tool-gateway`, `identity-service`, `audit-service`, `skills-hub`, `incident-service`, `web-ui`) and persisted to `shared/platform-ops/gitops/dev-k8s/.images.env`, which `deploy-overlay.sh` sources before applying overlays.
- **Reproducible base image**: the base image is built separately (`make base-images`) with pinned `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` passed as `--build-arg`; product images use `uv sync --frozen --no-dev` to pin dependencies exactly.
- **Non-root containers**: the base image creates an `app` user (uid 1000) and switches to it; all product images inherit this.
- **Kustomize-only Kubernetes config**: overlays live under `shared/platform-ops/gitops/`, with a `base/` directory per service plus a `shared/` ConfigMap area. Runtime profiles (dashscope, deepseek, openai, mutating-dev) are separate overlays layered on top.
- **Secrets provisioning is script-driven**: `deploy.sh` calls `sync-*-secrets.sh` scripts for token delegation, audit ingestion, skills credentials, incident intake, sessions DB, and OTel ingest; each supports a `SKIP_*_SECRETS=true` env var for CI where secrets are injected externally.
- **Policy bundle is single-sourced**: the canonical policy lives in `shared/shared-contracts/policies/policy-default.yaml`; consumers copy it via `make sync-policy` and validate against a JSON schema via `make validate-policy`.

## Conventions and constraints

- **Every Python product must have a `pyproject.toml` + `uv.lock`** and expose `sync`/`test` targets through `mk/python.mk`; adding a new product requires listing it in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` in the root `Makefile`.
- **Image builds must use the shared base image** `luban-aiops/base-uv:al2023`; product Dockerfiles follow the same pattern: copy `.python-version`, `pyproject.toml`, `uv.lock`, `src/`, run `uv sync --frozen --no-dev`, and `EXPOSE 8000`.
- **Version lockstep is enforced**: `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root; the `VERSION` file must match every product's `[project].version`.
- **Overlays must render cleanly**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on every overlay listed in `OVERLAYS`; failure blocks the verification gate.
- **Verification gate**: `make verify` runs `test` + `overlays` + `validate-policy` + `validate-version` — this is documented as the pre-commit/pre-push gate and is intended to be identical locally and in CI.
- **Deploy requires prior build**: `deploy-overlay.sh` aborts if `.images.env` does not contain `IMAGE_TAG`, enforcing the `make build` → `make deploy` sequence.
- **Config changes trigger rollouts**: after applying an overlay, the deploy script detects changes to `configmap/platform-runtime-config` or `configmap/platform-policy` and explicitly `rollout restart` all app deployments so env/policy updates take effect without manual intervention.
- **Multi-platform builds**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64` for native kind builds); `AUTO_LOAD_KIND=true` with `KIND_CLUSTER_NAME` auto-loads built images into a local kind cluster after `make build`.