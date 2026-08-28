#!/bin/sh

# Provision the incident intake/query credentials for the dev-k8s overlay
# (SPEC-015).
#
# incident-service authenticates two kinds of callers:
#
#   - the Alertmanager webhook (POST /api/v1/webhooks/alertmanager) with a
#     shared bearer token: INCIDENT_WEBHOOK_TOKEN
#   - platform query callers against a static registry (INCIDENT_QUERY_CLIENTS):
#
#       incident-service  →  INCIDENT_QUERY_CLIENTS (client registry)
#       platform-gateway  →  PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET
#       tool-gateway      →  GATEWAY_INCIDENTS_CLIENT_SECRET
#       agent-service     →  AGENT_INCIDENT_CLIENT_SECRET (SPEC-043,
#                            incident-report assembly)
#
# This script also ensures the 'incidents' database exists (fresh clusters
# get it via the postgres initdb script; existing clusters get it here
# through an idempotent CREATE DATABASE on the postgres pod). It then
# generates the webhook token and one shared query secret (or uses
# INCIDENT_WEBHOOK_TOKEN / INCIDENT_QUERY_SECRET if already exported),
# writes/updates the runtime-secrets.env files (all files are updated in
# place so audit/OTel secrets provisioned earlier are preserved), syncs the
# Kubernetes secrets, and restarts the affected deployments.
#
# Usage:
#   shared/platform-ops/gitops/sync-incident-secrets.sh [namespace]
#
# Override the generated secrets:
#   INCIDENT_WEBHOOK_TOKEN=my-token INCIDENT_QUERY_SECRET=my-secret \
#     shared/platform-ops/gitops/sync-incident-secrets.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_INCIDENT_SECRETS=true make deploy

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NAMESPACE="${1:-dev-luban-aiops}"

if [ "${SKIP_INCIDENT_SECRETS:-}" = "true" ]; then
  echo "SKIP_INCIDENT_SECRETS=true; skipping incident-secret provisioning."
  exit 0
fi

# --- incidents database (idempotent for existing clusters) ------------------

