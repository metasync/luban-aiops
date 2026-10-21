---
kind: build_system
name: 'Workspace Build System: Makefile + Docker + Kustomize Orchestration'
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - VERSION
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/operator-portal/Makefile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/base-images/base-uv/Dockerfile
---

## What system/approach is used

The Luban workspace uses a **Makefile-driven multi-product build** layered over three toolchains:

- **Python products**: `uv` (lockfile-frozen) for dependency resolution and `pytest` for tests.
- **Container images**: `docker build --platform <arch>` with a shared base image (`shared/base-images/base-uv`) built from `mk/image.mk`.
- **Kubernetes deployment**: Kustomize overlays under `shared/platform-ops/gitops`, orchestrated by shell scripts in `shared/platform-ops/gitops/dev-k8s/`.

There is no CI configuration file in the repository (no `.github/workflows`, no GitLab CI, no Jenkinsfile); the root `Makefile` declares itself "Forge-agnostic" and is intended to be the pre-commit/pre-push gate run locally or inside any CI. The only GitHub metadata present is `.github/CODEOWNERS`, issue templates, and a PR template.

## Key files and packages

- `Makefile` — master entry point; defines product lists, coordinated image tag computation, policy/dashboard/version validation, overlay rendering, deploy, e2e, and the `verify` gate.
- `mk/defaults.mk` — single source of truth for overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `IMAGE_TAG_PREFIX`).
- `mk/image.mk` — shared container-image targets (`build`, `push`, `lint` via hadolint).
- `mk/python.mk` — shared Python targets (`sync`, `test`) using `uv sync --frozen` and pytest with OTLP exporters disabled.
- `products/<name>/Makefile` — per-product thin wrappers that set `IMAGE_NAME` and include the two shared fragments.
- `VERSION` — single source of truth for the platform semver (currently `0.49.0`), enforced against every product's version.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — deployment orchestrator that applies the overlay then runs secret-provisioning scripts for each feature area.
- `shared/platform-ops/gitops/runtime-profiles/*` — Kustomize overlays selecting runtime profiles (default, mutating-dev, browser-dev, ansible-dev, servicenow-dev).
- `shared/shared-contracts/scripts/*` — policy/schema validators invoked from the root Makefile (`validate_policy.py`, `validate_version.py`, `validate_secret_vocabulary.py`, `validate_password_policy.py`).

## Architecture and conventions

### Product model
Each service under `products/` is an independent Python package with its own `pyproject.toml`, `uv.lock`, `Dockerfile`, and a tiny `Makefile` that only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. The root `Makefile` enumerates them explicitly:

```
PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway
IMAGE_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway operator-portal
```

The operator portal is the exception: it has no Python test suite and instead builds a Vite/Vitest SPA served by nginx; its `Makefile` overrides `IMAGE_CONTEXT := ../..` so the Dockerfile can see the root `VERSION` file.

### Coordinated image tagging
The root `make build` computes one `IMAGE_TAG` once and passes it to every product, producing tags of the form `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for dirty trees). After building, it writes `shared/platform-ops/gitops/dev-k8s/.images.env` mapping each service name to its `luban-aiops/<service>:<tag>` reference, which `deploy.sh` consumes.

### Base image pinning
All Python services are built on top of `shared/base-images/base-uv/Dockerfile`, whose Python and uv versions are pinned via `BASE_UV_PYTHON_VERSION ?= 3.12` and `BASE_UV_UV_VERSION ?= 0.12.1` in `mk/defaults.mk`. The base image target is `make base-images`.

### Multi-arch support
`IMAGE_PLATFORM ?= linux/amd64` in `mk/defaults.mk`; cross-compilation is done via `--platform $(IMAGE_PLATFORM)` on every `docker build`. An optional `AUTO_LOAD_KIND=true KIND_CLUSTER_NAME=<cluster>` flag after `make build` auto-loads all nine images into a local kind cluster.

### Policy as code
Canonical policy bundles live in `shared/shared-contracts/policies/` and are copied to consumers via `make sync-policy`. Consumers are validated against JSON schemas via `make validate-policy` and scenario suites via `make validate-policy-scenarios`. A separate password-policy contract (`SPEC-062 R-2`) is validated and pinned to the connector floor.

### Version lockstep
`make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file matches every product's declared version.

### Secret vocabulary lockstep
`make validate-secret-vocabulary` enforces that secret literal names stay synchronized across `agent-platform`, `tool-gateway`, and `skills-hub`.

### Verification gate
`make verify` aggregates all checks: product tests, Kustomize overlay renders, dashboard validation, policy validation/scenarios, version lockstep, secret vocabulary, password policy, secret-delivery demo, portal SPA tests/build, and the execution failure test. It is documented as the pre-commit/pre-push gate.

### Deployment flow
`make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which:
1. Applies the Kustomize overlay via `deploy-overlay.sh`.
2. Runs a sequence of `sync-*` scripts to provision secrets (OIDC delegation, audit ingestion, execution signing/handoff tokens, skills/incident/browser/Ansible/ServiceNow credentials, sessions DB, OTel ingest).
3. Optionally reconciles the Keycloak realm and portal OIDC client.

Runtime profiles are selected via overlays under `runtime-profiles/` and validated by `kustomize build --load-restrictor LoadRestrictionsNone` during verification.

### Dashboards
OpenObserve dashboards under `shared/platform-ops/dashboards/` are validated offline by `make validate-dashboards` (SPEC-065 R-3): parse + envelope/panel schema + every metric reference resolves to an emitted OTEL stream.

## Conventions and constraints

- **GNU make required**: the root Makefile header states this explicitly and is used everywhere.
- **No `latest` tags**: `mk/defaults.mk` comments state pinned values are defaults for reproducible builds — never `latest`; `IMAGE_TAG` is computed from `VERSION` plus git SHA.
- **Product enumeration is explicit**: new products must be added to both `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` in the root `Makefile`; there is no auto-discovery loop.
- **Per-product Makefiles are thin**: they only set `IMAGE_NAME` (and optionally `IMAGE_CONTEXT` / `IMAGE_DOCKERFILE`) and include the shared fragments — no duplicate logic.
- **Python dependencies are frozen**: `uv sync --frozen` is used everywhere; `uv.lock` is the source of truth.
- **Tests disable OTLP export**: `mk/python.mk` sets `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` so tests remain deterministic without a backend.
- **Operator portal is excluded from `make test`**: SPEC-063 R-8c documents that the SPA is tested separately via `make portal-test`, which runs Vitest and the Vite production build; zero tests is a failure.
- **Samples are out-of-band from the base overlay**: SPEC-050 R-11 requires samples to be installed via `make deploy-samples` rather than being part of the base overlay, so `make deploy` never names a sample.
- **Secret provisioning is fail-closed**: deploy scripts document that missing secrets cause services to fail closed (e.g. `CREDENTIAL_SET_NOT_FOUND`, `audited signing_unavailable rejection`) rather than running open.
- **Image registry is opt-in**: `REGISTRY` defaults empty; when unset images are tagged only as `luban-aiops/<name>:<tag>` locally, and `make push` still pushes that local tag.
- **Kustomize overlays are verified at render time**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` for every overlay listed in `OVERLAYS`.
- **Coordinated tag propagation**: the root `make build` writes `.images.env` and also hardcodes the nine image names (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, etc.) consumed by the overlay — adding a product means updating both the loop and these echo lines.