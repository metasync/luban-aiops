---
kind: build_system
name: Makefile-Driven Multi-Product Build, Containerization & GitOps Deploy Pipeline
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
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/Makefile
    - products/tool-gateway/Makefile
    - products/identity-broker/Makefile
    - products/operator-portal/Makefile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/deploy-overlay.sh
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

The repository uses a **GNU Make–driven multi-product build system** layered on top of three toolchains: `uv` for Python dependency resolution and test execution, Docker for container image builds, and Kustomize for Kubernetes overlay rendering. A single root `Makefile` orchestrates cross-cutting concerns (coordinated image tagging, policy sync, overlay validation, deploy) while delegating per-product routines to shared fragments under `mk/`. Deployment to Kubernetes is performed via the `shared/platform-ops/gitops` Kustomize overlays and helper scripts (`deploy-overlay.sh`, `deploy.sh`). There is no CI pipeline file in `.github/workflows`; the verification gate is the local `make verify` target intended to run identically in any forge.

## Key files and packages

- Root orchestration: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), coordinated tag computation, `build`, `push`, `verify`, `sync-policy`, `overlays`, `deploy`, and `clean` targets.
- Shared build fragments:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, `BASE_UV_*`); guarded against double inclusion via `LUBAN_DEFAULTS_INCLUDED`.
  - `mk/image.mk` — per-product container-image targets (`build`, `push`, `lint`) that resolve `IMAGE_REF` from `luban-aiops/<name>:<tag>` (or `<REGISTRY>/luban-aiops/<name>:<tag>`), defaulting tag to short git SHA.
  - `mk/python.mk` — `sync` (`uv sync --frozen`) and `test` (`uv sync --frozen && uv run pytest`) targets for Python products.
- Per-product Makefiles (e.g. `products/agent-platform/Makefile`, `products/platform-gateway/Makefile`, `products/tool-gateway/Makefile`, `products/identity-broker/Makefile`, `products/operator-portal/Makefile`) set only `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`.
- Base image: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal with pinned `uv` (via `UV_VERSION` build arg), non-root `app` user (uid 1000), env vars pinning `UV_PYTHON`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Product images: each product's `Dockerfile` (e.g. `products/agent-platform/Dockerfile`) inherits `luban-aiops/base-uv:al2023`, copies `pyproject.toml` + `uv.lock` + `src`, runs `uv sync --frozen --no-dev`, and exposes port 8000.
- Dependency manifests: per-product `pyproject.toml` + `uv.lock` (e.g. `products/agent-platform/pyproject.toml`) define dependencies, entry points, and `[dependency-groups] dev` for tests.
- GitOps deployment:
  - `shared/platform-ops/gitops/dev-k8s/kustomization.yaml` — namespace `dev-luban-aiops`, includes `base` and a runtime profile overlay.
  - `shared/platform-ops/gitops/deploy-overlay.sh` — reads `.images.env`, applies `kubectl apply -k`, then patches all five deployments' images via `kubectl set image` and waits with `rollout status`.
  - `shared/platform-ops/gitops/dev-k8s/deploy.sh` — invokes `deploy-overlay.sh`, optionally provisions token-delegation secrets, and reconciles the portal OIDC client.
- Policy synchronization: root `Makefile` declares `POLICY_CANONICAL := shared/shared-contracts/policies/policy-default.yaml` and `sync-policy` copies it into `tool-gateway`, `platform-gateway`, and the k8s base overlay; `validate-policy` runs `shared/shared-contracts/scripts/validate_policy.py`.

## Architecture and conventions

- **Coordinated tagging**: The root `Makefile` computes a single `IMAGE_TAG` once using `IMAGE_TAG_PREFIX` (+ optional `IMAGE_TAG_PROFILE`), the current git short SHA, and a `-dirty-YYYYMMDDHHMMSS` suffix when the working tree has uncommitted changes. This tag is written to `shared/platform-ops/gitops/dev-k8s/.images.env` alongside per-service image names, which `deploy-overlay.sh` consumes to patch every deployment consistently.
- **Layered Makefile design**: Product Makefiles are thin shells that only declare `IMAGE_NAME` and include shared fragments; all logic lives in `mk/*.mk`. Defaults live exclusively in `mk/defaults.mk` and are included by both the root Makefile and the fragments so standalone `make -C products/<name>` resolves identical values.
- **Frozen Python builds**: All dependency installation uses `uv sync --frozen`, pinning to `uv.lock`. Production images add `--no-dev` to exclude test dependencies.
- **Base image strategy**: All backend services derive from the custom `luban-aiops/base-uv:al2023` image built from `shared/base-images/base-uv/Dockerfile`, which pins `uv` version and Python version via `--build-arg` and sets deterministic `UV_*` environment variables. The base image is built first via `make base-images` before `make build`.
- **Multi-target platform**: `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64` for native kind builds). The root `build` target passes it through to each product's `docker build`.
- **Kind integration**: When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all five images into the named kind cluster after building them locally.
- **Policy as code**: The canonical policy YAML lives in `shared/shared-contracts/policies/policy-default.yaml` and is duplicated into consumers via `make sync-policy`; schema validation is enforced via `make validate-policy`.
- **Overlay validation**: `make overlays` runs `kustomize build` against every overlay listed in `OVERLAYS` (`dev-k8s`, `runtime-profiles/dashscope|deepseek|openai`) as part of the verification gate.

## Conventions and constraints

- **Products must follow the fragment contract**: Each product Makefile must set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`; adding a new product requires listing it in `PYTHON_PRODUCTS` and/or `IMAGE_PRODUCTS` at the root `Makefile`.
- **No unpinned base images**: `mk/defaults.mk` comments explicitly state "never `latest"`; base image versions are controlled via `BASE_UV_IMAGE` / `BASE_UV_TAG` build args.
- **Deterministic tags**: Image tags are derived deterministically from git SHA plus dirty-state timestamp; overriding `IMAGE_TAG` on the command line is supported but the computed value is the default.
- **Registry re-tagging**: Setting `REGISTRY` causes `make push` to re-tag images as `<REGISTRY>/luban-aiops/<name>:<tag>` before pushing; without it, images remain local under `luban-aiops/...`.
- **Deployment requires prior build**: `deploy-overlay.sh` aborts if `.images.env` does not contain `IMAGE_TAG`; users must run `make build` (or export `IMAGE_TAG`) before deploying.
- **Namespace convention**: Deployments target `dev-luban-aiops` by default (configurable via `NAMESPACE`); overlays and `deploy.sh` assume this namespace.
- **Verification gate**: `make verify` runs `test` (all Python products), `overlays` (kustomize render check), and `validate-policy` (policy JSON schema validation); this is documented as the pre-commit/pre-push gate.
- **Non-root containers**: The base image creates an `app` user (uid 1000) and switches to it; product images inherit this user.
- **No CI workflow files present**: No GitHub Actions workflows were found under `.github/workflows`; the build system is designed to be forge-agnostic and invoked locally or by external CI.