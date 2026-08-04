# Shared build configuration defaults.
#
# Single source of truth for overridable build settings. Included by the root
# Makefile and by the shared fragments in mk/ so that root invocations and
# standalone product invocations (`make -C products/<name>`) resolve the same
# defaults. Config lives here; processing logic lives in the Makefiles and
# .mk fragments.
#
# All values use `?=`, so command-line overrides always win, e.g.:
#   make build IMAGE_PLATFORM=linux/arm64
#   make base-images BASE_UV_UV_VERSION=0.13.0
#
# Pinned values below are defaults for reproducible builds — never `latest`.

# Guard against double inclusion (root Makefile and fragments may both
# include this file in one parse).
ifndef LUBAN_DEFAULTS_INCLUDED
LUBAN_DEFAULTS_INCLUDED := 1

# --- Image builds -----------------------------------------------------------

# Target platform for all image builds, including the shared base image.
# The deployment target is linux/amd64; use linux/arm64 for native
# local/kind builds on arm64 hosts.
IMAGE_PLATFORM ?= linux/amd64

# Coordinated image tag prefix/profile used by the root `make build`
# (final tag: <prefix>[-<profile>]-<gitsha>[-dirty-<timestamp>]).
IMAGE_TAG_PREFIX  ?= dev-k8s
IMAGE_TAG_PROFILE ?=

# Optional registry re-tag/push target (empty = local images only).
REGISTRY ?=

# Auto-load built images into a local kind cluster after `make build`
# (KIND_CLUSTER_NAME is required when enabled).
AUTO_LOAD_KIND    ?= false
KIND_CLUSTER_NAME ?=

# Note: IMAGE_TAG and IMAGE_CONTEXT deliberately stay in mk/image.mk —
# IMAGE_TAG has a computed standalone fallback and the root Makefile relies
# on `$(origin IMAGE_TAG)`; IMAGE_CONTEXT is a per-product fragment hook.

# --- Shared base image (shared/base-images/base-uv) -------------------------

BASE_UV_IMAGE          ?= luban-aiops/base-uv
BASE_UV_TAG            ?= al2023
BASE_UV_UV_VERSION     ?= 0.12.1
BASE_UV_PYTHON_VERSION ?= 3.12

endif # LUBAN_DEFAULTS_INCLUDED
