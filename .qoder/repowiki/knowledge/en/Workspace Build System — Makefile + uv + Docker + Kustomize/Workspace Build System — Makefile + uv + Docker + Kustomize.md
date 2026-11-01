---
kind: build_system
name: Workspace Build System — Makefile + uv + Docker + Kustomize
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - VERSION
---

## Approach

The Luban AIOps workspace is built with a layered, forge-agnostic system:

1. **GNU Make** at the repository root orchestrates cross-cutting concerns (sync, test, lint, build, push, overlays, policy validation, dashboards, e2e).
2. **uv** is the Python dependency manager and runner; every product pins its dependencies in `pyproject.toml` + `uv.lock`, and builds use `uv sync --frozen`.
3. **Docker** builds container images for each product, all based on a shared `shared/base-images/base-uv` image (Amazon Linux 2023 minimal, pinned `uv` version, non-root `app` user uid 1000).
4. **Kustomize** renders GitOps overlays under `shared/platform-ops/gitops/` as part of verification (`make overlays`).
5. No CI workflow files are present in `.github/workflows`; the root `Makefile` is explicitly documented as "Forge-agnostic: `make verify` is the pre-commit/pre-push gate and runs the same checks locally and under any CI".

## Key Files

- `Makefile` — root orchestrator; defines `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, coordinated `IMAGE_TAG`, and targets `sync`, `test`, `lint`, `build`, `push`, `overlays`, `validate-dashboards`, `verify`, `deploy`, `e2e`.
- `mk/defaults.mk` — single source of truth for overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- `mk/image.mk` — shared `build` / `push` / `lint` targets for Docker images; requires the including Makefile to set `IMAGE_NAME`.
- `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled.
- `shared/base-images/base-uv/Dockerfile` — base image (AL2023-minimal, pinned `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, non-root `app`).
- Per-product `products/<name>/Makefile` — thin wrapper setting `IMAGE_NAME` and including `../../mk/image.mk` and `../../mk/python.mk`.
- Per-product `products/<name>/Dockerfile` — copies `.python-version pyproject.toml uv.lock src`, runs `uv sync --frozen --no-dev`, exposes port 8000, CMD `uv run <entrypoint>`.
- `VERSION` — single source of truth for the platform release semver; consumed by the root Makefile to compute `PLATFORM_VERSION` and enforced via `make validate-version`.
- `shared/shared-contracts/scripts/` — scripts invoked from the root Makefile for policy and contract validation (`validate_policy.py`, `validate_version.py`, `validate_secret_vocabulary.py`, `validate_password_policy.py`, `validate_policy_scenarios.py`, `policy_diff.py`).
- `shared/platform-ops/gitops/` — Kustomize overlays validated by `make overlays`.
- `shared/platform-ops/dashboards/validate_dashboards.py` — offline dashboard validation target (`make validate-dashboards`).

## Architecture and Conventions

### Coordinated image tagging
The root `Makefile` computes a single `IMAGE_TAG` once per invocation: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, or `...-dirty-<timestamp>` for dirty trees. All products are built with that tag, and the resulting image names are written to `shared/platform-ops/gitops/dev-k8s/.images.env` so `make deploy` uses the exact same artifacts.

### Product decomposition
Each product under `products/<name>/` is self-contained: it has its own `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, `Makefile`, and `tests/`. The root Makefile enumerates them in two lists:
- `PYTHON_PRODUCTS` — those with a `uv` test suite (`agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`).
- `IMAGE_PRODUCTS` — those producing a container image (adds `operator-portal`).

### Shared fragments
Cross-cutting logic lives in `mk/`: `defaults.mk` (config), `image.mk` (Docker targets), `python.mk` (uv targets). Product Makefiles include these fragments rather than duplicating logic.

### Base image strategy
All backend services derive from `luban-aiops/base-uv:al2023`, which installs a pinned `uv` binary, creates a non-root `app` user (uid 1000), and sets `UV_PYTHON` / `UV_PYTHON_INSTALL_DIR` so each product's `.python-version` resolves deterministically. The base image itself is built via `make base-images` with overridable `BASE_UV_UV_VERSION` and `BASE_UV_PYTHON_VERSION`.

### Policy and contract synchronization
Canonical policies live under `shared/shared-contracts/policies/` and are copied into consumers via `make sync-policy`. Contract validation scripts under `shared/shared-contracts/scripts/` enforce lockstep between `VERSION`, product versions, secret vocabulary, and password policy.

### Verification gate
`make verify` aggregates product tests, overlay rendering, dashboard validation, policy validation/scenarios, version lockstep, secret-vocabulary check, password-policy check, secret-delivery demo, portal SPA tests+build, audit contract test, delegated custody/runtime/multi-process/edge tests, and execution-failure test.

## Conventions and Constraints

- **Pinned Python toolchain**: Every product declares a `.python-version`; the base image pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` (in `mk/defaults.mk` and `shared/base-images/base-uv/Dockerfile`). Overrides go through `--build-arg` on `make base-images`.
- **Frozen dependency resolution**: All `uv sync` invocations use `--frozen`, enforcing that `uv.lock` is committed and not regenerated during builds.
- **Non-root containers**: The base image switches to `USER app` (uid 1000); product Dockerfiles inherit this.
- **No `latest` tags**: `mk/defaults.mk` comments state "Pinned values below are defaults for reproducible builds — never `latest`".
- **Coordinated tagging**: The root `Makefile` computes `IMAGE_TAG` once and passes it to every product build; `make build` writes the coordinated tag to `shared/platform-ops/gitops/dev-k8s/.images.env` consumed by `make deploy`.
- **Registry re-tagging**: When `REGISTRY` is set, `docker tag` produces a registry-prefixed ref before `docker push`; otherwise images stay local under `luban-aiops/<name>:<tag>`.
- **Kind auto-loading**: `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME=<name>` after `make build` loads all nine images into the named kind cluster.
- **Image platform override**: `IMAGE_PLATFORM ?= linux/amd64` supports `linux/arm64` for native local/kind builds on arm64 hosts.
- **Overlay validation**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` against every overlay listed in `OVERLAYS`.
- **Dashboard validation**: `make validate-dashboards` runs `shared/platform-ops/dashboards/validate_dashboards.py` to parse envelopes, panels, and metric references offline (SPEC-065 R-3).
- **Version lockstep**: `make validate-version` invokes `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file matches every product and portal version.
- **Secret vocabulary lockstep**: `make validate-secret-vocabulary` enforces alignment across `agent-platform`, `tool-gateway`, and `skills-hub`.
- **Password policy enforcement**: `make validate-password-policy` validates the canonical password policy and pins the connector floor to it (SPEC-062 R-2).
- **Portal coverage gap handled explicitly**: The root Makefile comment notes the operator-portal SPA is not a uv product; `make verify` calls `make -C products/operator-portal test` and `web-build` separately to run Vitest and the typechecked production build.
- **Forge-agnostic CI**: The root Makefile header states `make verify` is the pre-commit/pre-push gate intended to run identically locally and under any CI; no GitHub Actions workflows exist in the repo.