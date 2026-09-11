---
kind: build_system
name: Makefile-driven Monorepo Build, Image Tagging, and GitOps Overlay Deployment
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
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

The repository uses a **GNU Make-based monorepo build system** layered over Docker image builds, the `uv` Python package manager (with frozen lockfiles), and Kubernetes GitOps overlays via `kustomize`. There is no CI pipeline file in `.github/workflows`; instead, the root `make verify` target is designed as a forge-agnostic pre-commit/pre-push gate that runs identically locally and in any CI environment. Deployment is driven by a shell script (`shared/platform-ops/gitops/dev-k8s/deploy.sh`) that applies Kustomize overlays and provisions secrets.

## Key files and packages

- Root orchestrator: `Makefile` — declares product lists, computes coordinated image tags, delegates per-product `sync`/`test`/`build`/`push`, and composes cross-cutting gates (`verify`, `overlays`, `deploy`).
- Shared fragments under `mk/`:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
  - `mk/image.mk` — shared `build`/`push`/`lint` targets for every product Dockerfile; resolves `IMAGE_REF` against `luban-aiops/*` or a user-supplied `REGISTRY`.
  - `mk/python.mk` — shared `sync`/`test` targets that run `uv sync --frozen` then `uv run pytest` with OTel exporters disabled to keep test output clean.
- Per-product entry points: each product directory under `products/<name>/` has a tiny `Makefile` that sets `IMAGE_NAME` and includes both `../../mk/image.mk` and `../../mk/python.mk`.
- Base image: `shared/base-images/base-uv/Dockerfile` built by `make base-images` using pinned `BASE_UV_PYTHON_VERSION=3.12` and `BASE_UV_UV_VERSION=0.12.1`.
- Versioning: root `VERSION` file (`0.36.1`) is the single source of truth; `validate-version` enforces lockstep across products and the portal.
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml` is copied into `tool-gateway`, `platform-gateway`, and the dev overlay via `make sync-policy`.
- Deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` applies overlays and sequentially provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) before reconciling the Keycloak realm and portal OIDC client.

## Architecture and conventions

### Coordinated image tagging
The root `Makefile` computes a single `IMAGE_TAG` once and reuses it for all images. The tag format is `<semver>-<prefix>[-<profile>]-<gitsha>` for a clean tree, or `<...>-dirty-<timestamp>` when `git status --porcelain` reports uncommitted changes. The tag is written to `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy step always references the exact images just built.

### Product decomposition
Each service is an independent Python project with its own `pyproject.toml` + `uv.lock`, `Dockerfile`, and minimal `Makefile`. The root `Makefile` maintains explicit whitelists:
- `PYTHON_PRODUCTS` — services that expose `sync`/`test`.
- `IMAGE_PRODUCTS` — services that produce container images (adds `operator-portal` which is a static web UI).
This keeps new products opt-in rather than auto-discovered.

### Base image strategy
All Python services derive from `luban-aiops/base-uv:al2023`, built once with `uv sync --frozen --no-dev` inside the image. This pins the runtime Python version and dependency set at image-build time.

### GitOps overlays
Kubernetes manifests live under `shared/platform-ops/gitops/`. The `dev-k8s` overlay is the default deployment target; additional overlays (`runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`) are validated by `make overlays` via `kustomize build --load-restrictor LoadRestrictionsNone`. Overlays are not built by the Makefile — they are rendered on demand during verification and deployment.

### Secret provisioning convention
Every secret type has a dedicated `sync-*.sh` script under `shared/platform-ops/gitops/`. The deploy script calls them in a fixed order and supports `SKIP_*_SECRETS=true` environment variables to skip provisioning when secrets are injected externally (e.g., by CI). This pattern is documented inline in the deploy script comments tied to SPEC numbers.

### Policy management
The canonical policy bundle lives in `shared/shared-contracts/policies/policy-default.yaml`. Consumers copy it via `make sync-policy`. Validation is split into schema validation (`validate-policy`), scenario evaluation against both engines (`validate-policy-scenarios`), and a diff tool (`policy-diff`) comparing a candidate bundle against the canonical one.

## Conventions and constraints

- **Reproducible Python installs**: All `uv sync` invocations use `--frozen`, pinning dependencies to `uv.lock`. Tests also disable OTel exporters (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) so tracing tests can run without external backends.
- **No `latest` tags**: `mk/defaults.mk` explicitly states pinned values are defaults for reproducible builds — never `latest`. Image tags are derived from `VERSION` + git SHA.
- **Single platform default**: `IMAGE_PLATFORM ?= linux/amd64`; ARM builds require explicit override. The comment notes the deployment target is `linux/amd64`.
- **Registry abstraction**: Setting `REGISTRY=` causes images to be tagged under `luban-aiops/*` only; setting it to a value adds a registry prefix and triggers push. Push is gated behind this variable.
- **Kind integration**: `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<name>` after `make build` loads all nine images into the named kind cluster automatically.
- **Verification gate**: `make verify` composes `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, and `validate-secret-vocabulary`. It is intended to be the sole pre-commit/pre-push check.
- **Version lockstep**: `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` matches every product's declared version.
- **Secret vocabulary lockstep**: `make validate-secret-vocabulary` runs `validate_secret_vocabulary.py` against `agent-platform`, `tool-gateway`, and `skills-hub` to ensure declared secret literals stay synchronized.
- **Sample isolation**: Tutorial samples under `samples/` are deployed out-of-band via `make deploy-samples` so the base overlay never names a sample resource (per SPEC-050 R-11).
- **Per-product help**: Each product exposes `make help` through the shared fragment, listing only that product's targets.