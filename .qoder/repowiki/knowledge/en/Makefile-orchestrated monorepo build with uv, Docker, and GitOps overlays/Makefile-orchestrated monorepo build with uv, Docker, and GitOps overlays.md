---
kind: build_system
name: Makefile-orchestrated monorepo build with uv, Docker, and GitOps overlays
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
    - products/platform-gateway/Dockerfile
    - products/platform-gateway/pyproject.toml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - VERSION
---

## What system/approach is used

The repository uses a **GNU Make-driven monorepo build** that coordinates Python packaging (uv), container image builds (Docker), policy validation, Kustomize overlay rendering, and a coordinated deploy pipeline. There is no CI configuration in `.github/workflows`; the root `Makefile` declares itself "forge-agnostic" and is intended to run identically locally and under any CI provider.

Python dependencies are managed per-product via `pyproject.toml` + `uv.lock`, resolved by `uv sync --frozen`. Container images are built from per-product `Dockerfile`s on top of a shared base image (`shared/base-images/base-uv/Dockerfile`) based on Amazon Linux 2023 minimal with a pinned `uv` binary and no system Python — `uv` resolves the interpreter from each product's `.python-version` file.

Deployment is GitOps-oriented: `make build` produces images tagged with a coordinated `<semver>-<prefix>[-<profile>]-<gitsha>` tag (dirty builds append `-dirty-<timestamp>`), writes them into `shared/platform-ops/gitops/dev-k8s/.images.env`, and `make deploy` runs `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which applies Kustomize overlays and provisions secrets via helper scripts.

## Key files and packages

- Root orchestrator: `Makefile` — defines `sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `e2e`, `clean`, plus cross-cutting `sync-policy` / `validate-policy` / `validate-version` targets.
- Shared build fragments:
  - `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`, tag prefix/profile).
  - `mk/image.mk` — shared `build` / `push` / `lint` (hadolint) targets for product Makefiles; requires `IMAGE_NAME`.
  - `mk/python.mk` — shared `sync` / `test` targets using `uv sync --frozen` and `pytest` with OTLP exporters disabled during tests.
- Shared base image: `shared/base-images/base-uv/Dockerfile` — pins `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, installs `uv` into `/usr/local/bin`, creates non-root `app` user (uid 1000), sets `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Per-product entry points: each product under `products/<name>/` has a minimal `Makefile` that only sets `IMAGE_NAME` and includes `../../mk/image.mk` and `../../mk/python.mk`, plus a thin `Dockerfile` that copies `.python-version`, `pyproject.toml`, `uv.lock`, `src/`, runs `uv sync --frozen --no-dev`, and `CMD ["uv", "run", "<entrypoint>"]`.
- Version lock: `VERSION` at repo root (`0.21.1`) is the single source of truth; `make validate-version` enforces every product's `pyproject.toml` version matches it (via `shared/shared-contracts/scripts/validate_version.py`).
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml` is copied to consumers by `make sync-policy` (tool-gateway, platform-gateway, dev-k8s base); validated by `make validate-policy` against JSON schema.
- Deployment scripts: `shared/platform-ops/gitops/dev-k8s/deploy.sh` orchestrates Kustomize apply and secret provisioning scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-sessions-db.sh`, `sync-otel-secrets.sh`, `reconcile-luban-realm.sh`, `reconcile-portal-oidc-client.sh`).
- E2E demos: `shared/platform-ops/e2e/*.sh` invoked via `make e2e` after `make deploy`.

## Architecture and conventions

- **Per-product isolation**: Each product owns its `pyproject.toml`, `uv.lock`, `.python-version`, `Dockerfile`, `src/`, and `tests/`. The root Makefile enumerates products in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists and delegates to `make -C products/<name> <target>`.
- **Shared fragments over duplication**: Product Makefiles are intentionally tiny — they only declare `IMAGE_NAME` and include `mk/image.mk` and `mk/python.mk`. All build logic lives in `mk/`.
- **Coordinated tagging**: A single `IMAGE_TAG` is computed once at the root level (using `PLATFORM_VERSION` from `VERSION`, optional `IMAGE_TAG_PREFIX`/`IMAGE_TAG_PROFILE`, git short SHA, and dirty detection) and propagated to all product builds so every service ships with the same tag.
- **Base image strategy**: All backend services depend on `luban-aiops/base-uv:al2023`, built via `make base-images`. The base image pins both `uv` and `python` versions and runs as non-root `app`.
- **Frozen dependency resolution**: Both runtime (`uv sync --frozen --no-dev` in Dockerfile) and test environments (`uv sync --frozen` in `mk/python.mk`) use `--frozen`, enforcing that `uv.lock` is authoritative.
- **Policy as code**: The policy YAML is maintained centrally and synced to consumers; `validate-policy` checks it against a JSON schema before deployment.
- **GitOps-first deploy**: `make deploy` does not push images directly to Kubernetes; it renders Kustomize overlays (`kustomize build --load-restrictor LoadRestrictionsNone`) and runs secret-provisioning helpers. The `.images.env` state file bridges `make build` and `make deploy`.
- **Kind integration**: Setting `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME=<name>` auto-loads all built images into a local kind cluster after `make build`.

## Conventions and constraints

- **GNU make required**: The root Makefile comment states it requires GNU make (default on macOS/Linux). All targets assume GNU semantics.
- **Single version source**: `VERSION` must match every product's `pyproject.toml` version; `make validate-version` enforces this invariant via `shared/shared-contracts/scripts/validate_version.py`.
- **No system Python in containers**: The base image deliberately omits a system Python; `uv` resolves interpreters from `.python-version` files, making Python version pinning explicit per product.
- **Non-root containers**: Base image creates uid 1000 `app` user and `USER app` is set; product images inherit this.
- **Deterministic tags**: Tags follow `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees and add `-dirty-<YYYYMMDDHHMMSS>` when `git status --porcelain` reports changes. `IMAGE_TAG` can be overridden but the default computation is enforced.
- **Registry re-tagging**: When `REGISTRY` is set, `make build` additionally tags images as `$(REGISTRY)/luban-aiops/<name>:<tag>`; `make push` pushes that reference. Without `REGISTRY`, images stay local.
- **Overridable defaults via `?=`**: All build settings in `mk/defaults.mk` use shell-style `?=`, allowing command-line overrides like `make build IMAGE_PLATFORM=linux/arm64 BASE_UV_UV_VERSION=0.13.0`.
- **Verification gate**: `make verify` runs `test` + `overlays` + `validate-policy` + `validate-version`; designed as the pre-commit/pre-push gate.
- **Secret provisioning flags**: Deploy scripts honor `SKIP_*_SECRETS` environment variables (e.g., `SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_OTEL_SECRETS`) so CI can skip external secret injection.
- **Kustomize overlays**: `OVERLAYS := dev-k8s runtime-profiles/default runtime-profiles/mutating-dev` are rendered via `kustomize build --load-restrictor LoadRestrictionsNone` as part of verification.