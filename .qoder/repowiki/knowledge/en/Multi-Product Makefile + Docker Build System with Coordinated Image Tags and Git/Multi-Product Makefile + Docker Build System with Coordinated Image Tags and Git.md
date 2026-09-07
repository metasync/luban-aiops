---
kind: build_system
name: Multi-Product Makefile + Docker Build System with Coordinated Image Tags and GitOps Deployment
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
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
---

## What system/approach is used

The repository uses a **GNU Make-driven multi-product build system** layered over per-product `Dockerfile`s, with a shared fragment library under `mk/` that standardizes image builds, Python dependency/test runs, and linting. There are no CI workflow files in `.github/workflows`; the root `Makefile` defines a single `verify` gate intended to run identically locally and in any CI environment (the comment states it is "forge-agnostic" and requires GNU make). Deployment is GitOps-based via Kustomize overlays under `shared/platform-ops/gitops`, orchestrated by a top-level `make deploy` that delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which in turn calls a series of secret-sync scripts before applying the overlay.

## Key files and packages

- **Root orchestrator**: `Makefile` — declares product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), computes a coordinated `IMAGE_TAG` from `VERSION` plus git SHA/dirty flag, dispatches per-product `build`/`test`/`lint`, renders Kustomize overlays, validates policy bundles and version lockstep, and drives e2e demo scripts.
- **Shared fragments**:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, etc.) using `?=` so command-line overrides always win; guarded against double inclusion.
  - `mk/image.mk` — provides `build`/`push`/`lint` targets for any product that sets `IMAGE_NAME` (and optionally `IMAGE_CONTEXT`/`IMAGE_DOCKERFILE`). Uses `docker build --platform $(IMAGE_PLATFORM)` and conditionally re-tags/pushes when `REGISTRY` is set.
  - `mk/python.mk` — provides `sync` and `test` targets that run `uv sync --frozen` then `uv run pytest` with OTel exporters disabled so tracing tests can stay active without OTLP noise.
- **Per-product Makefiles** — minimal stubs that only set `IMAGE_NAME` and include the two fragments (e.g. `products/agent-platform/Makefile`, `products/operator-portal/Makefile`). The operator portal additionally overrides `IMAGE_CONTEXT := ../..` and `IMAGE_DOCKERFILE := Dockerfile` because its multi-stage Dockerfile needs the repo-root `VERSION` file and the Vite project at `web-ui/app`.
- **Base image**: `shared/base-images/base-uv/Dockerfile` built by `make base-images`, pinned to `BASE_UV_PYTHON_VERSION=3.12` and `BASE_UV_UV_VERSION=0.12.1`.
- **Deployment scripts**: `shared/platform-ops/gitops/dev-k8s/deploy.sh` applies the overlay and sequentially provisions secrets (delegation, audit, execution signing/handoff, skills, incidents, browser credentials, sessions DB, OTel) before reconciling the Keycloak realm and portal OIDC client.
- **Version file**: `VERSION` (currently `0.35.0`) is the single source of truth; the root Makefile reads it into `PLATFORM_VERSION` and the `validate-version` target enforces lockstep across products and the portal.

## Architecture and conventions

- **Coordinated tagging**: All images share one tag computed as `<semver>-<prefix>[-<profile>]-<gitsha>` (or `<prefix>-dirty-<timestamp>` on dirty trees). The root `make build` writes an `.images.env` state file listing every product image reference so `make deploy` consumes a consistent set.
- **Product taxonomy**: Products are classified into two lists — `PYTHON_PRODUCTS` (get `sync`+`test` via `uv`) and `IMAGE_PRODUCTS` (get `build`+`push`+`lint` via Docker). A product can appear in both (most do); `operator-portal` appears only in `IMAGE_PRODUCTS` because it has no Python test suite.
- **Fragment composition**: Product Makefiles are intentionally tiny — they declare `IMAGE_NAME` and `include ../../mk/image.mk` (plus `../../mk/python.mk` if applicable). All logic lives in `mk/`. This keeps new product onboarding to three lines.
- **Python toolchain**: Every Python product uses `uv` with a frozen lockfile (`uv sync --frozen`); there is no pip or Poetry usage. Tests run with `pytest` invoked through `uv run`.
- **Policy bundling**: A canonical policy YAML lives in `shared/shared-contracts/policies/policy-default.yaml` and is copied to each consumer (`products/tool-gateway/...`, `products/platform-gateway/...`, `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`) via `make sync-policy`. Validation and diff tools live under `shared/shared-contracts/scripts/`.
- **Secret provisioning pattern**: Each sensitive integration has a dedicated `sync-*.sh` script under `shared/platform-ops/gitops/` that is idempotent and skip-able via `SKIP_*_SECRETS=true` (for CI environments where secrets are injected externally).
- **Local dev acceleration**: `AUTO_LOAD_KIND=true` after `make build` auto-loads all images into a kind cluster named by `KIND_CLUSTER_NAME`; `make e2e` runs scripted demos against the deployed cluster.

## Conventions and constraints

- **Single entry point**: `make verify` is the pre-commit/pre-push gate; it runs `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, and `validate-secret-vocabulary` in sequence. All checks must pass for a change to be considered verified.
- **Pinned base versions**: Base image tags and tool versions are explicitly pinned in `mk/defaults.mk` (`al2023`, `0.12.1`, `3.12`) — the comments explicitly say "never `latest`" for reproducible builds.
- **Platform override**: `IMAGE_PLATFORM ?= linux/amd64` is the default but can be overridden per-invocation (e.g. `linux/arm64` for native local/kind builds on arm64 hosts).
- **Registry push gating**: `make push` only pushes when `REGISTRY` is set; otherwise images remain local under the `luban-aiops/` namespace. Tagging for push happens inside `mk/image.mk` based on whether `REGISTRY` is non-empty.
- **Version lockstep**: `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root to enforce that `VERSION`, each product's declared version, and the portal are synchronized.
- **Secret vocabulary validation**: `make validate-secret-vocabulary` ensures redaction vocabularies between `agent-platform` and `tool-gateway` stay in lockstep.
- **Overlay validation**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` against every overlay listed in `OVERLAYS` (`dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`); failures abort the verification gate.
- **No CI workflows checked in**: No GitHub Actions workflow files were found under `.github/`; the design intent (per the root Makefile header) is that the same `make verify` pipeline runs in any forge.