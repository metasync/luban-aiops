---
kind: build_system
name: 'Monorepo Build System: Root Makefile, Shared Fragments, and Coordinated Image/Version Policy'
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - VERSION
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - products/platform-gateway/Makefile
    - products/operator-portal/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
---

## What system/approach is used

The repository uses a **GNU Make-driven monorepo build** centered on a root `Makefile` that delegates per-product routines to individual product Makefiles under `products/<name>/`. Cross-cutting concerns (image building, Python dependency sync, testing, policy validation, version lockstep, GitOps overlay rendering, and e2e demos) are implemented as shared fragments in `mk/` (`defaults.mk`, `image.mk`, `python.mk`) and invoked from the root. Container images are built with Docker using per-product `Dockerfile`s, and deployment targets a Kustomize-based GitOps overlay under `shared/platform-ops/gitops/dev-k8s/`. There is no CI pipeline file in `.github/workflows`; the documented pre-commit/pre-push gate is `make verify`.

## Key files and packages

- `Makefile` — master entry point; defines product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), coordinated image tag computation, `build`/`push`/`deploy`/`verify`/`overlays`/`e2e` targets, and policy/version gates.
- `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- `mk/image.mk` — shared `build`/`push`/`lint` targets for container images; resolves `IMAGE_REF` against `luban-aiops/` registry or an optional `REGISTRY` override.
- `mk/python.mk` — shared `sync`/`test` targets using `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled so tracing tests pass without backends.
- `VERSION` — single source of truth for platform semver; read by the root Makefile and enforced by `validate_version.py`.
- `shared/shared-contracts/scripts/validate_version.py` — enforces that every product's `pyproject.toml` `[project] version`, `src/*/metadata.py` `SERVICE_VERSION`, any `__version__`, and the operator portal's Vite wiring all match `VERSION`.
- `shared/shared-contracts/scripts/validate_policy.py` — validates the canonical `policy-default.yaml` against `policy-rule.schema.json` (Draft 2020-12), forbids duplicate rule ids, and requires `version == 1`.
- Per-product `Makefile` (e.g. `products/platform-gateway/Makefile`) — only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`.
- `products/operator-portal/Dockerfile` — multi-stage Node+nginx build that copies the repo-root `VERSION` into the build context so `vite.config.ts` can inject `PLATFORM_VERSION` at build time.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — wrapper invoked by `make deploy`.

## Architecture and conventions

### Product model
Each service lives under `products/<name>/` with a uniform layout: `src/<package>/`, `tests/`, `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, and a thin `Makefile` that just declares `IMAGE_NAME` and includes the shared fragments. This lets `make -C products/<name>` work standalone while still honoring root-level defaults.

### Image naming and tagging
- Default local image reference: `luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>`.
- When `REGISTRY` is set, images are re-tagged to `<REGISTRY>/luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>` before push.
- The root `make build` computes a coordinated `IMAGE_TAG` once: `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` if the working tree has uncommitted changes). It then builds every `IMAGE_PRODUCT`, writes the tag plus all eight product image names into `shared/platform-ops/gitops/dev-k8s/.images.env`, and optionally loads them into a kind cluster when `AUTO_LOAD_KIND=true`.
- Base image `luban-aiops/base-uv:<tag>` is built from `shared/base-images/base-uv/Dockerfile` with pinned `UV_VERSION` and `PYTHON_VERSION` defaults.

### Versioning strategy
`VERSION` is the single source of truth. The `make validate-version` target runs `validate_version.py`, which:
- Parses `VERSION` and rejects non-semver values.
- Scans every `products/*/pyproject.toml` for `[project].version`.
- Scans each product's `src/*/metadata.py` for `SERVICE_VERSION = "..."`.
- Scans package roots for `__version__` where present.
- Asserts the operator portal's `vite.config.ts` contains the specific patterns that read the repo-root `VERSION` and define `__PLATFORM_VERSION__` at build time.
Any drift causes failure.

### Policy management
A canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml`. `make sync-policy` copies it to the two consumer services (`tool-gateway`, `platform-gateway`) and the deployed Kubernetes base overlay. `make validate-policy` runs `validate_policy.py` against `policy-rule.schema.json`.

### Verification gate
`make verify` composes `test` + `overlays` + `validate-policy` + `validate-version`. The root Makefile comment states this is intended as the pre-commit/pre-push gate and must run identically locally and in CI.

### Deployment
`make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which renders the dev-k8s Kustomize overlay. E2E scripts under `shared/platform-ops/e2e/` are executed via `make e2e` after port-forwarding the gateway and identity services.

## Conventions and constraints

- **Per-product Makefiles are minimal**: they only set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`. All logic lives in `mk/`.
- **Dependency resolution is frozen**: `uv sync --frozen` is used everywhere, pinning to `uv.lock`.
- **Python test isolation**: OTEL exporters are explicitly set to `none` during `uv run pytest` so tracing tests run without live backends.
- **Image platforms default to `linux/amd64`**; `linux/arm64` is supported via `IMAGE_PLATFORM` for native kind builds.
- **Registry pushes require `REGISTRY` to be set**; otherwise images stay local under `luban-aiops/`.
- **Policy bundles must have `version == 1`** and unique rule ids; validated by schema against Draft 2020-12.
- **Portal SPA build context is the repo root** so `vite.config.ts` can resolve `../../../../VERSION`; the Dockerfile mirrors the in-repo layout to make that path valid.
- **No CI workflow files exist** in `.github/`; the documented gate is `make verify`.
- **Overlays are checked declaratively**: `kustomize build` is run against every overlay listed in `OVERLAYS` during verification.