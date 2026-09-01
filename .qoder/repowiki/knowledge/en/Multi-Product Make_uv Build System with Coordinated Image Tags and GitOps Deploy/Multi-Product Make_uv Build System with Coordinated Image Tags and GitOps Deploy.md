---
kind: build_system
name: Multi-Product Make/uv Build System with Coordinated Image Tags and GitOps Deploy
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
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

The repository uses a **Makefile-driven multi-product workspace** built on top of:
- **GNU make** as the orchestrator (root `Makefile` delegates to per-product `products/<name>/Makefile` files).
- **uv** for Python dependency resolution and test execution (`uv sync --frozen`, `uv run pytest`).
- **Docker** for container image builds, orchestrated via shared fragments in `mk/`.
- **kustomize** for rendering Kubernetes overlays under `shared/platform-ops/gitops/`.
- A coordinated tag-and-deploy pipeline that pins every product image to a single `IMAGE_TAG` derived from the root `VERSION` file plus git SHA.

There is no CI configuration checked into `.github/workflows`; verification gates are expressed entirely as `make verify` targets intended to run locally and in any CI environment.

## Key files and packages

- Root orchestration: `Makefile`, `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Per-product build entry points: `products/*/Makefile` (each only sets `IMAGE_NAME` and includes the two shared fragments)
- Container images: `products/*/Dockerfile` (Python products inherit `luban-aiops/base-uv:al2023`; operator portal uses a Node build + nginx runtime)
- Shared base image: `shared/base-images/base-uv/Dockerfile`
- Version lock: `VERSION` (single source of truth; enforced by `validate-version`)
- GitOps deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` plus sibling `sync-*.sh` scripts that provision secrets and reconcile K8s resources
- Policy bundle synchronization: canonical policy at `shared/shared-contracts/policies/policy-default.yaml`, copied to `tool-gateway`, `platform-gateway`, and `dev-k8s/base/shared/policy.yaml` via `make sync-policy`
- E2E demos: `shared/platform-ops/e2e/*.sh` invoked through `make e2e`

## Architecture and conventions

### Product layout
Every product under `products/` follows an identical structure: a `src/<package>/`, a `tests/` directory, a `pyproject.toml` + `uv.lock`, a `Dockerfile`, and a tiny `Makefile` that declares `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. This lets `make -C products/<name>` work standalone or be driven from the root.

### Coordinated image tagging
The root `Makefile` computes one `IMAGE_TAG` per invocation using this formula:
```
<semver-from-VERSION>-<IMAGE_TAG_PREFIX>[ -<IMAGE_TAG_PROFILE> ]-<git-sha>[-dirty-<timestamp>]
```
The default prefix is `dev-k8s`. The `build` target iterates all `IMAGE_PRODUCTS` and passes the same `IMAGE_TAG` to each product's `make build`, then writes the resulting tags into `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy script can reference them. The list of images written covers agent-service, platform-gateway, tool-gateway, identity-service, audit-service, skills-hub, incident-service, execution-runtime, and web-ui.

### Base image strategy
All Python services build on `shared/base-images/base-uv/Dockerfile`, which is itself built first by `make base-images` using pinned `BASE_UV_UV_VERSION` (default `0.12.1`) and `BASE_UV_PYTHON_VERSION` (default `3.12`) from `mk/defaults.mk`. Production images run `uv sync --frozen --no-dev` and execute via `uv run <entrypoint>`.

### Operator portal build
The operator portal uses a two-stage Dockerfile: a `node:22-alpine` stage builds the Vite/React SPA (with the root `VERSION` injected at build time via `vite.config.ts`), and an `nginxinc/nginx-unprivileged:1.27-alpine` runtime serves the static bundle and proxies `/api/` to the gateway.

### Deployment flow
`make deploy` runs `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which calls `deploy-overlay.sh` and then sequentially provisions secrets via `sync-*` scripts (delegation, audit, execution signing/handoff, skills, incidents, sessions DB, OTel). It optionally reconciles a Keycloak realm and portal OIDC client. Namespaces and toggles are controlled via environment variables (`NAMESPACE`, `SKIP_*_SECRETS`, `RECONCILE_OIDC_PORTAL_CLIENT`).

### Verification gate
`make verify` composes the full pre-commit/pre-push check: `test` (runs `make test` in every Python product), `overlays` (kustomize build checks for `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`), `validate-policy`, `validate-policy-scenarios`, and `validate-version`.

### Policy management
A single canonical policy YAML lives in `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to both gateway products and the K8s overlay. `make validate-policy` validates against a JSON schema; `make validate-policy-scenarios` evaluates scenario expectations against both engines; `make policy-diff CANDIDATE=<path>` reports per-(role, action) differences.

## Conventions and constraints

- **Single version source**: `VERSION` is the authoritative release number; `PLATFORM_VERSION` is read from it and propagated to image tags and the portal build. `make validate-version` enforces that product versions stay in lockstep.
- **Frozen dependencies**: All Python products use `uv sync --frozen`, pinning to `uv.lock` — no network resolution during build or test.
- **Reproducible base images**: Base image versions (`BASE_UV_IMAGE`, `BASE_UV_TAG`, `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`) are pinned defaults in `mk/defaults.mk` and overridable via `?=` so command-line flags win.
- **Cross-platform builds**: `IMAGE_PLATFORM ?= linux/amd64` is the default; set to `linux/arm64` for native local/kind builds on arm64 hosts.
- **Registry push pattern**: Set `REGISTRY=<host>` to re-tag and push images to a remote registry; without it, images stay local under `luban-aiops/<name>:<tag>`.
- **Kind integration**: `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<name>` auto-loads all built images into the named kind cluster after `make build`.
- **Per-product Makefiles must not duplicate logic**: They only declare `IMAGE_NAME` and include the shared fragments; all build/test/lint logic lives in `mk/`.
- **Policy bundle is canonical-only**: Consumers never edit their own copy directly — they must go through `make sync-policy`.
- **GitOps overlays are validated as part of verify**: `kustomize build --load-restrictor LoadRestrictionsNone` is run against each overlay in `OVERLAYS`.
- **E2E requires a deployed cluster**: `make e2e` expects `make deploy` to have completed and port-forwards for the chat legs to be active.