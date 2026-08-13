#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
STATE_FILE="${STATE_FILE:-$SCRIPT_DIR/dev-k8s/.images.env}"
OVERLAY_DIR="${1:-}"
NAMESPACE="${NAMESPACE:-dev-luban-aiops}"

if [ -z "$OVERLAY_DIR" ]; then
  echo "Usage: $0 <overlay-directory>" >&2
  exit 1
fi

case "$OVERLAY_DIR" in
  /*) ;;
  *) OVERLAY_DIR="$SCRIPT_DIR/$OVERLAY_DIR" ;;
esac

if [ ! -d "$OVERLAY_DIR" ]; then
  echo "Overlay directory not found: $OVERLAY_DIR" >&2
  exit 1
fi

if [ -f "$STATE_FILE" ]; then
  # shellcheck disable=SC1090
  . "$STATE_FILE"
fi

IMAGE_TAG="${IMAGE_TAG:-}"
AGENT_SERVICE_IMAGE="${AGENT_SERVICE_IMAGE:-}"
AUDIT_SERVICE_IMAGE="${AUDIT_SERVICE_IMAGE:-}"
IDENTITY_SERVICE_IMAGE="${IDENTITY_SERVICE_IMAGE:-}"
PLATFORM_GATEWAY_IMAGE="${PLATFORM_GATEWAY_IMAGE:-}"
TOOL_GATEWAY_IMAGE="${TOOL_GATEWAY_IMAGE:-}"
WEB_UI_IMAGE="${WEB_UI_IMAGE:-}"

if [ -z "$IMAGE_TAG" ]; then
  echo "IMAGE_TAG is not set. Run 'make build' first or export IMAGE_TAG." >&2
  exit 1
fi

AGENT_SERVICE_IMAGE="${AGENT_SERVICE_IMAGE:-luban-aiops/agent-service:$IMAGE_TAG}"
AUDIT_SERVICE_IMAGE="${AUDIT_SERVICE_IMAGE:-luban-aiops/audit-service:$IMAGE_TAG}"
IDENTITY_SERVICE_IMAGE="${IDENTITY_SERVICE_IMAGE:-luban-aiops/identity-service:$IMAGE_TAG}"
PLATFORM_GATEWAY_IMAGE="${PLATFORM_GATEWAY_IMAGE:-luban-aiops/platform-gateway:$IMAGE_TAG}"
TOOL_GATEWAY_IMAGE="${TOOL_GATEWAY_IMAGE:-luban-aiops/tool-gateway:$IMAGE_TAG}"
WEB_UI_IMAGE="${WEB_UI_IMAGE:-luban-aiops/web-ui:$IMAGE_TAG}"

kubectl apply -k "$OVERLAY_DIR"

kubectl -n "$NAMESPACE" set image deployment/web-ui \
  "web-ui=$WEB_UI_IMAGE"
kubectl -n "$NAMESPACE" set image deployment/platform-gateway \
  "platform-gateway=$PLATFORM_GATEWAY_IMAGE"
kubectl -n "$NAMESPACE" set image deployment/tool-gateway \
  "tool-gateway=$TOOL_GATEWAY_IMAGE"
kubectl -n "$NAMESPACE" set image deployment/agent-service \
  "agent-service=$AGENT_SERVICE_IMAGE"
kubectl -n "$NAMESPACE" set image deployment/identity-service \
  "identity-service=$IDENTITY_SERVICE_IMAGE"
kubectl -n "$NAMESPACE" set image deployment/audit-service \
  "audit-service=$AUDIT_SERVICE_IMAGE"

kubectl -n "$NAMESPACE" rollout status deployment/web-ui --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/platform-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/tool-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/agent-service --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/identity-service --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/audit-service --timeout=120s

echo "Applied overlay $OVERLAY_DIR with IMAGE_TAG=$IMAGE_TAG in namespace $NAMESPACE"
