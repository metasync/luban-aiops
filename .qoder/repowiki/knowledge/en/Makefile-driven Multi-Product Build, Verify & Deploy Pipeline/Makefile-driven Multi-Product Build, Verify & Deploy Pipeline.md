---
kind: build_system
name: Makefile-driven Multi-Product Build, Verify & Deploy Pipeline
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/python.mk
    - mk/image.mk
    - VERSION
    - products/agent-platform/Makefile
    - products/operator-portal/Makefile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/base-images/base-uv/Dockerfile
---

# Build System Overview

Luban is a multi-product Python workspace (8 FastAPI services + operator-portal SPA) orchestrated by a single GNU Makefile at the repository root. There is no CI workflow YAML in `.github/`; the documented pre-commit/pre-push gate is `make verify`, which runs the same checks locally and under any CI.

## Architecture

### Two-layer Makefile design

- **Root `Makefile`** — aggregates per-product routines, owns cross-cutting concerns (GitOps overlay validation, policy sync/validation, dashboard validation, coordinated image tagging, deploy, e2e).
- **Per-product `products/<name>/Makefile`** — thin wrapper that sets `IMAGE_NAME` and includes shared fragments from `mk/`. Example: `products/agent-platform/Makefile` is only 10 lines.
- **Shared fragments in `mk/`**:
  - `defaults.mk` — single source of truth for overridable build settings (`IMAGE_PLATFORM`, `BASE_UV_*`, `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`). All values use `?=` so command-line overrides always win.
  - `python.mk` — provides `sync` / `test` targets using `uv sync --frozen` then `uv run pytest`, with OTel exporters disabled during tests.
  - `image.mk` — provides `build` / `push` / `lint` targets around `docker build`, with hadolint fallback via `docker run hadolint/hadolint`.

### Product inventory

The root Makefile enumerates two lists:
- `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`
- `IMAGE_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway operator-portal`

Each product has its own `Dockerfile`, `pyproject.toml`, `uv.lock`, `.python-version`, and `Makefile`.

### Image tagging strategy

Coordinated tag computation (root `Makefile`):
```
<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]
```
- Semver comes from the root `VERSION` file (`0.51.0`).
- Prefix defaults to `dev-k8s` (`IMAGE_TAG_PREFIX`), profile is empty unless `IMAGE_TAG_PROFILE` is set.
- Clean tree → `<version>-dev-k8s-<short-sha>`; dirty tree → appends `-dirty-YYYYMMDDHHMMSS`.
- The computed tag is written into `shared/platform-ops/gitops/dev-k8s/.images.env` alongside per-service image names (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, etc.) consumed by the deploy script.

### Base images

`shared/base-images/base-uv/Dockerfile` builds a pinned base image (`luban-aiops/base-uv:al2023`) with pinned `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`. Built via `make base-images` before `make build`.

### Operator portal (non-Python product)

`products/operator-portal/Makefile` defines `test` (runs `npm test` via Vitest) and `web-build` (runs `tsc --noEmit && vite build`). It uses `IMAGE_CONTEXT := ../..` because the Dockerfile needs the root `VERSION` file plus the Vite project. The root `verify` target delegates to `portal-test`, which runs both unit suite and production build — no skip toggle is accepted as a release pass (SPEC-063 R-8c).

## Key Targets

| Target | Scope | Description |
|---|---|---|
| `make sync` | All Python products | `uv sync --frozen` per product |
| `make test` | All Python products | Runs pytest per product |
| `make lint` | All container images | hadolint per Dockerfile |
| `make build` | All images | Builds all images with coordinated tag, writes `.images.env`, optionally loads into kind |
| `make push` | All images | Pushes images to `$(REGISTRY)/luban-aiops/<name>:<tag>` |
| `make overlays` | GitOps | `kustomize build` on every overlay in `OVERLAYS` |
| `make validate-dashboards` | Observability | Validates OpenObserve dashboards offline (SPEC-065 R-3) |
| `make validate-policy` | Policy | Validates canonical policy bundle against JSON schema |
| `make validate-policy-scenarios` | Policy | Evaluates scenario expectations against both engines |
| `make validate-version` | Versioning | Enforces lockstep between `VERSION`, products, and portal |
| `make validate-secret-vocabulary` | Contracts | Validates secret-literal lockstep across agent-platform/tool-gateway/skills-hub |
| `make verify` | All above | Pre-commit/pre-push gate combining test, overlays, dashboards, policy, version, secret vocabulary, secret-delivery demo, portal test, and delegated-custody/runtime/multi-process/edge/execution-failure proofs |
| `make deploy` | Cluster | Wraps `shared/platform-ops/gitops/dev-k8s/deploy.sh` |
| `make e2e` | Cluster | Runs demo scripts against deployed dev cluster |

## GitOps & Deployment

- Overlays live under `shared/platform-ops/gitops/` with `dev-k8s` as the default overlay and `runtime-profiles/*` variants (`default`, `mutating-dev`, `browser-dev`, `ansible-dev`, `servicenow-dev`, `delegated-dev`).
- `make overlays` validates every overlay via `kustomize build --load-restrictor LoadRestrictionsNone`.
- `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`.
- Samples are kept out-of-band from the base overlay (SPEC-050 R-11): `make deploy-samples` installs tutorial skills separately.

## Conventions Observed

- Every Python product pins dependencies via `uv.lock` and installs them frozen (`uv sync --frozen`).
- Every product exposes a `Dockerfile` and a `Makefile` that includes `../../mk/image.mk` and `../../mk/python.mk`.
- Image names follow the `luban-aiops/<service-name>:<tag>` convention; when `REGISTRY` is set, they are re-tagged to `$(REGISTRY)/luban-aiops/<service-name>:<tag>`.
- The root `VERSION` file is the single source of truth for the platform semver; it is injected into the operator-portal build via `PLATFORM_VERSION`.
- Policy bundles are authored once at `shared/shared-contracts/policies/policy-default.yaml` and synced to consumers via `make sync-policy`.
- Secret vocabulary and password-policy contracts are validated centrally via scripts under `shared/shared-contracts/scripts/`.
- Cross-cutting integration tests (audit contract, delegated custody, delegated runtime, delegated multiproc, delegated edge, execution failure) are invoked from the root Makefile rather than per-product `make test`.
- The `verify` target is the authoritative gate: it chains product tests, GitOps overlay renders, dashboard validation, policy validation/scenarios, version lockstep, secret vocabulary, secret-delivery demo, portal unit+build, and all delegated/execution proof suites.