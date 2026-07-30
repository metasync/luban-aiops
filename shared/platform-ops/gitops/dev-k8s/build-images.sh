#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../../.." && pwd)
STATE_FILE="${STATE_FILE:-$SCRIPT_DIR/.images.env}"
IMAGE_TAG_PREFIX="${IMAGE_TAG_PREFIX:-dev-k8s}"
IMAGE_TAG_PROFILE="${IMAGE_TAG_PROFILE:-}"
IMAGE_BUILD_LABEL="${IMAGE_BUILD_LABEL:-dev-k8s overlay}"

resolve_tag_base() {
  if [ -n "$IMAGE_TAG_PROFILE" ]; then
    echo "${IMAGE_TAG_PREFIX}-${IMAGE_TAG_PROFILE}"
    return
  fi

  echo "$IMAGE_TAG_PREFIX"
}

resolve_default_tag() {
  TAG_BASE=$(resolve_tag_base)
  if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    GIT_REF=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo manual)
    if [ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]; then
      echo "${TAG_BASE}-${GIT_REF}-dirty-$(date +%Y%m%d%H%M%S)"
      return
    fi
    echo "${TAG_BASE}-${GIT_REF}"
    return
  fi

  echo "${TAG_BASE}-$(date +%Y%m%d%H%M%S)"
}

IMAGE_TAG="${IMAGE_TAG:-$(resolve_default_tag)}"
AUTO_LOAD_KIND="${AUTO_LOAD_KIND:-false}"
KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-}"

build_image() {
  IMAGE_NAME="$1"
  IMAGE_CONTEXT="$2"
  FULL_IMAGE="luban-aiops/$IMAGE_NAME:$IMAGE_TAG"

  echo "Building $FULL_IMAGE"
  docker build -t "$FULL_IMAGE" "$REPO_ROOT/$IMAGE_CONTEXT"
}

build_image "agent-service" "products/agent-platform"
build_image "api-gateway" "products/tool-gateway"
build_image "identity-service" "products/identity-broker"
build_image "web-ui" "products/operator-portal"

cat <<EOF > "$STATE_FILE"
IMAGE_TAG=$IMAGE_TAG
AGENT_SERVICE_IMAGE=luban-aiops/agent-service:$IMAGE_TAG
API_GATEWAY_IMAGE=luban-aiops/api-gateway:$IMAGE_TAG
IDENTITY_SERVICE_IMAGE=luban-aiops/identity-service:$IMAGE_TAG
WEB_UI_IMAGE=luban-aiops/web-ui:$IMAGE_TAG
EOF

if [ "$AUTO_LOAD_KIND" = "true" ]; then
  if [ -z "$KIND_CLUSTER_NAME" ]; then
    echo "KIND_CLUSTER_NAME is required when AUTO_LOAD_KIND=true" >&2
    exit 1
  fi

  kind load docker-image --name "$KIND_CLUSTER_NAME" \
    "luban-aiops/web-ui:$IMAGE_TAG" \
    "luban-aiops/api-gateway:$IMAGE_TAG" \
    "luban-aiops/agent-service:$IMAGE_TAG" \
    "luban-aiops/identity-service:$IMAGE_TAG"
fi

echo "Built $IMAGE_BUILD_LABEL images with IMAGE_TAG=$IMAGE_TAG"
echo "Saved image metadata to $STATE_FILE"
