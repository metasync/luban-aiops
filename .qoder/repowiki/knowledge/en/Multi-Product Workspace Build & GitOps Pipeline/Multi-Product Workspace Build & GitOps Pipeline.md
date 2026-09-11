---
kind: build_system
name: Multi-Product Workspace Build & GitOps Pipeline
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
    - products/operator-portal/Makefile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml
    - samples/deploy-samples.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/policy_diff.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
---

## What system/approach is used

The repository uses a **multi-product workspace** built with GNU Make, Docker, and the `uv` Python package manager. A single root `Makefile` orchestrates per-product routines (each product lives under `products/<name>/`) and cross-cutting concerns: shared base image build, coordinated container tagging, policy synchronization, Kustomize overlay rendering, version lockstep validation, and deployment to a Kubernetes cluster via GitOps overlays in `shared/platform-ops/gitops/`. There are no CI workflow files checked into `.github/workflows`; the specs reference a `ci.yml` that would run the same `make verify` gate locally and in CI.

## Key files and packages

- Root orchestration: `Makefile`, `mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`
- Version source of truth: `VERSION` (semver, e.g. `0.36.0`)
- Shared base image: `shared/base-images/base-uv/Dockerfile` (Amazon Linux 2023 minimal, pinned `uv` 0.12.1, Python 3.12, runs as non-root `app` uid 1000)
- Per-product entrypoints: each `products/<name>/Makefile` sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk` (Python products); `operator-portal/Makefile` only includes `image.mk` because it builds a static SPA served by nginx
- Product Dockerfiles: one per product, all `FROM luban-aiops/base-uv:al2023`, `uv sync --frozen --no-dev`, `EXPOSE 8000`, `CMD ["uv", "run", ...]`
- GitOps overlays: `shared/platform-ops/gitops/dev-k8s/` (base manifests + kustomization) plus runtime profile overlays (`runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`)
- Deploy script: `shared/platform-ops/gitops/dev-k8s/deploy.sh` — applies overlays then provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel), optionally reconciles Keycloak realm and portal OIDC client
- Sample skill installer: `samples/deploy-samples.sh` (packs sample skill docs into a ConfigMap and restarts skills-hub)
- Policy scripts: `shared/shared-contracts/scripts/validate_policy.py`, `validate_policy_scenarios.py`, `policy_diff.py`, `validate_version.py`, `validate_secret_vocabulary.py`

## Architecture and conventions

### Coordinated image tagging
The root `Makefile` computes a single `IMAGE_TAG` once using the formula `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for uncommitted changes). The semver comes from the root `VERSION` file; `IMAGE_TAG_PREFIX` defaults to `dev-k8s`; `IMAGE_TAG_PROFILE` selects a runtime profile. Every product image is tagged `luban-aiops/<name>:<IMAGE_TAG>`. After building, the root writes `IMAGE_TAG` and every product image name into `shared/platform-ops/gitops/dev-k8s/.images.env`, which the deploy step consumes so the overlay references exactly the images just built.

### Product decomposition
Each product is self-contained: `src/<package>/`, `tests/`, `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, and a thin `Makefile` that only declares `IMAGE_NAME` and includes the shared fragments. The root enumerates `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists to drive `sync`, `test`, `lint`, `build`, and `push` across all services uniformly.

### Base image strategy
All backend services derive from the shared `shared/base-images/base-uv` image built by `make base-images`. It pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`, installs uv into `/usr/local/bin`, creates a non-root `app` user (uid 1000), and sets `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON_INSTALL_DIR=/app/.python`. Product Dockerfiles copy only `pyproject.toml`, `uv.lock`, `.python-version`, `README.md`, and `src/` to leverage layer caching, then run `uv sync --frozen --no-dev` at build time.

### Python toolchain
Products use `uv` exclusively — `uv sync --frozen` for dependency resolution against locked `uv.lock` files, and `uv run pytest` for tests. Test output suppresses OTLP exporters (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) so tracing tests can exercise the SDK without network noise. The operator-portal product has no Python suite; its frontend tests live in `web-ui/app` and are not invoked by the root Makefile.

### Policy synchronization
A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to both gateway consumers (`products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`) and the deployed overlay (`shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`). Validation (`make validate-policy`, `make validate-policy-scenarios`, `make policy-diff`) runs the shared scripts against both engines.

### Version lockstep
`make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file stays in lockstep with every product's declared version. This is part of the `verify` gate.

### Secret provisioning
`make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which calls a series of `sync-*.sh` scripts to provision secrets (token delegation, audit ingest, execution signing/handoff, skills query, incidents, browser credentials, sessions DB schema, OTel credentials). Each script supports a `SKIP_*_SECRETS=true` environment variable so CI can skip secret injection when secrets are provided externally.

### Overlay-driven deployment
Deployment uses Kustomize over `shared/platform-ops/gitops/dev-k8s/`. The root `OVERLAYS` list drives `kustomize build --load-restrictor LoadRestrictionsNone` during verification. Runtime profiles (`default`, `mutating-dev`, `browser-dev`) are applied as additional overlays. Samples are installed out-of-band via `make deploy-samples` so the base overlay never names a specific sample (per SPEC-050 R-11).

## Conventions and constraints

- **Single source of truth for version**: `VERSION` at the repo root is the platform release version; `make validate-version` enforces lockstep with product versions.
- **Frozen dependencies**: All `uv sync` invocations use `--frozen`, pinning to `uv.lock` — no transitive drift is allowed.
- **Reproducible base image**: `shared/base-images/base-uv/Dockerfile` pins `UV_VERSION` and `PYTHON_VERSION` via build args; overrides go through `BASE_UV_UV_VERSION` / `BASE_UV_PYTHON_VERSION` in `mk/defaults.mk`.
- **Non-root containers**: The base image creates an `app` user (uid 1000) and switches to it; product images inherit this posture.
- **Coordinated tagging**: `IMAGE_TAG` is computed once at the root and propagated to every product build; `make build` writes the final tag and all image refs into `.images.env` consumed by deploy.
- **Verification gate**: `make verify` runs `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, and `validate-secret-vocabulary` — this is documented as the pre-commit/pre-push gate and is intended to be the CI entrypoint.
- **Kind integration**: `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<name>` after `make build` auto-loads all images into the named kind cluster.
- **Secrets are optional per feature**: Each `sync-*.sh` script is guarded by a `SKIP_*_SECRETS` env var, enabling CI deployments where secrets are injected by external secret management.
- **Samples are decoupled from the base overlay**: `samples/deploy-samples.sh` is the only coupling point between tutorial samples and the running cluster; the base overlay declares a generic `samples` source with an empty/absent ConfigMap.