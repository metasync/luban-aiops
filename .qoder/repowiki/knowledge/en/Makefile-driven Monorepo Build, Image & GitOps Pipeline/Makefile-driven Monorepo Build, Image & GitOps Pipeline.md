---
kind: build_system
name: Makefile-driven Monorepo Build, Image & GitOps Pipeline
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
---

## What system/approach is used

The repository uses a **GNU Make-based monorepo build orchestration** layered on top of per-product `pyproject.toml`/`uv.lock` Python projects and Docker images. There is no CI configuration file in this repo (`.github/` contains only issue templates and a PR template); the root `Makefile` is explicitly designed as a forge-agnostic gate (`make verify`) that runs identically locally and in any CI environment.

Key tools:
- **GNU make** — root orchestrator plus per-product entry points.
- **uv** — Python dependency manager and runner; every product pins dependencies via `uv.lock` and installs with `uv sync --frozen`.
- **Docker** — container image builder for all nine services plus the operator portal web UI.
- **kustomize** — GitOps overlay renderer validated during verification.
- **kind** — optional local Kubernetes cluster loader via `AUTO_LOAD_KIND=true`.
- **hadolint** — Dockerfile linting (with a docker-run fallback).

## Key files and packages

- **Root orchestrator**: `Makefile` — declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, computes a coordinated `IMAGE_TAG` from `VERSION` + git SHA (+ `-dirty-<timestamp>` for unclean trees), writes `.images.env` under `shared/platform-ops/gitops/dev-k8s/`, and dispatches to per-product Makefiles.
- **Shared fragments**:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
  - `mk/image.mk` — shared `build`/`push`/`lint` targets; resolves `IMAGE_REF` as `luban-aiops/<name>:<tag>` (or `<REGISTRY>/luban-aiops/<name>:<tag>` when `REGISTRY` is set).
  - `mk/python.mk` — shared `sync`/`test` targets using `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled so tracing tests still work.
- **Per-product Makefiles** (e.g. `products/platform-gateway/Makefile`) are minimal: they set `IMAGE_NAME` and include both `../../mk/image.mk` and `../../mk/python.mk`.
- **Base image**: `shared/base-images/base-uv/Dockerfile` built by `make base-images`; pinned to `al2023` with `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`.
- **Version pin**: `VERSION` at the repo root (`0.25.0`) is the single source of truth; enforced by `make validate-version` which runs `shared/shared-contracts/scripts/validate_version.py` against it.
- **Policy sync**: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into each consumer's `policies/policy-default.yaml` and the dev-k8s overlay.
- **Deployment**: `shared/platform-ops/gitops/dev-k8s/deploy.sh` wraps `deploy-overlay.sh` and sequentially provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, sessions DB, OTel) before reconciling the Keycloak realm and portal OIDC client.
- **E2E**: `shared/platform-ops/e2e/*.sh` scripts invoked via `make e2e` after `make deploy`.

## Architecture and conventions

1. **Single-tag coordinated builds**: The root `make build` computes one `IMAGE_TAG` (format `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`) and passes it to every product's `make build IMAGE_TAG=...`. All images produced by one invocation share the same tag, and the final tag is recorded in `shared/platform-ops/gitops/dev-k8s/.images.env` for the deploy step.
2. **Per-product isolation with shared fragments**: Each product lives under `products/<name>/` with its own `Dockerfile`, `pyproject.toml`, `uv.lock`, `src/`, `tests/`, and a tiny Makefile that just includes the shared `mk/*` fragments. This keeps product-specific logic out of the root Makefile.
3. **Frozen Python environments**: Every `uv` invocation uses `--frozen`, so builds are reproducible off the lockfile. Dev dependencies are excluded from images (`uv sync --frozen --no-dev` in Dockerfiles).
4. **Platform version lockstep**: `VERSION` must stay in lockstep with every product's declared version; `make validate-version` enforces this invariant via a script in `shared/shared-contracts/scripts/`.
5. **GitOps-first deployment**: Overlays under `shared/platform-ops/gitops/` are rendered with `kustomize build --load-restrictor LoadRestrictionsNone` during `make overlays` (part of `make verify`). Deployment goes through `make deploy` → `dev-k8s/deploy.sh`, which applies the overlay and then provisions secrets idempotently.
6. **Local kind workflow**: Setting `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME=<cluster>` after `make build` automatically loads all built images into the named kind cluster.
7. **Registry re-tagging**: When `REGISTRY` is set, `make push` re-tags local images to `<REGISTRY>/luban-aiops/<name>:<tag>` and pushes them; otherwise images remain local-only.
8. **Verification gate**: `make verify` = `test` + `overlays` + `validate-policy` + `validate-version`. It is intended as the pre-commit/pre-push gate.

## Conventions and constraints

- **Every Python service must have**: a `pyproject.toml` + `uv.lock` under the product dir, a `Dockerfile` based on `luban-aiops/base-uv:al2023`, a `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`, and a `src/<package>/` layout with an executable entry point invoked via `uv run <entrypoint>`.
- **Image naming convention**: Images are tagged `luban-aiops/<product-name>:<coordinated-tag>` locally; when `REGISTRY` is set they become `<REGISTRY>/luban-aiops/<product-name>:<tag>`.
- **No `latest` tags**: `mk/defaults.mk` comments explicitly state that pinned values are defaults for reproducible builds — never `latest`.
- **Cross-platform builds**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64` for native arm64 host/kind builds); the base image target honors it too.
- **Secret provisioning is opt-in per secret**: Each `sync-*` script in `shared/platform-ops/gitops/` supports a `SKIP_*_SECRETS=true` env var to skip provisioning when secrets are injected externally (e.g. by CI).
- **Policy bundle is canonical**: `shared/shared-contracts/policies/policy-default.yaml` is the single source; consumers must keep their copy in sync via `make sync-policy`.
- **E2E requires port-forward prerequisites**: `make e2e` prints explicit `kubectl port-forward` commands for `platform-gateway:18083` and `identity-service:18081` before running demo scripts.