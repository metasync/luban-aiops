#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RECONCILE_OIDC_PORTAL_CLIENT=${RECONCILE_OIDC_PORTAL_CLIENT:-true}

"$SCRIPT_DIR/../deploy-overlay.sh" "$SCRIPT_DIR"

if [ "$RECONCILE_OIDC_PORTAL_CLIENT" = "true" ]; then
  "$SCRIPT_DIR/reconcile-portal-oidc-client.sh"
else
  echo "Skipping browser portal Keycloak client reconciliation."
fi
