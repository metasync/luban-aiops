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
PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway
# Products with a container image.
IMAGE_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway operator-portal

# GitOps overlays rendered as part of verification.
GITOPS_DIR := shared/platform-ops/gitops

# End-to-end demo scripts run against a deployed cluster via `make e2e`.
E2E_DIR := shared/platform-ops/e2e

# Self-contained tutorial samples; installed into the dev cluster out-of-band
# via `make deploy-samples` so the base overlay never names a sample (SPEC-050 R-11).
SAMPLES_DIR := samples
# Target namespace for cluster-facing sample helpers.
NAMESPACE ?= dev-luban-aiops

OVERLAYS := dev-k8s \
	runtime-profiles/default \
	runtime-profiles/mutating-dev \
	runtime-profiles/browser-dev

# Coordinated deploy build state (written by `make build`, read by `make deploy`).
IMAGE_STATE := $(GITOPS_DIR)/dev-k8s/.images.env

# Platform release version (semver; single source of truth is the root
# VERSION file). Prefixes the coordinated image tag and is kept in lockstep
# with every product version — enforced by `make validate-version`.
PLATFORM_VERSION := $(shell cat VERSION 2>/dev/null)

# Overridable build settings (IMAGE_PLATFORM, BASE_UV_*, kind loading, ...).
# Config lives in mk/defaults.mk; this Makefile holds processing logic.
include mk/defaults.mk

