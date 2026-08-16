---
kind: build_system
name: Unified Makefile + Docker + uv Build System with GitOps Overlays
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - shared/base-images/base-uv/Dockerfile
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - products/agent-platform/Dockerfile
    - products/operator-portal/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
---

## What system/approach is used

The repository uses a **Makefile-driven monorepo build** that coordinates Python packaging (via `uv`), container image builds (via `docker`), and Kubernetes deployment through Kustomize GitOps overlays. There is no CI pipeline file in the repo; the root `Makefile` declares itself "Forge-agnostic" and intended to run identically locally and under any CI (`make verify` is the pre-commit/pre-push gate). The build surface is split into three layers:

1. **Root orchestrator** (`Makefile`) — enumerates products, computes a coordinated image tag, runs per-product targets, renders GitOps overlays, validates policy bundles, and invokes the deploy script.
2. **Shared fragments** (`mk/defaults.mk`, `mk/image.mk`, `mk/python.mk`) — single source of truth for overridable settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*` versions) and reusable `build`/`push`/`lint`/`sync`/`test` targets.
3. **Per-product Makefiles** — minimal files that set `IMAGE_NAME` and include the two shared fragments, plus a product `Dockerfile` and a `pyproject.toml`/`uv.lock`.

## Key files and packages

- Root: `Makefile` — top-level entry point defining `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`, and targets `sync`, `test`, `lint`, `base-images`, `build`, `push`, `overlays`, `verify`, `deploy`, `clean`, `sync-policy`, `validate-policy`.
- Shared config: `mk/defaults.mk` — guarded double-inclusion guard (`LUBAN_DEFAULTS_INCLUDED`), pinned defaults for `IMAGE_PLATFORM=linux/amd64`, `IMAGE_TAG_PREFIX=dev-k8s`, `BASE_UV_IMAGE=luban-aiops/base-uv`, `BASE_UV_TAG=al2023`, `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`.
- Image fragment: `mk/image.mk` — defines `build`/`push`/`lint` using `docker build --platform $(IMAGE_PLATFORM)`; resolves `IMAGE_REF` as `luban-aiops/<name>:<tag>` or `<REGISTRY>/luban-aiops/<name>:<tag>`; falls back to git short SHA for `IMAGE_TAG` when not provided.
- Python fragment: `mk/python.mk` — `uv sync --frozen` then `uv run pytest`; enforces frozen lockfiles.
- Base image: `shared/base-images/base-uv/Dockerfile` — Amazon Linux 2023 minimal, installs a pinned `uv` version via `curl | sh`, creates non-root `app` user (uid 1000), sets `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON=<version>`, `UV_PYTHON_INSTALL_DIR=/app/.python`.
- Product images: each service under `products/<name>/Dockerfile` follows the same pattern: `FROM luban-aiops/base-uv:al2023`, copy `.python-version pyproject.toml uv.lock src`, `RUN uv sync --frozen --no-dev`, `CMD ["uv", "run", "<entrypoint>"]`. The operator portal uses `nginxinc/nginx-unprivileged:1.27-alpine` instead.
- Per-product Makefiles: e.g. `products/platform-gateway/Makefile` — only sets `IMAGE_NAME := platform-gateway` and includes `../../mk/image.mk` and `../../mk/python.mk`.
- Deployment: `shared/platform-ops/gitops/dev-k8s/deploy.sh` — calls `deploy-overlay.sh`, then provisions secrets via helper scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-otel-secrets.sh`), optionally reconciles Keycloak realm and portal OIDC client.
- Coordinated state: `shared/platform-ops/gitops/dev-k8s/.images.env` — written by `make build` with `IMAGE_TAG` and all seven service image references.

## Architecture and conventions

- **Coordinated tagging**: The root `make build` computes one `IMAGE_TAG` once using the formula `<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` suffix if `git status --porcelain` reports uncommitted changes) and passes it to every product build. All services in a single `make build` share the same tag.
- **Product enumeration**: Products are declared centrally in `PYTHON_PRODUCTS` and `IMAGE_PRODUCTS` lists at the top of the root `Makefile`; adding a new service requires updating both lists.
- **Layered Makefile design**: Product-specific logic lives in per-product `Makefile`s; cross-cutting behavior is factored into `mk/*.mk` fragments included from both the root and per-product contexts. `mk/defaults.mk` is included twice but guarded against redefinition.
- **Frozen dependency resolution**: Python dependencies are resolved exclusively from `uv.lock` via `uv sync --frozen`; no runtime `pip install` or editable installs.
- **Base image strategy**: All backend services derive from the custom `luban-aiops/base-uv:al2023` base image built from `shared/base-images/base-uv/Dockerfile`. The base image pins `uv` and `python` versions via `--build-arg` and installs them into `/usr/local/bin` and `/app/.python` respectively, running as uid 1000.
- **Image registry convention**: Local images are tagged `luban-aiops/<service>:<tag>`; pushing to a remote registry is done by setting `REGISTRY=` on the command line, which re-tags to `<REGISTRY>/luban-aiops/<service>:<tag>` before `docker push`.
- **Kustomize overlays**: GitOps overlays under `shared/platform-ops/gitops/` are validated via `kustomize build --load-restrictor LoadRestrictionsNone` during `make overlays` (part of `make verify`).
- **Policy synchronization**: A canonical policy bundle at `shared/shared-contracts/policies/policy-default.yaml` is copied to `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` via `make sync-policy`, then validated against a JSON schema via `make validate-policy`.
- **Kind integration**: When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all built images into the named kind cluster after building.

## Conventions and constraints

- **GNU make required**: The root `Makefile` explicitly states it requires GNU make (default on macOS and Linux).
- **Pinned base versions**: `mk/defaults.mk` comments state "Pinned values below are defaults for reproducible builds — never `latest`"; base image versions are passed as `--build-arg` rather than `latest` tags.
- **Command-line overrides win**: `mk/defaults.mk` uses `?=` for every setting so `make build IMAGE_PLATFORM=linux/arm64 REGISTRY=ghcr.io/me` always takes precedence over defaults.
- **Double-inclusion guard**: `mk/defaults.mk` wraps its contents in `ifndef LUBAN_DEFAULTS_INCLUDED ... endif` because both the root Makefile and per-product fragments may include it.
- **Frozen lockfiles enforced**: Both `mk/python.mk` and every product `Dockerfile` use `uv sync --frozen`, ensuring builds cannot drift from `uv.lock`.
- **Non-root containers**: The base image switches to `USER app` (uid 1000); product Dockerfiles inherit this and do not re-run as root.
- **Single coordinated tag per build**: The root `make build` writes `IMAGE_TAG` and per-service image refs to `.images.env` so `make deploy` consumes a consistent set of images.
- **Deploy script contract**: `deploy.sh` expects environment variables like `NAMESPACE` (default `dev-luban-aiops`) and optional flags like `RECONCILE_OIDC_PORTAL_CLIENT`, `SKIP_DELEGATION_SECRETS`, `SKIP_AUDIT_SECRETS`, `SKIP_SKILLS_SECRETS`, `SKIP_OTEL_SECRETS` to control which provisioning steps run.