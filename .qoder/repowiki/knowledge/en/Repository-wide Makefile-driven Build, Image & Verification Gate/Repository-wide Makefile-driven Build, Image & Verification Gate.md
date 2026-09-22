---
kind: build_system
name: Repository-wide Makefile-driven Build, Image & Verification Gate
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
    - shared/base-images/base-uv/Dockerfile
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
---

## What system/approach is used

The repository uses a **Makefile-centric, forge-agnostic build system** built on GNU make. There are no CI workflow files in the repo; instead, `make verify` is documented as the pre-commit/pre-push gate and runs identically locally and under any CI. Python products use **uv** (with frozen lockfiles) for dependency resolution and test execution. Container images are built with **Docker**, orchestrated through shared Makefile fragments under `mk/`. GitOps overlays under `shared/platform-ops/gitops` are validated via `kustomize build`. Policy bundles are centrally managed and synced to consumers.

## Key files and packages

- Root orchestrator: `Makefile` — defines product lists, coordinated image tagging, verification gate (`verify`), deploy/e2e targets, policy sync/validation, version validation, overlay rendering.
- Shared configuration: `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- Shared image fragment: `mk/image.mk` — provides `build`, `push`, `lint` targets for each product Dockerfile; computes `IMAGE_REF` from `IMAGE_NAME` + `IMAGE_TAG` + optional `REGISTRY`; supports hadolint via binary or docker-run fallback.
- Shared Python fragment: `mk/python.mk` — provides `sync` (`uv sync --frozen`) and `test` (runs pytest with OTLP exporters disabled so tracing tests stay functional).
- Product Makefiles (minimal): e.g. `products/agent-platform/Makefile` sets `IMAGE_NAME := agent-service` and includes both fragments; every product under `products/` follows this pattern.
- Product Dockerfiles: thin multi-stage-style images based on `luban-aiops/base-uv:al2023`, copy `.python-version`, `pyproject.toml`, `uv.lock`, `src`, run `uv sync --frozen --no-dev`, expose port 8000, `CMD ["uv", "run", "<entrypoint>"]`.
- Base image definition: `shared/base-images/base-uv/Dockerfile` (built by `make base-images`).
- Version file: `VERSION` (semver, currently `0.40.0`) — single source of truth for platform release version.
- Policy sync targets reference `shared/shared-contracts/policies/policy-default.yaml` as canonical and copy it into `platform-gateway`, `tool-gateway`, and `dev-k8s/base/shared/policy.yaml`.
- E2E scripts: `shared/platform-ops/e2e/*.sh` invoked by `make e2e` against a deployed cluster.

## Architecture and conventions

1. **Two-level Makefile hierarchy.** The root `Makefile` declares lists of `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS`, then loops over them calling `$(MAKE) -C products/<name> <target>`. Each product Makefile is a one-liner that sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. This keeps product code free of build logic.

2. **Coordinated image tagging.** The root computes a single `IMAGE_TAG` once per invocation using the formula `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` for dirty trees). All images are built with that tag, then an `.images.env` state file is written at `shared/platform-ops/gitops/dev-k8s/.images.env` containing all nine service image references plus `WEB_UI_IMAGE`. `make deploy` reads this file to install the matching set.

3. **Reproducible base image.** `make base-images` builds `shared/base-images/base-uv` with pinned `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12` (from `mk/defaults.mk`). All product images `FROM luban-aiops/base-uv:al2023`, ensuring identical toolchains.

4. **Frozen uv environments.** Every product pins dependencies via `uv.lock`; `sync` and `test` always run `uv sync --frozen`. Production images also run `uv sync --frozen --no-dev`.

5. **Policy-as-code lifecycle.** A single canonical policy YAML lives in `shared/shared-contracts/policies/`. `make sync-policy` copies it to all consumers. `make validate-policy` validates against a JSON schema; `make validate-policy-scenarios` evaluates scenario expectations against both the API and tools engines; `make policy-diff` compares a candidate bundle to canonical.

6. **Version lockstep enforcement.** `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to assert that the root `VERSION`, every product's declared version, and the portal are in lockstep.

7. **Secret vocabulary lockstep.** `make validate-secret-vocabulary` asserts that secret literal declarations across `agent-platform`, `tool-gateway`, and `skills-hub` match.

8. **GitOps overlay validation.** `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` over `dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, and `runtime-profiles/browser-dev`.

9. **Verification gate.** `make verify` chains `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, and `validate-secret-vocabulary` — intended as the single pre-commit/pre-push entry point.

10. **Kind integration.** When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all built images into the named kind cluster after building.

## Conventions and constraints

- **Every product must declare `IMAGE_NAME` and include both `../../mk/image.mk` and `../../mk/python.mk`** in its own `Makefile` to participate in root-level `build`, `test`, `lint`, `push`, and `help` targets.
- **Python products must have a `pyproject.toml` and `uv.lock`**; `uv sync --frozen` is the only supported dependency resolution mode — no editable installs or non-frozen syncs in build/test paths.
- **Images must be based on `luban-aiops/base-uv:al2023`** and follow the template: copy `.python-version`, `pyproject.toml`, `uv.lock`, `README.md`, `src`; run `uv sync --frozen --no-dev`; expose 8000; CMD via `uv run <entrypoint>`.
- **Image tags are never `latest`**; they are derived from `VERSION` + prefix/profile + git SHA (or dirty timestamp). The root `IMAGE_TAG` computation enforces this.
- **Registry pushes require setting `REGISTRY`**; without it, images are tagged locally as `luban-aiops/<name>:<tag>` and `make push` still works but reuses the local tag.
- **Cross-platform builds default to `linux/amd64`** (`IMAGE_PLATFORM ?= linux/amd64`); override via `make build IMAGE_PLATFORM=linux/arm64` for native arm64/kind builds.
- **Policy changes must go through the canonical location** and be propagated via `make sync-policy`; consumers do not maintain independent copies outside the sync target.
- **Samples are kept out of the base GitOps overlay** (per SPEC-050 R-11); they are installed separately via `make deploy-samples` and `make deploy-sample-app`.
- **No CI pipeline files exist in the repository**; the documented contract is that `make verify` is the portable gate consumed by whatever external CI the team configures.