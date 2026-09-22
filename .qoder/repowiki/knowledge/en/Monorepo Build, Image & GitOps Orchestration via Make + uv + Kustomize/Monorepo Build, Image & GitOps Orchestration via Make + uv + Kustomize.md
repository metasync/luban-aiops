---
kind: build_system
name: Monorepo Build, Image & GitOps Orchestration via Make + uv + Kustomize
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - VERSION
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - products/agent-platform/pyproject.toml
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/shared-contracts/policies/password-policy.yaml
    - shared/shared-contracts/scripts/validate_version.py
---

## What system/approach is used

The repository uses a **Make-driven monorepo build surface** that coordinates nine Python services and one Node-based portal through three layers:

1. **Root `Makefile`** — the single entry point for workspace-wide operations (`sync`, `test`, `build`, `push`, `verify`, `deploy`, `e2e`). It enumerates `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS`, computes a coordinated `IMAGE_TAG` from the root `VERSION` file plus git SHA (with `-dirty-<timestamp>` suffix on uncommitted changes), and writes an `.images.env` state file consumed by deployment.
2. **Shared fragments in `mk/`** — reusable make targets split by concern: `image.mk` (Docker build/push/lint with `--platform $(IMAGE_PLATFORM)`), `python.mk` (`uv sync --frozen` + pytest with OTel exporters disabled), and `defaults.mk` (single source of overridable defaults: base image versions, registry, kind auto-load, tag prefix/profile).
3. **Per-product `Makefile`s** — each product under `products/<name>/` sets only `IMAGE_NAME` and includes both fragments; no per-product build logic is duplicated.

Python dependency management is **uv** with lockfiles (`uv.lock`) and frozen installs (`uv sync --frozen`). Each product declares its own `pyproject.toml` with pinned dependency ranges and `uv_build` as the build backend. The shared base image `luban-aiops/base-uv:al2023` (built from `shared/base-images/base-uv/Dockerfile`) pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`.

Deployment is **Kustomize-based GitOps**: overlays live under `shared/platform-ops/gitops/` (`dev-k8s/base`, `runtime-profiles/{default,mutating-dev,browser-dev}`) and are rendered via `kustomize build --load-restrictor LoadRestrictionsNone`. The root `make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies the overlay to the current cluster.

## Key files and packages

- Root orchestration: `Makefile`, `VERSION`, `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Per-product build scaffolding: `products/*/Makefile` (all set `IMAGE_NAME` and include both mk fragments)
- Container images: `products/*/Dockerfile` (multi-stage via `FROM luban-aiops/base-uv:al2023`, `uv sync --frozen --no-dev`, expose port 8000, run via `uv run <entrypoint>`)
- Dependency manifests: `products/*/pyproject.toml`, `products/*/uv.lock`, `shared/base-images/base-uv/Dockerfile`
- GitOps overlays: `shared/platform-ops/gitops/dev-k8s/kustomization.yaml`, `shared/platform-ops/gitops/runtime-profiles/*/kustomization.yaml`
- Policy synchronization: `shared/shared-contracts/policies/policy-default.yaml`, `password-policy.yaml`; synced into `products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` via `make sync-policy`
- Version validation: `shared/shared-contracts/scripts/validate_version.py` invoked by `make validate-version`
- E2E scripts: `shared/platform-ops/e2e/*.sh` and `samples/acme-admin/demo-suite.sh` invoked by `make e2e`

## Architecture and conventions

- **Coordinated tagging**: All images share one `IMAGE_TAG` computed once at the root level (`<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`). The root `make build` builds every image product with this tag and persists it in `shared/platform-ops/gitops/dev-k8s/.images.env`, which the deploy script reads so the running cluster always references the same image set.
- **Platform-agnostic builds**: `IMAGE_PLATFORM ?= linux/amd64` in `defaults.mk` lets developers target `linux/arm64` for native local/kind builds without changing any Dockerfile.
- **Frozen reproducibility**: Both dependency resolution (`uv sync --frozen`) and base image tags are pinned; nothing pulls `latest`.
- **Single policy source**: Canonical policies in `shared/shared-contracts/policies/` are copied into consumers via `make sync-policy`; `make validate-policy` and `make validate-policy-scenarios` enforce schema and scenario expectations against both the API and tools engines.
- **Version lockstep**: The root `VERSION` file is the single source of truth; `make validate-version` runs a script that checks product versions and the portal stay in sync.
- **Secret vocabulary enforcement**: `make validate-secret-vocabulary` ensures agent-platform, tool-gateway, and skills-hub agree on secret literal names.
- **Password policy contract**: Per SPEC-062 R-2, `password-policy.yaml` is authored once and synced into tool-gateway; `make validate-password-policy` pins the connector floor to it.
- **Samples are out-of-band**: Tutorial samples (`samples/acme-admin/*`) are never part of the base overlay (per SPEC-050 R-11); they are installed separately via `make deploy-samples` and `make deploy-sample-app`.
- **Kind integration**: `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` after `make build` auto-loads all built images into the named kind cluster.

## Conventions and constraints

- Every product must declare `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk` in its `Makefile` — there is no per-product build logic beyond that.
- Python products must use `uv` with a `pyproject.toml` and `uv.lock`; tests run via `uv run pytest` with OTel exporters disabled to avoid noise.
- Dockerfiles must be based on `luban-aiops/base-uv:al2023` and install dependencies with `uv sync --frozen --no-dev`.
- The verification gate `make verify` runs `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, and `secret-delivery-demo`; it is intended as the pre-commit/pre-push gate.
- Image linting falls back from `hadolint` to `docker run hadolint/hadolint` if the binary is not available locally.
- Overlays are validated by running `kustomize build --load-restrictor LoadRestrictionsNone` against every overlay listed in `OVERLAYS`.
- The `IMAGE_STATE` file (`shared/platform-ops/gitops/dev-k8s/.images.env`) is written by `make build` and read by `make deploy`; deleting it via `make clean` forces regeneration.