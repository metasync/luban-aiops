---
kind: build_system
name: Coordinated Makefile + Kustomize Build & Release System
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - products/operator-portal/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/shared-contracts/policies/password-policy.yaml
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - shared/shared-contracts/scripts/validate_password_policy.py
---

## What system/approach is used

The repository uses a **GNU Make–driven coordinated build** layered over per-product `uv` (Python) and Docker builds, with **Kustomize GitOps overlays** for Kubernetes deployment. A single root `Makefile` orchestrates cross-cutting concerns (image tagging, policy sync, version validation, overlay rendering, e2e demos), while each product under `products/<name>/` declares its own lightweight `Makefile` that includes shared fragments from `mk/`. Container images are built via `docker build` against per-product `Dockerfile`s; the operator-portal uses a multi-stage Node+nginx build. Deployment targets are pure Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/`, invoked through `make deploy` which delegates to `deploy.sh`.

## Key files and packages

- Root orchestration: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), computes `IMAGE_TAG` from `VERSION` + git SHA + profile, and wires `sync`, `test`, `lint`, `build`, `push`, `verify`, `deploy`, `e2e`, `policy-*`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, `overlays`, `deploy-samples`, `undeploy-samples`, `deploy-sample-app`.
- Shared build fragments in `mk/`: `defaults.mk` (single source of overridable settings: `IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`), `image.mk` (per-product `build`/`push`/`lint` using `docker build --platform $(IMAGE_PLATFORM)`), `python.mk` (`sync`/`test` via `uv sync --frozen` and `uv run pytest` with OTel exporters disabled).
- Per-product `Makefile`s (e.g. `products/agent-platform/Makefile`) set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`; identical pattern across all eight Python services plus `operator-portal`.
- `Dockerfile`s in each product directory use the shared base image `luban-aiops/base-uv:al2023` (built by `make base-images` from `shared/base-images/base-uv/Dockerfile`) and run `uv sync --frozen --no-dev` at build time; the operator-portal has a separate multi-stage `node:22-alpine` → `nginxinc/nginx-unprivileged` build that injects `PLATFORM_VERSION` from the repo-root `VERSION` file.
- GitOps overlays: `shared/platform-ops/gitops/dev-k8s/kustomization.yaml` plus per-service subdirs (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`, `operator-portal`, `infra/shared`); runtime profiles under `runtime-profiles/{default,mutating-dev,browser-dev}` are validated by `make overlays` via `kustomize build --load-restrictor LoadRestrictionsNone`.
- Version single source of truth: root `VERSION` (currently `0.41.1`), consumed by `PLATFORM_VERSION := $(shell cat VERSION 2>/dev/null)` and enforced by `make validate-version` running `shared/shared-contracts/scripts/validate_version.py`.
- Policy bundle synchronization: canonical `shared/shared-contracts/policies/policy-default.yaml` (and `password-policy.yaml`) copied into `products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` via `make sync-policy`.

## Architecture and conventions

- **Coordinated tagging**: The root `make build` computes one `IMAGE_TAG` per invocation (format `<semver>-<prefix>[-<profile>]-<gitsha>` or `<prefix>-<gitsha>-dirty-<timestamp>` for dirty trees) and writes it to `shared/platform-ops/gitops/dev-k8s/.images.env` along with every product image name, so all services ship as a consistent release. `make push` reuses this tag.
- **Per-product isolation with shared fragments**: Each product only sets `IMAGE_NAME` and includes `mk/image.mk` and `mk/python.mk`; all build logic lives in `mk/`. This makes `make -C products/<name> build` work standalone while still honoring root-level overrides like `IMAGE_PLATFORM` and `REGISTRY`.
- **Frozen dependency resolution**: All Python products pin dependencies via `uv.lock` and install with `uv sync --frozen`; no transitive drift is allowed during build or test.
- **Base image strategy**: A single `base-uv` image (AL2023 + pinned `uv` + Python 3.12) is built once by `make base-images` and reused by every Python service Dockerfile, ensuring reproducible environments.
- **Multi-stage portal build**: The operator-portal build context is the repository root so `vite.config.ts` can read `../../../../VERSION`; the compiled SPA is served by nginx with immutable `/assets/` caching and SPA fallback on `/`.
- **GitOps-first deployment**: There is no Helm chart; `make deploy` runs `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies the Kustomize overlay. Samples are installed out-of-band via `make deploy-samples` so the base overlay never references them (enforced by SPEC-050 R-11).
- **Verification gate**: `make verify` aggregates `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, and `secret-delivery-demo`; this is intended as the pre-commit/pre-push gate and runs identically locally and in CI.
- **Policy as code**: Policy bundles live in `shared/shared-contracts/policies/` and are synced to consumers; `make validate-policy-scenarios` exercises both the API engine (platform-gateway) and tools engine (tool-gateway) against scenario expectations.

## Conventions and constraints

- Every Python product must declare itself in the root `Makefile`'s `PYTHON_PRODUCTS` and/or `IMAGE_PRODUCTS` lists to participate in coordinated builds/tests/lint. (Enforced by the loop targets.)
- Image tags must be derived from the root `VERSION` file; `make validate-version` enforces lockstep between `VERSION`, each product's declared version, and the portal build output.
- All container images must be built with `--platform $(IMAGE_PLATFORM)` (default `linux/amd64`); cross-compilation is supported via the `IMAGE_PLATFORM` override documented in `mk/defaults.mk`.
- Dockerfiles must lint via `hadolint` (with a docker-run fallback) — `make lint` runs this for every `IMAGE_PRODUCT`.
- Secrets and runtime config are not baked into images; they are supplied via Kustomize `runtime-config.env` / `runtime-secrets.example.env` files per service under `shared/platform-ops/gitops/dev-k8s/base/<service>/`.
- Samples (`samples/acme-admin/*`) are intentionally excluded from the base overlay; they are deployed separately via `make deploy-sample-app` and `make deploy-samples`, keeping the production overlay free of sample resources.
- The verification gate (`make verify`) is the authoritative local/CI entry point; any new product or check should be wired into this target rather than ad-hoc scripts.