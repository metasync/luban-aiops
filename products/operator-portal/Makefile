# operator-portal product routines (SPA served by nginx).
#
# Usage:  make -C products/operator-portal <target>   (or cd here and run make)
# Image targets only — this product has no Python test suite; frontend tests
# live in web-ui/app (`npm test`). Run `make help`.

IMAGE_NAME := web-ui
# Repo-root build context: the multi-stage Dockerfile needs the root VERSION
# file (PLATFORM_VERSION injection) plus the Vite project in web-ui/app.
IMAGE_CONTEXT := ../..
IMAGE_DOCKERFILE := Dockerfile

include ../../mk/image.mk
