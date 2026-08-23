---
kind: build_system
name: Multi-Product Makefile + Kustomize GitOps Build System
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - products/platform-gateway/Makefile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
---

## What system/approach is used

The repository uses a **Makefile-driven multi-product build system** layered on top of **Docker image builds**, **uv-based Python dependency management**, and **Kustomize GitOps overlays**. There is no CI pipeline file in `.github/workflows`; the `make verify` target (tests, overlay rendering, policy validation, version lockstep) is intended as the pre-commit/pre-push gate that runs identically locally and under any CI.

Each product under `products/` is an independently deployable service with its own `Dockerfile`, `pyproject.toml`/`uv.lock`, and a tiny product Makefile. Cross-cutting logic is centralized in `mk/defaults.mk`, `mk/image.mk`, and `mk/python.mk`, which are included by every product Makefile so that root-level and standalone invocations resolve the same defaults.

## Key files and packages

- Root orchestrator: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), coordinated image tag computation, `build`, `push`, `sync`, `test`, `lint`, `overlays`, `verify`, `deploy`, `e2e`, `clean`, plus policy/version sync targets.
- Shared build fragments:
  - `mk/defaults.mk` — single source of overridable settings (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`).
  - `mk/image.mk` — shared `build`/`push`/`lint` Docker targets; resolves `IMAGE_REF` from `IMAGE_NAME` and optional `REGISTRY`; supports `hadolint` with docker-run fallback.
  - `mk/python.mk` — shared `sync`/`test` targets using `uv sync --frozen` and `uv run pytest` with OTel exporters disabled for test output cleanliness.
- Version source of truth: `VERSION` (semver, e.g. `0.9.0`); enforced via `shared/shared-contracts/scripts/validate_version.py` invoked by `make validate-version`.
- Coordinated image tagging: computed once per invocation as `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` suffix for uncommitted changes). Written to `shared/platform-ops/gitops/dev-k8s/.images.env` by `make build`.
- Product Makefiles (minimal): e.g. `products/platform-gateway/Makefile` sets `IMAGE_NAME` then includes `../../mk/image.mk` and `../../mk/python.mk`. All seven Python services follow this pattern.
- Base image: `shared/base-images/base-uv/Dockerfile` built via `make base-images` using pinned `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION`.
- GitOps deployment assets: `shared/platform-ops/gitops/dev-k8s/` (base manifests per service, `kustomization.yaml`, `deploy.sh`) plus runtime profile overlays under `runtime-profiles/{dashscope,deepseek,openai,mutating-dev}/`.
- Policy synchronization: canonical `shared/shared-contracts/policies/policy-default.yaml` copied to `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` via `make sync-policy`.

## Architecture and conventions

1. **Single root, delegated products.** The root `Makefile` enumerates all products and dispatches to `make -C products/<name> <target>`. Products themselves contain no build logic — only `IMAGE_NAME` assignment and two `include` statements.
2. **Coordinated image tagging.** A single `IMAGE_TAG` is computed at the root and propagated to every product build, ensuring all images in a release share the same semantic tag derived from `VERSION`, `IMAGE_TAG_PREFIX`, optional `IMAGE_TAG_PROFILE`, and git SHA.
3. **Frozen Python dependencies.** Every product uses `uv sync --frozen`, pinning to `uv.lock`. Tests run inside the synced environment with `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` to suppress OTel noise while keeping tracing tests functional.
4. **Image platform abstraction.** `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden globally (e.g. `make build IMAGE_PLATFORM=linux/arm64`) or per-product. The root `build` target also supports `AUTO_LOAD_KIND=true` to auto-load built images into a named kind cluster after building.
5. **Registry indirection.** When `REGISTRY` is set, images are re-tagged to `<REGISTRY>/luban-aiops/<IMAGE_NAME>:<TAG>` before push; otherwise they stay local under `luban-aiops/...`.
6. **Kustomize-only Kubernetes delivery.** Deployment manifests live under `shared/platform-ops/gitops/dev-k8s/base/` and are rendered via `kustomize build` during `make overlays` and deployed through `shared/platform-ops/gitops/dev-k8s/deploy.sh`. Runtime profiles are applied as Kustomize overlays.
7. **Policy as code, centrally managed.** The canonical policy YAML lives in `shared/shared-contracts/policies/` and is duplicated into each consumer product and the GitOps base via `make sync-policy`; `make validate-policy` validates it against a JSON schema.
8. **Version lockstep enforcement.** `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root to ensure the root `VERSION`, each product's declared version, and the portal version stay synchronized.

## Conventions and constraints

- **GNU make required.** The root Makefile explicitly states it requires GNU make (default on macOS/Linux).
- **No `latest` tags anywhere.** Pinned versions are enforced for the base UV image (`BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`) and for Python deps via `uv sync --frozen`.
- **Products must declare `IMAGE_NAME` before including `mk/image.mk`.** This is the only contract between product Makefiles and the shared fragment.
- **All cross-cutting concerns live in `mk/` and `shared/`.** Product directories should not duplicate build logic.
- **Verification gate is uniform:** `make verify` runs `test`, `overlays`, `validate-policy`, and `validate-version` — this is the prescribed pre-commit/pre-push check.
- **Deploy state is file-backed:** `make build` writes `shared/platform-ops/gitops/dev-k8s/.images.env` containing `IMAGE_TAG` and one `*_IMAGE=luban-aiops/<service>:<TAG>` line per service; `make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which consumes this file.
- **E2E scripts require prior deployment and port-forwarding.** `make e2e` expects `platform-gateway` on port 18083 and `identity-service` on port 18081 to be forwarded locally.