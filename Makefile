# Luban AIOps workspace — developer and release routines.
#
# Forge-agnostic by design: the verification gate (`make verify`) runs the same
# checks locally and under any CI, so the project does not couple to a specific
# forge's workflow format. Run `make` (or `make help`) to list targets.
#
# Portable across GNU make and BSD make (macOS): no GNU-only features.

SHELL := /bin/sh

# Python products that carry a test suite (uv-managed).
PYTHON_PRODUCTS := agent-platform identity-broker tool-gateway

# GitOps overlays rendered as part of verification.
GITOPS_DIR := shared/platform-ops/gitops
OVERLAYS := dev-k8s \
	runtime-profiles/dashscope \
	runtime-profiles/deepseek \
	runtime-profiles/openai

# Image build/push settings (override on the command line).
REGISTRY ?=
IMAGE_STATE := $(GITOPS_DIR)/dev-k8s/.images.env

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' Makefile \
		| awk 'BEGIN {FS = ":.*## "} {printf "  %-18s %s\n", $$1, $$2}'

.PHONY: sync
sync: ## Install/refresh dependencies for every Python product (frozen lock)
	@for p in $(PYTHON_PRODUCTS); do \
		echo "==> uv sync $$p"; \
		(cd products/$$p && uv sync --frozen) || exit 1; \
	done

.PHONY: test
test: ## Run every product test suite
	@for p in $(PYTHON_PRODUCTS); do \
		echo "==> pytest $$p"; \
		(cd products/$$p && uv sync --frozen && uv run pytest) || exit 1; \
	done

.PHONY: overlays
overlays: ## Render every GitOps overlay (kustomize build check)
	@for o in $(OVERLAYS); do \
		echo "==> kustomize build $$o"; \
		kustomize build $(GITOPS_DIR)/$$o >/dev/null || exit 1; \
	done

.PHONY: verify
verify: test overlays ## Full pre-commit gate: product tests + overlay render checks

.PHONY: build-images
build-images: ## Build all container images (wraps dev-k8s/build-images.sh)
	@$(GITOPS_DIR)/dev-k8s/build-images.sh

.PHONY: push-images
push-images: ## Push built images; set REGISTRY to re-tag (e.g. REGISTRY=ghcr.io/org)
	@test -f $(IMAGE_STATE) || { echo "No $(IMAGE_STATE); run 'make build-images' first." >&2; exit 1; }
	@. $(IMAGE_STATE); \
	for img in "$$AGENT_SERVICE_IMAGE" "$$API_GATEWAY_IMAGE" "$$IDENTITY_SERVICE_IMAGE" "$$WEB_UI_IMAGE"; do \
		if [ -n "$(REGISTRY)" ]; then \
			target="$(REGISTRY)/$$img"; \
			echo "==> tag + push $$target"; \
			docker tag "$$img" "$$target" && docker push "$$target" || exit 1; \
		else \
			echo "==> push $$img"; \
			docker push "$$img" || exit 1; \
		fi; \
	done

.PHONY: deploy
deploy: ## Deploy the dev-k8s overlay to the current cluster (wraps dev-k8s/deploy.sh)
	@$(GITOPS_DIR)/dev-k8s/deploy.sh

.PHONY: clean
clean: ## Remove Python caches and image build state
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -f $(IMAGE_STATE)
