---
kind: build_system
name: Coordinated Multi-Product Makefile + Docker Build with GitOps Kustomize Deployment
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
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - VERSION
---

## What system/approach is used

The repository uses a **Makefile-driven, multi-product build system** centered on three layers:

1. **Root `Makefile`** — orchestrates cross-cutting concerns: iterating over product lists (`PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`), building shared base images, computing a coordinated image tag, writing `.images.env`, and running the verification gate.
2. **Shared fragments under `mk/`** — reusable Makefile modules (`defaults.mk`, `image.mk`, `python.mk`) that every product includes so `make -C products/<name>` works standalone or via the root aggregator.
3. **Per-product `Dockerfile` + `pyproject.toml` + `uv.lock`** — each Python service is built as a container image using a shared Amazon Linux 2023 base image (`shared/base-images/base-uv/Dockerfile`) that pins `uv` (0.12.1) and installs per-product interpreters into `/app/.python`.

Deployment is GitOps-driven: `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which calls `kustomize build` against overlays in `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai}` and provisions secrets via helper scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, etc.).

## Key files and packages

- `Makefile` — root aggregator; defines `sync`, `test`, `lint`, `build`, `push`, `overlays`, `verify`, `deploy`, `clean`; computes `IMAGE_TAG` from `VERSION` + git SHA + dirty flag.
- `mk/defaults.mk` — single source of overridable defaults (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`).
- `mk/image.mk` — shared `build`/`push`/`lint` targets for any product that sets `IMAGE_NAME`; supports local-only or registry-tagged builds.
- `mk/python.mk` — shared `sync` (`uv sync --frozen`) and `test` (`uv run pytest`) targets.
- `shared/base-images/base-uv/Dockerfile` — pinned base image (Amazon Linux 2023 minimal, uv 0.12.1, Python 3.12, non-root `app` user).
- `products/*/Makefile` — thin wrappers that set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`.
- `products/*/Dockerfile` — copy `.python-version`, `pyproject.toml`, `uv.lock`, `src/`; run `uv sync --frozen --no-dev`.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — deployment entrypoint that runs overlay deploy and secret provisioning scripts.
- `VERSION` — single source of truth for platform version (e.g. `0.6.0`); consumed by root `IMAGE_TAG` computation and validated by `validate-version`.
- `shared/shared-contracts/scripts/validate_version.py` and `validate_policy.py` — invoked by `make validate-version` and `make validate-policy`.

## Architecture and conventions

- **Product taxonomy**: Products are classified at the root level as either Python-testable (`PYTHON_PRODUCTS := agent-platform audit-service identity-broker incident-service platform-gateway skills-hub tool-gateway`) or image-producing (`IMAGE_PRODUCTS` adds `operator-portal`). The root loop drives all cross-product operations.
- **Coordinated tagging**: A single `IMAGE_TAG` is computed once per invocation as `<semver>-<prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]` and propagated to every product via `$(MAKE) -C products/$$p build IMAGE_TAG=$(IMAGE_TAG)`. After building, the root `build` target writes `shared/platform-ops/gitops/dev-k8s/.images.env` mapping logical names (e.g. `AGENT_SERVICE_IMAGE`, `PLATFORM_GATEWAY_IMAGE`) to `luban-aiops/<name>:<tag>`, which the deploy script consumes.
- **Base image strategy**: All backend services derive from `luban-aiops/base-uv:al2023`, built via `make base-images`. The base image pins `UV_VERSION=0.12.1` and `PYTHON_VERSION=3.12`, installs uv into `/usr/local/bin`, creates a non-root `app` user (uid 1000), and sets `UV_PYTHON_INSTALL_DIR=/app/.python` so each product's interpreter is isolated.
- **Frozen dependency resolution**: Every product uses `uv sync --frozen` (both in `mk/python.mk` and Dockerfiles) against its own `uv.lock`, ensuring reproducible builds without network access during image build.
- **Policy synchronization**: `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into both consumer services (`tool-gateway`, `platform-gateway`) and the deployed overlay (`dev-k8s/base/shared/policy.yaml`), keeping policy bundles in lockstep.
- **Version lockstep**: `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` to enforce that the root `VERSION` file stays synchronized with product versions and the portal.
- **Multi-environment overlays**: Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/{dashscope,deepseek,openai}` select runtime profiles; `make overlays` validates them via `kustomize build --load-restrictor LoadRestrictionsNone`.
- **Local kind integration**: Setting `AUTO_LOAD_KIND=true` plus `KIND_CLUSTER_NAME` after `make build` auto-loads all built images into the named kind cluster.

## Conventions and constraints

- **GNU make required**: The root Makefile header states it requires GNU make (default on macOS/Linux); all fragments assume GNU make semantics.
- **Pinned base versions**: Base image args (`BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`, `BASE_UV_TAG`) default to pinned values in `mk/defaults.mk`; comments explicitly say "never `latest`".
- **Image platform**: Default `IMAGE_PLATFORM = linux/amd64`; overrides propagate through `--platform` flags in both `base-images` and per-product `docker build`.
- **Registry re-tagging**: When `REGISTRY` is set, `mk/image.mk` tags images as `$(REGISTRY)/luban-aiops/$(IMAGE_NAME):$(IMAGE_TAG)` before pushing; otherwise images stay local under `luban-aiops/...`.
- **Verification gate**: `make verify` is documented as the pre-commit/pre-push gate and runs `test`, `overlays`, `validate-policy`, and `validate-version` — this is the canonical CI-equivalent command.
- **Secret provisioning is opt-in in CI**: Deploy scripts check environment variables like `SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_SKILLS_SECRETS`, `SKIP_INCIDENT_SECRETS`, `SKIP_OTEL_SECRETS` to skip secret provisioning when secrets are injected externally (e.g. by CI).
- **Non-root containers**: The base image switches to `USER app` (uid 1000); product Dockerfiles inherit this convention.
- **Single source of truth for version**: The root `VERSION` file feeds both the coordinated image tag prefix and the version validation step; product-level versions must stay in lockstep.