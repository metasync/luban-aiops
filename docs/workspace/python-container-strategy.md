# Python Container Strategy

This note captures the recommended container strategy for Python backend services in this workspace, with specific attention to `uv`, `.python-version`, deterministic builds, and future alignment with environment-specific base images.

## Goals

Use a container approach that:

- stays reproducible across local development and future CI pipelines
- keeps Python interpreter selection explicit and reviewable
- works cleanly with `uv` as the standard tool for interpreter and package management
- keeps the current development Kubernetes overlay workflow simple enough for Release 0 delivery
- leaves room for future platform-specific runtime bases such as `amazonlinux:minimal`

## Current Baseline

Current Python service images use:

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

## Why The Current Baseline Still Makes Sense

- it is simple and operationally predictable for the current development k8s overlay workflow
- it minimizes bootstrapping logic inside the Dockerfile
- it works well with the existing product-local build contexts
- it already enforces lockfile-based dependency determinism
- it avoids an extra installation step for `uv` itself during image build

## Future Candidate Strategy

The alternative you suggested is valid and worth planning for:

- start from an environment-specific base such as `amazonlinux:minimal`
- install `uv`
- let `uv` resolve the interpreter using `.python-version`
- let `uv` create the environment and install packages

Representative shape:

```dockerfile
FROM amazonlinux:minimal

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1

WORKDIR /app

RUN microdnf install -y curl ca-certificates \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv

COPY .python-version pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv python install \
    && uv sync --frozen --no-dev

CMD ["uv", "run", "<service-script>"]
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

## Recommendation

Use a two-stage decision:

1. keep the current official `uv` base image strategy for Release 0 and the active development k8s overlay workflow
2. prepare for a controlled follow-up migration to an environment-specific base once the target CI and deployment baseline is fixed

This is the recommended path because:

- the repo is already aligned with `uv` and `.python-version`
- the current delivery risk is in runtime and platform behavior, not base image selection
- switching base strategy now would add build-surface churn without immediate functional payoff
- the future migration will be easier because the codebase already treats `uv` as the single packaging interface

## Preconditions For Migration

Before switching all Python services to an environment-specific base, confirm:

- the target base image for CI and runtime is final
- the OS package installation path is stable and approved
- `uv` installation is pinned to a repeatable method or version
- `uv python install` behavior is acceptable in offline, proxied, or restricted enterprise build environments
- vulnerability scanning and patch cadence are better with the new base than with the current one

## Suggested Rollout

When ready, migrate in this order:

1. prototype the new strategy in one service such as `identity-broker`
2. verify image size, vulnerability scan results, startup time, and build reproducibility
3. update the shared container convention docs
4. roll the strategy across `tool-gateway` and `agent-platform`

## Current Workspace Rule

Until that migration is explicitly started:

- keep Python backend images on the official `uv` Python base
- keep `.python-version` in the repo root and Python product roots
- keep `uv.lock` in deterministic image build paths
- keep `UV_NO_SYNC=1` at the image level
- prefer documentation and validation passes over speculative container churn
