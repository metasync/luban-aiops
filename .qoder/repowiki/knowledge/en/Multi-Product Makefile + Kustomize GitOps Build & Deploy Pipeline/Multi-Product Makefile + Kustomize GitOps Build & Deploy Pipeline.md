---
kind: build_system
name: Multi-Product Makefile + Kustomize GitOps Build & Deploy Pipeline
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
    - products/platform-gateway/Makefile
    - products/tool-gateway/Makefile
    - products/identity-broker/Makefile
    - products/operator-portal/Makefile
    - products/agent-platform/Dockerfile
    - products/agent-platform/pyproject.toml
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## What system/approach is used

The repository uses a **Makefile-driven, multi-product build pipeline** layered on top of **Docker**, **uv (Python dependency manager)**, and **Kustomize** for Kubernetes manifests. There is no CI YAML in this repo; the root `Makefile` is explicitly designed as a "forge-agnostic" gate (`make verify`) that runs identically locally and under any CI provider.

Each product under `products/<name>/` is an independent Python FastAPI service (or static nginx web UI) with its own `pyproject.toml`, `uv.lock`, `Dockerfile`, and a tiny `Makefile` that only sets `IMAGE_NAME` and includes shared fragments from `mk/`. The root orchestrates cross-cutting concerns: coordinated image tagging, base-image building, test/lint execution across all products, Kustomize overlay validation, and deployment to a local kind cluster.

## Key files and packages

