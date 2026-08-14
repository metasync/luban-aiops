---
kind: build_system
name: Makefile-driven Monorepo Build with Shared Base Image, uv Locking, and Kustomize GitOps Deploy
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
    - products/platform-gateway/Dockerfile
    - products/audit-service/Dockerfile
    - products/operator-portal/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/deploy-overlay.sh
---

## What system/approach is used

The repository uses a **GNU Make-based monorepo build orchestration** layered on top of three concrete technologies:

- **Container images**: Docker, built per product via `docker build --platform $(IMAGE_PLATFORM)`. All Python services share a single custom base image (`luban-aiops/base-uv:al2023`) built from `shared/base-images/base-uv/Dockerfile`.
- **Python dependency management**: `uv` (astral.sh), invoked as `uv sync --frozen` in every product Dockerfile and test target. Each product pins its dependencies in `pyproject.toml` + `uv.lock`; the lock file is copied into the image so builds are reproducible without network access.
- **Kubernetes deployment**: Kustomize overlays under `shared/platform-ops/gitops/` (base `dev-k8s`, plus runtime profiles for dashscope/deepseek/openai). Deployment is driven by shell scripts (`deploy-overlay.sh`, `deploy.sh`) that apply the overlay and then patch image tags via `kubectl set image`.

There is no CI pipeline definition in this snapshot; the root `Makefile` explicitly states it is "Forge-agnostic" and intended to run identically locally and under any CI.

## Key files and packages

- Root orchestrator: `Makefile` — defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, coordinated `IMAGE_TAG` computation, and targets `sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `clean`, `sync-policy`, `validate-policy`.
- Shared defaults: `mk/defaults.mk` — single source of truth for overridable settings (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`).
- Shared fragments: `mk/image.mk` (Docker build/push/lint targets, image ref resolution), `mk/python.mk` (`uv sync --frozen` + `uv run pytest`).
- Product Makefiles: each `products/<name>/Makefile` sets `IMAGE_NAME` and includes both fragments (e.g. `agent-platform/Makefile` → `IMAGE_NAME := agent-service`).
- Base image: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal, pinned `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, installs uv, creates non-root `app` user (uid 1000), exports `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Product Dockerfiles: uniform pattern — `FROM luban-aiops/base-uv:al2023`, copy `.python-version pyproject.toml uv.lock README.md src`, `RUN uv sync --frozen --no-dev`, `CMD ["uv", "run", "<entrypoint>"]`.
- Operator portal: `products/operator-portal/Dockerfile` is the exception — static Nginx image (`nginxinc/nginx-unprivileged:1.27-alpine`) serving `web-ui/`.
- Deployment scripts: `shared/platform-ops/gitops/dev-k8s/deploy.sh` (calls `deploy-overlay.sh`, provisions secrets, reconciles Keycloak realm/client); `shared/platform-ops/gitops/deploy-overlay.sh` (loads `.images.env`, applies Kustomize overlay, patches all six deployments, runs rollout status).
- Policy sync: `make sync-policy` copies canonical policy from `shared/shared-contracts/policies/policy-default.yaml` into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.

## Architecture and conventions

### Layered Makefile design
The root `Makefile` delegates to per-product Makefiles via `$(MAKE) -C products/$$p <target>`. Product Makefiles are intentionally tiny — they only declare `IMAGE_NAME` and include the shared fragments. This keeps cross-cutting logic (image building, linting, Python sync/test) in one place while letting each product opt in.

### Coordinated tagging
`IMAGE_TAG` is computed once at the root level using the formula `<prefix>[-<profile>]-<gitsha>` (dirty worktrees append `-dirty-YYYYMMDDHHMMSS`). The same tag is applied to every product image and written into `shared/platform-ops/gitops/dev-k8s/.images.env`, which `deploy-overlay.sh` sources to patch all deployments atomically. This guarantees all services in a deploy use the same commit hash.

### Base image strategy
All Python services inherit from `luban-aiops/base-uv:al2023`, which has no system Python installed. `uv` resolves the interpreter from each product's `.python-version` file during `uv sync`, with `UV_PYTHON` as a deterministic fallback. The base image is built first (`make base-images`) and tagged `al2023`; versions of uv and Python are pinned via `--build-arg` defaults in `mk/defaults.mk`.

### Frozen dependency resolution
Every product Dockerfile runs `uv sync --frozen --no-dev`, meaning the image build will fail if `uv.lock` drifts from `pyproject.toml`. Tests also run `uv sync --frozen` before `pytest`, ensuring CI and local environments match exactly.

### Kustomize overlays as the deployment surface
Kubernetes manifests live under `shared/platform-ops/gitops/`. The `dev-k8s` overlay is the base; runtime-profile overlays (`runtime-profiles/dashscope|deepseek|openai`) provide provider-specific ConfigMaps/secrets. The `overlays` target validates them via `kustomize build` (to `/dev/null`). Deployment applies the overlay then uses `kubectl set image` to swap in the coordinated tag, followed by `rollout status` checks per deployment.

### Policy bundle synchronization
Policy YAML is authored in one canonical location (`shared/shared-contracts/policies/policy-default.yaml`) and distributed to consumers via `make sync-policy`. Validation against the JSON schema lives in `shared/shared-contracts/scripts/validate_policy.py` and is invoked via `make validate-policy`.

## Conventions and constraints

- **Per-product isolation**: Each service under `products/<name>/` is self-contained with its own `src/`, `tests/`, `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, and `Makefile`. Cross-cutting behavior is achieved through inclusion of shared `mk/*.mk` fragments, not shared code.
- **Non-root containers**: The base image creates an `app` user (uid 1000) and switches to it; product Dockerfiles `COPY --chown=app:app` to preserve ownership.
- **No mutable base tags**: All base images and tool versions are pinned — `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, `nginxinc/nginx-unprivileged:1.27-alpine`. Overrides go through `--build-arg` or make variables, never by changing the default.
- **Multi-platform builds**: `IMAGE_PLATFORM ?= linux/amd64` is the default but can be overridden (e.g. `linux/arm64` for native kind builds on arm64 hosts). The same flag propagates to both base-image and product-image builds.
- **Registry push gating**: `make push` only pushes when `REGISTRY` is set; otherwise images remain local under `luban-aiops/<name>:<tag>`.
- **Kind integration**: `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<cluster>` auto-loads all built images into the named kind cluster after `make build`.
- **Verification gate**: `make verify` runs `test` + `overlays` + `validate-policy` in sequence and is intended as the pre-commit/pre-push gate across environments.
- **Secret provisioning**: `deploy.sh` optionally provisions token-delegation and audit secrets via helper scripts; external secret injection is supported via `SKIP_DELEGATION_SECRETS` / `SKIP_AUDIT_SECRETS` environment variables.