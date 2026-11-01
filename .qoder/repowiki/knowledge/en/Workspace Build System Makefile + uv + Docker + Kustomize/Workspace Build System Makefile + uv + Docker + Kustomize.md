---
kind: build_system
name: 'Workspace Build System: Makefile + uv + Docker + Kustomize'
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
    - shared/platform-ops/gitops/dev-k8s/.images.env
---

## What system/approach is used

The Luban workspace is built with a layered, forge-agnostic approach:

- **GNU make** at the repository root orchestrates cross-cutting concerns (image builds, policy sync, overlay validation, e2e demos) and delegates per-product work to each product's own `Makefile`.
- **uv** is the Python dependency manager; every Python product pins its dependencies in `uv.lock` and runs `uv sync --frozen` / `uv run pytest`. There is no `requirements.txt`, no pip, and no Poetry.
- **Docker** builds one image per product from a thin `Dockerfile` that layers `src/` over a shared base image.
- **Kustomize** renders GitOps overlays under `shared/platform-ops/gitops/<overlay>/` as part of verification (`make overlays`).
- **No CI workflow files exist** in `.github/workflows`; the root comment states `Forge-agnostic: make verify is the pre-commit/pre-push gate and runs the same checks locally and under any CI.` The CI provider is therefore external to this repo.

## Key files and packages

- Root orchestrator: `Makefile` — declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`, computes `IMAGE_TAG`, and wires `verify`, `build`, `push`, `deploy`, `e2e`, policy/dashboards/version secret-vocabulary validators.
- Shared build fragments under `mk/`:
  - `mk/defaults.mk` — single source of truth for overridable settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`). All values use `?=` so command-line overrides always win.
  - `mk/image.mk` — shared `build` / `push` / `lint` targets for container images. Requires `IMAGE_NAME`; supports `IMAGE_CONTEXT` / `IMAGE_DOCKERFILE` hooks.
  - `mk/python.mk` — shared `sync` / `test` targets running `uv sync --frozen` then `pytest` with OTLP exporters disabled.
- Per-product `Makefile`s are minimal stubs that set `IMAGE_NAME` and include both fragments (see `products/agent-platform/Makefile`).
- Per-product `Dockerfile`s follow a uniform pattern: `FROM luban-aiops/base-uv:<tag>`, copy `.python-version pyproject.toml uv.lock README.md src`, run `uv sync --frozen --no-dev`, expose port 8000, `CMD ["uv", "run", "<entrypoint>"]`.
- Shared base image: `shared/base-images/base-uv/Dockerfile`, built via `make base-images` with `BASE_UV_PYTHON_VERSION=3.12` and `BASE_UV_UV_VERSION=0.12.1` (overridable).
- Version source of truth: root `VERSION` file (`0.52.0`), enforced against all products by `make validate-version`.
- Coordinated image tag computation: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, `<...>-dirty-<timestamp>` for dirty trees; written into `shared/platform-ops/gitops/dev-k8s/.images.env` by `make build`.
- Policy contracts: canonical bundle at `shared/shared-contracts/policies/policy-default.yaml` (and `password-policy.yaml`) synced by `make sync-policy` into `products/tool-gateway`, `products/platform-gateway`, and the dev overlay.
- Dashboard validation: `shared/platform-ops/dashboards/validate_dashboards.py` invoked by `make validate-dashboards` (SPEC-065 R-3).

## Architecture and conventions

1. **Two-level Makefile hierarchy.** The root `Makefile` owns cross-cutting orchestration; each product's `Makefile` only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`. This keeps per-product logic trivial and centralizes behavior in `mk/`.
2. **Product registry lists.** `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` in the root `Makefile` are the single source of truth for which services participate in `sync`, `test`, `lint`, `build`, `push`. New services must be added to both lists.
3. **Coordinated tagging.** All images produced by `make build` share one `IMAGE_TAG` computed once at the root level, ensuring a deploy uses a consistent snapshot across all nine services plus the web UI.
4. **Kind integration.** When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all nine service images plus `web-ui` into the named kind cluster after building.
5. **Verification gate.** `make verify` is the canonical pre-commit/pre-push entry point; it runs product tests, kustomize render checks, dashboard validation, policy/schema validations, version lockstep, secret vocabulary, secret-delivery demo, portal unit+build, audit contract test, delegated-custody/runtime/multi-process/edge tests, and execution-failure test.
6. **GitOps overlays as first-class artifacts.** Overlays under `shared/platform-ops/gitops/` are validated offline via `kustomize build --load-restrictor LoadRestrictionsNone` during verification.
7. **Policy-as-code with canonical source.** The canonical policy YAML lives under `shared/shared-contracts/policies/` and is copied into consumers by `make sync-policy`; `make validate-policy` and `make validate-policy-scenarios` enforce schema and behavioral expectations.
8. **Python dependency hygiene.** Every Python product has `pyproject.toml` + `uv.lock`; `make sync` / `make test` always use `--frozen` mode, preventing drift between local and CI environments.
9. **Operator portal exception.** The operator-portal SPA is not a uv product; it is exercised through `make portal-test` which runs its Vitest suite and production build separately (SPEC-063 R-8c).

## Conventions and constraints

- **Forge-agnostic CI:** The root `Makefile` header explicitly states `Forge-agnostic: make verify is the pre-commit/pre-push gate and runs the same checks locally and under any CI`. No `.github/workflows` directory exists in the repo.
- **Pinned base image versions:** `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; the comment says "never latest".
- **Single version source:** `VERSION` is the single source of truth for the platform release semver; `make validate-version` enforces lockstep with every product and the portal.
- **Image naming convention:** Images are tagged `luban-aiops/<service>:<IMAGE_TAG>` locally; when `REGISTRY` is set they are re-tagged to `$(REGISTRY)/luban-aiops/<service>:<IMAGE_TAG>` before push.
- **Overlay list is authoritative:** `OVERLAYS` enumerates every overlay rendered by `make overlays`; adding an overlay requires updating this list.
- **Samples kept out of base overlay:** `samples/acme-admin` is deployed out-of-band via `make deploy-samples` / `make deploy-sample-app` because SPEC-050 R-11 requires samples not to appear in the base overlay.
- **Secret vocabulary lockstep:** `make validate-secret-vocabulary` enforces alignment among agent-platform, tool-gateway, and skills-hub.
- **Password policy floor:** `make validate-password-policy` validates the password-strength contract and pins the connector floor to it (SPEC-062 R-2).
- **Dashboard importability:** `make validate-dashboards` validates OpenObserve dashboards offline (parse + envelope/panel schema + metric reference resolution) per SPEC-065 R-3.
- **Portal coverage invariant:** `make verify` never skips the operator-portal SPA; its full Vitest suite and typechecked production build are required (SPEC-063 R-8c).
- **Multi-process/delegate edge proofs:** Dedicated `make` targets (`delegated-custody-test`, `delegated-runtime-test`, `delegated-multiproc-test`, `delegated-edge-test`, `execution-failure-test`) are wired into `verify` to prove cross-replica and crash-safety properties.