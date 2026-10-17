---
kind: build_system
name: Luban Platform Build System — Makefile + Docker + uv Monorepo Orchestration
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
    - products/platform-gateway/Dockerfile
    - products/operator-portal/Makefile
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

# Build & Artifact Management

## Approach

The Luban platform is a Python/Node monorepo orchestrated by **GNU make** at the workspace root, with per-product `Makefile`s delegating to shared fragments under `mk/`. Container images are built with **Docker**, Python dependencies are managed via **uv** (frozen lockfiles), and Kubernetes manifests are rendered through **kustomize**. There is no CI pipeline file in this checkout; the root `Makefile` is explicitly forge-agnostic and intended as the pre-commit/pre-push gate (`make verify`) that runs identically locally and in any CI.

## Key Files

| File | Role |
|---|---|
| `Makefile` | Root orchestrator: product loops, coordinated image tagging, policy/dashboard/version validation, e2e/demo targets, deploy wrapper |
| `mk/defaults.mk` | Single source of overridable build settings (`IMAGE_PLATFORM`, `BASE_UV_*`, `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`) |
| `mk/image.mk` | Shared `build` / `push` / `lint` targets for every product's Dockerfile |
| `mk/python.mk` | Shared `sync` / `test` targets using `uv sync --frozen` and `pytest` |
| `VERSION` | Single source of truth for the platform release semver |
| `products/<product>/Makefile` | Thin product shim declaring `IMAGE_NAME` and including `../../mk/image.mk` and `../../mk/python.mk` |
| `products/<product>/Dockerfile` | Per-service container definition based on `luban-aiops/base-uv:<tag>` |
| `shared/platform-ops/gitops/` | Kustomize overlays validated by `make overlays` |
| `shared/platform-ops/dashboards/` | OpenObserve dashboard JSON validated offline by `make validate-dashboards` |
| `shared/shared-contracts/scripts/` | Policy, version, secret-vocabulary, password-policy validators invoked from the root Makefile |
| `products/operator-portal/Makefile` | Non-Python product: npm-based Vitest suite + Vite production build |

## Architecture

### Product decomposition

Each service under `products/` follows an identical layout:

```
products/<name>/
├── src/<package_name>/
├── tests/
├── .python-version
├── Dockerfile
├── Makefile          # declares IMAGE_NAME, includes mk/image.mk + mk/python.mk
├── pyproject.toml
└── uv.lock
```

The root `Makefile` enumerates two lists:
- `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`
- `IMAGE_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway operator-portal`

Every loop target (`sync`, `test`, `lint`, `build`, `push`) iterates these lists and invokes `$(MAKE) -C products/$$p <target>`, so adding a new product means registering it in one place.

### Coordinated image tagging

All images share one tag computed once by the root Makefile:

```
<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]
```

- Semver comes from `VERSION`.
- Prefix/profile come from `IMAGE_TAG_PREFIX` / `IMAGE_TAG_PROFILE` (default `dev-k8s`).
- A dirty working tree appends `-dirty-YYYYMMDDHHMMSS`.
- The resulting tag is written into `shared/platform-ops/gitops/dev-k8s/.images.env` alongside per-image variables (`AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`, …) consumed by the GitOps deploy script.

### Base image strategy

Python services all derive from a single shared base image built by `make base-images` from `shared/base-images/base-uv/Dockerfile`, parameterized by `BASE_UV_IMAGE`, `BASE_UV_TAG`, `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION` (defaults: `al2023`, uv `0.12.1`, Python `3.12`). Production Dockerfiles run `uv sync --frozen --no-dev`; development/test flows use `uv sync --frozen` without `--no-dev`.

### Verification gate

`make verify` composes the full pre-commit/pre-push contract:

```
test overlays validate-dashboards validate-policy validate-policy-scenarios \
  validate-version validate-secret-vocabulary validate-password-policy \
  secret-delivery-demo portal-test execution-failure-test
```

This covers: per-product pytest suites, kustomize overlay rendering, offline dashboard schema/metric-reference validation, canonical policy bundle validation against its JSON schema, scenario evaluation against both engines, VERSION lockstep across products and portal, secret-literal vocabulary lockstep, password-policy enforcement, local secret-handoff demo, operator-portal Vitest + Vite production build, and a crash-safety failure test.

