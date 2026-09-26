# operator-portal product routines (SPA served by nginx).
#
# Usage:  make -C products/operator-portal <target>   (or cd here and run make)
# Image targets plus the SPA frontend suite. This product has no Python (uv)
# test suite; frontend tests and the production build live in web-ui/app and run
# through npm via the `test` and `web-build` targets below. Run `make help`.

IMAGE_NAME := web-ui
# Repo-root build context: the multi-stage Dockerfile needs the root VERSION
# file (PLATFORM_VERSION injection) plus the Vite project in web-ui/app.
IMAGE_CONTEXT := ../..
IMAGE_DOCKERFILE := Dockerfile

# The SPA project (Vite + Vitest). Frontend tests and the production build run
# through npm here rather than uv; `make verify` delegates to the test/web-build
# targets below (SPEC-063 R-8c). Vitest runs the whole suite and fails on zero
# tests, so there is no skip/zero-tests green path.
WEB_UI_APP := web-ui/app

include ../../mk/image.mk

.PHONY: test web-build
test: ## Run the portal SPA unit suite (vitest run; fails on zero tests, no skip toggle)
	npm --prefix $(WEB_UI_APP) test

web-build: ## Typecheck and build the portal SPA (tsc --noEmit && vite build)
	npm --prefix $(WEB_UI_APP) run build