POSTGRES_POD=$(kubectl -n "$NAMESPACE" get pods -l app=postgres \
  -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POSTGRES_POD" ]; then
  echo "No postgres pod found in namespace '$NAMESPACE'; deploy the overlay first." >&2
  exit 1
fi
kubectl -n "$NAMESPACE" exec "$POSTGRES_POD" -- \
  sh -c 'psql -U audit -tAc "SELECT 1 FROM pg_database WHERE datname = '\''incidents'\''" | grep -q 1 \
    || psql -U audit -c "CREATE DATABASE incidents"'
echo "Database 'incidents' is present on $POSTGRES_POD."

# --- shared secrets ----------------------------------------------------------

if [ -z "${INCIDENT_WEBHOOK_TOKEN:-}" ]; then
  INCIDENT_WEBHOOK_TOKEN=$(openssl rand -hex 24)
  echo "Generated INCIDENT_WEBHOOK_TOKEN (export it to reuse across runs)."
fi
if [ -z "${INCIDENT_QUERY_SECRET:-}" ]; then
  INCIDENT_QUERY_SECRET=$(openssl rand -hex 24)
  echo "Generated INCIDENT_QUERY_SECRET (export it to reuse across runs)."
fi

# Insert or replace KEY=VALUE in an env file, preserving all other lines.
upsert_env_line() {
  upsert_file="$1"
  upsert_key="$2"
  upsert_line="$3"
  touch "$upsert_file"
  if grep -q "^${upsert_key}=" "$upsert_file"; then
    sed -i.bak "s|^${upsert_key}=.*|${upsert_line}|" "$upsert_file"
    rm -f "${upsert_file}.bak"
  else
    printf '%s\n' "$upsert_line" >> "$upsert_file"
  fi
}

sync_secret() {
  secret_name="$1"
  env_file="$2"
  kubectl -n "$NAMESPACE" create secret generic "$secret_name" \
    --from-env-file="$env_file" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo "Synced secret '$secret_name' in namespace '$NAMESPACE'."
}

# Merge a single KEY=VALUE into an existing cluster Secret without touching
# any other key; create the Secret with just that key if it does not exist
# yet (sibling sync scripts fill in the remaining keys on their next run).
merge_secret_key() {
  merge_secret_name="$1"
  merge_line="$2"
  merge_value_b64=$(printf '%s' "${merge_line#*=}" | base64 | tr -d '\n')
  merge_key="${merge_line%%=*}"
  if kubectl -n "$NAMESPACE" get secret "$merge_secret_name" >/dev/null 2>&1; then
    kubectl -n "$NAMESPACE" patch secret "$merge_secret_name" \
      --type merge \
      -p "{\"data\":{\"${merge_key}\":\"${merge_value_b64}\"}}"
    echo "Merged '$merge_key' into existing secret '$merge_secret_name'."
  else
    kubectl -n "$NAMESPACE" create secret generic "$merge_secret_name" \
      --from-literal="$merge_line"
    echo "Created secret '$merge_secret_name' with '$merge_key' only."
  fi
}

BASE_DIR="$SCRIPT_DIR/dev-k8s/base"

# --- incident-service registry + webhook token (in-place updates) ------------

INCIDENT_SECRET_FILE="$BASE_DIR/incident-service/runtime-secrets.env"
upsert_env_line "$INCIDENT_SECRET_FILE" INCIDENT_WEBHOOK_TOKEN \
  "INCIDENT_WEBHOOK_TOKEN=${INCIDENT_WEBHOOK_TOKEN}"
upsert_env_line "$INCIDENT_SECRET_FILE" INCIDENT_QUERY_CLIENTS \
  "INCIDENT_QUERY_CLIENTS=platform-gateway=${INCIDENT_QUERY_SECRET},tool-gateway=${INCIDENT_QUERY_SECRET},agent-service=${INCIDENT_QUERY_SECRET}"
sync_secret incident-service-runtime-secrets "$INCIDENT_SECRET_FILE"

# --- caller credentials (in-place update, preserves existing secrets) --------

PG_SECRET_FILE="$BASE_DIR/platform-gateway/runtime-secrets.env"
upsert_env_line "$PG_SECRET_FILE" PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET \
  "PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET=${INCIDENT_QUERY_SECRET}"
sync_secret platform-gateway-runtime-secrets "$PG_SECRET_FILE"

TG_SECRET_FILE="$BASE_DIR/tool-gateway/runtime-secrets.env"
upsert_env_line "$TG_SECRET_FILE" GATEWAY_INCIDENTS_CLIENT_SECRET \
  "GATEWAY_INCIDENTS_CLIENT_SECRET=${INCIDENT_QUERY_SECRET}"
sync_secret tool-gateway-runtime-secrets "$TG_SECRET_FILE"

# SPEC-043: agent-service fetches incident bundles when assembling
# incident_report documents; it shares the registry query secret. The
# agent-platform-runtime-secrets Secret is owned by the active runtime
# profile file (sync-audit-secrets.sh and sync-otel-secrets.sh use the
# same source), so the key is upserted there and the whole file is
# re-synced — syncing a partial file would wipe the audit credential
# and the LLM provider keys provisioned by the sibling scripts.
AP_PROFILE_DIR=$(sed -n 's|^ *- *\.\./runtime-profiles/||p' \
  "$SCRIPT_DIR/dev-k8s/kustomization.yaml" | head -1)
AP_PROFILE_FILE="$SCRIPT_DIR/runtime-profiles/$AP_PROFILE_DIR/runtime-secrets.env"
if [ -n "$AP_PROFILE_DIR" ] && [ -f "$AP_PROFILE_FILE" ]; then
  upsert_env_line "$AP_PROFILE_FILE" AGENT_INCIDENT_CLIENT_SECRET \
    "AGENT_INCIDENT_CLIENT_SECRET=${INCIDENT_QUERY_SECRET}"
  sync_secret agent-platform-runtime-secrets "$AP_PROFILE_FILE"
else
  echo "No local runtime-profile secret file (profile: ${AP_PROFILE_DIR:-none});"
  echo "merging the incident query key into the cluster Secret instead."
  merge_secret_key agent-platform-runtime-secrets \
    "AGENT_INCIDENT_CLIENT_SECRET=${INCIDENT_QUERY_SECRET}"
fi

# --- restart affected workloads ----------------------------------------------

kubectl -n "$NAMESPACE" rollout restart deployment/incident-service
kubectl -n "$NAMESPACE" rollout restart deployment/platform-gateway
kubectl -n "$NAMESPACE" rollout restart deployment/tool-gateway
kubectl -n "$NAMESPACE" rollout restart deployment/agent-service

echo ""
echo "Incident secrets provisioned. Waiting for rollout..."
kubectl -n "$NAMESPACE" rollout status deployment/incident-service --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/platform-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/tool-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/agent-service --timeout=120s

echo ""
echo "Incident intake and query are now configured."
echo "Point Alertmanager at incident-service:8000/api/v1/webhooks/alertmanager"
echo "with the INCIDENT_WEBHOOK_TOKEN as the bearer token."
