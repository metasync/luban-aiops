---
kind: build_system
name: Luban Platform Workspace Build & Artifact System
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
    - products/agent-platform/Dockerfile
    - products/platform-gateway/Dockerfile
    - products/operator-portal/Dockerfile
    - products/agent-platform/Makefile
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## Approach

The Luban platform is a Python/Node monorepo built with **GNU Make** as the single entry point. Each product under `products/<name>/` owns its own `Dockerfile`, `pyproject.toml` + `uv.lock`, and a thin per-product `Makefile` that includes shared fragments from `mk/`. The root `Makefile` orchestrates cross-cutting concerns: coordinated image tagging, GitOps overlay validation, policy bundle sync, dashboard validation, portal SPA build, and end-to-end demo execution.

Python dependencies are managed by **uv** (lockfile-driven via `uv sync --frozen`). Container images are built with **docker** against a shared base image `luban-aiops/base-uv:al2023` (built from `shared/base-images/base-uv/Dockerfile`). The operator portal (`operator-portal`) is a Vite/React SPA built in a multi-stage Dockerfile using `node:22-alpine` and served by `nginxinc/nginx-unprivileged:1.27-alpine`.

## Key files

- `Makefile` — master orchestration: `sync`, `test`, `lint`, `build`, `push`, `verify`, `deploy`, `e2e`, `overlays`, `validate-dashboards`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, `sync-policy`, `policy-diff`, `portal-test`, plus sample deployment targets.
- `mk/defaults.mk` — single source of overridable defaults: `IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`, `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, `BASE_UV_IMAGE`, `BASE_UV_TAG`, `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`.
- `mk/image.mk` — shared container-image targets (`help`, `build`, `push`, `lint`); computes `IMAGE_REF` as `luban-aiops/<name>:<tag>` or `<REGISTRY>/luban-aiops/<name>:<tag>`; falls back to `hadolint` → `docker run hadolint/hadolint` for linting.
- `mk/python.mk` — shared `sync` / `test` targets running `uv sync --frozen` then `pytest` with OTLP exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`).
- `VERSION` — single source of truth for the platform release semver (currently `0.50.0`), consumed by the root Makefile to compute `PLATFORM_VERSION` and injected into the portal's Vite build.
- Per-product `Dockerfile`s — Python products follow the same pattern: `FROM luban-aiops/base-uv:al2023`, copy `.python-version pyproject.toml uv.lock README.md src`, run `uv sync --frozen --no-dev`, expose port 8000, CMD `uv run <entrypoint>`.
- `products/operator-portal/Dockerfile` — multi-stage Node build copying `VERSION` from repo root so `vite.config.ts` can inject `PLATFORM_VERSION`; nginx serves hashed assets at `/` with SPA fallback.
- `shared/platform-ops/gitops/` — Kustomize overlays validated by `make overlays` (`dev-k8s`, `runtime-profiles/{default,mutating-dev,browser-dev,ansible-dev,servicenow-dev}`).
- `shared/platform-ops/dashboards/` — OpenObserve dashboards validated offline by `make validate-dashboards` (SPEC-065 R-3).
- `shared/shared-contracts/scripts/` — policy, version, secret-vocabulary, password-policy validators invoked by root Makefile targets.

## Architecture and conventions

1. **Two-level Makefile design.** Root `Makefile` delegates per-product work via `$(MAKE) -C products/$$p ...`; each product `Makefile` is ~10 lines declaring `IMAGE_NAME` and including `../../mk/image.mk` and `../../mk/python.mk`. This keeps product logic out of the root file while giving a uniform interface.

2. **Coordinated image tagging.** The root `make build` computes one `IMAGE_TAG` once (format: `<semver>-<prefix>[-<profile>]-<gitsha>`, or `<semver>-<prefix>-dirty-<timestamp>` for dirty trees) and passes it to every product. After building all images, it writes `shared/platform-ops/gitops/dev-k8s/.images.env` mapping logical names (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, etc.) to the coordinated tag, which `make deploy` consumes.

3. **Product classification lists.** `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` enumerate which products participate in which top-level targets; adding a new product requires updating both lists in the root Makefile.

4. **Reproducible base image.** `make base-images` builds `luban-aiops/base-uv:<tag>` from `shared/base-images/base-uv/Dockerfile` with pinned `UV_VERSION` and `PYTHON_VERSION` from `mk/defaults.mk`; Python product images depend on this base rather than an upstream Python image directly.

5. **Policy-as-code sync.** Canonical policy bundles live in `shared/shared-contracts/policies/` and are copied to consumers via `make sync-policy` (tool-gateway, platform-gateway, and the dev-k8s GitOps overlay). Consumers validate them via scripts in `shared/shared-contracts/scripts/`.

6. **Version lockstep.** `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root to enforce that `VERSION`, every product's declared version, and the portal's build-time version stay in sync.

7. **Secret vocabulary lockstep.** `make validate-secret-vocabulary` enforces that secret literal declarations across `agent-platform`, `tool-gateway`, and `skills-hub` match a canonical set.

8. **GitOps overlay gate.** `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on every overlay listed in `OVERLAYS`; failures block verification.

9. **Verification gate.** `make verify` aggregates product tests, overlay rendering, dashboard validation, policy validation, policy-scenario evaluation, version/secret/password-policy checks, secret-delivery demo, portal unit+build, audit contract test, delegated-custody test, and execution-failure test — intended as the pre-commit/pre-push gate.

10. **Kind integration.** When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all nine images into the named kind cluster after building.

## Conventions and constraints

- **Every Python product uses uv with a frozen lockfile.** `mk/python.mk` runs `uv sync --frozen`; no ad-hoc `pip install` paths are used in build scripts.
- **Container images are built with `--platform $(IMAGE_PLATFORM)`**, defaulting to `linux/amd64` but overridable (e.g., `linux/arm64` for native kind builds on arm64 hosts).
- **Image tags are deterministic:** clean tree → `<semver>-<prefix>[-<profile>]-<gitsha>`; dirty tree → appends `-dirty-<timestamp>`.
- **The root `VERSION` file is the single source of truth** for the platform release semver; it is read by the root Makefile and copied into the operator-portal build context so the SPA embeds it at build time.
- **All overridable settings use `?=` in `mk/defaults.mk`**, so command-line overrides always win (documented in the file header).
- **Dockerfiles are linted via hadolint with a docker-run fallback** (`mk/image.mk` `lint` target); the root `make lint` invokes it for every `IMAGE_PRODUCT`.
- **Portal tests are not part of `make test`** because the operator-portal SPA is not a uv product; `make verify` explicitly calls `make portal-test` which runs Vitest and the production Vite build (`products/operator-portal/test` and `web-build`).
- **Samples are kept out-of-band from the base overlay** (SPEC-050 R-11): they are deployed separately via `make deploy-samples` / `make deploy-sample-app` and never appear in `make deploy`'s base overlay.
- **Cross-cutting contracts are enforced by dedicated scripts** under `shared/shared-contracts/scripts/`: `validate_policy.py`, `validate_policy_scenarios.py`, `validate_version.py`, `validate_secret_vocabulary.py`, `validate_password_policy.py`, `policy_diff.py`.
- **End-to-end demos** are orchestrated by `make e2e`, which runs a fixed sequence of scripts under `shared/platform-ops/e2e/` and `samples/acme-admin/demo-suite.sh` against a deployed cluster requiring port-forwards for `platform-gateway:18083` and `identity-service:18081`.