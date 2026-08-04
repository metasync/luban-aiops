# Python Container Strategy

This note captures the container strategy for Python backend services in this workspace, with specific attention to `uv`, `.python-version`, deterministic builds, and alignment with environment-specific base images.

**Status: the migration to the environment-specific base image (Option B) has been executed.** All Python backend images build from the shared `luban-aiops/base-uv:al2023` base image; the historical Option A baseline is retained below for context.

## Goals

Use a container approach that:

- stays reproducible across local development and future CI pipelines
- keeps Python interpreter selection explicit and reviewable
- works cleanly with `uv` as the standard tool for interpreter and package management
- keeps the current development Kubernetes overlay workflow simple enough for Release 0 delivery
- leaves room for future platform-specific runtime bases such as `amazonlinux:minimal`

## Current Baseline

Current Python service images use:

- the shared base image `luban-aiops/base-uv:al2023` (built from `shared/base-images/base-uv/Dockerfile` by `make base-images`, wired into `make build`)
- Amazon Linux 2023 minimal with a pinned uv (`UV_VERSION` ARG, default pinned — never `latest`)
- no system Python — `uv` resolves the interpreter from the product-local `.python-version` during `uv sync`; `UV_PYTHON` (`PYTHON_VERSION` ARG, default aligned with the workspace pin) is the deterministic fallback when no `.python-version` is found
- `uv.lock` with `uv sync --frozen --no-dev`
- container-level `UV_NO_SYNC=1`
- a non-root `app` user (uid 1000) declared in the base image and enforced by deployment `securityContext` (`runAsNonRoot`, `runAsUser`, `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`)
- a single explicit target platform via `IMAGE_PLATFORM` (default `linux/amd64`, the deployment target), applied to the base image and all product builds; override with `make build IMAGE_PLATFORM=linux/arm64` for native local/kind builds on arm64 hosts (amd64 builds on arm64 hosts run under QEMU emulation and are slower)
- overridable build settings (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`, ...) live in `mk/defaults.mk` — the single configuration source included by the root `Makefile` and `mk/image.mk`; the `.mk` fragments keep processing logic only

Supply-chain note (accepted decision): uv is installed from the pinned-version
installer URL (`https://astral.sh/uv/<version>/install.sh`, which verifies its
own downloaded artifacts) rather than a repo-owned checksummed tarball. The
pinned URL is consciously accepted as sufficient for this phase; revisit only
if stricter provenance guarantees are required.

Current example pattern:

```dockerfile
FROM luban-aiops/base-uv:al2023

WORKDIR /app

COPY --chown=app:app .python-version pyproject.toml uv.lock README.md ./
COPY --chown=app:app src ./src

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "<service-script>"]
```

The environment contract (`PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`, `UV_LINK_MODE=copy`, `UV_NO_SYNC=1`, `UV_PYTHON`, `UV_PYTHON_INSTALL_DIR`) and `USER app` come from the base image; products re-declare `WORKDIR /app` explicitly so Dockerfile linters see the copy destination.

## Historical Baseline (Option A, superseded)

Before the migration, Python service images used:

- the official `uv` Python base image
- product-local `.python-version`
- `uv.lock`
- `uv sync --frozen --no-dev`
- container-level `UV_NO_SYNC=1`

Current example pattern:

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1

WORKDIR /app

COPY .python-version pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

CMD ["uv", "run", "<service-script>"]
```

## Why Option A Was The Original Choice

- it is simple and operationally predictable for the current development k8s overlay workflow
- it minimizes bootstrapping logic inside the Dockerfile
- it works well with the existing product-local build contexts
- it already enforces lockfile-based dependency determinism
- it avoids an extra installation step for `uv` itself during image build

## Adopted Strategy (Option B, executed)

The migration implemented the environment-specific base:

- start from `public.ecr.aws/amazonlinux/amazonlinux:2023-minimal`
- install a pinned `uv` (versioned installer URL, `UV_INSTALL_DIR=/usr/local/bin`)
- let `uv` resolve the interpreter using `.python-version` (fallback: `UV_PYTHON`)
- let `uv` create the environment and install packages
- run as a non-root `app` user (uid 1000) end to end

Representative shape (the actual base image):

```dockerfile
ARG UV_VERSION=0.12.1
ARG PYTHON_VERSION=3.12

FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal

ARG UV_VERSION
ARG PYTHON_VERSION

RUN dnf install -y curl-minimal ca-certificates tar gzip shadow-utils && \
    export UV_INSTALL_DIR=/usr/local/bin && \
    curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh && \
    useradd --uid 1000 --create-home app && \
    dnf clean all

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1 \
    UV_PYTHON=${PYTHON_VERSION} \
    UV_PYTHON_INSTALL_DIR=/app/.python \
    HOME=/home/app

WORKDIR /app
RUN chown app:app /app
USER app
```

This is conceptually cleaner when:

- CI or runtime policy requires a platform-standard base image
- the organization wants `uv` to manage both Python and packages end to end
- base image selection must align with enterprise patching, hardening, or vulnerability scanning rules

## Trade-Offs

### Option A: official `uv` Python base

Strengths:

- lowest Dockerfile complexity
- fastest path for the current workspace
- fewer moving parts during image build
- easier local troubleshooting

Risks:

- base image choice is less aligned with environment-specific runtime standards
- future CI systems may still require a different base strategy

### Option B: environment-specific base plus installed `uv`

Strengths:

- better alignment with platform-standard base images
- clearer fit for future `luban-ci` style pipelines
- allows `uv` to manage interpreter resolution from `.python-version`

Risks:

- more moving parts during build
- more responsibility for OS package bootstrapping
- higher risk of subtle image drift if `uv` installation and Python bootstrap are not pinned carefully

## Decision History

The original recommendation was a two-stage decision: keep the official `uv`
base for Release 0, then migrate to an environment-specific base once the
deployment baseline was fixed. After SPEC-010 delivery the migration was
executed in one move across all four Python products, because:

- the repo was already aligned with `uv` and `.python-version`
- the gateway split had already surfaced per-product Dockerfile drift
  (platform-gateway on amazonlinux, the others on bookworm-slim) that a
  shared base image removes
- non-root enforcement became a requirement, and the shared base is the
  natural single place to own the runtime user

## Preconditions (met at migration time)

- target base image fixed: `public.ecr.aws/amazonlinux/amazonlinux:2023-minimal`
- OS package installation path: `dnf` with a bounded install set, cleaned in the same layer
- `uv` installation pinned: versioned installer URL via the `UV_VERSION` ARG (default pinned, never `latest`)
- interpreter resolution: `uv sync --frozen` downloads the managed interpreter from `.python-version`; `UV_PYTHON` provides a deterministic fallback

## Rollout (executed)

All four Python products (`agent-platform`, `identity-broker`,
`platform-gateway`, `tool-gateway`) switched to the shared base in one
change; `operator-portal` (nginx) is out of scope for the uv base but moved
to `nginxinc/nginx-unprivileged` on port 8080 in the same change. All app
deployments carry a non-root `securityContext`.

## Current Workspace Rule

- all Python backend images build `FROM luban-aiops/base-uv:al2023`; build it with `make base-images` (already a prerequisite of `make build`)
- keep `.python-version` in the repo root and Python product roots; it selects the runtime interpreter
- keep `uv.lock` with `uv sync --frozen --no-dev` in image builds
- keep `UV_NO_SYNC=1` at the image level (inherited from the base)
- bump `BASE_UV_UV_VERSION` / `BASE_UV_PYTHON_VERSION` defaults (root `Makefile` and the Dockerfile ARGs) together with any workspace-wide toolchain migration; never default to `latest`
- keep the non-root `app` user (uid 1000) and the matching deployment `securityContext`; no service may regress to root
- prefer documentation and validation passes over speculative container churn
