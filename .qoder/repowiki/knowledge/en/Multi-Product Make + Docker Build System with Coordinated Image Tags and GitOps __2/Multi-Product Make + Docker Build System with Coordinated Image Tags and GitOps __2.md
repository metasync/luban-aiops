---
kind: build_system
name: Multi-Product Make + Docker Build System with Coordinated Image Tags and GitOps Overlays
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - products/operator-portal/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
---

# Build & Artifact Management

## Approach

The repository is a multi-product Python workspace (8 services + 1 web UI) built with a **Makefile-driven, Docker-based pipeline** that coordinates image builds across all products. There is no CI configuration in this snapshot; the build surface is entirely local via GNU make.

### Core tools
- **GNU make** — root orchestrator plus per-product fragments under `mk/`.
- **uv** — Python dependency resolver/installer (`uv sync --frozen`, pinned `uv.lock`).
- **Docker** — container image builder for every product.
- **kustomize** — GitOps overlay rendering (`shared/platform-ops/gitops/<overlay>`).
- **Node/npm** — Vite/React SPA build for `operator-portal`.

## Key files

| File | Role |
|---|---|
| `Makefile` | Root orchestrator: lists `PYTHON_PRODUCTS` / `IMAGE_PRODUCTS`, computes coordinated `IMAGE_TAG`, runs `build`, `test`, `lint`, `overlays`, `verify`, `deploy`, `e2e`. |
| `mk/defaults.mk` | Single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`). |
| `mk/image.mk` | Shared Docker targets (`build`, `push`, `lint`) included by each product Makefile; sets `IMAGE_REF = luban-aiops/<name>:<tag>`. |
| `mk/python.mk` | Shared `sync` / `test` targets using `uv sync --frozen` and `uv run pytest` with OTel exporters disabled. |
| `products/*/Makefile` | Thin wrappers that set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`. |
| `products/*/Dockerfile` | Product images based on `luban-aiops/base-uv:al2023`; copy `.python-version`, `pyproject.toml`, `uv.lock`, `src/`; `RUN uv sync --frozen --no-dev`; `CMD ["uv", "run", "<entrypoint>"]`. |
| `shared/base-images/base-uv/Dockerfile` | Base image built via `make base-images` with pinned `UV_VERSION` and `PYTHON_VERSION`. |
| `VERSION` | Single source of truth for platform semver; consumed by root tag computation and injected into the portal build. |
| `shared/platform-ops/gitops/dev-k8s/` | Kustomize overlays rendered by `make overlays`; deployed via `make deploy` which calls `dev-k8s/deploy.sh`. |
| `shared/shared-contracts/scripts/validate_version.py` | Enforces lockstep between `VERSION`, product versions, and portal version. |

## Architecture and conventions

### Coordinated tagging
The root `Makefile` computes one `IMAGE_TAG` once:
```
<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]
```
The semver comes from `VERSION`; `IMAGE_TAG_PREFIX` defaults to `dev-k8s`; `IMAGE_TAG_PROFILE` is optional. The same tag is applied to every product image and written to `shared/platform-ops/gitops/dev-k8s/.images.env`, which the deploy step consumes so all services ship as a single release.

### Per-product delegation
Each product directory has a tiny `Makefile` that only declares `IMAGE_NAME` and includes the shared fragments. This keeps product-specific logic minimal while reusing identical `build`/`push`/`lint`/`sync`/`test` semantics across all 9 products.

### Base image strategy
All Python services derive from `luban-aiops/base-uv:al2023`, built once via `make base-images` with pinned `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`. Production images use `uv sync --frozen --no-dev`; development/test uses `--no-dev` omitted.

### Multi-stage portal build
`operator-portal/Dockerfile` is the exception: it uses a two-stage build (`node:22-alpine` → `nginxinc/nginx-unprivileged:1.27-alpine`). The build context is the repo root so `vite.config.ts` can read `../../../../VERSION` at build time, injecting `PLATFORM_VERSION` into the SPA.

### GitOps overlays
Deployment manifests live under `shared/platform-ops/gitops/` with overlays `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`. `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` against each overlay to validate them without mutating state.

### Policy synchronization
A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it into both gateway consumers and the k8s overlay. `make validate-policy` and `make validate-policy-scenarios` exercise validation scripts under `shared/shared-contracts/scripts/`.

### Version lockstep
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to enforce that `VERSION`, each product's declared version, and the portal version stay in sync — part of the `verify` gate.

### Secret vocabulary lockstep
`make validate-secret-vocabulary` ensures the redaction vocabulary used by `agent-platform` and `tool-gateway` stays consistent.

## Conventions and constraints

- **Every product must expose `make help`, `make build`, `make push`, `make lint`, `make sync`, `make test`** — enforced by including `mk/image.mk` and `mk/python.mk` from each product Makefile.
- **Images are tagged with a coordinated `<semver>-<prefix>[-<profile>]-<sha>` scheme**; the root `IMAGE_TAG` is computed once and reused for all products and the deploy manifest.
- **Python dependencies are frozen**: `uv sync --frozen` is used everywhere; `uv.lock` is committed and copied into images.
- **Base image versions are pinned**: `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`, `BASE_UV_IMAGE=luban-aiops/base-uv`, `BASE_UV_TAG=al2023` — never `latest`.
- **Cross-platform builds default to `linux/amd64`**, overridable via `IMAGE_PLATFORM` (e.g. `linux/arm64` for native arm64 kind clusters).
- **Registry pushing requires setting `REGISTRY`**; without it, images are tagged locally only as `luban-aiops/<name>:<tag>`.
- **Local kind loading is opt-in** via `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME`; the root `make build` will load all 9 images into the named cluster after building.
- **Verification gate**: `make verify` runs `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary` — intended as the pre-commit/pre-push gate.
- **Deploy target** delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`; samples are installed separately via `make deploy-samples` so the base overlay never references sample skills (per SPEC-050 R-11).
- **E2E demos** (`skills-demo.sh`, `incident-demo.sh`, `mutating-demo.sh`) require a deployed cluster plus port-forwards to `platform-gateway:18083` and `identity-service:18081`.