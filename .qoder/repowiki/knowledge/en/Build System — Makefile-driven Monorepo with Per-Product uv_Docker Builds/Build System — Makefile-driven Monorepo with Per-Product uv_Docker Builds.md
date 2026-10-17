---
kind: build_system
name: Build System — Makefile-driven Monorepo with Per-Product uv/Docker Builds
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/operator-portal/Makefile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/dashboards/validate_dashboards.py
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_password_policy.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - VERSION
---

## Approach

The Luban workspace is built entirely through **GNU make** orchestration plus per-product `Dockerfile`s and Python/Node toolchains. There is no CI pipeline definition in `.github/workflows` (only issue templates and a PR template), so the build system documented here is the local/dev-side surface; CI integration is referenced by specs but not present in this branch.

Two layers of abstraction are used:

1. **Root `Makefile`** — aggregates cross-cutting concerns: coordinated image tagging, GitOps overlay rendering (`kustomize build`), policy validation, dashboard validation, secret-vocabulary checks, portal SPA tests, execution-failure e2e, and the `verify` gate that composes them all.
2. **Shared fragments under `mk/`** — reusable targets included by every product Makefile:
   - `mk/defaults.mk` — single source of truth for overridable settings (`IMAGE_PLATFORM`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*` versions).
   - `mk/image.mk` — shared `build` / `push` / `lint` Docker targets (uses `docker build --platform $(IMAGE_PLATFORM)`, falls back to `hadolint/hadolint` container if `hadolint` binary is missing).
   - `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` + `uv run pytest` with OTLP exporters disabled during tests.

## Key Files

- `Makefile` — root orchestrator, declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`, `GITOPS_DIR`, `E2E_DIR`, `DASHBOARDS_DIR`, `SAMPLES_DIR`, computes `IMAGE_TAG` from `VERSION` + git SHA + profile + dirty flag, writes coordinated state to `shared/platform-ops/gitops/dev-k8s/.images.env`.
- `mk/defaults.mk` — guarded include (`ifndef LUBAN_DEFAULTS_INCLUDED`) with all `?=` defaults.
- `mk/image.mk` — per-product image fragment; sets `IMAGE_CONTEXT ?= .`, `IMAGE_DOCKERFILE ?= $(IMAGE_CONTEXT)/Dockerfile`, resolves `IMAGE_REF` against `luban-aiops/*` or `$(REGISTRY)/luban-aiops/*`.
- `mk/python.mk` — `uv sync --frozen` + pytest with `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`.
- `products/<name>/Makefile` — thin wrappers that set `IMAGE_NAME` and `include ../../mk/{image,python}.mk`. The operator-portal overrides `IMAGE_CONTEXT := ../..` and `IMAGE_DOCKERFILE := Dockerfile` because its multi-stage Dockerfile needs the repo root (for `VERSION`).
- `shared/base-images/base-uv/Dockerfile` — shared base image built via `make base-images` with pinned `UV_VERSION` and `PYTHON_VERSION`.
- `shared/platform-ops/gitops/` — Kustomize overlays rendered by `make overlays`.
- `shared/platform-ops/dashboards/validate_dashboards.py` — offline OpenObserve dashboard validator invoked by `make validate-dashboards`.
- `shared/shared-contracts/scripts/` — policy, version, secret-vocabulary, password-policy validators invoked from the root Makefile.
- `VERSION` — single source of truth for the platform semver (currently `0.47.0`); propagated into images via `PLATFORM_VERSION`.

## Architecture & Conventions

- **Coordinated image tagging**: `make build` computes one `IMAGE_TAG` per invocation as `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` when `git status --porcelain` is non-empty). All eight Python services plus the `operator-portal` web UI are tagged with the same digest and written into `.images.env`, which `deploy.sh` consumes.
- **Per-product isolation**: each product has its own `pyproject.toml` + `uv.lock` (Python products) or Vite/NPM project (operator-portal). Root `make test` / `make lint` / `make sync` iterate over `PYTHON_PRODUCTS` / `IMAGE_PRODUCTS` and delegate via `$(MAKE) -C products/$$p <target>`.
- **Policy contracts**: canonical bundles live in `shared/shared-contracts/policies/`; `make sync-policy` copies them into `products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. `make validate-policy` / `validate-password-policy` / `policy-diff` enforce schema and scenario conformance.
- **Secret vocabulary lockstep**: `make validate-secret-vocabulary` runs `shared/shared-contracts/scripts/validate_secret_vocabulary.py` across agent-platform, tool-gateway, and skills-hub.
- **Version lockstep**: `make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` to keep `VERSION`, every product's declared version, and the portal in sync.
- **Kustomize overlays**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`.
- **Dashboard validation**: `make validate-dashboards` runs `shared/platform-ops/dashboards/validate_dashboards.py` to parse envelopes, panels, and resolve every metric reference against emitted OTEL streams (SPEC-065 R-3).
- **Portal SPA**: operator-portal is excluded from `PYTHON_PRODUCTS`; it has its own `test` (Vitest) and `web-build` (Vite + tsc) targets, and `make verify` delegates to `portal-test` (SPEC-063 R-8c).
- **Kind integration**: `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<name>` after `make build` loads all nine images into the named kind cluster.
- **Verification gate**: `make verify` = `test` + `overlays` + `validate-dashboards` + `validate-policy` + `validate-policy-scenarios` + `validate-version` + `validate-secret-vocabulary` + `validate-password-policy` + `secret-delivery-demo` + `portal-test` + `execution-failure-test`.

## Conventions & Constraints

- Every Python product uses `uv sync --frozen` (no network, lockfile-bound) — enforced by `mk/python.mk`.
- Docker builds always pass `--platform $(IMAGE_PLATFORM)` (default `linux/amd64`, overridden via `make build IMAGE_PLATFORM=linux/arm64`) — enforced by `mk/image.mk`.
- Image references are always `luban-aiops/<name>:<tag>` locally; setting `REGISTRY` re-tags to `$(REGISTRY)/luban-aiops/<name>:<tag>` before push — enforced by `mk/image.mk`.
- The root `VERSION` file is the single source of truth for the platform release version; `make validate-version` enforces lockstep with product and portal versions.
- Policy bundles are authored once in `shared/shared-contracts/policies/` and copied to consumers via `make sync-policy` — the canonical locations are enumerated in the root Makefile.
- Dashboard artifacts must pass `make validate-dashboards` (SPEC-065 R-3) before deploy; the live import step is separate (R-4).
- The operator-portal SPA unit suite and production build are required by `make verify` (SPEC-063 R-8c); Vitest fails on zero tests, so there is no skip path.
- Samples (`samples/acme-admin/...`) are deployed out-of-band via `make deploy-samples` / `deploy-sample-app` and never appear in the base Kustomize overlay (SPEC-050 R-11).
- No CI workflow files exist in `.github/workflows` on this branch; the spec history references adding `ci.yml` and an overlay-render workflow, but they are not present in the current tree.