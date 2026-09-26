---
kind: build_system
name: 'Workspace Build System: Makefile + uv + Docker Multi-Stage'
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/Makefile
    - products/operator-portal/Makefile
    - products/agent-platform/Dockerfile
---

## What system/approach is used

The repository uses a **GNU make-driven workspace build** layered over three toolchains:

1. **Make** (root `Makefile` + shared fragments in `mk/`) — orchestrates cross-cutting concerns (image builds, policy sync/validation, GitOps overlay checks, e2e demos).
2. **uv** (Python package manager) — each Python product has its own `pyproject.toml` + `uv.lock`; dependency install and test execution go through `uv sync --frozen` / `uv run pytest`.
3. **Docker multi-stage images** — every backend service and the operator-portal SPA are containerized; all images derive from a pinned shared base image `luban-aiops/base-uv` built from `shared/base-images/base-uv/Dockerfile`.

There is no CI configuration file in `.github/` (only issue templates and a PR template); the root `Makefile` comment states that `make verify` is the pre-commit/pre-push gate and runs the same checks locally and under any CI.

## Key files and packages

- `Makefile` — master entrypoint; declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, computes coordinated `IMAGE_TAG`, delegates per-product targets, and owns policy/version/overlay validation.
- `mk/defaults.mk` — single source of truth for overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- `mk/image.mk` — shared `build` / `push` / `lint` (hadolint with docker-run fallback) targets; requires `IMAGE_NAME` from the including Makefile.
- `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `uv run pytest` with OTLP exporters disabled.
- `shared/base-images/base-uv/Dockerfile` — pinned Amazon Linux 2023 minimal base with pinned `uv` (0.12.1) and Python 3.12, running as non-root user `app` (uid 1000).
- Per-product `products/<name>/Makefile` — thin wrappers setting `IMAGE_NAME` and including `../../mk/image.mk` and `../../mk/python.mk`.
- Per-product `products/<name>/Dockerfile` — multi-stage image copying `.python-version`, `pyproject.toml`, `uv.lock`, `src/`, then `uv sync --frozen --no-dev`.
- `VERSION` — single source of truth for the platform release version (semver), consumed by the root Makefile to compute `PLATFORM_VERSION`.
- `shared/platform-ops/gitops/` — Kustomize overlays validated via `kustomize build --load-restrictor LoadRestrictionsNone`.
- `shared/shared-contracts/scripts/` — policy and version validation scripts invoked by root Makefile targets.

## Architecture and conventions

### Two-level Makefile hierarchy

The root `Makefile` is purely an aggregator: it loops over `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` and invokes `$(MAKE) -C products/$$p <target>`. Each product's Makefile is a 5–10 line file that only sets `IMAGE_NAME` and includes the shared fragments. This keeps product-specific logic out of the root and makes adding a new product a matter of appending to the two lists plus writing a one-line Makefile.

### Coordinated image tagging

All images share one tag computed once at the root level:

```
<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]
```

where semver comes from `VERSION`, prefix/profile come from `IMAGE_TAG_PREFIX` / `IMAGE_TAG_PROFILE`, and the git SHA + dirty flag come from `git status --porcelain`. The resulting tag is written into `shared/platform-ops/gitops/dev-k8s/.images.env` so `make deploy` consumes the exact images that were just built.

### Shared base image strategy

All backend services build on top of `luban-aiops/base-uv:al2023`, which pins both `uv` (0.12.1) and Python (3.12) via build args. The base image installs `curl-minimal`, `ca-certificates`, `tar`, `gzip`, `shadow-utils`, creates a non-root `app` user (uid 1000), and exports `UV_PYTHON=3.12` / `UV_LINK_MODE=copy` / `UV_NO_SYNC=1`. Product images then do `uv sync --frozen --no-dev` to install runtime deps without dev dependencies.

### Policy and contract synchronization

Policy bundles have a canonical location (`shared/shared-contracts/policies/`) and are copied into consumers via `make sync-policy`. A separate password-policy contract is synced into `tool-gateway` only (SPEC-062 R-2). Validation is done via scripts under `shared/shared-contracts/scripts/` invoked from root targets (`validate-policy`, `validate-policy-scenarios`, `policy-diff`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`).

### Operator portal exception

The operator-portal is not a Python product — it is a Vite/Vitest SPA served by nginx. Its Makefile overrides `IMAGE_CONTEXT := ../..` (so the Dockerfile can see the root `VERSION` file) and adds `test` (runs `npm test` via Vitest) and `web-build` (runs `tsc --noEmit && vite build`). The root `verify` target explicitly calls `portal-test` because `make test` never covers it (documented as SPEC-063 R-8c).

### GitOps overlays

Overlays under `shared/platform-ops/gitops/` are validated by `make overlays`, which runs `kustomize build --load-restrictor LoadRestrictionsNone` for each overlay listed in `OVERLAYS` (`dev-k8s`, `runtime-profiles/default`, `runtime-profiles/mutating-dev`, `runtime-profiles/browser-dev`). Deployment goes through `make deploy`, which shells out to `shared/platform-ops/gitops/dev-k8s/deploy.sh`.

### E2E and samples

- `make e2e` runs demo scripts against a deployed cluster after port-forwarding `platform-gateway:18083` and `identity-service:18081`.
- `make execution-failure-test` runs `shared/platform-ops/e2e/execution-failure-test.sh`.
- `make execution-acceptance` runs `samples/acme-admin/execution_acceptance.py`.
- Tutorial skills are installed out-of-band via `make deploy-samples` (never part of the base overlay, per SPEC-050 R-11).

## Conventions and constraints

- **Pinned base versions**: `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; comments state these are defaults for reproducible builds and "never latest". The base image Dockerfile re-pins them via ARGs.
- **Frozen dependency resolution**: All `uv sync` invocations use `--frozen`, requiring `uv.lock` to be committed and preventing drift between environments.
- **Non-root containers**: The base image switches to `USER app` (uid 1000); product images inherit this.
- **Coordinated tagging**: The root `IMAGE_TAG` computation is the single point where semver, profile, git SHA, and dirty-state are combined; individual product `make build` targets receive this tag rather than computing their own.
- **Registry tagging pattern**: `mk/image.mk` always builds to `luban-aiops/<name>:<tag>` locally; if `REGISTRY` is set, it additionally tags `<registry>/luban-aiops/<name>:<tag>` before push.
- **Verification gate composition**: `make verify` composes `test`, `overlays`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, `secret-delivery-demo`, `portal-test`, and `execution-failure-test` — intended as the pre-commit/pre-push gate.
- **Per-product Makefiles must declare `IMAGE_NAME`**: `mk/image.mk` requires the including Makefile to set `IMAGE_NAME` (the short image name such as `agent-service` or `platform-gateway`).
- **Operator portal excluded from Python test loop**: The root `PYTHON_PRODUCTS` list does not include `operator-portal`; its tests are exercised only via the explicit `portal-test` target.
- **Samples kept out of base overlay**: Both tutorial skills and the acme-admin sample application are deployed via separate scripts (`deploy-samples`, `deploy-sample-app`) so they never appear in the base overlay, enforced by the root Makefile comments referencing SPEC-050 R-11 and SPEC-059 R-6.