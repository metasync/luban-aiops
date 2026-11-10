---
kind: build_system
name: Luban Workspace Build & Artifact System (Make + uv + Docker + Kustomize)
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/python.mk
    - mk/image.mk
    - VERSION
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/Makefile
    - products/operator-portal/Makefile
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/platform-ops/dashboards/validate_dashboards.py
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_secret_vocabulary.py
    - shared/shared-contracts/scripts/validate_password_policy.py
---

# Build System Overview

The Luban workspace is a Python monorepo of eight services plus an operator-portal SPA, built through a **single root Makefile** that delegates per-product work to shared fragments under `mk/`. There is no CI pipeline file in this repository (no `.github/workflows`); the documented gate is `make verify`, which is intended to run identically locally and under any CI.

## Architecture

```
Makefile (root)
├── mk/defaults.mk          # single source of overridable build settings
├── mk/python.mk           # uv sync/test targets for Python products
├── mk/image.mk            # docker build/push/lint targets for containerized products
└── products/<name>/Makefile   # thin wrapper: sets IMAGE_NAME, includes mk/*.mk
```

Each product Makefile is typically 5–10 lines — it only declares `IMAGE_NAME` and includes the two shared fragments. The root Makefile owns cross-cutting orchestration: iterating over `PYTHON_PRODUCTS` / `IMAGE_PRODUCTS`, computing a coordinated image tag, writing `.images.env`, and composing the verification gate.

## Key Files

| File | Role |
|---|---|
| `Makefile` | Root orchestrator; defines `sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `e2e`, policy/dashboard/version validators |
| `mk/defaults.mk` | All `?=` defaults: `IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*` pins |
| `mk/python.mk` | `uv sync --frozen` + pytest with OTel exporters disabled |
| `mk/image.mk` | `docker build`/`tag`/`push`/`hadolint` using `luban-aiops/<IMAGE_NAME>:<IMAGE_TAG>` |
| `shared/base-images/base-uv/Dockerfile` | Shared base image built by `make base-images` |
| `products/*/Dockerfile` | Per-service multi-stage images |
| `products/operator-portal/Dockerfile` | Nginx-based SPA image; context is repo root so it can read `VERSION` |
| `shared/platform-ops/gitops/dev-k8s/` | Kustomize overlays (`default`, `mutating-dev`, `browser-dev`, `ansible-dev`, `servicenow-dev`, `delegated-dev`) validated by `make overlays` |
| `shared/platform-ops/dashboards/validate_dashboards.py` | Offline schema/metric-reference validation for OpenObserve dashboards |
| `shared/shared-contracts/scripts/validate_version.py` | Enforces lockstep between root `VERSION` and every product's declared version |
| `shared/shared-contracts/scripts/validate_secret_vocabulary.py` | Enforces secret-literal lockstep across agent-platform/tool-gateway/skills-hub |
| `shared/shared-contracts/scripts/validate_password_policy.py` | Enforces password-policy contract (SPEC-062 R-2) |
| `VERSION` | Single source of truth for platform semver; used as prefix of coordinated image tags |

## Image Tagging Strategy

Coordinated tags are computed once at the root:

```
<semver>-<prefix>[-<profile>]-<gitsha>
```

- `<semver>` comes from `VERSION` (currently `0.55.0`).
- `<prefix>` defaults to `dev-k8s` (`IMAGE_TAG_PREFIX`).
- `<profile>` is optional (`IMAGE_TAG_PROFILE`).
- A clean tree appends the short git SHA; a dirty tree appends `-dirty-YYYYMMDDHHMMSS`.
- If not inside a git worktree, the timestamp is used instead of SHA.

The root `make build` writes `shared/platform-ops/gitops/dev-k8s/.images.env` with all nine service image names keyed by `IMAGE_TAG`; `make deploy` reads this file to render overlays against one consistent set of images.

## Product Categories

- **Python products** (`agent-platform`, `audit-service`, `execution-runtime`, `identity-broker`, `incident-service`, `platform-gateway`, `skills-hub`, `tool-gateway`): use `uv` with a per-product `pyproject.toml` + `uv.lock`; `make test` runs `uv sync --frozen && uv run pytest` with OTel exporters set to `none` so tracing tests pass without network.
- **Operator portal** (`operator-portal`): Vite + Vitest SPA served by nginx; `make test` runs `npm test`, `make web-build` runs `tsc --noEmit && vite build`; `make verify` requires both to pass (SPEC-063 R-8c).
- **Shared base image**: `make base-images` builds `luban-aiops/base-uv:<BASE_UV_TAG>` (default `al2023`) pinned to `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`.

## Cross-Cutting Gates

`make verify` composes the full pre-commit/pre-push gate:

1. `test` — all Python product suites
2. `overlays` — `kustomize build` on every overlay under `shared/platform-ops/gitops`
3. `validate-dashboards` — offline OpenObserve dashboard validation (SPEC-065 R-3)
4. `validate-policy` / `validate-policy-scenarios` — canonical policy bundle vs JSON schema and scenario expectations against both engines
5. `validate-version` — enforces VERSION lockstep
6. `validate-secret-vocabulary` — enforces secret literal lockstep
7. `validate-password-policy` — enforces SPEC-062 R-2
8. `secret-delivery-demo` — local sample handoff proof
9. `portal-test` — SPA unit suite + production build
10. `audit-contract-test` — disposable Postgres integration test
11. `delegated-custody-test` / `delegated-runtime-test` / `delegated-multiproc-test` / `delegated-edge-test` — real delegated custody/runtime proofs
12. `execution-failure-test` — crash-safety proof

## Deployment

- `make deploy` wraps `shared/platform-ops/gitops/dev-k8s/deploy.sh` to apply the dev overlay.
- `make deploy-samples` installs tutorial skills out-of-band (SPEC-050 R-11 keeps samples out of the base overlay).
- `make deploy-sample-app` builds and deploys the acme-admin sample application separately.
- `make e2e` runs the demo scripts in `shared/platform-ops/e2e/` against a deployed cluster requiring port-forwards for `platform-gateway` and `identity-service`.

## Conventions and Constraints

- **GNU make required**: the root Makefile comment states it requires GNU make (default on macOS/Linux); POSIX sh is forced via `SHELL := /bin/sh`.
- **Single source of truth for versions**: `VERSION` is the platform release version; `make validate-version` enforces lockstep with every product's declared version.
- **Pinned base image versions**: `mk/defaults.mk` pins `BASE_UV_UV_VERSION=0.12.1` and `BASE_UV_PYTHON_VERSION=3.12`; comments explicitly say "never latest".
- **Frozen dependency resolution**: Python products use `uv sync --frozen` so `uv.lock` is authoritative.
- **Coordinated tagging**: `make build` computes one `IMAGE_TAG` and applies it to every product image; `make push` pushes them all.
- **Policy bundles are authored once**: `shared/shared-contracts/policies/policy-default.yaml` and `password-policy.yaml` are copied to consumers via `make sync-policy`.
- **Kustomize overlays must render**: `make overlays` fails if any overlay does not pass `kustomize build --load-restrictor LoadRestrictionsNone`.
- **Dashboard artifacts cannot rot silently**: `make validate-dashboards` validates parse, envelope/panel schema, and metric references offline (SPEC-065 R-3).
- **Portal build is part of the gate**: `make verify` requires both Vitest and the Vite production build to succeed (SPEC-063 R-8c).
- **No CI files in-tree**: there are no GitHub Actions workflows or other CI configuration committed; the Makefile comment describes `make verify` as the forge-agnostic gate.