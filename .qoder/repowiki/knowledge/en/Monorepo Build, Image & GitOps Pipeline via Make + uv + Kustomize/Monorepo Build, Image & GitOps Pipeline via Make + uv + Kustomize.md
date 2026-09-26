---
kind: build_system
name: Monorepo Build, Image & GitOps Pipeline via Make + uv + Kustomize
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
    - products/platform-gateway/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
---

## What system/approach is used

The repository uses a **Make-driven monorepo build** that composes three layers:

1. **Python packaging**: each product under `products/<name>/` is an independent Python package managed by [uv](https://github.com/astral-sh/uv) with a pinned `pyproject.toml` and `uv.lock`. The shared fragment `mk/python.mk` provides `sync` (frozen install) and `test` targets that run `pytest` with OTLP exporters disabled so tracing tests stay quiet.
2. **Container images**: every service ships a `Dockerfile` based on the shared base image `shared/base-images/base-uv/Dockerfile` (AL2023 + pinned uv/python). The shared fragment `mk/image.mk` standardizes `build`, `push`, and `lint` (hadolint with docker-run fallback) targets; each product Makefile only sets `IMAGE_NAME` and includes both fragments.
3. **GitOps deployment**: Kubernetes manifests live in `shared/platform-ops/gitops/` and are rendered via `kustomize build --load-restrictor LoadRestrictionsNone`. Overlays (`dev-k8s`, `runtime-profiles/default|mutating-dev|browser-dev`) are validated as part of verification.

There is no CI configuration checked into `.github/workflows`; the root `Makefile` declares itself "Forge-agnostic" and is intended to be the pre-commit/pre-push gate across any forge.

## Key files and packages

- Root orchestration: `Makefile`, `VERSION`, `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Product entrypoints: `products/*/Makefile` (each only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`)
- Container images: `products/*/Dockerfile` (all follow the same pattern: `FROM luban-aiops/base-uv:al2023`, copy `pyproject.toml`/`uv.lock`/`src`, `uv sync --frozen --no-dev`, `CMD ["uv", "run", "<entrypoint>"]`)
- Base image: `shared/base-images/base-uv/Dockerfile`
- Deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` (wraps overlay render + secret provisioning scripts), `shared/platform-ops/gitops/runtime-profiles/*` overlays
- Cross-cutting validation: `shared/shared-contracts/scripts/{validate_policy.py,validate_policy_scenarios.py,validate_version.py,validate_secret_vocabulary.py,validate_password_policy.py,policy_diff.py}`

## Architecture and conventions

### Coordinated tagging
The root `Makefile` computes a single `IMAGE_TAG` once per invocation using the formula `<semver>-<prefix>[-<profile>]-<gitsha>` (dirty builds append `-dirty-<timestamp>`). Semver comes from the root `VERSION` file. All product images are built with this tag and written to `shared/platform-ops/gitops/dev-k8s/.images.env`, which `make deploy` consumes. This enforces that all services ship together as one release artifact.

### Product decomposition
Products are split by stable architectural boundary (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway, operator-portal). Each has its own `src/<package>/`, `tests/`, `pyproject.toml`, `uv.lock`, `Dockerfile`, and tiny `Makefile`. The root `Makefile` enumerates them in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists — adding a new product requires updating those lists.

### Shared fragments over duplication
`mk/defaults.mk` centralizes all overridable settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`). `mk/image.mk` and `mk/python.mk` provide reusable targets. A product Makefile is typically three lines: set `IMAGE_NAME`, include the two fragments. This makes `make -C products/<name> help` work standalone while still honoring root-level overrides.

### Policy and contract synchronization
Policy bundles are authored once in `shared/shared-contracts/policies/` and copied to consumers via `make sync-policy`. Password policy is similarly synchronized to `tool-gateway`. Consumers validate against JSON schemas via scripts under `shared/shared-contracts/scripts/`.

### Version lockstep
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to assert that the root `VERSION` matches every product version. Secret-literal vocabularies are cross-checked via `make validate-secret-vocabulary`.

### Deployment flow
`make deploy` calls `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders the overlay via `deploy-overlay.sh` and then runs a series of idempotent `sync-*` scripts that provision secrets (token delegation, audit ingest, execution signing/handoff, skills credentials, browser credentials, sessions DB, OTel credentials, Keycloak realm/client). Secrets can be skipped with environment variables (`SKIP_*_SECRETS=true`) for CI environments where they are injected externally.

### Local dev workflow
`make base-images` builds the shared `base-uv` image. `make build` builds all images and optionally auto-loads them into a kind cluster when `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set. `make e2e` runs demo scripts against a deployed cluster after port-forwarding the gateway and identity-service.

## Conventions and constraints

- **Single source of truth for versions**: `VERSION` at the repo root drives coordinated image tags and is enforced by `make validate-version`.
- **Frozen dependency resolution**: all `uv sync` invocations use `--frozen`, pinning installs to `uv.lock`.
- **No `latest` tags**: `mk/defaults.mk` comments explicitly state pinned values are defaults for reproducible builds — never `latest`.
- **Image naming convention**: local images are always `luban-aiops/<product>:<tag>`; pushing to a registry re-tags to `$(REGISTRY)/luban-aiops/<product>:<tag>`.
- **Base image**: all service Dockerfiles derive from `luban-aiops/base-uv:al2023`, built from `shared/base-images/base-uv/Dockerfile` with pinned `UV_VERSION` and `PYTHON_VERSION`.
- **Verification gate**: `make verify` chains `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, and `secret-delivery-demo` — this is the canonical pre-commit/pre-push gate.
- **Samples are out-of-band**: tutorial samples under `samples/` are never included in the base overlay (per SPEC-050 R-11); they are installed separately via `make deploy-samples` and `make deploy-sample-app`.
- **Runtime profiles**: deployments select behavior via Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/` (default, mutating-dev, browser-dev), selected through `select-runtime-profile.sh`.
- **Secrets are provisioned imperatively**: `deploy.sh` calls dedicated `sync-*` scripts rather than embedding secrets in manifests; each script supports a `SKIP_*_SECRETS` env var for CI.