- **Root orchestration**: `Makefile` — defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`; targets `sync`, `test`, `lint`, `base-images`, `build`, `push`, `overlays`, `verify`, `deploy`, `clean`.
- **Shared build fragments**:
  - `mk/defaults.mk` — single source of overridable defaults via `?=` (e.g. `IMAGE_PLATFORM=linux/amd64`, `IMAGE_TAG_PREFIX=dev-k8s`, `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`). Includes guard against double inclusion.
  - `mk/image.mk` — shared Docker image targets (`build`, `push`, `lint`); computes `IMAGE_REF` as `luban-aiops/<name>:<tag>` (optionally prefixed by `REGISTRY/`); falls back to git short SHA for `IMAGE_TAG`.
  - `mk/python.mk` — shared `uv sync --frozen` and `uv run pytest` targets.
- **Per-product Makefiles** (minimal): `products/agent-platform/Makefile`, `products/platform-gateway/Makefile`, `products/tool-gateway/Makefile`, `products/identity-broker/Makefile`, `products/operator-portal/Makefile` — each only declares `IMAGE_NAME` and includes `../../mk/image.mk` (+ `../../mk/python.mk` for Python products).
- **Base image**: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal, installs pinned `uv` (via `UV_INSTALL_DIR=/usr/local/bin`), creates non-root `app` user (uid 1000), sets `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=<python version>`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- **Product Dockerfiles** — e.g. `products/agent-platform/Dockerfile`: `FROM luban-aiops/base-uv:al2023`, copies `.python-version pyproject.toml uv.lock src/`, runs `uv sync --frozen --no-dev`, exposes port 8000, entrypoint `uv run agent-service`.
- **Coordinated tag state**: `shared/platform-ops/gitops/dev-k8s/.images.env` — written by root `make build`; contains `IMAGE_TAG` plus per-product image refs (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, etc.) consumed by deploy.
- **Kubernetes overlays**: `shared/platform-ops/gitops/dev-k8s/kustomization.yaml` (namespace `dev-luban-aiops`, resources `base` + runtime profile overlay like `runtime-profiles/deepseek`); other overlays under `runtime-profiles/{dashscope,deepseek,openai}`.
- **Deploy script**: `shared/platform-ops/gitops/dev-k8s/deploy.sh` — calls `../deploy-overlay.sh`, provisions token-delegation secrets via `sync-delegation-secrets.sh`, optionally reconciles portal OIDC client.
- **Product dependency manifests**: each product has `pyproject.toml` + `uv.lock` (e.g. `products/agent-platform/pyproject.toml` pins `agentscope>=2.0.4,<3.0`, `fastapi>=0.115,<1.0`, `opentelemetry-*`, `redis`, `uvicorn[standard]`, dev deps in `[dependency-groups] dev = [pytest, fakeredis, jsonschema]`).

## Architecture and conventions

1. **Two-level Makefile hierarchy**: Root `Makefile` owns cross-product coordination; each product's `Makefile` is a thin wrapper declaring `IMAGE_NAME` and including shared fragments. This lets you run `make -C products/<name> test` standalone or `make test` at the repo root.
2. **Coordinated image tagging**: The root computes a single `IMAGE_TAG` once using `<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]` and passes it to every product build. After building, it writes `IMAGE_TAG` and per-product image refs into `shared/platform-ops/gitops/dev-k8s/.images.env`, which the deploy step reads.
3. **Base image strategy**: All backend services derive from `shared/base-images/base-uv:al2023`, built via `make base-images` with pinned `UV_VERSION` and `PYTHON_VERSION`. No system Python is installed — `uv` resolves the interpreter from each product's `.python-version` file, with `UV_PYTHON` as deterministic fallback.
4. **Frozen dependency resolution**: Both development (`uv sync --frozen`) and production (`uv sync --frozen --no-dev`) use `--frozen` against `uv.lock`, ensuring reproducible builds.
5. **Kustomize overlay validation**: `make overlays` runs `kustomize build` against every overlay listed in `OVERLAYS` (`dev-k8s`, `runtime-profiles/dashscope`, `runtime-profiles/deepseek`, `runtime-profiles/openai`) as part of the verification gate.
6. **Kind integration**: When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all five images (`web-ui`, `platform-gateway`, `tool-gateway`, `agent-service`, `identity-service`) into the named kind cluster after building.
7. **Registry abstraction**: `REGISTRY` is optional; when unset images are tagged locally as `luban-aiops/<name>:<tag>`, when set they are re-tagged to `$(REGISTRY)/luban-aiops/<name>:<tag>` and pushed via `make push`.
8. **Non-root containers**: Base image creates uid 1000 `app` user; product images inherit it.
9. **Dockerfile linting**: `make lint` runs `hadolint` if available, falling back to `docker run hadolint/hadolint` if not, then silently skipping if neither exists.

## Conventions and constraints

- **GNU make required**: The root Makefile header states it requires GNU make (default on macOS/Linux). All `SHELL := /bin/sh` ensures POSIX shell compatibility.
- **No `latest` tags**: `mk/defaults.mk` comments enforce pinned values for reproducible builds — never `latest`. Image tags are derived from git SHA or timestamp.
- **Products must declare `IMAGE_NAME`**: The `mk/image.mk` fragment expects the including Makefile to set `IMAGE_NAME`; without it, image references resolve incorrectly.
- **Python products must include both fragments**: Python-backed products include both `../../mk/image.mk` and `../../mk/python.mk`; the operator-portal (static nginx) includes only `image.mk` since it has no Python test suite.
- **Dependency pinning via `uv.lock`**: Development and container builds both use `uv sync --frozen`, so `uv.lock` is the authoritative dependency manifest.
- **Verification gate invariant**: `make verify` runs `test` (all Python products) and `overlays` (all Kustomize overlays); this is intended as the pre-commit/pre-push gate.
- **Deploy assumes prior build**: `make deploy` wraps `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which depends on `shared/platform-ops/gitops/dev-k8s/.images.env` being present from a prior `make build`.
- **Namespace convention**: Kustomize base deploys to namespace `dev-luban-aiops` (overridable via `NAMESPACE` env var in `deploy.sh`).
- **Runtime profiles**: Separate Kustomize overlays under `runtime-profiles/{dashscope,deepseek,openai}` select different LLM provider configurations; the active one is selected via the `kustomization.yaml` in `dev-k8s`.