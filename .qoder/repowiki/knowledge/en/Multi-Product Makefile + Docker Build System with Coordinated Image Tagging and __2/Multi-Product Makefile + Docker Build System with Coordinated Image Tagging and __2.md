---
kind: build_system
name: Multi-Product Makefile + Docker Build System with Coordinated Image Tagging and GitOps Deployment
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
    - products/agent-platform/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - VERSION
---

## What system/approach is used

The repository uses a **Makefile-driven, multi-product build system** centered on three layers:

1. **Root `Makefile`** — orchestrates cross-cutting concerns (sync, test, lint, image build/push, policy validation, overlay rendering, deploy, e2e) and delegates per-product work to each product's own `Makefile`.
2. **Shared fragments in `mk/`** — reusable targets for Python (`python.mk`, `uv sync --frozen` + pytest), container images (`image.mk`, docker build/push/lint via hadolint), and overridable defaults (`defaults.mk`).
3. **Per-product `Dockerfile`s** — all backend services are built as container images from a shared base image `shared/base-images/base-uv/Dockerfile` (Amazon Linux 2023 minimal, pinned `uv` 0.12.1, Python 3.12, non-root `app` user).

There is no CI workflow file checked into the repo; the specs reference a `.github/workflows/ci.yml` that was planned but not present in this snapshot. The root `make verify` target is designed to be the pre-commit/pre-push gate run locally or in any CI.

## Key files and packages

- Root orchestration: `Makefile`
- Shared build configuration: `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Shared base image: `shared/base-images/base-uv/Dockerfile`
- Per-product entry points (all follow the same pattern):
  - `products/<name>/Makefile` — sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`
  - `products/<name>/Dockerfile` — copies `.python-version`, `pyproject.toml`, `uv.lock`, `src/`; runs `uv sync --frozen --no-dev`; CMD `uv run <service>`
  - `products/<name>/pyproject.toml` + `uv.lock` — dependency manifest (lockfile)
  - `products/<name>/.python-version` — pins interpreter version per product
- Version single source of truth: `VERSION` (semver)
- Version lockstep enforcement: `shared/shared-contracts/scripts/validate_version.py` (checks `VERSION` against every `products/*/pyproject.toml`, `src/*/metadata.py`, `src/*/__init__.py`, and operator-portal Vite wiring)
- Policy bundle sync/validation: `shared/shared-contracts/policies/policy-default.yaml` plus `sync-policy`, `validate-policy`, `validate-policy-scenarios`, `policy-diff` targets
- GitOps deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` (wraps `deploy-overlay.sh` and provisions secrets via `sync-*` scripts), `kustomize` overlays under `shared/platform-ops/gitops/{dev-k8s,runtime-profiles/*}`
- E2E demos: `shared/platform-ops/e2e/*.sh` invoked via `make e2e`

## Architecture and conventions

### Product structure convention
Every Python service under `products/` follows an identical layout: `src/<service_name>/`, `tests/`, `Dockerfile`, `Makefile`, `pyproject.toml`, `uv.lock`, `.python-version`. The root `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists enumerate them centrally so adding a new product requires updating those two variables only.

### Image tagging strategy
A coordinated tag is computed once by the root `Makefile`:
```
<PLATFORM_VERSION>-<IMAGE_TAG_PREFIX>[-<IMAGE_TAG_PROFILE>]-<git-sha>[-dirty-<timestamp>]
```
The `PLATFORM_VERSION` comes from the root `VERSION` file. All images produced by `make build` share this tag, and the resulting values are written to `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy step references one consistent set of images.

### Base image strategy
All backend services derive from `luban-aiops/base-uv:al2023`, which installs a pinned `uv` binary, creates a non-root `app` user (uid 1000), and sets `UV_PYTHON` / `UV_PYTHON_INSTALL_DIR` so each product resolves its interpreter from its own `.python-version`. No system Python is installed.

### Dependency management
Each product uses `uv` with a frozen lockfile (`uv sync --frozen`). Tests run inside that environment with OTel exporters disabled (`OTEL_TRACES_EXPORTER=none`, etc.) to avoid noise while keeping tracing SDKs active for tracing tests.

### Policy distribution
The canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it into both gateway products and the dev-k8s overlay. `make validate-policy` and `make validate-policy-scenarios` enforce schema and scenario expectations against both engines.

### Secret provisioning during deploy
`make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which calls a sequence of `sync-*-secrets.sh` scripts (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel). Each script supports a `SKIP_*_SECRETS=true` env var for CI environments where secrets are injected externally.

### Version lockstep
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which asserts that every product's `pyproject.toml` version, `SERVICE_VERSION` in `metadata.py`, `__version__` in package roots, and the operator-portal's Vite build-time VERSION read all match the root `VERSION` file exactly. This is enforced as part of `make verify`.

### Overlay validation
`make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` over each overlay listed in `OVERLAYS` (`dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`). Failure aborts the verification gate.

## Conventions and constraints

- **Single source of truth for versions**: `VERSION` at the repo root is the authoritative semver; `make validate-version` enforces lockstep across all products and the portal.
- **Frozen dependencies**: `uv sync --frozen` is used everywhere; no ad-hoc `pip install` without a lockfile.
- **Non-root containers**: All images run as uid 1000 (`app`); enforced by the shared base image.
- **Coordinated image tags**: All images built through `make build` share one tag derived from `VERSION` + git sha; `make push` pushes the whole set.
- **Verification gate**: `make verify` combines `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, and `validate-secret-vocabulary` — intended as the pre-commit/pre-push gate.
- **Policy must be copied from canonical location**: Consumers do not maintain their own policy files; they are synced from `shared/shared-contracts/policies/policy-default.yaml`.
- **Secrets provisioned out-of-band in CI**: Deploy scripts skip secret provisioning when the corresponding `SKIP_*_SECRETS` env var is set, allowing CI to inject secrets via other mechanisms.
- **No system Python in images**: The base image installs only `uv`; Python interpreters are resolved per-product via `.python-version`.
- **Image platform override**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64`) for local kind builds on arm64 hosts.