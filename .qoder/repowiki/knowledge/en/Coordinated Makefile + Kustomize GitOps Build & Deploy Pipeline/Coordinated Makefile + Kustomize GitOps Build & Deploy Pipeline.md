---
kind: build_system
name: Coordinated Makefile + Kustomize GitOps Build & Deploy Pipeline
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - VERSION
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/Dockerfile
    - shared/platform-ops/gitops/deploy-overlay.sh
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/shared-contracts/scripts/validate_version.py
---

## What system/approach is used

The repository uses a **Makefile-driven, multi-product build pipeline** centered on three layers:

1. **Root `Makefile`** — orchestrates cross-cutting concerns (sync, test, lint, verify, build, push, deploy, e2e) and delegates per-product work to each product's own `Makefile`.
2. **Shared fragments in `mk/`** — reusable targets for Python (`python.mk`: `uv sync --frozen`, `uv run pytest`) and container images (`image.mk`: `docker build/push/lint` with hadolint fallback), plus a single source of defaults (`defaults.mk`).
3. **Kustomize-based GitOps overlays** under `shared/platform-ops/gitops/` — rendered and applied via `deploy.sh` / `deploy-overlay.sh`, which injects image tags from a coordinated state file.

Python dependency management is handled per-product via **`pyproject.toml` + `uv.lock`** with `uv sync --frozen`; the shared base image `luban-aiops/base-uv:al2023` pins `uv` (0.12.1) and Python (3.12) and runs as non-root user `app` (uid 1000).

Container images are built with Docker, tagged with a coordinated `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]` scheme derived from the root `VERSION` file, and pushed to `luban-aiops/*` (or a `REGISTRY` override). A single `.images.env` state file written by `make build` carries all service image references into the deployment step.

## Key files and packages