### Operator portal exception

The operator portal is a Next.js/Vite SPA served by nginx. It has no Python/uv suite; its `Makefile` exposes `test` (npm Vitest) and `web-build` (npm `tsc --noEmit && vite build`), which the root `verify` target calls via `make -C products/operator-portal test` and `make -C products/operator-portal web-build`. Its Dockerfile uses the repo-root as `IMAGE_CONTEXT` so it can read `VERSION` and the Vite project lives at `web-ui/app`.

### Deployment

- `make deploy` delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`.
- `make deploy-samples` / `undeploy-samples` install/remove tutorial skills out-of-band (SPEC-050 R-11 keeps samples out of the base overlay).
- `make deploy-sample-app` builds and deploys the acme-admin sample application separately.
- `make e2e` runs the scripted demos in `shared/platform-ops/e2e/` against a deployed cluster requiring port-forwards to `platform-gateway:18083` and `identity-service:18081`.
- `make push` re-tags and pushes every product image when `REGISTRY` is set.

## Conventions and Constraints

1. **Single source of truth for versions**: `VERSION` holds the platform semver; `make validate-version` enforces lockstep between it, every product's metadata, and the portal. Source: root `Makefile` `validate-version` target and `shared/shared-contracts/scripts/validate_version.py`.

2. **Frozen dependency resolution**: All Python products use `uv sync --frozen` (both dev and prod paths). No `pip install` or editable installs in build paths. Source: `mk/python.mk`, every product Dockerfile.

3. **No `latest` tags**: `mk/defaults.mk` documents pinned defaults for reproducible builds — `BASE_UV_TAG ?= al2023`, `BASE_UV_UV_VERSION ?= 0.12.1`, `BASE_UV_PYTHON_VERSION ?= 3.12` — and explicitly states "never `latest`".

4. **Image naming convention**: Images are tagged `luban-aiops/<image-name>:<tag>`, optionally prefixed by `REGISTRY/` when set. Source: `mk/image.mk` lines 26–30.

5. **Coordinated tagging**: `make build` computes one `IMAGE_TAG` and writes it plus per-image env vars into `shared/platform-ops/gitops/dev-k8s/.images.env`; `make deploy` reads that state. Source: root `Makefile` lines 55–68 and 100–113.

6. **Policy bundles are canonical**: `shared/shared-contracts/policies/policy-default.yaml` is the single authoring location; `make sync-policy` copies it to `products/tool-gateway`, `products/platform-gateway`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`. Source: root `Makefile` `POLICY_TARGETS` / `sync-policy`.

7. **Password policy floor**: SPEC-062 R-2 pins the connector floor to `shared/shared-contracts/policies/password-policy.yaml`; `make validate-password-policy` enforces it. Source: root `Makefile` `PASSWORD_POLICY_CANONICAL` / `validate-password-policy`.

8. **Secret vocabulary lockstep**: `make validate-secret-vocabulary` validates literal secret declarations across `agent-platform`, `tool-gateway`, and `skills-hub`. Source: root `Makefile` `validate-secret-vocabulary`.

9. **Dashboard validation is offline**: `make validate-dashboards` parses OpenObserve dashboard JSON, validates envelope/panel schemas, and verifies every metric reference resolves to an emitted `OTEL_MIRROR_FAMILIES` stream — no cluster required. Source: root `Makefile` `validate-dashboards` and `shared/platform-ops/dashboards/validate_dashboards.py`.

10. **Portal tests cannot be skipped**: SPEC-063 R-8c requires the operator-portal Vitest suite to run and fail on zero tests; there is no skip toggle accepted as a release pass. Source: root `Makefile` comment on line 223–227 and `products/operator-portal/Makefile` comment.

11. **Kind auto-loading is opt-in**: `AUTO_LOAD_KIND=true` requires `KIND_CLUSTER_NAME` to be set; otherwise `make build` refuses to load images. Source: root `Makefile` lines 114–128.

12. **Forge-agnostic CI contract**: The root `Makefile` header states `make verify` is the pre-commit/pre-push gate and runs the same checks locally and under any CI. No `.github/workflows/` files exist in this checkout. Source: root `Makefile` header comment lines 8–10.