---
kind: build_system
name: Monorepo Build, Image & GitOps Pipeline via Make + uv + Kustomize
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/Makefile
    - products/platform-gateway/Dockerfile
    - products/agent-platform/pyproject.toml
    - VERSION
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - samples/deploy-samples.sh
---

## What system/approach is used

The Luban AIOps Platform monorepo uses a **Make-driven orchestration layer** over three building blocks:

1. **uv (Python dependency manager)** — every Python product declares `pyproject.toml` + `uv.lock`; `uv sync --frozen` installs dependencies deterministically and `uv run pytest` executes tests.
2. **Docker + multi-stage images** — each product ships a thin `Dockerfile` that layers on a shared base image (`shared/base-images/base-uv`) built from Amazon Linux 2023 minimal with a pinned `uv` binary; images are tagged with a coordinated `<semver>-<prefix>[-<profile>]-<gitsha>` scheme.
3. **Kustomize overlays** — Kubernetes manifests live under `shared/platform-ops/gitops/` as layered overlays (`dev-k8s`, `runtime-profiles/*`); `make overlays` validates them via `kustomize build --load-restrictor LoadRestrictionsNone`.

There is no CI configuration in this repository snapshot (no `.github/workflows`), so the build surface exposed here is the local/CI entrypoint: the root `Makefile` plus per-product `Makefile`s that include shared fragments under `mk/`.

## Key files and packages

- Root orchestrator: `Makefile` — defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`, and top-level targets `sync`, `test`, `lint`, `build`, `push`, `verify`, `deploy`, `e2e`, `deploy-samples`, `undeploy-samples`, `clean`.
- Shared build fragments:
  - `mk/defaults.mk` — single source of truth for overridable settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`).
  - `mk/image.mk` — generic Docker build/push/lint targets; computes `IMAGE_REF` as `luban-aiops/<name>:<tag>` (optionally re-tagged to `$(REGISTRY)/...`).
  - `mk/python.mk` — `sync`/`test` targets that run `uv sync --frozen` then `uv run pytest` with OTel exporters disabled to avoid noise during tracing tests.
- Shared base image: `shared/base-images/base-uv/Dockerfile` — pins `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, creates non-root `app` user (uid 1000).
- Per-product Makefiles (minimal): e.g. `products/agent-platform/Makefile` sets `IMAGE_NAME := agent-service` and includes `../../mk/image.mk` and `../../mk/python.mk`; all eight backend services follow this pattern.
- Product containers: one `Dockerfile` per service (e.g. `products/platform-gateway/Dockerfile`) that copies `.python-version`, `pyproject.toml`, `uv.lock`, `src/`, runs `uv sync --frozen --no-dev`, and `CMD ["uv", "run", <entrypoint>]`.
- Version lock: `VERSION` file at repo root (`0.32.0`) is the single source of truth; `make validate-version` enforces that every product's `pyproject.toml` version matches it via `shared/shared-contracts/scripts/validate_version.py`.
- Policy bundle: canonical policy at `shared/shared-contracts/policies/policy-default.yaml`; `make sync-policy` copies it into `tool-gateway`, `platform-gateway`, and the dev overlay; `make validate-policy` / `validate-policy-scenarios` / `policy-diff` exercise validation scripts under `shared/shared-contracts/scripts/`.
- Deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` wraps `deploy-overlay.sh` and sequentially provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) before reconciling Keycloak realm and portal OIDC client.
- Samples installer: `samples/deploy-samples.sh` packs sample skill `.md` files into a `skills-samples` ConfigMap and restarts `skills-hub`; invoked via `make deploy-samples` / `make undeploy-samples`.

## Architecture and conventions

- **Two-layer Makefile design**: the root `Makefile` owns cross-cutting concerns (coordinated image tagging, policy sync, overlay validation, e2e gate); each product `Makefile` is a 3-line shim declaring `IMAGE_NAME` and including the shared fragments. This keeps product code free of build logic.
- **Coordinated image tagging**: `IMAGE_TAG` is computed once by the root Makefile as `<PLATFORM_VERSION>-<IMAGE_TAG_PREFIX>[-<IMAGE_TAG_PROFILE>]-<gitsha>`, with `-dirty-<timestamp>` appended when `git status --porcelain` reports uncommitted changes. The same tag is applied to every product image and written into `shared/platform-ops/gitops/dev-k8s/.images.env`, which the deploy script consumes.
- **Frozen, reproducible Python builds**: every product pins its exact dependency tree in `uv.lock`; `uv sync --frozen` refuses to resolve anything outside the lock. Base image versions (`BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`) are also pinned defaults in `mk/defaults.mk`.
- **Image platform abstraction**: `IMAGE_PLATFORM ?= linux/amd64` lets developers target `linux/arm64` locally (for kind) while deployment defaults to amd64; `base-images` target rebuilds the shared base image with the chosen platform.
- **Kind auto-loading**: setting `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` after `make build` automatically loads all nine images into the named kind cluster.
- **Policy-as-code distribution**: the canonical policy YAML is the single source; consumers copy it via `make sync-policy`. Validation against JSON schema and scenario evaluation use shared scripts under `shared/shared-contracts/scripts/`.
- **GitOps overlay separation**: base manifests declare deployments/services but never reference specific image tags or samples; overlays inject runtime config/secrets, and samples are installed out-of-band via `deploy-samples.sh` (per SPEC-050 R-11). `make overlays` validates every overlay with `kustomize build`.
- **Verification gate**: `make verify` chains `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version` — intended as the pre-commit/pre-push gate.

## Conventions and constraints

- **Every Python product must**: have a `pyproject.toml` + `uv.lock`, a `Dockerfile` based on `luban-aiops/base-uv:al2023`, a `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`, and a `tests/` directory runnable via `pytest`.
- **Version lockstep**: `VERSION` at the repo root and each product's `pyproject.toml` `[project].version` must match; enforced by `make validate-version`.
- **Image naming**: all images are published under the `luban-aiops/` namespace; when `REGISTRY` is set they are re-tagged to `$(REGISTRY)/luban-aiops/<name>:<tag>` before push.
- **Non-root containers**: the base image switches to `USER app` (uid 1000); products inherit this and should not override it.
- **Deterministic env**: `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=<pinned>`, `UV_PYTHON_INSTALL_DIR=/app/.python` are baked into the base image.
- **Tests suppress OTel exporters**: `mk/python.mk` sets `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` so tracing tests can keep the SDK active without network noise.
- **Samples are decoupled from the base overlay**: `deploy-samples.sh` is the only thing that mounts sample skill files into the cluster; running `make deploy` alone deploys the platform with zero samples.
- **Secret provisioning is opt-in per feature**: `deploy.sh` sources `sync-*.sh` scripts guarded by environment flags (`SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_EXECUTION_SIGNING_SECRET`, `SKIP_EXECUTION_HANDOFF_SECRET`, `SKIP_SKILLS_SECRETS`, `SKIP_INCIDENT_SECRETS`, `SKIP_BROWSER_CREDENTIALS`, `SKIP_OTEL_SECRETS`), allowing CI to skip any secret step.