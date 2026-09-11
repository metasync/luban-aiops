---
kind: build_system
name: Multi-Product Build, Image & GitOps Deployment System
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
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - shared/shared-contracts/scripts/policy_diff.py
---

## What system/approach is used

The repository uses a **Makefile-driven multi-product build system** centered on three layers:

1. **Root Makefile** (`Makefile`) — orchestrates cross-cutting concerns: dependency sync, test execution, image building, policy validation, Kustomize overlay rendering, and deployment.
2. **Shared fragments in `mk/`** — reusable Make targets for Python (uv) tooling (`python.mk`), Docker image building/pushing/linting (`image.mk`), and a single source of overridable defaults (`defaults.mk`).
3. **Per-product Makefiles** — minimal files that set `IMAGE_NAME` and include the shared fragments; each product also ships its own `Dockerfile`, `pyproject.toml`, and `uv.lock`.

Container images are built with Docker using a shared base image `luban-aiops/base-uv` (Alpine Linux + uv + Python pinned via `BASE_UV_PYTHON_VERSION` / `BASE_UV_UV_VERSION` in `mk/defaults.mk`). Kubernetes manifests are managed as **Kustomize overlays** under `shared/platform-ops/gitops/` (base + dev-k8s + runtime-profiles overlays).

## Key files and packages

- Root orchestration: `Makefile`, `VERSION`, `.python-version`
- Shared build fragments: `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Per-product entry points (example): `products/agent-platform/Makefile`, `products/agent-platform/Dockerfile`, `products/agent-platform/pyproject.toml`, `products/agent-platform/.python-version`
- Base image definition: `shared/base-images/base-uv/Dockerfile`
- GitOps overlays: `shared/platform-ops/gitops/dev-k8s/kustomization.yaml`, `shared/platform-ops/gitops/runtime-profiles/*/kustomization.yaml`
- Deploy script: `shared/platform-ops/gitops/dev-k8s/deploy.sh` (wraps `deploy-overlay.sh` plus secret-sync helpers)
- Secret provisioning helpers: `shared/platform-ops/gitops/sync-*.sh` (delegation, audit, execution-signing/handoff, skills, incidents, browser credentials, sessions DB, OTel, runtime secret)
- Policy validation scripts: `shared/shared-contracts/scripts/validate_policy.py`, `validate_policy_scenarios.py`, `validate_version.py`, `validate_secret_vocabulary.py`, `policy_diff.py`

## Architecture and conventions

### Product model
Each service lives under `products/<name>/` and follows an identical layout: `src/<service_name>/`, `tests/`, `Dockerfile`, `Makefile`, `pyproject.toml`, `uv.lock`, `.python-version`. The root Makefile enumerates them explicitly:
- `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`
- `IMAGE_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway operator-portal`

### Image tagging strategy
A **coordinated tag** is computed once by the root Makefile and reused across all products:
- Clean tree: `<PLATFORM_VERSION>-<IMAGE_TAG_PREFIX>[-<IMAGE_TAG_PROFILE>]-<gitsha>`
- Dirty tree: same but suffixed `-dirty-<YYYYMMDDHHMMSS>`
- `PLATFORM_VERSION` is read from the root `VERSION` file (currently `0.36.1`).

After `make build`, the root Makefile writes `shared/platform-ops/gitops/dev-k8s/.images.env` mapping logical names (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, etc.) to `luban-aiops/<product>:<IMAGE_TAG>`, which the deploy script consumes.

### Multi-stage container builds
Every product `Dockerfile` starts from `FROM luban-aiops/base-uv:al2023`, copies only `pyproject.toml`, `uv.lock`, `.python-version`, `README.md`, and `src/`, then runs `uv sync --frozen --no-dev`. This enforces reproducible installs from frozen lockfiles and keeps images small.

### Python toolchain
All Python products use **uv** as both dependency manager and runner. The shared `mk/python.mk` target `sync` runs `uv sync --frozen`; `test` re-syncs then runs `uv run pytest` with OpenTelemetry exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) so tests produce no OTLP noise while keeping tracing SDKs active.

### Kustomize overlays
Deployment manifests live under `shared/platform-ops/gitops/` with a layered structure:
- `base/` — core service deployments, services, RBAC, shared configmaps/secrets
- `dev-k8s/` — dev overlay that references the base and injects image tags via `.images.env`
- `runtime-profiles/{default,mutating-dev,browser-dev}/` — feature toggles (e.g., mutating tools, browser sidecars)

The root `overlays` target runs `kustomize build --load-restrictor LoadRestrictionsNone <overlay>` to validate every overlay at verify time.

### Version and policy lockstep
- `make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` against the repo root to enforce that the root `VERSION` stays in lockstep with per-product versions.
- `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.
- `make validate-policy` validates the canonical policy against JSON schema; `make validate-policy-scenarios` evaluates scenario expectations against both engines; `make policy-diff` reports per-(role, action) differences between canonical and a candidate bundle.
- `make validate-secret-vocabulary` enforces redaction vocabulary consistency between `agent-platform` and `tool-gateway`.

### Deployment flow
`make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which:
1. Calls `deploy-overlay.sh` to render and apply the Kustomize overlay.
2. Runs a sequence of `sync-*.sh` helpers to provision secrets (delegation, audit ingestion, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) — each helper supports a `SKIP_*_SECRETS=true` env var for CI where secrets are injected externally.
3. Optionally reconciles the Keycloak realm and portal OIDC client (`RECONCILE_OIDC_PORTAL_CLIENT`).

### Local kind workflow
`AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name> make build` automatically loads the built images into the named kind cluster after building. E2E demos are driven by `make e2e`, which runs scripts under `shared/platform-ops/e2e/` against a deployed cluster.

## Conventions and constraints

- **Single source of truth for versions**: `VERSION` at the repo root drives coordinated image tags; per-product versions must stay in lockstep (enforced by `make validate-version`).
- **Frozen dependencies**: All `uv sync` invocations use `--frozen`, requiring `uv.lock` to be committed alongside changes.
- **No `latest` tags**: `defaults.mk` pins `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION`; images are tagged with explicit semver-derived tags.
- **Image naming convention**: Images are always published as `luban-aiops/<product>:<tag>` locally; when `REGISTRY` is set, they are additionally re-tagged to `<REGISTRY>/luban-aiops/<product>:<tag>` before push.
- **Platform pinning**: `IMAGE_PLATFORM ?= linux/amd64` is the default; cross-compilation is done by overriding this variable (e.g., `linux/arm64` for native arm64 kind clusters).
- **Policy bundling**: The canonical policy lives in `shared/shared-contracts/policies/policy-default.yaml` and must be propagated to consumers via `make sync-policy`; direct edits to consumer copies are overwritten.
- **Secrets provisioning gate**: `deploy.sh` provisions secrets via dedicated `sync-*.sh` scripts; CI should set the corresponding `SKIP_*_SECRETS=true` flags so deployment does not fail open or block on missing local secrets.
- **Verification gate**: `make verify` aggregates `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, and `validate-secret-vocabulary` — intended as the pre-commit/pre-push gate (documented in the root Makefile header).