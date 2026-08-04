# Shared Python base image for all backend services (see
# docs/workspace/python-container-strategy.md).
#
# - Amazon Linux 2023 minimal with a pinned uv; no system Python — uv
#   resolves the interpreter from each product's .python-version during
#   `uv sync` (UV_PYTHON is the deterministic fallback default).
# - Runs as the non-root `app` user (uid 1000); product builds inherit it.
#
# Pinned defaults; override via --build-arg (see `make base-images`).
ARG UV_VERSION=0.12.1
ARG PYTHON_VERSION=3.12

FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal

# Re-declare so the ARGs are in scope inside the stage.
ARG UV_VERSION
ARG PYTHON_VERSION

# Pinned uv install into a world-readable location; no system Python.
# Note: 2023-minimal ships curl-minimal; installing full curl conflicts
# with it, so keep the minimal variant (sufficient for the uv installer).
# UV_INSTALL_DIR must be exported so it reaches `sh` across the pipe.
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
