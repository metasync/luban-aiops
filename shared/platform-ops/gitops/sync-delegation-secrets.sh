#!/bin/sh

# Provision the token-delegation secrets for the dev-k8s overlay (SPEC-008).
#
# The platform-gateway exchanges the user's portal JWT for a short-lived,
# audience-bound delegated token at the identity-broker.  That exchange
# requires a shared service credential:
#
#   platform-gateway  →  PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET
#   identity-broker   →  IDENTITY_SERVICE_CLIENTS (client registry)
#
# Both values must carry the same client secret.  This script generates one
# (or uses DELEGATION_CLIENT_SECRET if already exported), writes the two
# runtime-secrets.env files, syncs both Kubernetes secrets, and restarts the
# affected deployments.
#
# Usage:
#   shared/platform-ops/gitops/sync-delegation-secrets.sh [namespace]
#
# Override the generated secret:
#   DELEGATION_CLIENT_SECRET=my-secret shared/platform-ops/gitops/sync-delegation-secrets.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_DELEGATION_SECRETS=true make deploy

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NAMESPACE="${1:-dev-luban-aiops}"

if [ "${SKIP_DELEGATION_SECRETS:-}" = "true" ]; then
  echo "SKIP_DELEGATION_SECRETS=true; skipping delegation-secret provisioning."
  exit 0
fi

# --- shared secret --------------------------------------------------------

if [ -z "${DELEGATION_CLIENT_SECRET:-}" ]; then
  DELEGATION_CLIENT_SECRET=$(openssl rand -hex 24)
  echo "Generated DELEGATION_CLIENT_SECRET (export it to reuse across runs)."
fi

# --- platform-gateway secret -----------------------------------------------

PG_SECRET_DIR="$SCRIPT_DIR/dev-k8s/base/platform-gateway"
PG_SECRET_FILE="$PG_SECRET_DIR/runtime-secrets.env"

cat > "$PG_SECRET_FILE" <<EOF
PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET=$DELEGATION_CLIENT_SECRET
EOF

kubectl -n "$NAMESPACE" create secret generic platform-gateway-runtime-secrets \
  --from-env-file="$PG_SECRET_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Synced secret 'platform-gateway-runtime-secrets' in namespace '$NAMESPACE'."

# --- identity-broker secret ------------------------------------------------

IB_SECRET_DIR="$SCRIPT_DIR/dev-k8s/base/identity-broker"
IB_SECRET_FILE="$IB_SECRET_DIR/runtime-secrets.env"

cat > "$IB_SECRET_FILE" <<EOF
IDENTITY_SERVICE_CLIENTS=platform-gateway:${DELEGATION_CLIENT_SECRET}:tool-gateway
EOF

kubectl -n "$NAMESPACE" create secret generic identity-service-runtime-secrets \
  --from-env-file="$IB_SECRET_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Synced secret 'identity-service-runtime-secrets' in namespace '$NAMESPACE'."

# --- restart affected deployments -----------------------------------------

kubectl -n "$NAMESPACE" rollout restart deployment/platform-gateway
kubectl -n "$NAMESPACE" rollout restart deployment/identity-service

echo ""
echo "Delegation secrets provisioned.  Waiting for rollout..."
kubectl -n "$NAMESPACE" rollout status deployment/platform-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/identity-service --timeout=120s

echo ""
echo "Token delegation chain is now configured."
echo "The agent should be able to discover and invoke tools via tool-gateway."
