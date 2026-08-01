# Shared Python (uv) targets for products with a test suite.
#
# Included by Python product Makefiles (via `include ../../mk/python.mk`).
# Targets run in the product directory, so uv resolves that product's
# pyproject.toml / uv.lock. Requires GNU make and uv.

SHELL := /bin/sh

.PHONY: sync test

sync: ## Install/refresh this product's dependencies (frozen lock)
	uv sync --frozen

test: ## Run this product's test suite
	uv sync --frozen
	uv run pytest
