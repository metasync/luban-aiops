# Shared container-image targets.
#
# Included by each product Makefile (via `include ../../mk/image.mk`). The
# including Makefile must set IMAGE_NAME (the short image name, e.g. platform-gateway)
# and may set IMAGE_CONTEXT (the docker build context, default: product dir).
#
# Overridable settings (IMAGE_PLATFORM, REGISTRY, ...) default in
# mk/defaults.mk, included below; command-line overrides always win, e.g.:
#   make build IMAGE_TAG=v1 REGISTRY=ghcr.io/me IMAGE_PLATFORM=linux/arm64
# Command-line overrides propagate to these targets from the root Makefile too.
#
# Requires GNU make and docker.

SHELL         := /bin/sh

# Pull shared defaults relative to this fragment, so standalone product
# builds resolve the same configuration as root-driven builds.
include $(dir $(lastword $(MAKEFILE_LIST)))defaults.mk

IMAGE_CONTEXT  ?= .
IMAGE_TAG      ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

ifeq ($(REGISTRY),)
IMAGE_REF := luban-aiops/$(IMAGE_NAME):$(IMAGE_TAG)
else
IMAGE_REF := $(REGISTRY)/luban-aiops/$(IMAGE_NAME):$(IMAGE_TAG)
endif

.PHONY: help build push lint

help: ## Show available targets for this product
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*## "} {printf "  %-16s %s\n", $$1, $$2}'

build: ## Build this product's container image (local tag; +registry tag if REGISTRY set)
	docker build --platform $(IMAGE_PLATFORM) -t luban-aiops/$(IMAGE_NAME):$(IMAGE_TAG) $(IMAGE_CONTEXT)
ifneq ($(REGISTRY),)
	docker tag luban-aiops/$(IMAGE_NAME):$(IMAGE_TAG) $(IMAGE_REF)
endif

push: ## Push this product's container image (set REGISTRY to re-tag)
ifneq ($(REGISTRY),)
	docker tag luban-aiops/$(IMAGE_NAME):$(IMAGE_TAG) $(IMAGE_REF)
endif
	docker push $(IMAGE_REF)

lint: ## Lint this product's Dockerfile (hadolint; docker-run fallback)
	@if command -v hadolint >/dev/null 2>&1; then \
		hadolint $(IMAGE_CONTEXT)/Dockerfile; \
	elif command -v docker >/dev/null 2>&1; then \
		docker run --rm -i hadolint/hadolint < $(IMAGE_CONTEXT)/Dockerfile; \
	else \
		echo "hadolint not available; skipping Dockerfile lint"; \
	fi
