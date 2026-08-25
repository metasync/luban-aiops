---
kind: build_system
name: 'Monorepo Build System: Root Makefile, Shared Fragments, and Coordinated Image Pipeline'
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
    - shared/shared-contracts/scripts/validate_version.py
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - products/platform-gateway/Makefile
    - products/operator-portal/Makefile
---

## What system/approach is used

The repository uses a **GNU Make-driven monorepo build system** centered on a root `Makefile` that orchestrates per-product builds via shared fragments under `mk/`. Python products are built with `uv` (frozen lockfiles), container images are produced with Docker, and Kubernetes deployment is GitOps-based using Kustomize overlays. There is no CI pipeline file in `.github/workflows`; the `make verify` target (`test + overlays + validate-policy + validate-version`) is intended as the pre-commit/pre-push gate.

## Key files and packages

- **Root orchestration**: `Makefile` — defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), computes coordinated `IMAGE_TAG`, delegates to per-product Makefiles, runs policy sync/validation, version validation, overlay rendering, deploy, and e2e demos.
- **Shared build fragments**:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `IMAGE_TAG_PROFILE`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`).
  - `mk/image.mk` — shared `build` / `push` / `lint` targets for Docker images; resolves `IMAGE_REF` against `luban-aiops/` registry or an optional `REGISTRY` override.
  - `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and pytest with OTLP exporters disabled.
- **Per-product Makefiles** — minimal stubs that set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk` (e.g. `products/platform-gateway/Makefile`, `products/operator-portal/Makefile`).
- **Base image**: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal with pinned `uv` (0.12.1) and Python 3.12, running as non-root `app` user.
- **Version lockstep enforcement**: `VERSION` (single semver source), `shared/shared-contracts/scripts/validate_version.py` (checks `VERSION` against every `products/*/pyproject.toml`, `src/*/metadata.py` `SERVICE_VERSION`, `__version__`, and operator-portal Vite wiring).
- **Policy sync**: `sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into `tool-gateway`, `platform-gateway`, and the deployed base overlay.
- **Deployment**: `shared/platform-ops/gitops/dev-k8s/deploy.sh` wraps `deploy-overlay.sh` plus secret provisioning scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-sessions-db.sh`, `sync-otel-secrets.sh`, `reconcile-luban-realm.sh`, `reconcile-portal-oidc-client.sh`).
- **Kustomize overlays**: `shared/platform-ops/gitops/dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev` — validated by `make overlays` via `kustomize build --load-restrictor LoadRestrictionsNone`.

## Architecture and conventions

1. **Two-level Makefile design**: The root `Makefile` owns cross-cutting concerns (coordinated tagging, policy sync, version validation, overlay checks, deploy, e2e). Each product has a tiny Makefile that only declares `IMAGE_NAME` and includes the shared fragments. This lets you run `make -C products/<name>` standalone or `make test` / `make build` from the repo root.
2. **Coordinated image tagging**: `IMAGE_TAG` is computed once at the root as `<semver>-<prefix>[-<profile>]-<gitsha>` (dirty builds append `-dirty-<timestamp>`). All product images share this tag, and `make build` writes them into `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy script references a single consistent image set.
3. **Registry abstraction**: Images are always tagged locally as `luban-aiops/<name>:<tag>`; setting `REGISTRY` re-tags and pushes to `$(REGISTRY)/luban-aiops/<name>:<tag>`. The default registry is local-only.
4. **Multi-stage portal build**: The operator-portal sets `IMAGE_CONTEXT := ../..` and `IMAGE_DOCKFILE := Dockerfile` so its multi-stage Dockerfile can read the root `VERSION` file and the `web-ui/app` Vite project together.
5. **Python dependency management**: Every Python product uses `uv` with a frozen `uv.lock` (`uv sync --frozen`). The base image pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`; `UV_PYTHON_INSTALL_DIR=/app/.python` isolates per-product interpreters.
6. **GitOps-first deployment**: `make deploy` calls `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders the Kustomize overlay and provisions secrets via helper scripts. Overlays are validated during `make verify`.
7. **Kind integration**: Setting `AUTO_LOAD_KIND=true` (with `KIND_CLUSTER_NAME`) after `make build` auto-loads all images into the named kind cluster.

## Conventions and constraints

- **Single source of truth for version**: `VERSION` must be a valid `MAJOR.MINOR.PATCH` semver string. `make validate-version` enforces that every product's `pyproject.toml` `[project] version`, each `src/*/metadata.py` `SERVICE_VERSION`, any `__version__` in package roots, and the operator-portal's Vite build-time `PLATFORM_VERSION` wiring all match it. Drift causes failure.
- **Image platform pinning**: Default `IMAGE_PLATFORM = linux/amd64`; overrides propagate through both root and per-product builds. The base image is also built with the same platform.
- **Policy bundle synchronization**: The canonical policy lives in `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to `tool-gateway`, `platform-gateway`, and the deployed base overlay; `make validate-policy` validates it against the JSON schema via `shared/shared-contracts/scripts/validate_policy.py`.
- **Verification gate**: `make verify` runs `test` (all Python products), `overlays` (kustomize build check), `validate-policy`, and `validate-version`. It is documented as the pre-commit/pre-push gate.
- **Secret provisioning flags**: Deploy scripts honor `SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_SKILLS_SECRETS`, `SKIP_INCIDENT_SECRETS`, `SKIP_OTEL_SECRETS`, and `RECONCILE_OIDC_PORTAL_CLIENT` to allow CI environments to skip external secret injection.
- **E2E demo flow**: `make e2e` requires `make deploy` first and expects port-forwards for `platform-gateway` (18083) and `identity-service` (18081); it runs `skills-demo.sh`, `incident-demo.sh`, and `mutating-demo.sh` sequentially.
- **No CI workflow files present**: No GitHub Actions workflows were found under `.github/workflows`; the build system relies on `make verify` being executed by whatever CI provider is configured externally.