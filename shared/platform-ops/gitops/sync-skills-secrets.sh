#!/bin/sh

# Provision the skills query credentials for the dev-k8s overlay
# (SPEC-014 R-3/R-6).
#
# The tool-gateway queries skills-hub, which authenticates query callers
# against a static registry (SKILLS_QUERY_CLIENTS):
#
#   skills-hub    →  SKILLS_QUERY_CLIENTS (client registry)
#   tool-gateway  →  GATEWAY_SKILLS_CLIENT_SECRET
#
# This script also ensures the 'skills' database exists (fresh clusters get
# it via the postgres initdb script; existing clusters get it here through
# an idempotent CREATE DATABASE on the postgres pod). It then generates one
# secret (or uses SKILLS_QUERY_SECRET if already exported), writes/updates
# the runtime-secrets.env files (emitter files are updated in place so audit
# secrets provisioned earlier are preserved), syncs the Kubernetes secrets,
# and restarts the affected deployments.
#
# Usage:
#   shared/platform-ops/gitops/sync-skills-secrets.sh [namespace]
#
# Override the generated secret:
#   SKILLS_QUERY_SECRET=my-secret shared/platform-ops/gitops/sync-skills-secrets.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_SKILLS_SECRETS=true make deploy

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NAMESPACE="${1:-dev-luban-aiops}"

if [ "${SKIP_SKILLS_SECRETS:-}" = "true" ]; then
  echo "SKIP_SKILLS_SECRETS=true; skipping skills-secret provisioning."
  exit 0
fi

# --- skills database (idempotent for existing clusters) ---------------------

POSTGRES_POD=$(kubectl -n "$NAMESPACE" get pods -l app=postgres \
  -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POSTGRES_POD" ]; then
  echo "No postgres pod found in namespace '$NAMESPACE'; deploy the overlay first." >&2
  exit 1
fi
kubectl -n "$NAMESPACE" exec "$POSTGRES_POD" -- \
  sh -c 'psql -U audit -tAc "SELECT 1 FROM pg_database WHERE datname = '\''skills'\''" | grep -q 1 \
    || psql -U audit -c "CREATE DATABASE skills"'
echo "Database 'skills' is present on $POSTGRES_POD."

# --- shared secret ----------------------------------------------------------

if [ -z "${SKILLS_QUERY_SECRET:-}" ]; then
  SKILLS_QUERY_SECRET=$(openssl rand -hex 24)
  echo "Generated SKILLS_QUERY_SECRET (export it to reuse across runs)."
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

# --- skills-hub registry -----------------------------------------------------

SKILLS_SECRET_FILE="$BASE_DIR/skills-hub/runtime-secrets.env"
cat > "$SKILLS_SECRET_FILE" <<EOF
SKILLS_QUERY_CLIENTS=tool-gateway=${SKILLS_QUERY_SECRET}
EOF
sync_secret skills-hub-runtime-secrets "$SKILLS_SECRET_FILE"

# --- caller credential (in-place update, preserves existing secrets) ---------

TG_SECRET_FILE="$BASE_DIR/tool-gateway/runtime-secrets.env"
upsert_env_line "$TG_SECRET_FILE" GATEWAY_SKILLS_CLIENT_SECRET \
  "GATEWAY_SKILLS_CLIENT_SECRET=${SKILLS_QUERY_SECRET}"
sync_secret tool-gateway-runtime-secrets "$TG_SECRET_FILE"

# --- restart affected workloads ----------------------------------------------

kubectl -n "$NAMESPACE" rollout restart deployment/skills-hub
kubectl -n "$NAMESPACE" rollout restart deployment/tool-gateway

echo ""
echo "Skills query secrets provisioned. Waiting for rollout..."
kubectl -n "$NAMESPACE" rollout status deployment/skills-hub --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/tool-gateway --timeout=120s

echo ""
echo "Skills retrieval is now configured."
echo "Query skills via the agent's skills.search tool or GET skills-hub:8000/api/v1/skills."
