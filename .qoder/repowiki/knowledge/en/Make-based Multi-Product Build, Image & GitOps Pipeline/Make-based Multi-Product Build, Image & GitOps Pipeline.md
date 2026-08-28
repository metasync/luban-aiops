---
kind: build_system
name: Make-based Multi-Product Build, Image & GitOps Pipeline
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
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## What system/approach is used

The repository uses a **GNU Make-driven workspace build** that coordinates multiple Python FastAPI services and a React operator portal. There is no CI YAML in this snapshot; the root `Makefile` declares itself as the "Forge-agnostic" pre-commit/pre-push gate (`make verify`) intended to run identically locally and under any CI.

Key tools:
- **Make** (GNU make) — top-level orchestration and per-product delegation.
- **uv** — Python dependency resolution and execution (`uv sync --frozen`, `uv run pytest`, `uv run agent-service`).
- **Docker** — container image builds via per-product `Dockerfile`s built on a shared `luban-aiops/base-uv:al2023` base image.
- **kustomize** — GitOps overlay rendering (`kustomize build --load-restrictor LoadRestrictionsNone`).
- **hadolint** — Dockerfile linting with a docker-run fallback when the binary is absent.
- **Python scripts** under `shared/shared-contracts/scripts/` — policy schema validation and version lockstep checks.

## Key files and packages

- Root orchestrator: `Makefile` — defines product lists, coordinated image tag computation, `sync`/`test`/`lint`/`build`/`push`/`verify`/`deploy`/`e2e`/`clean` targets.
- Shared fragments: `mk/defaults.mk` (overridable defaults), `mk/image.mk` (docker build/push/lint), `mk/python.mk` (`uv sync --frozen`, `pytest` with OTel exporters disabled).
- Per-product entry points: each `products/<name>/Makefile` sets `IMAGE_NAME` and includes both `../../mk/image.mk` and `../../mk/python.mk`; e.g. `products/agent-platform/Makefile`.
- Container images: per-product `Dockerfile`s based on `FROM luban-aiops/base-uv:al2023`, copying `.python-version`, `pyproject.toml`, `uv.lock`, `src/`, running `uv sync --frozen --no-dev`, exposing port 8000.
- Base image: `shared/base-images/base-uv/Dockerfile` built by `make base-images` using pinned `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`.
- Version single source of truth: `VERSION` (semver, currently `0.22.0`), enforced by `make validate-version` which runs `shared/shared-contracts/scripts/validate_version.py` against every product's `pyproject.toml`, `src/*/metadata.py`, `src/*/__init__.py`, and the operator portal's `vite.config.ts` wiring.
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml` copied to consumers via `make sync-policy` into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.
- Deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` wraps `deploy-overlay.sh` plus secret provisioning scripts for token delegation, audit trail, execution signing/handoff, skills, incidents, sessions DB, OTel, and optional Keycloak realm reconciliation.

## Architecture and conventions

### Workspace layout
- `products/<service>/` — self-contained Python package with its own `pyproject.toml`, `uv.lock`, `tests/`, `Dockerfile`, and thin `Makefile`.
- `shared/shared-contracts/` — JSON schemas, default policy YAML, and validation scripts consumed by all services.
- `shared/platform-ops/gitops/` — Kustomize overlays (`dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`) rendered during verification.
- `mk/` — reusable Make fragments so adding a new product only requires a small `Makefile` + `Dockerfile`.

### Coordinated image tagging
The root `Makefile` computes a single `IMAGE_TAG` once: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, or `<semver>-<prefix>[-<profile>]-<gitsha>-dirty-<timestamp>` for dirty trees. This tag is passed to every product `make -C products/<name> build IMAGE_TAG=...`. After building, it writes `shared/platform-ops/gitops/dev-k8s/.images.env` with `IMAGE_TAG` plus one `*_IMAGE=luban-aiops/<name>:<tag>` line per service, which the deploy script consumes.

### Product build contract
Each product Makefile must set `IMAGE_NAME` and include both `mk/image.mk` and `mk/python.mk`. The image fragment expects `IMAGE_PLATFORM`, `REGISTRY`, `IMAGE_CONTEXT`, `IMAGE_DOCKERFILE` to be overridable via defaults in `mk/defaults.mk` or command-line flags. The Python fragment assumes `uv` is available and pins dependencies via `uv sync --frozen`.

### Verification gate
`make verify` runs `test` (all Python products), `overlays` (kustomize build check for all overlays), `validate-policy` (policy YAML against JSON schema), and `validate-version` (version lockstep). This is the documented pre-commit/pre-push gate.

### Deploy flow
`make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which runs `deploy-overlay.sh` then sequentially provisions secrets via dedicated `sync-*.sh` scripts (delegation, audit, execution signing/handoff, skills, incidents, sessions DB, OTel) and optionally reconciles the Keycloak realm and portal OIDC client. Secrets can be skipped per-script via `SKIP_*_SECRETS=true` for CI environments where they are injected externally.

### E2E
`make e2e` runs three demo scripts under `shared/platform-ops/e2e/` (`skills-demo.sh`, `incident-demo.sh`, `mutating-demo.sh`) against a deployed cluster after port-forwarding `platform-gateway` and `identity-service`.

### Auto-loading into kind
When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all nine built images into the named kind cluster after building them.

## Conventions and constraints

- **Single version file**: `VERSION` is the sole source of truth; `validate_version.py` enforces that every product's `pyproject.toml`, `src/*/metadata.py`, `src/*/__init__.py`, and the portal's Vite wiring match it. A non-semver value fails the check.
- **Frozen dependencies**: All Python products use `uv sync --frozen`, pinning versions from `uv.lock` — no runtime drift allowed.
- **Base image pinning**: The shared base image uses fixed tags (`BASE_UV_IMAGE ?= luban-aiops/base-uv`, `BASE_UV_TAG ?= al2023`) and pinned `UV_VERSION`/`PYTHON_VERSION`; comments explicitly state these are "never latest" for reproducible builds.
- **Image platform default**: `IMAGE_PLATFORM ?= linux/amd64`; arm64 local/kind builds override to `linux/arm64`.
- **Registry re-tagging**: Images are always built locally as `luban-aiops/<name>:<tag>`; pushing to a custom registry requires setting `REGISTRY`, which triggers an additional `docker tag` before `docker push`.
- **Policy synchronization**: The canonical policy lives in `shared/shared-contracts/policies/policy-default.yaml`; consumers do not edit it directly — `make sync-policy` copies it to all locations.
- **Overlay validation**: `kustomize build --load-restrictor LoadRestrictionsNone` is run against all overlays during `verify`; broken overlays fail the gate.
- **Secret provisioning idempotency**: Each `sync-*.sh` supports a `SKIP_*_SECRETS=true` environment variable so CI can skip provisioning when secrets are supplied externally.
- **Per-product isolation**: Tests run inside each product directory so `uv` resolves that product's `pyproject.toml`/`uv.lock`; the root `test` target iterates `PYTHON_PRODUCTS` and exits on the first failure.