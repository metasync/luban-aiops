---
kind: build_system
name: Monorepo Makefile + Docker/Kustomize Build & Deploy Pipeline
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
    - products/agent-platform/Dockerfile
    - products/operator-portal/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/policy_diff.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
---

## What system/approach is used

The repository uses a **Makefile-driven monorepo build** layered on top of three core tools:

- **GNU make** as the single entry point (`make verify`, `make build`, `make deploy`, `make e2e`) that orchestrates per-product routines.
- **uv** (Python package manager) for dependency resolution and test execution inside each product, using frozen lockfiles (`uv sync --frozen`, `uv run pytest`).
- **Docker** for container image builds, with a shared base image `luban-aiops/base-uv:al2023` built from `shared/base-images/base-uv/Dockerfile`.
- **Kustomize** for GitOps overlay rendering, validated via `kustomize build --load-restrictor LoadRestrictionsNone` during verification.

There is no CI configuration file in `.github/workflows`; the root `Makefile` explicitly states it is "forge-agnostic" and intended to be the same gate locally and under any CI. The `.github/` directory only contains issue templates and a pull request template — no workflow YAMLs were found.

## Key files and packages

- Root orchestration: `Makefile`, `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Version source of truth: `VERSION` (semver string)
- Per-product entry points: `products/<name>/Makefile` (minimal, sets `IMAGE_NAME` then includes `../../mk/image.mk` and `../../mk/python.mk`), `products/<name>/Dockerfile`, `products/<name>/pyproject.toml`, `products/<name>/uv.lock`
- Base image: `shared/base-images/base-uv/Dockerfile`
- Deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` plus sibling `sync-*` scripts and `deploy-overlay.sh`
- Policy validation: `shared/shared-contracts/scripts/validate_policy.py`, `validate_policy_scenarios.py`, `policy_diff.py`, `validate_version.py`, `validate_secret_vocabulary.py`
- Operator portal multi-stage build: `products/operator-portal/Dockerfile` (Node 22 build stage → nginx runtime)

## Architecture and conventions

### Product model
Each service under `products/` is an independent Python package with its own `pyproject.toml` + `uv.lock`, `Dockerfile`, and tiny `Makefile`. The root `Makefile` enumerates them in two lists:
- `PYTHON_PRODUCTS` — get `sync` / `test` targets
- `IMAGE_PRODUCTS` — get `build` / `push` / `lint` targets

This keeps cross-cutting logic centralized while letting products stand alone via `make -C products/<name>`.

### Coordinated image tagging
The root `make build` computes one `IMAGE_TAG` once and applies it to every product image. Tag format: `<semver>-<prefix>[-<profile>]-<gitsha>` (with `-dirty-<timestamp>` suffix when the working tree has uncommitted changes). The semver comes from `VERSION`; prefix/profile default to `dev-k8s` / empty but are overridable via `IMAGE_TAG_PREFIX` / `IMAGE_TAG_PROFILE`. After building, the tag is written to `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy step consumes the exact images just built.

### Image reference convention
Images are tagged locally as `luban-aiops/<product>:<tag>`. When `REGISTRY` is set, they are additionally re-tagged to `$(REGISTRY)/luban-aiops/<product>:<tag>` before push. All Python services use the shared `luban-aiops/base-uv:al2023` base image; the operator portal uses a Node 22 build stage served by `nginxinc/nginx-unprivileged:1.27-alpine`.

### Verification gate
`make verify` runs the full pre-commit/pre-push gate: per-product tests, Kustomize overlay rendering, policy bundle validation against JSON schema, scenario evaluation against both engines, version lockstep validation, and secret-vocabulary validation.

### Deployment flow
`make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which runs `deploy-overlay.sh` followed by a sequence of idempotent `sync-*` scripts that provision secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel ingest) and optionally reconcile a Keycloak realm and portal OIDC client. The target namespace defaults to `dev-luban-aiops`.

### Versioning constraints
- `VERSION` at the repo root is the single source of truth for the platform release version.
- `make validate-version` enforces that every product's declared version stays in lockstep with the root `VERSION` (via `shared/shared-contracts/scripts/validate_version.py`).
- The operator portal injects `PLATFORM_VERSION` into the SPA at build time by copying the root `VERSION` into the Node build context.

### Policy management
A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to all consumers (tool-gateway, platform-gateway, dev-k8s overlay). `make validate-policy` and `make validate-policy-scenarios` enforce schema and behavioral conformance across both policy engines.

## Conventions and constraints

- Every Python product must declare its dependencies in `pyproject.toml` and pin them in `uv.lock`; `uv sync --frozen` is the only supported way to install deps (no editable installs).
- Tests run with OpenTelemetry exporters disabled via environment variables (`OTEL_TRACES_EXPORTER=none`, etc.) to keep output clean while keeping the SDK active for tracing tests.
- Dockerfiles are linted via `hadolint` (with a docker-run fallback) through the shared `mk/image.mk` `lint` target.
- Cross-platform image builds default to `linux/amd64` (`IMAGE_PLATFORM ?= linux/amd64`) and can be overridden per-invocation.
- Local kind cluster loading is opt-in via `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME`; when enabled, `make build` automatically loads all nine images into the named cluster.
- E2E demos require a deployed cluster plus port-forwarded services for `platform-gateway` (18083) and `identity-service` (18081); `make e2e` runs the demo scripts in `shared/platform-ops/e2e/`.
- Samples are installed out-of-band via `make deploy-samples` so the base overlay never names a sample resource (enforced by SPEC-050 R-11, referenced in the root Makefile comments).
- Secrets provisioning is guarded by `SKIP_*_SECRETS` environment variables so CI can skip local-only secret setup.