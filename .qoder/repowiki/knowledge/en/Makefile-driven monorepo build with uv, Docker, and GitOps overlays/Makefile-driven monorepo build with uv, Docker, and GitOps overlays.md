---
kind: build_system
name: Makefile-driven monorepo build with uv, Docker, and GitOps overlays
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
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
---

## Build system overview

The repository uses a **GNU Make-based monorepo build** orchestrated from the root `Makefile`, which delegates per-product tasks to individual product Makefiles under `products/<name>/`. Shared build logic is factored into three reusable fragments in `mk/`: `defaults.mk` (overridable defaults), `image.mk` (Docker image targets), and `python.mk` (uv-based dependency sync and pytest). There is no CI configuration file in this snapshot; the root Makefile is designed as a forge-agnostic gate (`make verify`) intended to run identically locally and in CI.

## Key files and packages

- Root orchestrator: `Makefile` — declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, computes a coordinated `IMAGE_TAG`, runs `sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `e2e`, `clean`.
- Shared defaults: `mk/defaults.mk` — single source of overridable settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- Image fragment: `mk/image.mk` — provides `build` / `push` / `lint` targets that each product includes after setting `IMAGE_NAME` (and optionally `IMAGE_CONTEXT`, `IMAGE_DOCKERFILE`).
- Python fragment: `mk/python.mk` — `uv sync --frozen` + `uv run pytest` with OTLP exporters disabled for test output cleanliness.
- Product Makefiles: minimal stubs (e.g. `products/agent-platform/Makefile` sets `IMAGE_NAME := agent-service` and includes both fragments).
- Base image: `shared/base-images/base-uv/Dockerfile` built via `make base-images` using pinned `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12` on `al2023`.
- Version lockstep: `VERSION` at repo root is the single source of truth; `shared/shared-contracts/scripts/validate_version.py` enforces that every `products/*/pyproject.toml`, `src/*/metadata.py` (`SERVICE_VERSION`), `src/*/__init__.py` (`__version__`), and the operator portal's Vite wiring all match it.
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml` is copied to consumers via `make sync-policy`; validated by `make validate-policy`.
- GitOps deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` wraps `kustomize` overlay rendering plus secret provisioning scripts; `make deploy` invokes it.

## Architecture and conventions

### Coordinated image tagging
The root `Makefile` computes one `IMAGE_TAG` once per invocation using:
`<semver-from-VERSION>-<prefix>[ -<profile> ]-<gitsha>` (or `<prefix>-dirty-<timestamp>` for dirty trees). All product images are built with this tag, then an `.images.env` file is written under `shared/platform-ops/gitops/dev-k8s/.images.env` containing the full registry refs for every service (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, `TOOL_GATEWAY_IMAGE`, `IDENTITY_SERVICE_IMAGE`, `AUDIT_SERVICE_IMAGE`, `SKILLS_HUB_IMAGE`, `INCIDENT_SERVICE_IMAGE`, `WEB_UI_IMAGE`). This file is consumed by the deploy pipeline so all services ship together.

### Per-product composition
Each Python product follows the same layout: `pyproject.toml` + `uv.lock` + `Dockerfile` + `Makefile` + `tests/`. The product Makefile only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. Non-Python products (e.g. `operator-portal`) include only the image fragment and override `IMAGE_CONTEXT` to point at the repo root because its multi-stage Dockerfile needs the root `VERSION` file.

### Dependency management
Python dependencies are managed per-product with **uv** and frozen lockfiles (`uv sync --frozen`). No global `uv.lock` exists; each product pins its own transitive graph. The base image `luban-aiops/base-uv:al2023` is built once with a pinned uv version and reused across all product images.

### Verification gate
`make verify` composes four checks: `test` (pytest across all Python products), `overlays` (`kustomize build` against `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`), `validate-policy`, and `validate-version`. This target is documented as the pre-commit/pre-push gate and must be runnable anywhere GNU make is available.

### Deployment flow
`make build` → builds all images with the coordinated tag → writes `.images.env` → optionally loads them into a kind cluster (`AUTO_LOAD_KIND=true` + `KIND_CLUSTER_NAME`). `make deploy` runs `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders the kustomize overlay and sequentially provisions secrets (delegation, audit, skills, incident, sessions DB, OTel) and reconciles the Keycloak realm and portal OIDC client. E2E demos live under `shared/platform-ops/e2e/` and are invoked via `make e2e`.

### Platform version enforcement
The `VERSION` file is the single source of truth. `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which parses semver and asserts equality across every product's `pyproject.toml`, runtime metadata modules, and the operator portal's Vite build-time injection wiring. Drift causes the verification gate to fail.

## Conventions and constraints

- Every product exposes identical Make targets (`help`, `build`, `push`, `lint`, `sync`, `test`) via inclusion of shared fragments — adding a new product means creating a one-line Makefile that sets `IMAGE_NAME` and including the two fragments.
- Image builds default to `linux/amd64`; cross-compilation is done by overriding `IMAGE_PLATFORM` (e.g. `linux/arm64` for native arm64 kind clusters).
- Registry publishing is opt-in: set `REGISTRY=<host>` to re-tag and push; without it, images remain local under `luban-aiops/<name>:<tag>`.
- Dockerfile linting uses `hadolint` when installed, falling back to `docker run hadolint/hadolint` if docker is available; otherwise it skips silently.
- Policy bundles are centralized: the canonical YAML lives in `shared/shared-contracts/policies/` and must be propagated to consumers via `make sync-policy` rather than edited in place.
- The `verify` target is the authoritative pre-commit/pre-push gate; it must succeed for changes to be considered valid.
- Secrets provisioning during `make deploy` is guarded by environment variables (`SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_SKILLS_SECRETS`, `SKIP_INCIDENT_SECRETS`, `SKIP_OTEL_SECRETS`) so CI can skip steps where secrets are injected externally.