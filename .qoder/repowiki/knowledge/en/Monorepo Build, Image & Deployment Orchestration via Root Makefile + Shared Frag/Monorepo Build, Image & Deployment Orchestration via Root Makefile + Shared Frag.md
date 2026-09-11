---
kind: build_system
name: Monorepo Build, Image & Deployment Orchestration via Root Makefile + Shared Fragments
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
    - products/operator-portal/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - VERSION
---

## What system/approach is used

The repository uses a **Make-driven monorepo build system** centered on a root `Makefile` that orchestrates nine Python services and one web portal. Each product lives under `products/<name>/` with its own `pyproject.toml`, `uv.lock`, `Dockerfile`, and thin `Makefile`. Cross-cutting build logic is factored into shared fragments under `mk/` (`defaults.mk`, `image.mk`, `python.mk`) so that both root-level orchestration and standalone per-product invocations (`make -C products/<name>`) resolve identical defaults.

- **Dependency management**: `uv` (with `uv sync --frozen`) against per-product `uv.lock` files; the base image pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`.
- **Container images**: Docker builds driven by `mk/image.mk`; all backend services extend a shared `shared/base-images/base-uv/Dockerfile` (Amazon Linux 2023 minimal, non-root `app` user). The operator portal uses a multi-stage Node+nginx build.
- **Versioning**: A single source of truth at the repo root `VERSION` file (semver, e.g. `0.35.0`). The root Makefile computes a coordinated `IMAGE_TAG` as `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for dirty trees) and enforces lockstep between `VERSION`, each product's version, and the portal via `make validate-version`.
- **Deployment**: GitOps-style overlays under `shared/platform-ops/gitops/` validated with `kustomize build` during verification. `make deploy` runs `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies the overlay and then provisions secrets (OIDC, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) via sibling scripts.
- **Verification gate**: `make verify` aggregates `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, and `validate-secret-vocabulary` — designed to be the pre-commit/pre-push gate run identically locally and in CI.

## Key files and packages

- `Makefile` — root orchestrator: lists `PYTHON_PRODUCTS` / `IMAGE_PRODUCTS`, computes `IMAGE_TAG`, delegates per-product `build`/`push`/`test`/`lint`, writes `.images.env` state, runs policy/version validation, renders Kustomize overlays, deploys dev cluster.
- `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- `mk/image.mk` — shared `build`/`push`/`lint` targets using `docker build --platform $(IMAGE_PLATFORM)`; supports optional registry re-tag/push.
- `mk/python.mk` — shared `sync`/`test` targets running `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled.
- `shared/base-images/base-uv/Dockerfile` — pinned base image (AL2023, uv 0.12.1, Python 3.12, non-root `app` user).
- `products/*/Makefile` — thin wrappers setting `IMAGE_NAME` and including `../../mk/image.mk` and `../../mk/python.mk`.
- `products/*/Dockerfile` — uniform layout: copy `.python-version`, `pyproject.toml`, `uv.lock`, `src/`; run `uv sync --frozen --no-dev`; `CMD ["uv", "run", ...]`.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — deployment entrypoint applying overlay and provisioning secrets via `sync-*` scripts.
- `VERSION` — single semver source consumed by root Makefile and injected into the portal build.
- `shared/shared-contracts/scripts/validate_version.py`, `validate_policy*.py`, `validate_secret_vocabulary.py` — enforcement scripts invoked from root Makefile targets.

## Architecture and conventions

1. **Per-product isolation with shared fragments**: Every product has an identical Makefile shape (set `IMAGE_NAME`, include `mk/image.mk` + `mk/python.mk`). This lets developers run `make test` or `make build` inside any product directory without knowing about the monorepo.
2. **Coordinated tagging**: The root `make build` computes one `IMAGE_TAG` once and passes it to every product, guaranteeing all images share the same tag. The resulting tag is written to `shared/platform-ops/gitops/dev-k8s/.images.env` and referenced by the deploy script.
3. **Base image strategy**: All Python services derive from `luban-aiops/base-uv:al2023`, built once via `make base-images`. The base image pins uv and Python versions, creates a non-root `app` user, and sets `UV_LINK_MODE=copy` / `UV_NO_SYNC=1` for reproducible containers.
4. **GitOps-first deployment**: Overlays under `shared/platform-ops/gitops/` are treated as immutable manifests; `make overlays` fails if any overlay no longer renders (`kustomize build --load-restrictor LoadRestrictionsNone`). Secrets are provisioned imperatively by `deploy.sh` helper scripts, each guarded by a `SKIP_*_SECRETS=true` env var for CI.
5. **Policy-as-code synchronization**: A canonical policy bundle lives in `shared/shared-contracts/policies/policy-default.yaml`; `make sync-policy` copies it to `tool-gateway`, `platform-gateway`, and the dev overlay. `make validate-policy*` exercises both engines against scenario expectations.
6. **Kind integration**: When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all built images into the named kind cluster after building.
7. **E2E suite**: `make e2e` runs demo scripts under `shared/platform-ops/e2e/` against a deployed dev cluster (requires prior `make deploy` and port-forwarding).

## Conventions and constraints

- **GNU make required**: The root Makefile comment states it requires GNU make (default on macOS/Linux); all shell snippets use `#!/bin/sh`.
- **Frozen dependencies**: Python products must use `uv sync --frozen` (enforced in both `mk/python.mk` and product Dockerfiles) — no ad-hoc dependency resolution.
- **No `latest` tags**: `mk/defaults.mk` comments explicitly state pinned values are defaults for reproducible builds — never `latest`.
- **Single version source**: `VERSION` is the single source of truth; `make validate-version` enforces lockstep across all products and the portal.
- **Image naming convention**: Images are tagged `luban-aiops/<service>:<tag>` locally; when `REGISTRY` is set they are re-tagged to `<REGISTRY>/luban-aiops/<service>:<tag>` before push.
- **Non-root runtime**: Base image switches to `USER app` (uid 1000); product images inherit this posture.
- **Verification gate contract**: `make verify` is documented as the pre-commit/pre-push gate and must run identically locally and under any CI — it combines tests, overlay rendering, policy validation, version lockstep, and secret vocabulary checks.
- **Overlay immutability**: Kustomize overlays are validated with `LoadRestrictionsNone` to ensure they render independently of external resources; failures block the verify pipeline.
- **Secret provisioning guards**: Each `sync-*` script in `shared/platform-ops/gitops/` respects a `SKIP_*_SECRETS=true` environment variable so CI can skip provisioning when secrets are injected externally.