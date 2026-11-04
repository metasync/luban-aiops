---
kind: build_system
name: Workspace Build & Artifact Management (Make + uv + Docker + Kustomize)
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/platform-gateway/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - VERSION
---

## Approach

The Luban workspace is built with a layered, forge-agnostic system:

1. **GNU Make** at the repository root orchestrates cross-cutting concerns (sync, test, lint, build, push, overlays, policy validation, e2e).
2. **Per-product `Makefile`s** delegate to shared fragments under `mk/` (`image.mk`, `python.mk`) after declaring `IMAGE_NAME`.
3. **Docker** builds container images from per-product `Dockerfile`s on top of a shared base image `luban-aiops/base-uv:al2023`.
4. **uv** manages Python dependencies via `pyproject.toml` + `uv.lock`; all dependency installs use `uv sync --frozen` for reproducibility.
5. **Kustomize** renders GitOps overlays under `shared/platform-ops/gitops/<overlay>` as part of verification and deployment.
6. **Shell scripts** drive end-to-end demos, sample deployment, and specialized contract tests.

There are no CI workflow files committed in this snapshot; the author guidelines and SPEC-001 plan reference `.github/workflows/ci.yml` as an intended artifact, but it is not present in the tree.

## Key Files

- `Makefile` — master entry point; defines product lists, coordinated image tag computation, policy/dashboard/version gates, overlay rendering, deploy, e2e.
- `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`, `IMAGE_TAG_PREFIX`).
- `mk/image.mk` — shared `build` / `push` / `lint` targets for container images; resolves `IMAGE_REF` against `luban-aiops/` registry or user-supplied `REGISTRY`.
- `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled during tests.
- Per-product `products/<name>/Makefile` — thin wrappers that set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`.
- Per-product `Dockerfile` — multi-stage-free images based on `luban-aiops/base-uv:al2023`, running `uv sync --frozen --no-dev` then `uv run <entrypoint>`.
- `shared/base-images/base-uv/Dockerfile` — base image definition built by `make base-images`.
- `shared/platform-ops/gitops/` — Kustomize overlays rendered by `make overlays`.
- `shared/shared-contracts/scripts/` — policy, version, secret-vocabulary, password-policy validators invoked from root targets.
- `VERSION` — single source of truth for the platform release semver; consumed by `PLATFORM_VERSION := $(shell cat VERSION)` and enforced by `make validate-version`.
- `samples/acme-admin/deploy.sh`, `samples/deploy-samples.sh`, `shared/platform-ops/e2e/*.sh` — deployment and demo scripts.

## Architecture & Conventions

### Product taxonomy
Products are partitioned into two root-level lists:
- `PYTHON_PRODUCTS` — those with a `uv` test suite (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`).
- `IMAGE_PRODUCTS` — those producing a container image (adds `operator-portal`).

This drives the root `sync`, `test`, `lint`, and `build` loops.

### Coordinated tagging
The root `IMAGE_TAG` is computed once and reused across all products:
- Clean tree → `<semver>-<prefix>[-<profile>]-<gitsha>`.
- Dirty tree → same prefix plus `-dirty-<timestamp>`.
- The tag is written into `shared/platform-ops/gitops/dev-k8s/.images.env` so `make deploy` consumes the exact images just built.

### Image naming
Images are tagged `luban-aiops/<product>:<IMAGE_TAG>` locally; when `REGISTRY` is set, they are additionally re-tagged to `$(REGISTRY)/luban-aiops/<product>:<IMAGE_TAG>` and pushed.

### Base image pinning
All product images derive from `luban-aiops/base-uv:<BASE_UV_TAG>` (default `al2023`), which itself pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`. The base image is rebuilt first via `make base-images` before any product image.

### Dependency strategy
Each Python product ships its own `pyproject.toml` + `uv.lock`. There is no monorepo lockfile; `make sync` iterates products and runs `uv sync --frozen` per product. Tests also run `uv sync --frozen` before invoking pytest, ensuring the environment matches the lock.

### Policy contracts
Canonical policy bundles live in `shared/shared-contracts/policies/` and are copied to consumers via `make sync-policy` into `products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. Consumers validate them through scripts under `shared/shared-contracts/scripts/`.

### Version lockstep
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file stays in lockstep with every product's declared version.

### Secret vocabulary lockstep
`make validate-secret-vocabulary` enforces that secret literals used across `agent-platform`, `tool-gateway`, and `skills-hub` stay synchronized.

### Dashboard validation
`make validate-dashboards` runs `shared/platform-ops/dashboards/validate_dashboards.py` to parse OpenObserve dashboard JSON, validate envelope/panel schemas, and verify every metric reference resolves to an emitted OTEL stream (SPEC-065 R-3).

### Operator portal
The SPA under `products/operator-portal/web-ui` is not a uv product. It has its own `Makefile` exposing `test` (Vitest) and `web-build` (Vite + typecheck); the root `make portal-test` runs both, and `make verify` includes it as a delivery gate.

### Kind integration
When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all nine service images plus `web-ui` into the named kind cluster after building.

### Verification gate
`make verify` aggregates the full pre-commit/pre-push surface: product tests, Kustomize overlay render, dashboard validation, policy validation/scenarios, version lockstep, secret-vocabulary check, password-policy check, secret-delivery demo, portal test, audit contract test, delegated-custody/runtime/multiproc/edge tests, and execution-failure test.

## Conventions & Constraints

- **Forge-agnostic**: The root comment states `make verify` is the pre-commit/pre-push gate and runs identically locally and under any CI. No CI-specific logic lives in the Makefiles.
- **Pinned base versions**: `mk/defaults.mk` explicitly documents that pinned values are defaults for reproducible builds and "never `latest`".
- **Overridable defaults**: All build settings use `?=` so command-line overrides always win (documented in `mk/defaults.mk` and `mk/image.mk`).
- **Single source of truth for image tag**: The root Makefile computes `IMAGE_TAG` once and writes it to `.images.env`; product builds receive it via `IMAGE_TAG=$(IMAGE_TAG)` rather than recomputing.
- **Frozen dependency resolution**: Both `mk/python.mk` and product `Dockerfile`s use `uv sync --frozen`, enforcing that builds reproduce the locked dependency graph.
- **Product Makefiles must declare `IMAGE_NAME`**: Enforced by `mk/image.mk`, which requires the including Makefile to set `IMAGE_NAME` before inclusion.
- **Samples are out-of-band**: `make deploy` never names a sample; samples are installed separately via `make deploy-samples` and `make deploy-sample-app` (per SPEC-050 R-11).
- **Portal tests are mandatory in the delivery gate**: Root comment states the Vitest suite and production build run with no integration skip toggle accepted as a release pass.
- **Overlay rendering is verified**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` for every overlay listed in `OVERLAYS`.
- **Policy bundle synchronization is explicit**: Consumers do not import policies dynamically from `shared/shared-contracts/policies/`; they must be copied via `make sync-policy`.
- **Version lockstep is enforced**: `make validate-version` fails if the root `VERSION` diverges from product versions.

## Notable Absences

No CI workflow YAML files are present in `.github/workflows/` in this snapshot; only `ISSUE_TEMPLATE/`, `CODEOWNERS`, and `pull_request_template.md` exist. The referenced `ci.yml` appears only in spec task lists.