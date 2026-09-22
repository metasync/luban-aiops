---
kind: build_system
name: Makefile-driven Monorepo Build, Image & GitOps Pipeline
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
    - products/platform-gateway/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - shared/shared-contracts/scripts/validate_password_policy.py
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## What system/approach is used

The repository uses a **GNU Make-based monorepo build system** layered over Docker image builds and Kustomize GitOps overlays. There is no CI pipeline file in `.github/workflows`; the root `Makefile` is explicitly designed as a "forge-agnostic" gate that runs identically locally and under any CI (`make verify`). Python products are built with **uv** (lockfile-frozen installs) and containerized into images tagged with a coordinated semver+gitsha scheme sourced from the root `VERSION` file.

## Key files and packages

- Root orchestrator: `Makefile` — declares product lists, computes coordinated `IMAGE_TAG`, delegates per-product `build/test/lint/sync`, renders Kustomize overlays, validates policies and versions, and wires deploy/e2e.
- Shared fragments: `mk/defaults.mk` (overridable defaults for platform, registry, base image pins), `mk/image.mk` (shared `build/push/lint` targets using `docker build --platform $(IMAGE_PLATFORM)`), `mk/python.mk` (shared `sync/test` targets running `uv sync --frozen` + `pytest` with OTel exporters disabled).
- Per-product Makefiles: each under `products/<name>/Makefile` sets only `IMAGE_NAME` and includes the two shared fragments; e.g. `products/agent-platform/Makefile`.
- Product Dockerfiles: one per service, all `FROM luban-aiops/base-uv:al2023`, copy `pyproject.toml` + `uv.lock` first, run `uv sync --frozen --no-dev`, then `EXPOSE 8000` and `CMD ["uv", "run", "<entrypoint>"]`.
- Base image: `shared/base-images/base-uv/Dockerfile` built via `make base-images` with pinned `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`.
- Version source: `VERSION` (currently `0.42.0`) — single source of truth consumed by root `PLATFORM_VERSION` and validated across products via `shared/shared-contracts/scripts/validate_version.py`.
- GitOps overlays: `shared/platform-ops/gitops/dev-k8s/` (base manifests per service, `kustomization.yaml`, `deploy.sh`); overlay variants under `runtime-profiles/{default,mutating-dev,browser-dev}`; rendered via `kustomize build --load-restrictor LoadRestrictionsNone`.
- Coordinated image state: `shared/platform-ops/gitops/dev-k8s/.images.env` written by `make build` so `make deploy` always deploys the same set of images.
- Policy contracts: canonical bundles in `shared/shared-contracts/policies/` synced to consumers via `make sync-policy`; validated via scripts under `shared/shared-contracts/scripts/`.

## Architecture and conventions

### Layered makefile design
Each layer has a single responsibility:
1. `mk/defaults.mk` — configuration-only (all values use `?=`, command-line overrides win).
2. `mk/image.mk` / `mk/python.mk` — reusable targets; included by every product Makefile.
3. Per-product `Makefile` — declares `IMAGE_NAME` and includes fragments.
4. Root `Makefile` — aggregates products, computes coordinated tags, enforces cross-cutting checks.

### Coordinated image tagging
The root `IMAGE_TAG` is computed once as `<semver>-<prefix>[-<profile>]-<gitsha>` (dirty trees append `-dirty-<timestamp>`). All nine services plus the operator portal are built with this tag and recorded in `.images.env`. The `push` target re-tags to `$(REGISTRY)/luban-aiops/<name>:$(IMAGE_TAG)` before pushing.

### Product isolation
Python dependencies are isolated per product via `uv.lock` and installed with `uv sync --frozen`. Tests run with OpenTelemetry exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) to avoid OTLP retry noise while keeping tracing SDKs active for tests.

### GitOps-first deployment
Deployment is not done by `kubectl apply` directly; `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which uses Kustomize overlays. Overlays are verified at build time via `make overlays` (`kustomize build` against each overlay path). Samples (acme-admin app, skills) are deployed out-of-band via `make deploy-samples` / `make deploy-sample-app` so the base overlay never names them (per SPEC-050 R-11).

### Verification gate
`make verify` composes the pre-commit/pre-push gate: `test` → `overlays` → `validate-policy` → `validate-policy-scenarios` → `validate-version` → `validate-secret-vocabulary` → `validate-password-policy` → `secret-delivery-demo`. Failure anywhere aborts the chain.

### End-to-end testing
`make e2e` runs shell scripts under `shared/platform-ops/e2e/` against a deployed dev cluster after port-forwarding `platform-gateway:18083` and `identity-service:18081`. It also requires `make deploy-sample-app` and `make deploy-samples` to have been run.

## Conventions and constraints

- **Single version source**: `VERSION` is the authoritative platform version; `make validate-version` enforces lockstep between it and every product's declared version.
- **No mutable base images**: base image tags are pinned (`al2023`, `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`); `latest` is never used.
- **Frozen dependency resolution**: all Python installs use `uv sync --frozen` against `uv.lock`; no transitive drift is allowed.
- **Image platform control**: `IMAGE_PLATFORM ?= linux/amd64` is the default; arm64 local/kind builds override via `make build IMAGE_PLATFORM=linux/arm64`.
- **Registry push gated**: images are only pushed when `REGISTRY` is set; otherwise builds stay local under `luban-aiops/<name>:<tag>`.
- **Kind auto-load optional**: `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` loads built images into a kind cluster after `make build`.
- **Policy bundling**: policy YAMLs live in `shared/shared-contracts/policies/` and are copied (not symlinked) into consumers via `make sync-policy`; changes must be propagated through that target.
- **Secret vocabulary lockstep**: `make validate-secret-vocabulary` ensures secret literal declarations stay synchronized across agent-platform, tool-gateway, and skills-hub.
- **Password policy contract**: per SPEC-062 R-2, `password-policy.yaml` is authored once and synced into tool-gateway; `make validate-password-policy` pins the connector floor to it.
- **Samples kept out of base overlay**: samples are deployed separately via `make deploy-samples` / `make deploy-sample-app` so `make deploy` never references sample resources (SPEC-050 R-11).
- **Dockerfile lint fallback**: `make lint` prefers `hadolint` if available, falls back to `docker run hadolint/hadolint`, and skips silently if neither is present.