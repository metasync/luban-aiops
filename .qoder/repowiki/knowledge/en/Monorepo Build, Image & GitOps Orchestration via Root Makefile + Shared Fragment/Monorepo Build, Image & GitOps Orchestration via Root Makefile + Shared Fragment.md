---
kind: build_system
name: Monorepo Build, Image & GitOps Orchestration via Root Makefile + Shared Fragments
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
    - products/agent-platform/pyproject.toml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/policy_diff.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
---

## What system/approach is used

The repository uses a **Makefile-driven monorepo build** centered on a root `Makefile` that orchestrates per-product Python builds (via `uv`), container image creation (via `docker`), and GitOps overlay deployment (via `kustomize`). There is no CI pipeline file in `.github/`; the root Makefile is explicitly documented as "forge-agnostic" — `make verify` is intended to run identically locally and under any CI. Each product under `products/<name>/` is an independent Python package with its own `pyproject.toml`, `uv.lock`, `Dockerfile`, and thin `Makefile` that includes shared fragments from `mk/`.

## Key files and packages

- **Root orchestration**: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), computes a coordinated `IMAGE_TAG` from `VERSION` + git SHA (+ `-dirty-<timestamp>` for unclean trees), runs per-product `build`/`test`/`lint`, writes `.images.env` state, loads images into kind, deploys overlays, and runs e2e scripts.
- **Shared build fragments**:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
  - `mk/image.mk` — shared `build`/`push`/`lint` targets using `docker build --platform $(IMAGE_PLATFORM)`; supports optional registry re-tag/push.
  - `mk/python.mk` — shared `sync`/`test` targets running `uv sync --frozen` then `pytest` with OTel exporters disabled so tests stay local.
- **Per-product entry points**: each product's `Makefile` sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk` (e.g. `products/agent-platform/Makefile`).
- **Container images**: every product has a minimal `Dockerfile` based on `luban-aiops/base-uv:al2023`, copying `pyproject.toml`/`uv.lock`/`src/`, running `uv sync --frozen --no-dev`, and invoking the service via `uv run <entrypoint>`.
- **Base image**: `shared/base-images/base-uv/Dockerfile` built by `make base-images` with pinned `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`.
- **Version lockstep**: `VERSION` (root) is the single source of truth; `shared/shared-contracts/scripts/validate_version.py` enforces that every `products/*/pyproject.toml` `[project] version`, every `metadata.py` `SERVICE_VERSION`, and portal Vite wiring all match it.
- **Deployment**: `shared/platform-ops/gitops/dev-k8s/deploy.sh` renders Kustomize overlays, then calls `sync-*` scripts to provision secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) and reconcile Keycloak realm / portal OIDC client.
- **Policy sync**: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into both gateway products and the dev-k8s overlay; `make validate-policy` / `validate-policy-scenarios` / `policy-diff` use shared scripts under `shared/shared-contracts/scripts/`.

## Architecture and conventions

1. **Two-level Makefile design** — The root Makefile owns cross-cutting concerns (aggregation, tag computation, policy sync, overlay validation, deploy). Product Makefiles are intentionally tiny: they only declare `IMAGE_NAME` and include the shared fragments. This keeps adding a new product to three lines plus a `Dockerfile`.
2. **Coordinated tagging** — All images produced by `make build` share one `IMAGE_TAG` derived from `VERSION` + `IMAGE_TAG_PREFIX` + optional profile + short git SHA (+ dirty timestamp). The tag is written once to `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy step consumes a consistent set.
3. **Frozen dependency resolution** — Every Python product uses `uv sync --frozen` against its own `uv.lock`. No transitive drift is allowed at build time.
4. **Single base image strategy** — All services derive from `luban-aiops/base-uv:al2023`, built once with pinned uv and Python versions. Products never pin Python or uv themselves.
5. **GitOps-first deployment** — Kubernetes manifests live under `shared/platform-ops/gitops/` and are rendered via `kustomize build` during verification. Secrets are provisioned idempotently by `sync-*` scripts rather than checked in.
6. **Verification gate** — `make verify` chains `test` + `overlays` + `validate-policy` + `validate-policy-scenarios` + `validate-version` + `validate-secret-vocabulary`. It is designed to be the pre-commit/pre-push gate.
7. **Local-kind workflow** — `make build AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` auto-loads all images into a kind cluster after building, enabling rapid iteration.
8. **Samples are decoupled** — Tutorial samples under `samples/` are installed out-of-band via `make deploy-samples` so the base overlay never names them (enforced by SPEC-050 R-11).

## Conventions and constraints

- **GNU make required** — declared in the root Makefile comment and relied on throughout.
- **`IMAGE_PLATFORM` defaults to `linux/amd64`**; override to `linux/arm64` for native arm64 host/kind builds (documented in `mk/defaults.mk`).
- **`REGISTRY` is empty by default**, meaning `make build` produces local-only images tagged `luban-aiops/<name>:<tag>`; set `REGISTRY=` to re-tag and push.
- **`IMAGE_TAG` is computed automatically** when undefined (semver prefix + git sha + dirty marker); overriding it bypasses the coordinated tag logic.
- **`AUTO_LOAD_KIND` requires `KIND_CLUSTER_NAME`** — the root Makefile exits with an error if enabled without the cluster name set.
- **Version must be valid semver** (`MAJOR.MINOR.PATCH`) — enforced by `validate_version.py`; non-matching product versions cause failure.
- **Policy bundle is canonical in `shared/shared-contracts/policies/policy-default.yaml`** — consumers must obtain it via `make sync-policy`; direct edits elsewhere are not the source of truth.
- **Secret vocabulary is validated across agent-platform, tool-gateway, and skills-hub** via `validate_secret_vocabulary.py`; changes must keep the three locations in lockstep.
- **E2E scripts require a deployed cluster plus port-forwards** to `platform-gateway:18083` and `identity-service:18081` before running `make e2e`.
- **No CI configuration exists in this repo** — the build system is intentionally forge-agnostic and expected to be invoked by external CI using the same `make verify` / `make build` / `make deploy` commands.