- Root orchestration: `Makefile`, `VERSION`
- Shared build fragments: `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Per-product entry points (all follow the same pattern): `products/<name>/Makefile` (sets `IMAGE_NAME`, includes `../../mk/image.mk` and `../../mk/python.mk`), `products/<name>/Dockerfile`, `products/<name>/pyproject.toml`, `products/<name>/uv.lock`, `products/<name>/.python-version`
- Base image: `shared/base-images/base-uv/Dockerfile`
- Deployment: `shared/platform-ops/gitops/deploy-overlay.sh`, `shared/platform-ops/gitops/dev-k8s/deploy.sh`, `shared/platform-ops/gitops/dev-k8s/kustomization.yaml`, `shared/platform-ops/gitops/runtime-profiles/*/kustomization.yaml`
- Policy sync: `shared/shared-contracts/policies/policy-default.yaml` synced to `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` via `make sync-policy`
- Version lockstep validation: `shared/shared-contracts/scripts/validate_version.py` invoked by `make validate-version`
- E2E scripts: `shared/platform-ops/e2e/*.sh` invoked by `make e2e`

## Architecture and conventions

### Product structure convention
Every backend product follows an identical layout so the root Makefile can iterate uniformly over `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists:
- `src/<service_name>/` — Python package with `main.py`, `app.py`, `core/`, `api/`, `services/`, `schemas/`, optional `policies/`.
- `tests/` — pytest suite.
- `Dockerfile` — copies `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, then `src/`, runs `uv sync --frozen --no-dev`, exposes 8000, CMD `uv run <entrypoint>`.
- `Makefile` — only sets `IMAGE_NAME` and includes the two shared fragments; no duplicated logic.
- `pyproject.toml` — declares project name, version, dependencies, `[dependency-groups] dev = [...]`, and `build-system` using `uv_build`.

### Coordinated tagging
All images share one tag computed once at the root level:
```
IMAGE_TAG = <PLATFORM_VERSION>-<IMAGE_TAG_PREFIX>[-<IMAGE_TAG_PROFILE>][-<short-git-sha>][-dirty-<YYYYMMDDHHmmss>]
```
The semver comes from `VERSION` (currently `0.9.1`); `IMAGE_TAG_PREFIX` defaults to `dev-k8s`; `IMAGE_TAG_PROFILE` selects runtime profiles (dashscope, deepseek, openai, mutating-dev). The tag is written into `.images.env` alongside per-service image refs like `AGENT_SERVICE_IMAGE=luban-aiops/agent-service:<tag>`, consumed by `deploy-overlay.sh`.

### Image base strategy
A single shared base image `shared/base-images/base-uv/Dockerfile` is built first (`make base-images`) and depends on `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`. It installs `curl-minimal`, `ca-certificates`, `tar`, `gzip`, `shadow-utils`, pins uv into `/usr/local/bin`, creates a non-root `app` user (uid 1000), and exports `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=3.12`, `UV_PYTHON_INSTALL_DIR=/app/.python`. All product Dockerfiles inherit this image.

### GitOps overlay deployment
`make deploy` calls `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which:
1. Runs `deploy-overlay.sh` against the overlay directory.
2. Provisions secrets via idempotent `sync-*` scripts (delegation, audit, skills, incidents, OTel, sessions DB).
3. Optionally reconciles Keycloak realm and portal OIDC client.
4. Applies Kustomize manifests with `kubectl kustomize --load-restrictor LoadRestrictionsNone` (needed because `skills-hub` base pulls sample skill content from outside the overlay root).
5. Detects ConfigMap changes and rolls out deployments that consume them.
6. Uses `kubectl set image` to swap every deployment to the coordinated IMAGE_TAG.
7. Waits on rollout status for all eight deployments.

### Verification gate
`make verify` composes `test` + `overlays` + `validate-policy` + `validate-version`, intended as the pre-commit/pre-push gate runnable locally and in CI. `make overlays` runs `kustomize build` against every overlay listed in `OVERLAYS` to catch manifest errors early.

### Policy synchronization
The canonical policy bundle lives in `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it verbatim to both gateway consumers and the deployed `policy.yaml` in the dev overlay. `make validate-policy` validates it against the JSON schema via `shared/shared-contracts/scripts/validate_policy.py`.

### Version lockstep
`VERSION` at the repo root is the single source of truth for the platform release version. `make validate-version` runs `validate_version.py` from the tool-gateway product to assert that every product's `pyproject.toml` version matches the root `VERSION` (and the portal frontend version), enforced before deploy.

## Conventions and constraints

- **GNU make required** — documented in the root Makefile header; all targets assume GNU make semantics.
- **No loose `latest` tags** — `defaults.mk` comments explicitly state "never `latest`"; all versions (uv, python, image tags) are pinned or derived from git sha.
- **Frozen deps** — Python products always use `uv sync --frozen` (both in `python.mk` and Dockerfiles) so builds are reproducible from `uv.lock`.
- **Non-root containers** — base image switches to `USER app` (uid 1000); product Dockerfiles copy files with `--chown=app:app`.
- **Single coordinated tag** — `make build` computes `IMAGE_TAG` once and writes it into `.images.env`; downstream steps must not invent their own tags.
- **Registry re-tagging** — if `REGISTRY` is set, `image.mk` additionally tags and pushes `<REGISTRY>/luban-aiops/<name>:<tag>`; otherwise images stay local.
- **Multi-platform builds** — `IMAGE_PLATFORM ?= linux/amd64` is passed through to `docker build --platform`; ARM64 native builds are supported via `IMAGE_PLATFORM=linux/arm64`.
- **Kind auto-load** — `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<name>` after `make build` loads all images into the named kind cluster automatically.
- **Overlay list is authoritative** — new overlays must be added to the `OVERLAYS` variable in the root Makefile to participate in `make overlays` verification.
- **Secret provisioning is opt-in per feature** — each `sync-*` script checks a `SKIP_*_SECRETS=true` env var so CI can skip secret-dependent steps when secrets are injected externally.
- **Policy is single-sourced** — consumers never edit `policy-default.yaml` directly; they must go through `make sync-policy` to keep the deployed policy in sync with the canonical bundle.