# Compute the coordinated image tag once (mirrors the former build-images.sh):
# clean tree -> <semver>-<prefix>[-<profile>]-<gitsha>;
# dirty -> ...-dirty-<timestamp>.
ifeq ($(origin IMAGE_TAG),undefined)
IMAGE_TAG := $(shell \
	base="$(if $(PLATFORM_VERSION),$(PLATFORM_VERSION)-)$(IMAGE_TAG_PREFIX)$(if $(IMAGE_TAG_PROFILE),-$(IMAGE_TAG_PROFILE),)"; \
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

.PHONY: base-images
base-images: ## Build shared base images (base-uv)
	docker build --platform $(IMAGE_PLATFORM) \
		--build-arg UV_VERSION=$(BASE_UV_UV_VERSION) \
		--build-arg PYTHON_VERSION=$(BASE_UV_PYTHON_VERSION) \
		-t $(BASE_UV_IMAGE):$(BASE_UV_TAG) shared/base-images/base-uv

.PHONY: build
build: base-images ## Build all images (coordinated tag) and write .images.env for deploy
	@for p in $(IMAGE_PRODUCTS); do $(MAKE) -C products/$$p build IMAGE_TAG=$(IMAGE_TAG) IMAGE_PLATFORM=$(IMAGE_PLATFORM) || exit 1; done
	@echo "IMAGE_TAG=$(IMAGE_TAG)" > $(IMAGE_STATE)
	@echo "AGENT_SERVICE_IMAGE=luban-aiops/agent-service:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "PLATFORM_GATEWAY_IMAGE=luban-aiops/platform-gateway:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "TOOL_GATEWAY_IMAGE=luban-aiops/tool-gateway:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "IDENTITY_SERVICE_IMAGE=luban-aiops/identity-service:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "AUDIT_SERVICE_IMAGE=luban-aiops/audit-service:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "SKILLS_HUB_IMAGE=luban-aiops/skills-hub:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "INCIDENT_SERVICE_IMAGE=luban-aiops/incident-service:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "EXECUTION_RUNTIME_IMAGE=luban-aiops/execution-runtime:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "WEB_UI_IMAGE=luban-aiops/web-ui:$(IMAGE_TAG)" >> $(IMAGE_STATE)
	@echo "Built images with IMAGE_TAG=$(IMAGE_TAG); wrote $(IMAGE_STATE)"
	@if [ "$(AUTO_LOAD_KIND)" = "true" ]; then \
		if [ -z "$(KIND_CLUSTER_NAME)" ]; then \
			echo "KIND_CLUSTER_NAME is required when AUTO_LOAD_KIND=true" >&2; exit 1; \
		fi; \
		kind load docker-image --name "$(KIND_CLUSTER_NAME)" \
			"luban-aiops/web-ui:$(IMAGE_TAG)" \
			"luban-aiops/platform-gateway:$(IMAGE_TAG)" \
			"luban-aiops/tool-gateway:$(IMAGE_TAG)" \
			"luban-aiops/agent-service:$(IMAGE_TAG)" \
			"luban-aiops/identity-service:$(IMAGE_TAG)" \
			"luban-aiops/audit-service:$(IMAGE_TAG)" \
			"luban-aiops/skills-hub:$(IMAGE_TAG)" \
			"luban-aiops/incident-service:$(IMAGE_TAG)" \
			"luban-aiops/execution-runtime:$(IMAGE_TAG)"; \
	fi

.PHONY: push
push: ## Push every product container image (set REGISTRY to re-tag)
	@for p in $(IMAGE_PRODUCTS); do $(MAKE) -C products/$$p push || exit 1; done

# --- Policy management ------------------------------------------------------

POLICY_CANONICAL := shared/shared-contracts/policies/policy-default.yaml
POLICY_TARGETS := \
	products/tool-gateway/src/tool_gateway/policies/policy-default.yaml \
	products/platform-gateway/src/platform_gateway/policies/policy-default.yaml \
	shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml

.PHONY: sync-policy
sync-policy: ## Copy canonical policy bundle to all consumer locations
	@for t in $(POLICY_TARGETS); do \
		cp $(POLICY_CANONICAL) "$$t" && echo "synced $$t" || exit 1; \
	done

.PHONY: validate-policy
validate-policy: ## Validate canonical policy bundle against JSON schema
	@cd products/tool-gateway && uv run python ../../shared/shared-contracts/scripts/validate_policy.py

.PHONY: validate-policy-scenarios
validate-policy-scenarios: ## Evaluate scenario expectations against the canonical bundle (both engines)
	@cd products/platform-gateway && uv run python ../../shared/shared-contracts/scripts/validate_policy_scenarios.py --engine api
	@cd products/tool-gateway && uv run python ../../shared/shared-contracts/scripts/validate_policy_scenarios.py --engine tools

.PHONY: policy-diff
policy-diff: ## Per-(role, action) outcome report: canonical vs CANDIDATE=<path> bundle
	@if [ -z "$(CANDIDATE)" ]; then \
		echo "usage: make policy-diff CANDIDATE=<path-to-candidate-bundle>" >&2; exit 2; \
	fi
	@cd products/platform-gateway && uv run python ../../shared/shared-contracts/scripts/policy_diff.py --engine api --candidate "$(abspath $(CANDIDATE))"
	@cd products/tool-gateway && uv run python ../../shared/shared-contracts/scripts/policy_diff.py --engine tools --candidate "$(abspath $(CANDIDATE))"

.PHONY: validate-version
validate-version: ## Validate version lockstep between VERSION, products, and portal
	@cd products/tool-gateway && uv run python ../../shared/shared-contracts/scripts/validate_version.py ../..

# --- Cross-cutting ----------------------------------------------------------

.PHONY: overlays
overlays: ## Render every GitOps overlay (kustomize build check)
	@for o in $(OVERLAYS); do \
		echo "==> kustomize build $$o"; \
		kustomize build --load-restrictor LoadRestrictionsNone $(GITOPS_DIR)/$$o >/dev/null || exit 1; \
	done

.PHONY: verify
verify: test overlays validate-policy validate-policy-scenarios validate-version ## Verification gate: tests + overlays + policy + scenarios + version lockstep

.PHONY: deploy
deploy: ## Deploy the dev-k8s overlay to the current cluster (wraps deploy.sh)
	@$(GITOPS_DIR)/dev-k8s/deploy.sh

.PHONY: deploy-samples
deploy-samples: ## Install tutorial sample skills into the dev cluster (SAMPLE=<path> selects one; default all)
	@SAMPLE="$(SAMPLE)" $(SAMPLES_DIR)/deploy-samples.sh $(NAMESPACE)

.PHONY: undeploy-samples
undeploy-samples: ## Remove all tutorial sample skills from the dev cluster
	@ACTION=undeploy $(SAMPLES_DIR)/deploy-samples.sh $(NAMESPACE)

.PHONY: e2e
e2e: ## Run the e2e demo scripts against the deployed dev cluster
	@echo "Prerequisites: 'make deploy' completed, plus port-forwards for the chat legs:"
	@echo "  kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000"
	@echo "  kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000"
	@status=0; \
	for script in $(E2E_DIR)/skills-demo.sh $(E2E_DIR)/incident-demo.sh $(E2E_DIR)/mutating-demo.sh; do \
		echo "==> $$script"; \
		sh $$script || status=1; \
	done; \
	if [ $$status -ne 0 ]; then echo "E2E: one or more demos failed"; exit 1; fi; \
	echo "E2E_OK: all demos passed"

.PHONY: clean
clean: ## Remove Python caches and image build state
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -f $(IMAGE_STATE)
