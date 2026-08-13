#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RECONCILE_OIDC_PORTAL_CLIENT=${RECONCILE_OIDC_PORTAL_CLIENT:-true}
NAMESPACE=${NAMESPACE:-dev-luban-aiops}

"$SCRIPT_DIR/../deploy-overlay.sh" "$SCRIPT_DIR"

# Provision token-delegation secrets (SPEC-008) unless skipped.
# Set SKIP_DELEGATION_SECRETS=true when secrets are injected externally (e.g. CI).
"$SCRIPT_DIR/../sync-delegation-secrets.sh" "$NAMESPACE"

# Provision durable-audit-trail ingest secrets (SPEC-013) unless skipped.
# Set SKIP_AUDIT_SECRETS=true when secrets are injected externally (e.g. CI).
"$SCRIPT_DIR/../sync-audit-secrets.sh" "$NAMESPACE"

if [ "$RECONCILE_OIDC_PORTAL_CLIENT" = "true" ]; then
  # Self-contained realm (groups + test users) before the portal client, so
  # the client's `groups` scope resolves in the new realm.
  "$SCRIPT_DIR/../reconcile-luban-realm.sh"
  "$SCRIPT_DIR/reconcile-portal-oidc-client.sh"
else
  echo "Skipping browser portal Keycloak client reconciliation."
fi
