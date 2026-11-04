---
kind: build_system
name: Workspace Build System — Multi-Product Makefile, uv + Docker, Kustomize GitOps
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
    - products/operator-portal/Makefile
    - shared/platform-ops/gitops/dev-k8s/.images.env
    - shared/platform-ops/dashboards/validate_dashboards.py
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - shared/shared-contracts/scripts/validate_password_policy.py
    - shared/shared-contracts/scripts/validate_policy_scenarios.py
    - shared/shared-contracts/scripts/policy_diff.py
    - shared/platform-ops/e2e/observability-livecheck.sh
    - shared/platform-ops/e2e/execution-failure-test.sh
    - samples/acme-admin/deploy.sh
---

# Luban Agentic AIOps Platform — Build & Artifact Management

## Approach

The repository is a **multi-product workspace** (nine Python services plus an operator-portal SPA) orchestrated by a single root `Makefile` that delegates per-product work to shared fragments under `mk/`. There is no CI pipeline file in the repo; the author guidelines direct forge-agnostic verification via `make verify`, which runs the same checks locally and under any CI. The build surface is:

- **Python products**: `uv sync --frozen` + `pytest`, driven through `mk/python.mk`.
- **Container images**: `docker build` with a shared base image `luban-aiops/base-uv` (Al2023 + pinned `uv` + `python:3.12`), built via `mk/image.mk`.
- **Kubernetes deployment**: Kustomize overlays under `shared/platform-ops/gitops/`, rendered via `kustomize build --load-restrictor LoadRestrictionsNone` as part of verification.
- **Operator portal SPA**: Vite + Vitest + TypeScript, built via npm inside its product directory.
- **Policy contracts**: JSON-schema validation and scenario evaluation against both platform-gateway and tool-gateway engines.

## Key Files

| File | Role |
|---|---|
| `Makefile` | Root orchestrator: product loops, coordinated image tagging, policy/dashboard/version gates, e2e demo runner, deploy wrapper |
| `mk/defaults.mk` | Single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`) |
| `mk/image.mk` | Shared `build` / `push` / `lint` targets for every product's Dockerfile |
| `mk/python.mk` | Shared `sync` / `test` targets using `uv sync --frozen` + `pytest` |
| `VERSION` | Single source of truth for the platform release semver (currently `0.54.0`) |
| `shared/platform-ops/gitops/` | Kustomize overlays (`dev-k8s`, `runtime-profiles/*`) rendered by `make overlays` |
| `shared/platform-ops/dashboards/validate_dashboards.py` | Offline schema + metric-reference validator for OpenObserve dashboards |
| `shared/shared-contracts/scripts/` | Policy/schema validators invoked from root targets (`validate_policy.py`, `validate_version.py`, `validate_secret_vocabulary.py`, `validate_password_policy.py`, `validate_policy_scenarios.py`, `policy_diff.py`) |
| `products/*/Makefile` | Thin wrappers setting `IMAGE_NAME` and including `../../mk/image.mk` (+ `../../mk/python.mk` for Python products) |
| `products/operator-portal/Makefile` | Non-Python product: adds `test` (Vitest) and `web-build` (Vite production build) |
| `shared/platform-ops/e2e/` | End-to-end demo scripts invoked by `make e2e` |
| `samples/acme-admin/deploy.sh` | Sample app deployment target used by `make deploy-sample-app` |

## Architecture and Conventions

### Product taxonomy
Products are classified at the root level into two lists:
- `PYTHON_PRODUCTS`: agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway.
- `IMAGE_PRODUCTS`: same eight plus operator-portal.

This drives the `sync`, `test`, `lint`, and `build` loops — adding a new product means registering it in these lists and providing a thin `Makefile`.

### Coordinated image tagging
The root computes one `IMAGE_TAG` once:
```
[<semver>-]<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]
```
The semver comes from `VERSION`; prefix/profile come from `IMAGE_TAG_PREFIX` / `IMAGE_TAG_PROFILE`; dirty detection uses `git status --porcelain`. All images produced by `make build` share this tag, and the state is written to `shared/platform-ops/gitops/dev-k8s/.images.env` for the subsequent `make deploy` step.

### Base image strategy
All Python services build on `shared/base-images/base-uv/Dockerfile`, which pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` (overridable via `BASE_UV_UV_VERSION` / `BASE_UV_PYTHON_VERSION`). The root `make base-images` builds this image first, then each product's `make build` layers the service on top.

