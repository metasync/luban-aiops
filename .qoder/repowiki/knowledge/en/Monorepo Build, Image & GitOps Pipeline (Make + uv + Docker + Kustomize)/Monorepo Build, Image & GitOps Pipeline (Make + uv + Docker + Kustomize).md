---
kind: build_system
name: Monorepo Build, Image & GitOps Pipeline (Make + uv + Docker + Kustomize)
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
    - products/platform-gateway/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/deploy-overlay.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-browser-credentials.sh
    - shared/platform-ops/gitops/sync-sessions-db.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
---

## System overview

The Luban platform is built as a **monorepo** with a single root `Makefile` that orchestrates nine Python services plus an operator portal. The build pipeline is **forge-agnostic**: the same `make verify` target runs locally and in CI, and every product can also be built standalone via `make -C products/<name>`.

### Core tools

| Concern | Tool | Where configured |
|---|---|---|
| Python dependency resolution | `uv` (lockstep via `uv.lock`) | per-product `pyproject.toml` / `uv.lock`; shared `mk/python.mk` |
| Container images | Docker (`docker build --platform <arch>`) | per-product `Dockerfile` using `FROM luban-aiops/base-uv:al2023` |
| Base image | Custom `base-uv` on Amazon Linux 2023 | `shared/base-images/base-uv/Dockerfile`, built by `make base-images` |
| Kubernetes manifests | Kustomize overlays | `shared/platform-ops/gitops/dev-k8s/...` |
| Deployment | Shell scripts under `shared/platform-ops/gitops/` | `make deploy` wraps `dev-k8s/deploy.sh` |
| Versioning | Single `VERSION` file at repo root | enforced by `make validate-version` |

### Architecture of the Make system

1. **Shared fragments live in `mk/`**:
   - `mk/defaults.mk` — single source of overridable settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`). All values use `?=`, so command-line overrides always win.
   - `mk/image.mk` — provides `build`, `push`, `lint` targets for any product that sets `IMAGE_NAME`. Handles local tagging, optional registry re-tagging, and hadolint (with docker-run fallback).
   - `mk/python.mk` — provides `sync` and `test` targets that run `uv sync --frozen` then `uv run pytest` with OTel exporters disabled to keep test output clean.

2. **Per-product Makefiles are thin wrappers** that only set `IMAGE_NAME` and include the two fragments above. Example: `products/agent-platform/Makefile` is ten lines.

3. **Root `Makefile` owns cross-cutting concerns**:
   - Lists `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` arrays and iterates them for `sync`, `test`, `lint`, `build`, `push`.
   - Computes a coordinated `IMAGE_TAG` from `VERSION` + prefix/profile + git SHA (+ `-dirty-<timestamp>` for unclean trees) and writes it into `shared/platform-ops/gitops/dev-k8s/.images.env` so the overlay consumes the exact images just built.
   - Optionally auto-loads images into a kind cluster when `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set.
   - Provides policy tooling (`sync-policy`, `validate-policy`, `validate-policy-scenarios`, `policy-diff`) that copies a canonical policy bundle from `shared/shared-contracts/policies/policy-default.yaml` into both gateway consumers and the kustomize base.
   - Validates version lockstep across `VERSION`, each product's metadata, and the portal via `shared/shared-contracts/scripts/validate_version.py`.
   - Validates secret-literal lockstep across agent-platform / tool-gateway / skills-hub.
   - Renders all Kustomize overlays (`kustomize build --load-restrictor LoadRestrictionsNone`) as part of `verify`.

### Image naming and tagging

- Local images are tagged `luban-aiops/<product>:<IMAGE_TAG>`.
- When `REGISTRY` is set, images are additionally tagged `<REGISTRY>/luban-aiops/<product>:<IMAGE_TAG>` and pushed.
- The coordinated tag format is `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]`, where semver comes from the root `VERSION` file (currently `0.39.1`).
- The `.images.env` state file produced by `make build` is consumed by the dev-k8s overlay so deployments always reference the images just built.

### Deployment flow

`make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which:
1. Calls `deploy-overlay.sh` to apply the Kustomize overlay.
2. Runs a series of idempotent `sync-*` scripts that provision secrets (delegation, audit ingestion, execution signing/handoff, skills, incidents, browser credentials, OTel), create the sessions database, and reconcile the Keycloak realm and portal OIDC client.
3. Each script supports a `SKIP_*` env var for CI environments where secrets are injected externally.

Samples (tutorial skills and the acme-admin demo app) are deployed out-of-band via `make deploy-samples` / `make deploy-sample-app` so the base overlay never names sample resources (per SPEC-050 R-11).

### Verification gate

`make verify` is the pre-commit/pre-push gate and composes:
- `test` — runs every Python product's pytest suite via `uv run pytest`.
- `overlays` — validates all Kustomize overlays render.
- `validate-policy` + `validate-policy-scenarios` — validates the canonical policy bundle against its JSON schema and evaluates scenario expectations against both engines.
- `validate-version` — enforces version lockstep.
- `validate-secret-vocabulary` — enforces secret-literal lockstep.

### E2E and samples

`make e2e` runs shell-based demos under `shared/platform-ops/e2e/` against a deployed cluster, requiring prior `make deploy` and port-forwards for the chat legs. The acme-admin sample suite additionally requires `make deploy-sample-app` and `make deploy-samples`.

### Conventions and constraints observed

- Every Python product must have a `Dockerfile`, `pyproject.toml`, `uv.lock`, and a `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`.
- Images must derive from `luban-aiops/base-uv:al2023` and install dependencies with `uv sync --frozen --no-dev`.
- The root `VERSION` file is the single source of truth; `make validate-version` enforces lockstep between it and every product's metadata.
- Policy bundles are authored once in `shared/shared-contracts/policies/policy-default.yaml` and copied to consumers via `make sync-policy`.
- Secrets provisioning is scripted and idempotent; CI skips provisioning via `SKIP_*` env vars rather than editing scripts.
- The verification gate (`make verify`) is forge-agnostic and intended to run identically locally and in CI.