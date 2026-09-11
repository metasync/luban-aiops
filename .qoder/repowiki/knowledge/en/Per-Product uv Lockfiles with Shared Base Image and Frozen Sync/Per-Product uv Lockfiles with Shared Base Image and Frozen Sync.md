---
kind: dependency_management
name: Per-Product uv Lockfiles with Shared Base Image and Frozen Sync
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/image.mk
    - mk/defaults.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - Makefile
    - docs/workspace/python-container-strategy.md
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
---

## System Overview

The repository manages dependencies for a multi-product Python monorepo using **uv** as the sole package manager, with one `pyproject.toml` + `uv.lock` pair per product under `products/<name>/`. There is no workspace-level lockfile — each product independently declares its runtime and dev dependencies and pins an exact resolution in its own `uv.lock`. The root Makefile orchestrates dependency refreshes across all products via `make sync`, which iterates over the `PYTHON_PRODUCTS` list (`agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`) and runs each product's `sync` target.

## Key Files

- `mk/python.mk` — shared targets: `sync` runs `uv sync --frozen`; `test` re-syncs frozen then runs pytest with OTLP exporters disabled so tracing tests stay green without external backends.
- `mk/image.mk` — shared Docker image build/push/lint targets; every product includes this fragment and sets `IMAGE_NAME`.
- `mk/defaults.mk` — single source of truth for overridable build settings: `IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_UV_VERSION` (default `0.12.1`), `BASE_UV_PYTHON_VERSION` (default `3.12`).
- `shared/base-images/base-uv/Dockerfile` — shared base image built from `public.ecr.aws/amazonlinux/amazonlinux:2023-minimal`, installs a pinned `uv` from `https://astral.sh/uv/${UV_VERSION}/install.sh`, creates non-root `app` user (uid 1000), exports `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Product `Dockerfile`s (e.g. `products/agent-platform/Dockerfile`) — follow the canonical pattern: `FROM luban-aiops/base-uv:al2023`, copy `.python-version pyproject.toml uv.lock README.md src`, run `uv sync --frozen --no-dev`, CMD via `uv run <script>`.
- Each product's `pyproject.toml` — declares `[project]` dependencies with caret ranges (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`), optional `[dependency-groups.dev]` for test-only packages, and `[build-system]` pinning `uv_build>=0.8.14,<0.9.0`.
- Each product's `.python-version` — pins the interpreter (workspace default `3.12`); resolved by `uv` during `uv sync`.
- Root `Makefile` — `make verify` aggregates `test overlays validate-policy validate-policy-scenarios validate-version validate-secret-vocabulary`; `make sync` loops over all Python products.
- `docs/workspace/python-container-strategy.md` — authoritative design doc describing the adopted Option B strategy (environment-specific base image + installed uv) and the rule that all Python backend images build from `luban-aiops/base-uv:al2023`.
- `docs/specs/SPEC-042-dependency-hygiene/spec.md` — codifies the adoption policy: latest stable only (no alpha/beta/RC/dev), with one recorded exception for OpenTelemetry instrumentation on the permanent `0.xb` channel.

## Architecture and Conventions

1. **Per-product dependency isolation.** Each product owns its `pyproject.toml` and `uv.lock`. There is no cross-product Python dependency sharing at the package level; shared contracts live under `shared/shared-contracts/` as JSON schemas and YAML policies, not as installable Python packages.

2. **Frozen builds everywhere.** Development uses `uv sync --frozen` (via `mk/python.mk`), and production images use `uv sync --frozen --no-dev`. This guarantees that the locked resolution in `uv.lock` is the only resolution allowed — no network lookups or version drift between environments.

3. **Shared reproducible base image.** All Python services build from `luban-aiops/base-uv:al2023`, itself built from Amazon Linux 2023 minimal with a pinned `uv` version passed via `--build-arg UV_VERSION`. The base image also enforces non-root execution (`USER app`, uid 1000) and sets deterministic environment variables (`PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON`, `UV_PYTHON_INSTALL_DIR`).

4. **Interpreter pinning via `.python-version`.** Each product declares its Python version in a local `.python-version` file; `uv` resolves the interpreter from this file during `uv sync`. The base image's `UV_PYTHON` ARG provides a deterministic fallback when no `.python-version` is found.

5. **Version range policy.** Dependencies are declared with upper-bound caps (e.g. `<1.0`, `<7.0`, `<9.0`) to allow patch/minor updates while blocking breaking majors. Major version bumps require explicit adjudication — see SPEC-042's treatment of `cryptography` (raised from `<45.0` to `<51.0` after call-site review), parked `redis` (`<7.0`) and `elasticsearch` (`<9.0`) caps, and the recorded exception for OTel instrumentation on the `0.xb` channel.

6. **Coordinated image tagging.** The root `Makefile` computes a coordinated `IMAGE_TAG` from `VERSION` + prefix/profile/gitsha/dirty timestamp, builds all images with that tag, writes them to `.images.env`, and pushes them together via `make push`. This ensures all services in a deployment share the same immutable image tag.

7. **No vendoring.** Dependencies are resolved from PyPI (and ECR for the base image). There is no `vendor/` directory or offline cache committed to the repo — determinism comes from `uv.lock` plus `--frozen`.

## Conventions and Constraints

- **Adopt latest stable only.** Per SPEC-042, every adopted version must be a final stable release — no alpha, beta, RC, or dev builds. The only recorded exception is OpenTelemetry instrumentation packages, which publish on a permanent `0.xb` channel and stay at their locked SDK pairing rather than chasing newer betas.
- **Never default to `latest`.** Pinned defaults in `mk/defaults.mk` (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`) and the base image ARGs explicitly avoid floating tags. The container strategy doc states these are "pinned defaults; override via --build-arg" and "never `latest`".
- **Frozen sync is mandatory.** Both development (`uv sync --frozen`) and production (`uv sync --frozen --no-dev`) use the frozen flag, enforced by the shared `mk/python.mk` targets and the canonical Dockerfile pattern documented in `python-container-strategy.md`.
- **Base image must be rebuilt before product images.** `make build` depends on `base-images`, which builds `luban-aiops/base-uv:al2023` first. Product Dockerfiles `FROM luban-aiops/base-uv:al2023`.
- **Non-root containers.** The base image creates `USER app` (uid 1000); the container strategy doc states "no service may regress to root" and deployments carry matching `securityContext` (`runAsNonRoot`, `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`).
- **Single target platform per build.** `IMAGE_PLATFORM` defaults to `linux/amd64` (the deployment target) and is applied to both the base image and all product builds; overrides go through `mk/defaults.mk`.
- **Version lockstep across the workspace.** A root `VERSION` file drives coordinated image tags; `make validate-version` checks lockstep between `VERSION`, product `pyproject.toml` versions, and portal metadata via `shared/shared-contracts/scripts/validate_version.py`.
- **Policy bundle synchronization.** Policy files are copied from a canonical location (`shared/shared-contracts/policies/policy-default.yaml`) into consumers via `make sync-policy`; changes must propagate to all locations or validation fails.