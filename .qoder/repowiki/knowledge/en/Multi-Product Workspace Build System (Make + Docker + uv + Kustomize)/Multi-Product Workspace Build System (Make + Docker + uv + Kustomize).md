---
kind: build_system
name: Multi-Product Workspace Build System (Make + Docker + uv + Kustomize)
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/policy_diff.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - VERSION
---

## What system/approach is used

The repository is a multi-product Python workspace built with a layered, forge-agnostic build system:

- **GNU Make** at the root (`Makefile`) orchestrates cross-cutting concerns: per-product `sync`/`test`/`lint`/`build`/`push`, GitOps overlay validation, policy and version lockstep checks, and coordinated deployment.
- **Docker** builds container images for every product via shared fragments in `mk/image.mk`; each product only sets `IMAGE_NAME` and includes the fragment.
- **uv** is the Python dependency manager and runner. A shared base image (`shared/base-images/base-uv/Dockerfile`) installs a pinned `uv` (default `0.12.1`) on Amazon Linux 2023 minimal; products use `uv sync --frozen` against their own `uv.lock`.
- **Kustomize** renders GitOps overlays under `shared/platform-ops/gitops/<overlay>` as part of verification (`make overlays`).
- **Shell scripts** drive deployment (`shared/platform-ops/gitops/dev-k8s/deploy.sh`), sample installation (`samples/deploy-samples.sh`), and secret/runtime syncing.

There is no CI configuration file in this snapshot; the root Makefile is explicitly documented as the pre-commit/pre-push gate that runs identically locally and in any CI.

## Key files and packages

- Root orchestration: `Makefile`, `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Shared base image: `shared/base-images/base-uv/Dockerfile`
- Product manifests (one per service): `<product>/Makefile` (sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`), `<product>/Dockerfile`, `<product>/pyproject.toml`, `<product>/uv.lock`, `<product>/.python-version`
- Coordinated image tag state: `shared/platform-ops/gitops/dev-k8s/.images.env` (written by `make build`)
- Platform version single source of truth: `VERSION` (semver, e.g. `0.37.1`)
- Policy bundle canonical location: `shared/shared-contracts/policies/policy-default.yaml`, synced to consumers by `make sync-policy`
- Validation scripts: `shared/shared-contracts/scripts/validate_policy.py`, `validate_policy_scenarios.py`, `policy_diff.py`, `validate_version.py`, `validate_secret_vocabulary.py`
- GitOps overlays: `shared/platform-ops/gitops/dev-k8s/...`, `runtime-profiles/default|mutating-dev|browser-dev`
- E2E demo scripts: `shared/platform-ops/e2e/*.sh`

## Architecture and conventions

### Product layout
Every backend product under `products/<name>/` follows an identical structure: `src/<package>/`, `tests/`, `Dockerfile`, `Makefile`, `pyproject.toml`, `uv.lock`, `.python-version`. The root Makefile enumerates them in two lists — `PYTHON_PRODUCTS` (has tests) and `IMAGE_PRODUCTS` (has a container image).

### Image tagging strategy
The root computes a coordinated `IMAGE_TAG` once: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, or `...-dirty-<YYYYMMDDHHMMSS>` when `git status --porcelain` reports changes. This tag is applied to every product image and written into `.images.env`, which the deploy script consumes so all services ship the same version.

### Base image strategy
All Python services derive from `luban-aiops/base-uv:al2023`, built from `shared/base-images/base-uv/Dockerfile`. It pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`, installs uv into `/usr/local/bin`, creates a non-root `app` user (uid 1000), and sets `UV_PYTHON_INSTALL_DIR=/app/.python` so each product's interpreter is resolved from its `.python-version` during `uv sync --frozen`.

### Dependency management
Each product has its own `pyproject.toml` + `uv.lock`. The shared `mk/python.mk` target `sync` runs `uv sync --frozen`; `test` re-syncs then runs `uv run pytest` with OTLP exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) to keep test output clean while keeping tracing SDKs active for tracing tests.

### Verification gate
`make verify` composes: `test` (all Python products), `overlays` (kustomize build check for every overlay), `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`. This is the single command intended for both local pre-commit hooks and CI pipelines.

### Version lockstep
`VERSION` at the repo root is the single source of truth for the platform release version. `make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` to enforce that the root version matches every product's declared version and the portal.

### Policy synchronization
The canonical policy bundle lives in `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. `make validate-policy` validates the bundle against JSON schema; `make validate-policy-scenarios` evaluates scenario expectations against both engines; `make policy-diff CANDIDATE=<path>` reports per-(role,action) differences.

### Deployment
`make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which uses kustomize to render and apply the dev overlay. Samples are installed separately via `make deploy-samples` (out-of-band per SPEC-050 R-11). An optional `AUTO_LOAD_KIND=true` flag after `make build` auto-loads all images into a named kind cluster via `kind load docker-image`.

## Conventions and constraints

- **Forge-agnostic**: The root Makefile comment states `make verify` is the pre-commit/pre-push gate and must run identically locally and under any CI.
- **No mutable dependencies**: All Python installs use `uv sync --frozen` against locked `uv.lock` files; production Dockerfiles install with `--no-dev`.
- **Pinned base versions**: `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; comments explicitly say "never `latest`".
- **Single coordinated tag**: `make build` computes one `IMAGE_TAG` and applies it to every product image; there is no per-product independent tagging in the orchestrated flow.
- **Non-root containers**: The base image switches to `USER app` (uid 1000); product images inherit this.
- **Overlay-driven deployment**: Kubernetes manifests live under `shared/platform-ops/gitops/<overlay>` and are validated via `kustomize build` during `make overlays`.
- **Policy as code**: Policy bundles are centralized and copied to consumers; diffs and scenario validation are first-class make targets.
- **Secret vocabulary lockstep**: `make validate-secret-vocabulary` enforces consistency of secret literals across `agent-platform`, `tool-gateway`, and `skills-hub`.