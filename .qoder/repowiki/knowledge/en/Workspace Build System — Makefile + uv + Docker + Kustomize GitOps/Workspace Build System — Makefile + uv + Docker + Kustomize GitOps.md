---
kind: build_system
name: Workspace Build System — Makefile + uv + Docker + Kustomize GitOps
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/python.mk
    - mk/image.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - products/operator-portal/Makefile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - VERSION
---

# Build & Artifact Management

## Approach

The Luban workspace is a monorepo built with **GNU make** as the top-level orchestrator, **uv** for Python dependency resolution and test execution, **Docker** for container images, and **kustomize** for Kubernetes overlay rendering. There is no CI workflow file committed to the repo; the root `Makefile` is explicitly designed as the forge-agnostic gate (`make verify`) intended to run identically locally and under any CI.

## Top-level orchestration

- `Makefile` (root) declares the product lists: `PYTHON_PRODUCTS` (8 Python services) and `IMAGE_PRODUCTS` (9 products including `operator-portal`).
- It delegates per-product work via `$(MAKE) -C products/<name>` and owns cross-cutting concerns: GitOps overlay validation, policy sync/validation, dashboard validation, portal SPA build, secret-delivery demo, and execution failure tests.
- The single verification target `verify` chains: `test overlays validate-dashboards validate-policy validate-policy-scenarios validate-version validate-secret-vocabulary validate-password-policy secret-delivery-demo portal-test execution-failure-test`.
- Image tagging is coordinated: `IMAGE_TAG` is computed once from `VERSION` plus optional prefix/profile/git SHA/dirty timestamp, then written into `shared/platform-ops/gitops/dev-k8s/.images.env` so all overlays consume the same tag.
- `make deploy` wraps `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders the overlay and provisions secrets (OIDC client, audit trail, execution signing/handoff, skills, incident, browser, Ansible MCP, OTel) before reconciling the Keycloak realm and portal OIDC client.

## Shared fragments (`mk/`)

- `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`, `REGISTRY`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, `BASE_UV_IMAGE`, `BASE_UV_TAG`, `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`). All values use `?=`, so command-line overrides always win. Guarded against double inclusion via `LUBAN_DEFAULTS_INCLUDED`.
- `mk/python.mk` — shared `sync` / `test` targets for Python products. `sync` runs `uv sync --frozen`; `test` re-syncs frozen deps then runs `pytest` with OTEL exporters disabled (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) to keep test output clean while keeping the SDK active for tracing tests.
- `mk/image.mk` — shared `build` / `push` / `lint` targets. `build` runs `docker build --platform $(IMAGE_PLATFORM)` producing `luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>`; if `REGISTRY` is set it additionally tags/pushes `<REGISTRY>/luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>`. `lint` prefers `hadolint` when available, falls back to `docker run hadolint/hadolint`, and skips gracefully otherwise.

## Per-product layout

Each product under `products/<name>/` has an identical skeleton:

```
Makefile          # sets IMAGE_NAME, includes mk/image.mk and mk/python.mk
Dockerfile        # FROM luban-aiops/base-uv:al2023, COPY src + pyproject.toml + uv.lock, RUN uv sync --frozen --no-dev
pyproject.toml    # project metadata + dependencies
uv.lock           # pinned lockfile
.python-version   # interpreter pin
src/<package>/    # application code
tests/            # pytest suite
README.md
```

The only exception is `operator-portal`, which is a Node SPA served by nginx: its `Makefile` adds `test` (npm Vitest) and `web-build` (tsc + vite build), sets `IMAGE_CONTEXT := ../..` and `IMAGE_DOCKERFILE := Dockerfile` because the multi-stage Dockerfile needs the root `VERSION` file and the Vite project.

## Base image strategy

`shared/base-images/base-uv/Dockerfile` builds `luban-aiops/base-uv:al2023` on Amazon Linux 2023 minimal with a pinned `uv` (default `0.12.1`) and no system Python. Each product's `.python-version` pins the interpreter resolved at runtime by `uv`. The image runs as non-root user `app` (uid 1000). Product Dockerfiles layer on top with `COPY --chown=app:app .python-version pyproject.toml uv.lock README.md ./` and `RUN uv sync --frozen --no-dev`.

## Versioning

- Single source of truth: root `VERSION` file (currently `0.47.0`).
- `PLATFORM_VERSION` is read from `VERSION` and used in coordinated image tags.
- `make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` to enforce that every product version stays in lockstep with `VERSION`.
- Coordinated image tag format: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, `<semver>-<prefix>[-<profile>]-<gitsha>-dirty-<timestamp>` for dirty trees.

## Policy & contract tooling

- Canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`; `make sync-policy` copies it to `products/tool-gateway`, `products/platform-gateway`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.
- Password policy contract at `shared/shared-contracts/policies/password-policy.yaml` is synced to `products/tool-gateway/src/tool_gateway/policies/password-policy.yaml`.
- Validation scripts live under `shared/shared-contracts/scripts/`: `validate_policy.py`, `validate_policy_scenarios.py`, `policy_diff.py`, `validate_version.py`, `validate_secret_vocabulary.py`, `validate_password_policy.py`.
- Secret vocabulary lockstep between `agent-platform`, `tool-gateway`, and `skills-hub` is enforced by `make validate-secret-vocabulary`.

## GitOps & deployment

- Overlays under `shared/platform-ops/gitops/` are validated by `make overlays` via `kustomize build --load-restrictor LoadRestrictionsNone`.
- OpenObserve dashboards under `shared/platform-ops/dashboards/` are validated offline by `make validate-dashboards` using `validate_dashboards.py` (SPEC-065 R-3).
- `make e2e` runs the demo scripts under `shared/platform-ops/e2e/` against a deployed cluster (requires port-forwards for platform-gateway and identity-service).
- `make deploy-sample-app` / `deploy-samples` / `undeploy-samples` manage tutorial samples out-of-band from the base overlay (per SPEC-050 R-11).

## Conventions observed

- Every Python product uses `uv sync --frozen` (never `pip install` or editable installs) for reproducible builds and tests.
- Container images are tagged with a coordinated `IMAGE_TAG` derived from `VERSION`, not per-product versions.
- Dockerfiles inherit from `luban-aiops/base-uv:al2023` and copy only `src`, `pyproject.toml`, `uv.lock`, and `.python-version`.
- Tests disable OTEL network exporters (`OTEL_TRACES_EXPORTER=none`, etc.) to avoid noise during local/test runs.
- The operator-portal SPA is excluded from `make test` and exercised through `make portal-test`, which runs both Vitest and the production build (SPEC-063 R-8c).
- `make verify` is the canonical pre-commit/pre-push gate combining product tests, policy validation, overlay rendering, dashboard validation, portal build, secret-delivery demo, and execution failure proof.
- `IMAGE_PLATFORM` defaults to `linux/amd64` but can be overridden (e.g. `linux/arm64` for native kind builds); `AUTO_LOAD_KIND=true` auto-loads images into a named kind cluster after `make build`.

## Not present

No GitHub Actions workflows, CircleCI config, Jenkinsfile, or other CI pipeline files are committed to the repository. The author guidelines do not exclude this category, so the absence of CI configuration is noted descriptively rather than claimed as a rule.