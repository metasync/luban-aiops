---
kind: build_system
name: Workspace-wide Makefile-driven Build, Image & Deploy Pipeline
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
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/deploy-overlay.sh
---

## What system/approach is used

The repository uses a **GNU Make–centric workspace build** that coordinates Python (uv) dependency management, Docker image builds, policy validation, GitOps overlay rendering, and Kubernetes deployment across eight product services plus an operator portal. There is no CI YAML in this repo; the root `Makefile` declares itself as "Forge-agnostic" and is intended to run identically locally and under any CI provider.

Key tools:
- **GNU make** — orchestration layer at the workspace root and per-product entry points.
- **uv** — Python dependency resolver and runner (`uv sync --frozen`, `uv run pytest`, `uv run agent-service`).
- **Docker** — container image builder for every product; images are tagged with a coordinated tag derived from the root `VERSION` file, optional profile, git SHA, and dirty timestamp.
- **kustomize** — GitOps overlays under `shared/platform-ops/gitops/` are validated via `kustomize build --load-restrictor LoadRestrictionsNone` during verification.
- **hadolint** — Dockerfile linting, with a docker-run fallback when the binary is not installed.
- **Python scripts under `shared/shared-contracts/scripts/`** — enforce cross-cutting invariants (policy schema validation, scenario evaluation, version lockstep, secret vocabulary).

## Key files and packages

- `Makefile` — master orchestrator: defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`, computes `IMAGE_TAG`, and exposes `sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `e2e`, `clean`.
- `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*` versions). Guarded against double inclusion.
- `mk/image.mk` — shared Docker targets (`build`, `push`, `lint`) included by each product Makefile; resolves `IMAGE_REF` based on whether `REGISTRY` is set.
- `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `uv run pytest` with OTel exporters disabled.
- Per-product `products/<name>/Makefile` — thin wrappers that set `IMAGE_NAME` and include both fragments.
- `products/*/Dockerfile` — multi-stage-style images built from `luban-aiops/base-uv:al2023`, copy `pyproject.toml`, `uv.lock`, `src/`, then `uv sync --frozen --no-dev`.
- `shared/base-images/base-uv/Dockerfile` — pinned Amazon Linux 2023 base image with a fixed `UV_VERSION` and `PYTHON_VERSION`.
- `VERSION` — single semver source of truth (currently `0.37.1`); consumed by root `make build` and enforced by `validate_version.py`.
- `shared/shared-contracts/scripts/validate_version.py` — scans all `products/*/pyproject.toml`, `metadata.py`, `__init__.py`, and `operator-portal/web-ui/app/vite.config.ts` to ensure they match `VERSION`.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — deploys the dev overlay and provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) before reconciling Keycloak realm and portal OIDC client.
- `shared/platform-ops/gitops/*.sh` — secret-sync helpers invoked by deploy.

## Architecture and conventions

### Product model
Each service under `products/` is self-contained: it has its own `pyproject.toml`, `uv.lock`, `tests/`, `Dockerfile`, and a tiny `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`. The root `Makefile` enumerates products in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists and dispatches `$(MAKE) -C products/$$p <target>` for each.

### Coordinated tagging
`make build` computes one `IMAGE_TAG` once (semver + optional prefix/profile + short git SHA + `-dirty-timestamp` if uncommitted changes exist) and passes it to every product build. After building, it writes `shared/platform-ops/gitops/dev-k8s/.images.env` mapping logical names (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, …) to `luban-aiops/<service>:<tag>`, which the deploy script consumes.

### Base image strategy
All product images derive from `luban-aiops/base-uv:al2023`, built via `make base-images` using pinned `BASE_UV_UV_VERSION` (default `0.12.1`) and `BASE_UV_PYTHON_VERSION` (default `3.12`). This pins the Python toolchain across the workspace.

### Verification gate
`make verify` runs the full pre-commit/pre-push gate: `test` (all Python products), `overlays` (kustomize render check for `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`), `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`.

### Policy distribution
A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it into `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. Consumers validate it via `validate_policy.py` and `validate_policy_scenarios.py`.

### Version lockstep
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py`, which asserts that every product's `pyproject.toml [project] version`, `SERVICE_VERSION` in `metadata.py`, `__version__` in package roots, and the operator portal's Vite wiring all equal the root `VERSION` file. Drift causes failure.

### Deployment flow
`make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which runs `../deploy-overlay.sh` and then sequentially provisions secrets via dedicated sync scripts (each guarded by a `SKIP_*_SECRETS=true` env var for CI), creates the sessions database, and optionally reconciles the Keycloak realm and portal OIDC client. `make e2e` then runs shell-based demo scripts against the deployed cluster after port-forwarding the gateway and identity services.

### Local kind integration
Setting `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME=<name>` in `make build` automatically loads all nine built images into the named kind cluster after image creation.

## Conventions and constraints

- **Single source of truth for platform version**: `VERSION` at the repo root. Enforced by `make validate-version` (via `validate_version.py`); drift fails the verification gate.
- **Frozen Python dependencies**: All `uv sync` invocations use `--frozen`, pinning to `uv.lock`. Products must regenerate their lockfiles rather than editing them manually in CI.
- **No `latest` tags**: `mk/defaults.mk` comments explicitly state pinned values are defaults for reproducible builds — never `latest`.
- **Image naming convention**: Images are always tagged `luban-aiops/<service>:<coordinated-tag>`; pushing to a registry requires setting `REGISTRY=` so they are re-tagged as `$(REGISTRY)/luban-aiops/<service>:<tag>`.
- **Per-product Makefiles must only include fragments**: Product Makefiles set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`; they contain no build logic themselves.
- **GitOps overlays must render cleanly**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on each overlay; failures block verification.
- **Secret provisioning is opt-in per category**: Each `sync-*` script in `shared/platform-ops/gitops/` can be skipped by exporting `SKIP_<CATEGORY>_SECRETS=true`, allowing CI to inject secrets externally.
- **Policy bundles are centrally authored**: Changes to `shared/shared-contracts/policies/policy-default.yaml` must be propagated via `make sync-policy`; consumers validate via `make validate-policy` and `make validate-policy-scenarios`.