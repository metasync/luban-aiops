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

# Coordinated deploy build state (written by build-images.sh, read by deploy).
IMAGE_STATE := $(GITOPS_DIR)/dev-k8s/.images.env

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
build: ## Build every product container image (per-product, for iteration)
	@for p in $(IMAGE_PRODUCTS); do $(MAKE) -C products/$$p build || exit 1; done

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

.PHONY: build-images
build-images: ## Coordinated deploy build of all images (writes .images.env)
	@$(GITOPS_DIR)/dev-k8s/build-images.sh

.PHONY: deploy
deploy: ## Deploy the dev-k8s overlay to the current cluster (wraps deploy.sh)
	@$(GITOPS_DIR)/dev-k8s/deploy.sh

.PHONY: clean
clean: ## Remove Python caches and image build state
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -f $(IMAGE_STATE)
