# Luban AIOps workspace — master Makefile.
#
# Aggregates per-product routines (each product has its own Makefile under
# products/<name>/, built from the shared fragments in mk/) and owns the
# cross-cutting concerns: GitOps overlay checks, the verification gate, and
# the coordinated deploy pipeline.
#
# Forge-agnostic: `make verify` is the pre-commit/pre-push gate and runs the
# same checks locally and under any CI. Requires GNU make (default on macOS
# and Linux).

SHELL := /bin/sh

# Products with a Python (uv) test suite.
PYTHON_PRODUCTS := agent-platform identity-broker tool-gateway
# Products with a container image.
IMAGE_PRODUCTS := agent-platform identity-broker tool-gateway operator-portal

# GitOps overlays rendered as part of verification.
GITOPS_DIR := shared/platform-ops/gitops
OVERLAYS := dev-k8s \
	runtime-profiles/dashscope \
	runtime-profiles/deepseek \
	runtime-profiles/openai

# Coordinated deploy build state (written by `make build`, read by `make deploy`).
IMAGE_STATE := $(GITOPS_DIR)/dev-k8s/.images.env

# Image build settings (override on the command line).
IMAGE_TAG_PREFIX  ?= dev-k8s
IMAGE_TAG_PROFILE ?=
AUTO_LOAD_KIND    ?= false
KIND_CLUSTER_NAME ?=

# Compute the coordinated image tag once (mirrors the former build-images.sh):
# clean tree -> <prefix>[-<profile>]-<gitsha>; dirty -> ...-dirty-<timestamp>.
ifeq ($(origin IMAGE_TAG),undefined)
IMAGE_TAG := $(shell \
	base="$(IMAGE_TAG_PREFIX)$(if $(IMAGE_TAG_PROFILE),-$(IMAGE_TAG_PROFILE),)"; \
	if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		sha=`git rev-parse --short HEAD 2>/dev/null || echo manual`; \
		if [ -n "`git status --porcelain 2>/dev/null`" ]; then \
			echo "$$base-$$sha-dirty-`date +%Y%m%d%H%M%S`"; \
		else \
			echo "$$base-$$sha"; \
		fi; \
	else \
		echo "$$base-`date +%Y%m%d%H%M%S`"; \
	fi)
endif

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' Makefile \
		| awk 'BEGIN {FS = ":.*## "} {printf "  %-16s %s\n", $$1, $$2}'
	@echo ""
	@echo "Per-product routines: make -C products/<name> help"

# --- Per-product delegated routines -----------------------------------------

.PHONY: sync
sync: ## Install/refresh dependencies for every Python product
	@for p in $(PYTHON_PRODUCTS); do $(MAKE) -C products/$$p sync || exit 1; done

.PHONY: test
test: ## Run every product test suite
	@for p in $(PYTHON_PRODUCTS); do $(MAKE) -C products/$$p test || exit 1; done

.PHONY: lint
lint: ## Lint every product Dockerfile (hadolint; docker-run fallback)
	@for p in $(IMAGE_PRODUCTS); do $(MAKE) -C products/$$p lint || exit 1; done

.PHONY: build
build: ## Build all images (coordinated tag) and write .images.env for deploy
	@for p in $(IMAGE_PRODUCTS); do $(MAKE) -C products/$$p build IMAGE_TAG=$(IMAGE_TAG) || exit 1; done
	@echo "IMAGE_TAG=$(IMAGE_TAG)" > $(IMAGE_STATE)
	@echo "AGENT_SERVICE_IMAGE=luban-aiops/agent-service:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "API_GATEWAY_IMAGE=luban-aiops/api-gateway:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "IDENTITY_SERVICE_IMAGE=luban-aiops/identity-service:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "WEB_UI_IMAGE=luban-aiops/web-ui:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "Built images with IMAGE_TAG=$(IMAGE_TAG); wrote $(IMAGE_STATE)"
	@if [ "$(AUTO_LOAD_KIND)" = "true" ]; then \
		if [ -z "$(KIND_CLUSTER_NAME)" ]; then \
			echo "KIND_CLUSTER_NAME is required when AUTO_LOAD_KIND=true" >&2; exit 1; \
		fi; \
		kind load docker-image --name "$(KIND_CLUSTER_NAME)" \
			"luban-aiops/web-ui:$(IMAGE_TAG)" \
			"luban-aiops/api-gateway:$(IMAGE_TAG)" \
			"luban-aiops/agent-service:$(IMAGE_TAG)" \
			"luban-aiops/identity-service:$(IMAGE_TAG)"; \
	fi

.PHONY: push
push: ## Push every product container image (set REGISTRY to re-tag)
	@for p in $(IMAGE_PRODUCTS); do $(MAKE) -C products/$$p push || exit 1; done

# --- Cross-cutting ----------------------------------------------------------

.PHONY: overlays
overlays: ## Render every GitOps overlay (kustomize build check)
	@for o in $(OVERLAYS); do \
		echo "==> kustomize build $$o"; \
		kustomize build $(GITOPS_DIR)/$$o >/dev/null || exit 1; \
	done

.PHONY: verify
verify: test overlays ## Verification gate: product tests + overlay render checks

.PHONY: deploy
deploy: ## Deploy the dev-k8s overlay to the current cluster (wraps deploy.sh)
	@$(GITOPS_DIR)/dev-k8s/deploy.sh

.PHONY: clean
clean: ## Remove Python caches and image build state
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -f $(IMAGE_STATE)
