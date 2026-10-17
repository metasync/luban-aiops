---
kind: build_system
name: 'Luban Workspace Build System: Makefile Orchestration, uv/PyPI Images, and Kustomize GitOps'
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
    - products/operator-portal/Makefile
    - products/agent-platform/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - VERSION
---

## What system/approach is used

The repository uses a **GNU make-driven monorepo build** layered on top of three toolchains:

- **Python products**: `uv` (frozen lockfiles via `uv sync --frozen`, pytest for tests).
- **Container images**: Docker with a shared base image (`shared/base-images/base-uv`) built from Amazon Linux 2023 minimal.
- **Kubernetes deployment**: Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/`, rendered by `kustomize build` as part of verification.

There is no `.github/workflows/` directory present in this snapshot; the root `Makefile` is explicitly designed to be forge-agnostic — `make verify` is the pre-commit/pre-push gate that runs identically locally and under any CI.

## Key files and packages

- Root orchestrator: `Makefile` (281 lines) — aggregates per-product routines, owns cross-cutting concerns (GitOps overlay checks, verification gate, coordinated deploy pipeline).
- Shared fragments: `mk/defaults.mk` (overridable build settings), `mk/image.mk` (container-image targets), `mk/python.mk` (uv sync + pytest targets).
- Per-product entrypoints: each product under `products/<name>/` has a tiny `Makefile` that only sets `IMAGE_NAME` and includes the two shared fragments.
- Base image: `shared/base-images/base-uv/Dockerfile` — pinned `UV_VERSION=0.12.1`, Python 3.12, non-root `app` user (uid 1000).
- Product Dockerfiles: one per service (e.g. `products/agent-platform/Dockerfile`), all derived from `luban-aiops/base-uv:al2023`.
- GitOps overlays: `shared/platform-ops/gitops/dev-k8s/` (base manifests per service) plus runtime profiles under `runtime-profiles/`.
- Version single source of truth: `VERSION` (semver, currently `0.47.0`).
- Coordinated image state: `shared/platform-ops/gitops/dev-k8s/.images.env` written by `make build`, consumed by `make deploy`.

## Architecture and conventions

### Two-level Makefile hierarchy

The root `Makefile` declares two product lists:

```
PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway
IMAGE_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway operator-portal
```

It then dispatches `sync`, `test`, `lint`, `build`, and `push` by iterating over those lists and invoking `$(MAKE) -C products/$$p <target>`. Each product Makefile is intentionally thin — it only defines `IMAGE_NAME` (and optionally `IMAGE_CONTEXT` / `IMAGE_DOCKERFILE` for the portal) and includes `../../mk/image.mk` and/or `../../mk/python.mk`.

### Shared fragment contract

`mk/defaults.mk` is the single source of truth for overridable build settings. All values use `?=`, so command-line overrides always win (e.g. `make build IMAGE_PLATFORM=linux/arm64`). It guards against double inclusion via `ifndef LUBAN_DEFAULTS_INCLUDED`. The fragment is included both from the root Makefile and from `mk/image.mk` so standalone product builds resolve the same defaults.

### Image tagging strategy

Coordinated image tags are computed once at the root level:

```
<semver>-<prefix>[-<profile>]-<gitsha>
```

A dirty tree appends `-dirty-<timestamp>`. The tag is composed from `PLATFORM_VERSION` (from `VERSION`), `IMAGE_TAG_PREFIX` (default `dev-k8s`), `IMAGE_TAG_PROFILE`, and `git rev-parse --short HEAD`. `make build` writes the coordinated tag into `shared/platform-ops/gitops/dev-k8s/.images.env` alongside per-service image names (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, etc.), which `make deploy` consumes.

### Base image policy

All backend services derive from `luban-aiops/base-uv:al2023`, which pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` via build args. The image installs `curl-minimal` (not full curl, because Amazon Linux 2023 ships `curl-minimal` and installing full curl conflicts), installs uv to `/usr/local/bin`, creates a non-root `app` user (uid 1000), and sets `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=${PYTHON_VERSION}`, `UV_PYTHON_INSTALL_DIR=/app/.python`. Products run `uv sync --frozen --no-dev` during build.

