---
kind: build_system
name: Monorepo Build & Image Orchestration via Root Makefile and Shared Fragments
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
    - products/platform-gateway/Dockerfile
    - products/agent-platform/pyproject.toml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
---

## What system/approach is used

The repository uses a **Makefile-driven monorepo build system** centered on a root `Makefile` that delegates to per-product sub-Makefiles, which in turn include shared fragments under `mk/`. Python products are built with **uv** (lockfile-first via `uv sync --frozen`) and packaged into Docker images using a single shared base image (`luban-aiops/base-uv`). Deployment is GitOps-oriented: Kustomize overlays under `shared/platform-ops/gitops/` are rendered as part of verification and deployed through `make deploy`, which wraps `dev-k8s/deploy.sh`.

There is no CI pipeline file checked into this snapshot; the root Makefile explicitly states it is "forge-agnostic" and intended to be the same gate locally and under any CI.

## Key files and packages

- **Root orchestrator**: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), coordinated image tag computation, cross-cutting targets (`sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `e2e`, `clean`), policy sync, and version validation.
- **Shared build fragments**:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, tag prefix/profile).
  - `mk/image.mk` — generic `build` / `push` / `lint` targets for any product with a `Dockerfile`; computes `IMAGE_REF` from `IMAGE_NAME` + `IMAGE_TAG`.
  - `mk/python.mk` — `sync` and `test` targets that run `uv sync --frozen` then `uv run pytest` with OTLP exporters disabled so tests stay quiet while tracing stays active.
- **Per-product entry points**: each product directory under `products/<name>/` has a tiny `Makefile` that sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk` (or just `image.mk` for the non-Python `operator-portal`).
- **Base image**: `shared/base-images/base-uv/Dockerfile` built by `make base-images` using pinned `UV_VERSION` and `PYTHON_VERSION` from `mk/defaults.mk`.
- **Deployment scripts**: `shared/platform-ops/gitops/dev-k8s/deploy.sh` calls `deploy-overlay.sh` plus a sequence of `sync-*` secret provisioning scripts (delegation, audit, execution signing/handoff, skills, incidents, sessions DB, OTel) before reconciling the Keycloak realm and portal OIDC client.
- **Version lockstep**: root `VERSION` file is the single source of truth; `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against all products.
- **Policy sync**: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into `tool-gateway`, `platform-gateway`, and the dev-k8s overlay; `make validate-policy` validates it against the JSON schema.

## Architecture and conventions

1. **Two-level Makefile hierarchy.** The root `Makefile` owns orchestration; each product's `Makefile` is a thin shim that only declares `IMAGE_NAME` and includes the shared fragments. This lets you run `make -C products/<name>` standalone or `make verify` at the repo root.
2. **Coordinated tagging.** The root computes one `IMAGE_TAG` per invocation using the pattern `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for uncommitted changes). All images produced by `make build` share this tag, and `.images.env` is written so `make deploy` can reference them consistently.
3. **Single base image strategy.** Every Python service multi-stage builds from `luban-aiops/base-uv:<tag>`, which itself is built once from `shared/base-images/base-uv/Dockerfile` with pinned uv and Python versions. Product `Dockerfile`s only `COPY src ./src` and run `uv sync --frozen --no-dev`.
4. **Lockfile-first dependency management.** Each product pins dependencies in `pyproject.toml` + `uv.lock`; `uv sync --frozen` enforces exact versions. Dev-only deps live in `[dependency-groups] dev`.
5. **Image platform abstraction.** `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64` for local kind on arm64 hosts); the root `base-images` target honors it too.
6. **Kind auto-loading.** Setting `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME=<name>` after `make build` automatically loads all nine images into the named kind cluster.
7. **GitOps deployment flow.** `make deploy` → `dev-k8s/deploy.sh` → `deploy-overlay.sh` + sequential secret-sync scripts → optional Keycloak realm reconciliation. Secrets can be skipped per-script via `SKIP_*_SECRETS=true` for CI environments.
8. **Verification gate.** `make verify` = `test` + `overlays` (kustomize build check on `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`) + `validate-policy` + `validate-version`. Intended as the pre-commit/pre-push gate.
9. **End-to-end demos.** `make e2e` runs `skills-demo.sh`, `incident-demo.sh`, `mutating-demo.sh` against a deployed cluster after port-forwarding `platform-gateway` and `identity-service`.

## Conventions and constraints

- **Every Python product must expose an entrypoint script** in `pyproject.toml` `[project.scripts]` (e.g. `agent-service`, `platform-gateway`, `audit-service`) because the `CMD` in each `Dockerfile` invokes `uv run <script-name>`.
- **Products must declare `IMAGE_NAME`** in their `Makefile` before including `mk/image.mk`; otherwise the image tag resolves incorrectly.
- **Versions must stay in lockstep**: the root `VERSION` semver must match every product's `pyproject.toml` `version` field; `make validate-version` enforces this invariant via `shared/shared-contracts/scripts/validate_version.py ../..`.
- **Policy bundles are canonicalized**: `shared/shared-contracts/policies/policy-default.yaml` is the single source; consumers must not edit it directly — use `make sync-policy` to propagate changes.
- **Dockerfile linting is mandatory in verification**: `make lint` runs `hadolint` (with a `docker run hadolint/hadolint` fallback) on every product `Dockerfile`.
- **Tests must tolerate missing OTLP backends**: the shared `python.mk` disables trace/metric/log exporters via `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` so unit tests pass without an observability backend while still exercising the SDK.
- **Secret provisioning is opt-in per script** via environment variables (`SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_EXECUTION_SIGNING_SECRET`, `SKIP_EXECUTION_HANDOFF_SECRET`, `SKIP_SKILLS_SECRETS`, `SKIP_INCIDENT_SECRETS`, `SKIP_OTEL_SECRETS`), allowing CI to skip steps where secrets are injected externally.
- **No per-language toolchains beyond uv and docker**: there are no Gradle, Maven, npm/yarn build targets in the root Makefile; the frontend SPA under `operator-portal/web-ui/app` is built inside its own Dockerfile and is not invoked from the root build surface.