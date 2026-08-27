---
kind: build_system
name: Monorepo Build, Image & Release Orchestration via Shared Makefile Fragments
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - VERSION
---

## What system/approach is used

The repository uses a **Makefile-driven monorepo build system** centered on shared fragments under `mk/` that are included by each product's thin `products/<name>/Makefile`. Python products use **uv** (with frozen lockfiles) for dependency resolution and test execution; container images are built with **Docker** using a shared base image (`shared/base-images/base-uv`). Deployment is GitOps-oriented: the root `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders Kustomize overlays and provisions secrets via helper scripts. There is no CI configuration in `.github/workflows`; verification gates (`test`, `overlays`, `validate-policy`, `validate-version`) are defined locally so they can run identically in any forge.

## Key files and packages

- `Makefile` — master orchestrator: defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, coordinated `IMAGE_TAG`, and top-level targets (`sync`, `test`, `lint`, `build`, `push`, `verify`, `deploy`, `e2e`, `clean`).
- `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- `mk/image.mk` — shared Docker build/push/lint targets; computes `IMAGE_REF` as `luban-aiops/<name>:<tag>` (optionally re-tagged to `$(REGISTRY)/...`).
- `mk/python.mk` — shared `sync` (`uv sync --frozen`) and `test` targets that set `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` before running `uv run pytest`.
- `products/*/Makefile` — minimal per-product files that only set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`.
- `products/*/Dockerfile` — multi-stage-style images based on `FROM luban-aiops/base-uv:al2023`, copying `pyproject.toml`, `uv.lock`, `src/`, then `RUN uv sync --frozen --no-dev`.
- `shared/base-images/base-uv/Dockerfile` — builds the shared Python+uv base image from Amazon Linux 2023.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — deploys the dev overlay and sequentially provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, OTel) plus session DB and optional Keycloak portal client reconciliation.
- `VERSION` — single source of truth for the platform semver.
- `shared/shared-contracts/scripts/validate_version.py` — enforces that every product's `pyproject.toml` version, `metadata.SERVICE_VERSION`, package `__version__`, and operator-portal Vite wiring all match `VERSION`.
- `shared/shared-contracts/scripts/validate_policy.py` — validates the canonical policy bundle against its JSON schema.
- `shared/platform-ops/gitops/*.sh` — secret-sync and overlay helpers invoked by `deploy.sh`.

## Architecture and conventions

1. **Two-layer Makefile design.** The root `Makefile` owns cross-cutting concerns (product lists, coordinated tagging, policy sync, overlay rendering). Each product has a one-line `Makefile` that just declares `IMAGE_NAME` and includes the shared fragments. This lets `make -C products/<name>` work standalone while still resolving identical defaults via `include $(dir ...)/defaults.mk`.

2. **Coordinated image tagging.** The root `make build` computes a single `IMAGE_TAG` once using `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for uncommitted changes), then passes it to every product build. After building, it writes `shared/platform-ops/gitops/dev-k8s/.images.env` containing `IMAGE_TAG` and the full registry-prefixed image refs for all nine services plus `web-ui`, consumed by the deploy script.

3. **Single-source-of-truth versioning.** `VERSION` at the repo root is the authoritative platform semver. `make validate-version` runs `validate_version.py`, which checks:
   - Every `products/*/pyproject.toml` `[project] version`
   - Every `products/*/src/*/metadata.py` `SERVICE_VERSION = "..."`
   - Any `__version__` in `src/*/__init__.py`
   - That `operator-portal/web-ui/app/vite.config.ts` reads `VERSION` at build time (asserts the `new URL("../../../VERSION", import.meta.url)` and `__PLATFORM_VERSION__: JSON.stringify(platformVersion)` wiring).
   Drift causes the gate to fail.

4. **Policy bundling.** A canonical `shared/shared-contracts/policies/policy-default.yaml` is copied into `products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` via `make sync-policy`. Validation against the JSON schema is enforced by `make validate-policy`.

5. **Python toolchain.** All Python products use `uv` exclusively: `uv sync --frozen` for deterministic installs, `uv run pytest` for tests, and `uv run <entrypoint>` as the container `CMD`. Dev dependencies are excluded from images (`--no-dev`).

6. **Image linting fallback.** `make lint` runs `hadolint` if available, otherwise falls back to `docker run --rm -i hadolint/hadolint < Dockerfile`, so CI without a local `hadolint` binary still works.

7. **Local kind integration.** Setting `AUTO_LOAD_KIND=true` after `make build` automatically loads all built images into a `kind` cluster named by `KIND_CLUSTER_NAME`.

8. **GitOps deployment flow.** `make deploy` → `dev-k8s/deploy.sh` → `../deploy-overlay.sh` (kustomize render) → sequential secret provisioning scripts → optional Keycloak realm/client reconciliation. Secrets can be skipped per-script via `SKIP_*_SECRETS=true` flags for CI environments.

## Conventions and constraints

- **Every Python product must expose a `main` entry point runnable via `uv run <name>`** (the Dockerfile `CMD` pattern is uniform across all services).
- **Products must not pin their own versions independently**; `make validate-version` will fail if any `pyproject.toml` or `metadata.SERVICE_VERSION` diverges from `VERSION`.
- **All images derive from `luban-aiops/base-uv:al2023`** built from `shared/base-images/base-uv/Dockerfile`; adding a new service requires updating both `IMAGE_PRODUCTS` and the `.images.env` entries in the root `Makefile`.
- **Multi-platform builds default to `linux/amd64`** but can be overridden globally via `IMAGE_PLATFORM=linux/arm64` (documented for native arm64 host/kind builds).
- **Registry push is opt-in**: images are always tagged locally as `luban-aiops/<name>:<tag>`; pushing to an external registry requires setting `REGISTRY=<host>/<org>`.
- **Verification gate is `make verify`**, which runs `test`, `overlays`, `validate-policy`, and `validate-version` — intended as the pre-commit/pre-push hook equivalent across any CI forge.
- **End-to-end testing** is driven by `make e2e`, which assumes a deployed dev cluster and port-forwarded services, then executes `skills-demo.sh`, `incident-demo.sh`, and `mutating-demo.sh` under `shared/platform-ops/e2e/`.