### Verification gate

`make verify` is the canonical gate target. It chains:

```
test overlays validate-dashboards validate-policy validate-policy-scenarios validate-version validate-secret-vocabulary validate-password-policy secret-delivery-demo portal-test execution-failure-test
```

This covers product tests, Kustomize render checks, OpenObserve dashboard validation, policy bundle validation (against JSON schema and scenario expectations), version lockstep, secret vocabulary lockstep, password policy pinning, local secret-delivery demo, operator-portal Vitest + production build, and crash-safety failure test.

### Policy synchronization

Canonical policy bundles live in `shared/shared-contracts/policies/` and are copied into consumers via `make sync-policy`: `products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. A separate password policy is synced into `products/tool-gateway/src/tool_gateway/policies/password-policy.yaml`.

### Operator portal exception

The operator portal is not a Python product. Its Makefile sets `IMAGE_CONTEXT := ../..` (root build context, needed because the multi-stage Dockerfile requires the root `VERSION` file plus `web-ui/app`), and adds `test` (runs `npm --prefix web-ui/app test`) and `web-build` (runs `npm --prefix web-ui/app run build`, which invokes `tsc --noEmit && vite build`). `make verify` delegates to these via `portal-test`.

### Deployment flow

`make deploy` wraps `shared/platform-ops/gitops/dev-k8s/deploy.sh`. Samples are deployed out-of-band via `make deploy-samples` (invoking `samples/deploy-samples.sh`) so the base overlay never names a sample (SPEC-050 R-11). An optional `AUTO_LOAD_KIND=true` after `make build` loads all nine images into a kind cluster named by `KIND_CLUSTER_NAME`.

## Conventions and constraints

- **Forge-agnostic CI**: The root Makefile comment states `Forge-agnostic: make verify is the pre-commit/pre-push gate and runs the same checks locally and under any CI.` There is no `.github/workflows/` directory in this snapshot; CI is expected to invoke `make verify`.
- **Pinned dependencies**: Python deps via `uv sync --frozen`; base image via pinned `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`; no `latest` tags anywhere in the base image.
- **Single version source**: `VERSION` is the single source of truth for the platform release semver; `make validate-version` enforces lockstep between `VERSION`, every product, and the portal via `shared/shared-contracts/scripts/validate_version.py`.
- **Image naming convention**: Local images are tagged `luban-aiops/<service>:<tag>`; when `REGISTRY` is set they are re-tagged to `$(REGISTRY)/luban-aiops/<service>:<tag>`.
- **Non-root containers**: The base image switches to `USER app` (uid 1000); product images inherit this.
- **Overlay validation**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on every overlay listed in `OVERLAYS` (`dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`).
- **Dashboard validation**: `make validate-dashboards` runs `shared/platform-ops/dashboards/validate_dashboards.py`, which validates parseability, envelope/panel schema, and metric reference resolution against emitted OTEL streams (SPEC-065 R-3).
- **Portal build invariant**: `make verify` runs the portal's full Vitest suite and its typechecked production build; the comment notes "Vitest runs the whole suite and fails on zero tests, so there is no skip/zero-tests green path" (SPEC-063 R-8c).
- **Policy authoring discipline**: Canonical policies in `shared/shared-contracts/policies/` are the sole authoring location; consumers receive copies via `make sync-policy`, validated via `make validate-policy` and `make validate-policy-scenarios`.
- **Secret vocabulary lockstep**: `make validate-secret-vocabulary` enforces consistency across `agent-platform`, `tool-gateway`, and `skills-hub` via `shared/shared-contracts/scripts/validate_secret_vocabulary.py`.
- **Password policy floor**: `make validate-password-policy` validates the password-policy contract and pins the connector floor to it (SPEC-062 R-2).
- **Cross-platform images**: `IMAGE_PLATFORM ?= linux/amd64` (with `linux/arm64` documented for native local/kind builds on arm64 hosts); propagated through `docker build --platform $(IMAGE_PLATFORM)`.