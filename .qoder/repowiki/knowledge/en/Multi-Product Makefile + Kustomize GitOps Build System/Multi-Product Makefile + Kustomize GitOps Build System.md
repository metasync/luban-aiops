---
kind: build_system
name: Multi-Product Makefile + Kustomize GitOps Build System
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/identity-broker/Makefile
    - products/tool-gateway/Makefile
    - products/operator-portal/Makefile
    - products/agent-platform/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/deploy-overlay.sh
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

The Luban AIOps workspace uses a layered build system centered on GNU make at the repository root, shared Makefile fragments under `mk/`, per-product `Dockerfile`s, and Kustomize-based GitOps overlays for Kubernetes deployment.

**Root orchestration (`Makefile`)**
- Declares two product categories: `PYTHON_PRODUCTS := agent-platform identity-broker tool-gateway` (with Python test suites) and `IMAGE_PRODUCTS := agent-platform identity-broker tool-gateway operator-portal` (with container images).
- Computes a coordinated `IMAGE_TAG` once per invocation using `<prefix>[-<profile>]-<gitsha>` for clean trees or `<prefix>-<gitsha>-dirty-<timestamp>` for dirty trees; defaults to `dev-k8s` prefix.
- Aggregates per-product targets via `$(MAKE) -C products/$p <target>`, so `make sync/test/lint/build/push` iterate over all products.
- Writes a coordinated `.images.env` state file under `shared/platform-ops/gitops/dev-k8s/.images.env` containing `IMAGE_TAG` plus `AGENT_SERVICE_IMAGE`, `API_GATEWAY_IMAGE`, `IDENTITY_SERVICE_IMAGE`, `WEB_UI_IMAGE` — consumed by the deploy script.
- Optional `AUTO_LOAD_KIND=true` with `KIND_CLUSTER_NAME` auto-loads built images into a local Kind cluster after `make build`.
- `verify` target runs `test` then `overlays` (kustomize build checks for all overlays); `deploy` wraps `shared/platform-ops/gitops/dev-k8s/deploy.sh`.

**Shared fragments (`mk/`)**
- `mk/image.mk`: Provides `build`, `push`, `lint` targets. `build` runs `docker build -t luban-aiops/<IMAGE_NAME>:<IMAGE_TAG> .`; if `REGISTRY` is set it re-tags and pushes. `lint` prefers `hadolint`, falls back to `docker run hadolint/hadolint`.
- `mk/python.mk`: Provides `sync` (`uv sync --frozen`) and `test` (`uv sync --frozen && uv run pytest`). Requires GNU make and `uv`.

**Per-product Makefiles**
Each product under `products/<name>/` declares only `IMAGE_NAME` and includes the shared fragments:
- `agent-platform`: `IMAGE_NAME := agent-service`
- `identity-broker`: `IMAGE_NAME := identity-service`
- `tool-gateway`: `IMAGE_NAME := api-gateway`
- `operator-portal`: `IMAGE_NAME := web-ui` (no Python tests, so only `image.mk` is included)

This keeps product Makefiles minimal and delegates all logic to shared fragments.

**Container images**
- All Python products use the `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` base image, copy `pyproject.toml`, `uv.lock`, and `src/`, then run `uv sync --frozen --no-dev`. The entrypoint invokes the service via `uv run <entrypoint>` (e.g. `uv run agent-service`).
- Operator portal uses an nginx-based Dockerfile serving static HTML/JS/CSS.

**GitOps & Kubernetes deployment**
- Overlays live under `shared/platform-ops/gitops/`: `dev-k8s/base` defines the baseline services, and `runtime-profiles/{openai,dashscope,deepseek}` provide provider-specific ConfigMaps/secrets.
- `select-runtime-profile.sh <profile>` regenerates `dev-k8s/kustomization.yaml` to include the chosen runtime profile overlay.
- `deploy-overlay.sh` reads `.images.env`, applies the overlay via `kubectl apply -k`, then patches each deployment's image tag with `kubectl set image` and waits for rollout status.
- `deploy.sh` calls `deploy-overlay.sh` and optionally reconciles the portal's Keycloak OIDC client via `reconcile-portal-oidc-client.sh`.

**Conventions and constraints**
- Every product that ships a container must define `IMAGE_NAME` and include both `mk/image.mk` and `mk/python.mk` (if it has tests).
- Image tags are coordinated across all products through the single `IMAGE_TAG` computed at the root; there is no per-image versioning.
- Dependency resolution is frozen via `uv.lock` and `--frozen` flags, ensuring reproducible builds.
- The `verify` target is the canonical pre-commit/pre-push gate, enforcing both unit tests and Kustomize overlay validity.
- Deployments target the `dev-luban-aiops` namespace by default, configurable via the `NAMESPACE` environment variable.