---
kind: build_system
name: Monorepo Build, Image & Release Orchestration via Make + Docker + Kustomize
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/policy_diff.py
---

# Build System Overview

The Luban AIOps platform is a monorepo of eight Python microservices plus an operator web portal. Build, test, packaging and deployment are orchestrated from the root `Makefile` using shared fragments under `mk/`, with per-product `Makefile`s that only declare their image name and include those fragments.

## What system/approach is used

- **Orchestrator**: GNU `make` at the repository root (`Makefile`) delegates to per-product targets. The root file enumerates `PYTHON_PRODUCTS` (those with a `uv` test suite) and `IMAGE_PRODUCTS` (those producing container images).
- **Python dependency manager**: `uv` with frozen lockfiles (`uv sync --frozen`). Each product has its own `pyproject.toml` / `uv.lock`; tests run inside that product's virtual environment so imports resolve correctly.
- **Containerization**: `docker build` driven by per-product `Dockerfile`s. All images are based on a shared base image `luban-aiops/base-uv:al2023` built from `shared/base-images/base-uv/Dockerfile`.
- **Kubernetes deployment**: GitOps-style overlays under `shared/platform-ops/gitops/`. The root target `overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` against each overlay to validate them; `deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders the overlay and provisions secrets for every service.
- **Policy validation**: Canonical policy bundle lives in `shared/shared-contracts/policies/policy-default.yaml`; `sync-policy` copies it into both gateway products and the dev-k8s overlay, and `validate-policy` / `validate-policy-scenarios` / `policy-diff` exercise the two policy engines (API and tools) against JSON schemas and scenario expectations.
- **Versioning**: Single source of truth is the root `VERSION` file (semver). `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which asserts that every `products/*/pyproject.toml [project] version`, every `src/*/metadata.py SERVICE_VERSION`, any `__version__` in package roots, and the operator portal's Vite wiring all match the root value.

## Key files and packages

- Root orchestration: `Makefile`
- Shared defaults: `mk/defaults.mk` (overridable via `?=`), `mk/image.mk` (build/push/lint targets), `mk/python.mk` (sync/test targets)
- Per-product entry points: `products/<name>/Makefile` (sets `IMAGE_NAME`, includes `../../mk/image.mk` and `../../mk/python.mk`)
- Base image: `shared/base-images/base-uv/Dockerfile` (pinned `UV_VERSION`, `PYTHON_VERSION`)
- Product images: `products/<name>/Dockerfile` (e.g. `FROM luban-aiops/base-uv:al2023`, `uv sync --frozen --no-dev`, `CMD ["uv", "run", "<entrypoint>"]`)
- Deployment script: `shared/platform-ops/gitops/dev-k8s/deploy.sh` (renders overlay, calls `sync-*-secrets.sh` helpers)
- Version enforcement: `VERSION`, `shared/shared-contracts/scripts/validate_version.py`
- Policy tooling: `shared/shared-contracts/scripts/validate_policy.py`, `validate_policy_scenarios.py`, `policy_diff.py`

## Architecture and conventions

1. **Fragment-based Makefiles** — Products do not reimplement build logic. They set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`. The root `Makefile` loops over `IMAGE_PRODUCTS` / `PYTHON_PRODUCTS` to invoke `build`, `test`, `lint`, `push` uniformly.
2. **Coordinated tagging** — The root computes a single `IMAGE_TAG` once (pattern `<semver>-<prefix>[-<profile>]-<gitsha>` or `<prefix>-dirty-<timestamp>` when the tree is dirty) and passes it to every product build. After building, `make build` writes `shared/platform-ops/gitops/dev-k8s/.images.env` containing `AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, `TOOL_GATEWAY_IMAGE`, `IDENTITY_SERVICE_IMAGE`, `AUDIT_SERVICE_IMAGE`, `SKILLS_HUB_IMAGE`, `INCIDENT_SERVICE_IMAGE`, `EXECUTION_RUNTIME_IMAGE`, `WEB_UI_IMAGE`, all tagged with the same `IMAGE_TAG`. This file is consumed by the deploy pipeline so all services ship as one release.
3. **Base image pinning** — `BASE_UV_IMAGE`, `BASE_UV_TAG`, `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION` are pinned defaults in `mk/defaults.mk` and built via `make base-images`. Product Dockerfiles never pin `python` or `uv` themselves; they inherit from `luban-aiops/base-uv:al2023`.
4. **Registry abstraction** — If `REGISTRY` is unset, images are tagged locally as `luban-aiops/<name>:<tag>`. When `REGISTRY` is set, `mk/image.mk` re-tags and pushes to `$(REGISTRY)/luban-aiops/<name>:<tag>`.
5. **Local kind integration** — `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` after `make build` loads all nine images into the named kind cluster automatically.
6. **Cross-platform builds** — `IMAGE_PLATFORM ?= linux/amd64` is the default; override to `linux/arm64` for native arm64 local/kind builds. The root `base-images` target forwards `--platform $(IMAGE_PLATFORM)` to the base image build.
7. **Verification gate** — `make verify` aggregates `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`. It is intended as the pre-commit/pre-push gate and runs identically locally and in CI.
8. **E2E harness** — `make e2e` runs `shared/platform-ops/e2e/{skills-demo,incident-demo,mutating-demo}.sh` against a deployed cluster (requires port-forwards to `platform-gateway:18083` and `identity-service:18081`).
9. **Samples deployment** — Tutorial samples live under `samples/` and are installed out-of-band via `make deploy-samples` / `make undeploy-samples` so the base overlay never names sample resources (per SPEC-050 R-11).

## Conventions and constraints

- **Every Python product must expose `sync` and `test` targets** via including `mk/python.mk`; the root `make test` iterates all `PYTHON_PRODUCTS`.
- **Every containerized product must expose `build`, `push`, `lint`** via including `mk/image.mk`; the root `make lint` runs hadolint (with a docker-run fallback) against each product's `Dockerfile`.
- **Image tags are coordinated, not per-product** — individual products should not compute their own tag; the root `IMAGE_TAG` is passed in. Standalone product builds fall back to `git rev-parse --short HEAD` or `dev`.
- **Versions must stay in lockstep** — `make validate-version` enforces that `VERSION`, every `pyproject.toml` version, every `SERVICE_VERSION` in `src/*/metadata.py`, any `__version__`, and the operator portal's Vite wiring all match. Drift causes failure.
- **Policy bundles are canonical** — `shared/shared-contracts/policies/policy-default.yaml` is the single source; consumers must be updated via `make sync-policy`, not edited in place.
- **Overlays must render cleanly** — `make overlays` fails if any `kustomize build` fails, catching manifest errors before deploy.
- **Secret provisioning is opt-in per secret type** — `deploy.sh` sources `sync-*-secrets.sh` scripts guarded by `SKIP_*_SECRETS=true` env vars, allowing CI to skip provisioning when secrets are injected externally.
- **Test output isolation** — Tests run with `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` so OTel SDK stays active for tracing tests without emitting noise.