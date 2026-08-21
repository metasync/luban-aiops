#!/bin/sh

# Provision the durable-audit-trail ingest secrets for the dev-k8s overlay
# (SPEC-013 R-3).
#
# The tool-gateway, platform-gateway, identity-broker, and incident-service
# emit audit events to the audit-service, which authenticates ingest callers
# against a static registry (AUDIT_INGEST_CLIENTS). All emitters share one
# ingest secret:
#
#   audit-service     →  AUDIT_INGEST_CLIENTS (client registry)
#   tool-gateway      →  GATEWAY_AUDIT_CLIENT_SECRET
#   platform-gateway  →  PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET
#   identity-broker   →  IDENTITY_AUDIT_CLIENT_SECRET
#   incident-service  →  INCIDENT_AUDIT_CLIENT_SECRET
#
# This script generates one secret (or uses AUDIT_INGEST_SECRET if already
# exported), writes/updates the runtime-secrets.env files (emitter files are
# updated in place so delegation secrets provisioned earlier are preserved),
# syncs the Kubernetes secrets, and restarts the affected deployments.
#
# Usage:
#   shared/platform-ops/gitops/sync-audit-secrets.sh [namespace]
#
# Override the generated secret:
#   AUDIT_INGEST_SECRET=my-secret shared/platform-ops/gitops/sync-audit-secrets.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_AUDIT_SECRETS=true make deploy

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NAMESPACE="${1:-dev-luban-aiops}"

if [ "${SKIP_AUDIT_SECRETS:-}" = "true" ]; then
  echo "SKIP_AUDIT_SECRETS=true; skipping audit-secret provisioning."
  exit 0
fi

# --- shared secret ---------------------------------------------------------

if [ -z "${AUDIT_INGEST_SECRET:-}" ]; then
  AUDIT_INGEST_SECRET=$(openssl rand -hex 24)
  echo "Generated AUDIT_INGEST_SECRET (export it to reuse across runs)."
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

BASE_DIR="$SCRIPT_DIR/dev-k8s/base"

# --- audit-service registry -------------------------------------------------

AUDIT_SECRET_FILE="$BASE_DIR/audit-service/runtime-secrets.env"
# Preserve a previously provisioned OTLP header across the file rewrite:
# sync-otel-secrets.sh merges it cluster-side and mirrors it into this file,
# and dropping it here would make the secret sync below wipe it again.
PRESERVED_OTEL_LINE=$(grep '^OTEL_EXPORTER_OTLP_HEADERS=' "$AUDIT_SECRET_FILE" 2>/dev/null || true)
cat > "$AUDIT_SECRET_FILE" <<EOF
AUDIT_INGEST_CLIENTS=tool-gateway=${AUDIT_INGEST_SECRET},platform-gateway=${AUDIT_INGEST_SECRET},identity-broker=${AUDIT_INGEST_SECRET},incident-service=${AUDIT_INGEST_SECRET}
EOF
if [ -n "$PRESERVED_OTEL_LINE" ]; then
  printf '%s\n' "$PRESERVED_OTEL_LINE" >> "$AUDIT_SECRET_FILE"
fi
sync_secret audit-service-runtime-secrets "$AUDIT_SECRET_FILE"

# --- emitter credentials (in-place update, preserves existing secrets) ------

TG_SECRET_FILE="$BASE_DIR/tool-gateway/runtime-secrets.env"
upsert_env_line "$TG_SECRET_FILE" GATEWAY_AUDIT_CLIENT_SECRET \
  "GATEWAY_AUDIT_CLIENT_SECRET=${AUDIT_INGEST_SECRET}"
sync_secret tool-gateway-runtime-secrets "$TG_SECRET_FILE"

PG_SECRET_FILE="$BASE_DIR/platform-gateway/runtime-secrets.env"
upsert_env_line "$PG_SECRET_FILE" PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET \
  "PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET=${AUDIT_INGEST_SECRET}"
sync_secret platform-gateway-runtime-secrets "$PG_SECRET_FILE"

IB_SECRET_FILE="$BASE_DIR/identity-broker/runtime-secrets.env"
upsert_env_line "$IB_SECRET_FILE" IDENTITY_AUDIT_CLIENT_SECRET \
  "IDENTITY_AUDIT_CLIENT_SECRET=${AUDIT_INGEST_SECRET}"
sync_secret identity-service-runtime-secrets "$IB_SECRET_FILE"

IS_SECRET_FILE="$BASE_DIR/incident-service/runtime-secrets.env"
upsert_env_line "$IS_SECRET_FILE" INCIDENT_AUDIT_CLIENT_SECRET \
  "INCIDENT_AUDIT_CLIENT_SECRET=${AUDIT_INGEST_SECRET}"
sync_secret incident-service-runtime-secrets "$IS_SECRET_FILE"

# --- restart affected workloads ----------------------------------------------

kubectl -n "$NAMESPACE" rollout restart deployment/audit-service
kubectl -n "$NAMESPACE" rollout restart deployment/tool-gateway
kubectl -n "$NAMESPACE" rollout restart deployment/platform-gateway
kubectl -n "$NAMESPACE" rollout restart deployment/identity-service
kubectl -n "$NAMESPACE" rollout restart deployment/incident-service

echo ""
echo "Audit ingest secrets provisioned. Waiting for rollout..."
kubectl -n "$NAMESPACE" rollout status deployment/audit-service --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/tool-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/platform-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/identity-service --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/incident-service --timeout=120s

echo ""
echo "Durable audit trail ingestion is now configured."
echo "Emitters forward events to audit-service; query via GET /api/v1/audit/events."
