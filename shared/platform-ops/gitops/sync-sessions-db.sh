#!/bin/sh

# Provision the sessions database for the agent-platform session store
# (SPEC-016).
#
# The session store moved from Redis to Postgres. No secrets are involved
# (the DSN uses the committed dev credentials), so this script only
# ensures the 'sessions' database exists: fresh clusters get it via the
# postgres initdb ConfigMap, existing clusters get it here through an
# idempotent CREATE DATABASE on the postgres pod. It then restarts the
# agent-service deployment so the store connects with the database in
# place. Until the restart lands, the service fails open on its
# in-memory fallback.
#
# Usage:
#   shared/platform-ops/gitops/sync-sessions-db.sh [namespace]

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NAMESPACE="${1:-dev-luban-aiops}"

# --- sessions database (idempotent for existing clusters) -------------------

POSTGRES_POD=$(kubectl -n "$NAMESPACE" get pods -l app=postgres \
  -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POSTGRES_POD" ]; then
  echo "No postgres pod found in namespace '$NAMESPACE'; deploy the overlay first." >&2
  exit 1
fi
kubectl -n "$NAMESPACE" exec "$POSTGRES_POD" -- \
  sh -c 'psql -U audit -tAc "SELECT 1 FROM pg_database WHERE datname = '\''sessions'\''" | grep -q 1 \
    || psql -U audit -c "CREATE DATABASE sessions"'
echo "Database 'sessions' is present on $POSTGRES_POD."

# --- restart the agent platform ---------------------------------------------

kubectl -n "$NAMESPACE" rollout restart deployment/agent-service

echo ""
echo "Session store database provisioned. Waiting for rollout..."
kubectl -n "$NAMESPACE" rollout status deployment/agent-service --timeout=120s

echo ""
echo "The agent-platform session store now persists to Postgres."