### Dependency management
Each Python product has its own `pyproject.toml` + `uv.lock` under `products/<name>/`. The shared `mk/python.mk` always runs `uv sync --frozen`, so dependency resolution is locked and reproducible. Tests run with OTel exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) so tracing tests pass without a collector.

### Version lockstep
`make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file matches every product's declared version. This is part of the `verify` gate.

### Policy contract model
Canonical policy bundles live under `shared/shared-contracts/policies/`. `make sync-policy` copies them into consumers (tool-gateway, platform-gateway, dev-k8s overlay). Consumers never author policies directly; they consume the synced copy. Validation runs against both engines via `validate_policy_scenarios.py`.

### Secret vocabulary lockstep
`make validate-secret-vocabulary` enforces that secret literal declarations stay in sync across agent-platform, tool-gateway, and skills-hub.

### Password policy contract
Per SPEC-062 R-2, `shared/shared-contracts/policies/password-policy.yaml` is the canonical password-strength contract, copied into tool-gateway and validated by `make validate-password-policy`, which also pins the connector floor to it.

### Dashboard validation
OpenObserve dashboard definitions under `shared/platform-ops/dashboards/` are validated offline by `validate_dashboards.py`, which parses the envelope/panel schema and verifies every metric reference resolves to an emitted `OTEL_MIRROR_FAMILIES` stream (SPEC-065 R-3).

### Operator portal exception
The operator portal is not a uv product. Its `Makefile` sets `IMAGE_CONTEXT := ../..` because the multi-stage Dockerfile needs the root `VERSION` file plus `web-ui/app`. `make verify` explicitly calls `portal-test` (Vitest) and `web-build` (Vite production build); the comment documents that Vitest fails on zero tests, so there is no skip path.

### Kind integration
When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all nine images into the named kind cluster after building.

### Verification gate
`make verify` is the pre-commit/pre-push entry point. It runs:
- Per-product test suites
- Kustomize overlay rendering (`make overlays`)
- Dashboard validation
- Policy validation + scenario evaluation
- Version lockstep check
- Secret vocabulary check
- Password policy check
- Secret-delivery demo
- Portal unit suite + production build
- Audit contract test (disposable Postgres)
- Delegated custody / runtime / multiproc / edge integration tests
- Execution failure test

### Deploy flow
`make deploy` wraps `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies the rendered dev-k8s overlay. Samples are deployed out-of-band via `make deploy-samples` (and `deploy-sample-app` for the acme-admin sample) so the base overlay never names a sample (SPEC-050 R-11).

## Conventions and Constraints

- **Forge-agnostic CI**: The root `Makefile` header states `make verify` is the pre-commit/pre-push gate and runs the same checks locally and under any CI. No `.github/workflows/` or other CI config exists in the repo.
- **Single source of truth for versions**: `VERSION` is the only place the platform release semver lives; `make validate-version` enforces lockstep with every product.
- **No mutable dependencies**: Python products use `uv sync --frozen`; the lockfile is authoritative.
- **Pinned base image**: The base-uv image uses fixed `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`; the defaults file comments explicitly say "never `latest`".
- **Coordinated tagging**: All images built by the root `make build` receive the same computed `IMAGE_TAG`; individual product `make build` invocations inherit it from the parent.
- **Image naming convention**: Images are tagged `luban-aiops/<image-name>:<tag>` locally, optionally re-tagged to `<REGISTRY>/luban-aiops/<image-name>:<tag>` when `REGISTRY` is set.
- **Overlay rendering is enforced**: `make verify` runs `kustomize build` on every overlay listed in `OVERLAYS` with `--load-restrictor LoadRestrictionsNone`; a render failure stops the gate.
- **Dashboards must validate offline**: Per SPEC-065 R-3, `make validate-dashboards` must pass before deploy; it validates schema and metric references without touching a cluster.
- **Portal build is mandatory**: Per SPEC-063 R-8c, `make verify` includes `portal-test` and `web-build`; the comment notes Vitest fails on zero tests, so there is no skip path.
- **Samples are excluded from the base overlay**: Per SPEC-050 R-11, samples are installed via `make deploy-samples` / `make deploy-sample-app` out-of-band so `make deploy` never names a sample.
- **Policy bundles are authored once**: `make sync-policy` is the only way to propagate changes from `shared/shared-contracts/policies/` to consumers; consumers do not maintain their own copies independently.
- **Cross-cutting secrets are validated**: `make validate-secret-vocabulary` enforces lockstep between agent-platform, tool-gateway, and skills-hub.
- **Password policy is a contract**: Per SPEC-062 R-2, the password-strength bundle is synchronized into tool-gateway and the connector floor is pinned to it.