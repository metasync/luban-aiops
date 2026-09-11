---
kind: build_system
name: Multi-Product Make/uv/Docker Build System with GitOps Overlays
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
    - products/agent-platform/Dockerfile
    - products/agent-platform/pyproject.toml
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/shared-contracts/scripts/validate_version.py
---

## Build System Overview

The Luban AIOps platform uses a **multi-product workspace** built on three layers: per-product `pyproject.toml` + `uv.lock` (dependency management), shared GNU Make fragments under `mk/` (build orchestration), and Docker images deployed via Kustomize GitOps overlays. There is no CI pipeline file in the repo; the root `Makefile` defines the single verification gate (`make verify`) intended to run identically locally and in any CI.

## Key Files and Packages

- **Root orchestrator**: `Makefile` — declares product lists, computes coordinated image tags, delegates per-product `sync/test/lint/build/push`, runs policy validation, renders Kustomize overlays, and drives deploy/e2e.
- **Shared build fragments**:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`).
  - `mk/image.mk` — per-product `build` / `push` / `lint` targets using `docker build --platform $(IMAGE_PLATFORM)`; supports optional registry re-tagging.
  - `mk/python.mk` — `sync` (`uv sync --frozen`) and `test` (`uv run pytest` with OTLP exporters disabled).
- **Per-product manifests**: each product under `products/<name>/` has a minimal `Makefile` that sets `IMAGE_NAME` and includes both `../../mk/image.mk` and `../../mk/python.mk`; a `Dockerfile` based on `luban-aiops/base-uv:al2023` that runs `uv sync --frozen --no-dev` and `EXPOSE 8000`.
- **Versioning**: root `VERSION` file (`0.36.1`) is the single source of truth; `validate-version` script enforces every product's `pyproject.toml` version matches it.
- **GitOps overlays**: `shared/platform-ops/gitops/dev-k8s/` (base + overlay) plus `runtime-profiles/{default,mutating-dev,browser-dev}`; rendered by `kustomize build --load-restrictor LoadRestrictionsNone` during `overlays`.
- **Policy bundle**: canonical `shared/shared-contracts/policies/policy-default.yaml` is copied into `tool-gateway`, `platform-gateway`, and the dev-k8s base via `sync-policy`; validated against JSON schema and scenario expectations via scripts under `shared/shared-contracts/scripts/`.
- **Base image**: `shared/base-images/base-uv/Dockerfile` builds the pinned `luban-aiops/base-uv:al2023` image (Python 3.12 + uv 0.12.1) from `mk/defaults.mk`.

## Architecture and Conventions

### Coordinated multi-image builds
The root `make build` iterates `IMAGE_PRODUCTS` (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway, operator-portal), invoking each product's `make build IMAGE_TAG=... IMAGE_PLATFORM=...`. The computed tag follows the pattern `<semver>-<prefix>[-<profile>]-<gitsha>` (dirty worktrees append `-dirty-<timestamp>`). After building, all image names are written to `shared/platform-ops/gitops/dev-k8s/.images.env`, which the deploy step consumes so overlays reference exactly-built images.

### Per-product isolation
Each product owns its `pyproject.toml`, `uv.lock`, `Dockerfile`, and `tests/`. The root Makefile only enumerates products in two lists: `PYTHON_PRODUCTS` (for `sync`/`test`) and `IMAGE_PRODUCTS` (for `build`/`push`/`lint`). Product Makefiles are intentionally tiny — they set `IMAGE_NAME` and include the shared fragments, keeping cross-cutting logic centralized.

### Dependency management
All Python products use **uv** as the package manager and resolver. Dependencies are declared in `pyproject.toml` with pinned ranges (e.g. `fastapi>=0.115,<1.0`); `uv.lock` pins exact versions. `sync` and `test` always pass `--frozen` to enforce lockfile fidelity. Dev-only dependencies live in `[dependency-groups] dev` and are excluded from image builds via `uv sync --frozen --no-dev`.

### Image strategy
Images are multi-stage-free but reproducible: copy only `pyproject.toml`, `uv.lock`, `.python-version`, `README.md`, and `src/`, then `uv sync --frozen --no-dev`. The entrypoint is a `uv run <script>` command defined in `[project.scripts]`. All images share the `luban-aiops/base-uv:al2023` base image built once by `make base-images`.

### Deployment model
Deployment is GitOps-driven through Kustomize. The `dev-k8s` overlay references images from `.images.env`; runtime profiles under `runtime-profiles/` toggle features (browser sidecar, mutating tools). Secret synchronization is handled by helper scripts under `shared/platform-ops/gitops/sync-*.sh`. The `deploy` target wraps `shared/platform-ops/gitops/dev-k8s/deploy.sh`, and an optional `AUTO_LOAD_KIND=true` flag auto-loads images into a local kind cluster after `make build`.

### Verification gate
`make verify` composes the pre-commit/pre-push gate: runs every product's tests, renders all Kustomize overlays, validates the canonical policy bundle against schemas and scenarios, and checks version lockstep across VERSION and all products.

## Conventions and Constraints

- **GNU make required**: documented in the root Makefile header; all targets assume GNU make semantics.
- **Single version source**: `VERSION` at the repo root must match every product's `pyproject.toml` version; enforced by `make validate-version`.
- **Frozen dependency resolution**: all `uv sync` invocations use `--frozen`; no ad-hoc dependency updates outside `uv.lock`.
- **Image tagging discipline**: tags are never `latest`; they derive from `PLATFORM_VERSION` + prefix/profile + git SHA, with dirty-worktree timestamps appended.
- **Platform pinning**: `IMAGE_PLATFORM ?= linux/amd64` is the default; ARM builds require explicit override. Base image also respects this via `--platform`.
- **Registry push gated**: `make push` only re-tags and pushes when `REGISTRY` is set; otherwise images stay local.
- **Policy bundle ownership**: the canonical policy lives in `shared/shared-contracts/policies/`; consumers receive copies via `make sync-policy` — not edited in place.
- **Overlay rendering**: `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` for each overlay in `OVERLAYS`; failures block the verification gate.
- **E2E boundary**: `make e2e` requires a previously deployed dev cluster plus port-forwarded services; it runs shell demos under `shared/platform-ops/e2e/`.