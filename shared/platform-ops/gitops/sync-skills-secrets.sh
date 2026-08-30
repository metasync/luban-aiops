#!/bin/sh

# Provision the skills query credentials for the dev-k8s overlay
# (SPEC-014 R-3/R-6, SPEC-019 R-4).
#
# The tool-gateway, the platform-gateway, and agent-platform query
# skills-hub, which authenticates query callers against a static
# registry (SKILLS_QUERY_CLIENTS):
#
#   skills-hub       →  SKILLS_QUERY_CLIENTS (client registry)
#   tool-gateway     →  GATEWAY_SKILLS_CLIENT_SECRET
#   platform-gateway →  PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET
#   agent-service    →  AGENT_SKILLS_CLIENT_SECRET (SPEC-044,
#                       skill-draft validation)
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
# Attach a git-source PAT (never echoed, never committed): when SKILLS_GIT_TOKEN
# is exported, it is written into the skills-hub secret as
# SKILLS_GIT_TOKENS={"platform-skills":"<token>"} so the platform-skills git
# source can authenticate. Unset: the git source fails auth (scrubbed error on
# the status endpoint) while the local sources keep serving.
#
#   SKILLS_GIT_TOKEN=github_pat_... shared/platform-ops/gitops/sync-skills-secrets.sh
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

# --- skills-hub registry -----------------------------------------------------

SKILLS_SECRET_FILE="$BASE_DIR/skills-hub/runtime-secrets.env"
# Preserve a previously provisioned OTLP header across the file rewrite:
# sync-otel-secrets.sh mirrors it into this file, and dropping it here would
# make the secret sync below wipe it from the cluster Secret.
PRESERVED_OTEL_LINE=$(grep '^OTEL_EXPORTER_OTLP_HEADERS=' "$SKILLS_SECRET_FILE" 2>/dev/null || true)
# Preserve the audit ingest credential (SPEC-029): sync-audit-secrets.sh runs
# before this script in deploy.sh, and dropping the line here would wipe the
# cluster Secret's key and 401 every skills-hub audit emission.
PRESERVED_AUDIT_LINE=$(grep '^SKILLS_AUDIT_CLIENT_SECRET=' "$SKILLS_SECRET_FILE" 2>/dev/null || true)
cat > "$SKILLS_SECRET_FILE" <<EOF
SKILLS_QUERY_CLIENTS=tool-gateway=${SKILLS_QUERY_SECRET},platform-gateway=${SKILLS_QUERY_SECRET},agent-service=${SKILLS_QUERY_SECRET}
EOF
if [ -n "$PRESERVED_OTEL_LINE" ]; then
  printf '%s\n' "$PRESERVED_OTEL_LINE" >> "$SKILLS_SECRET_FILE"
fi
if [ -n "$PRESERVED_AUDIT_LINE" ]; then
  printf '%s\n' "$PRESERVED_AUDIT_LINE" >> "$SKILLS_SECRET_FILE"
fi
# Git-source PAT: the secret file was just truncated, so a plain append is
# idempotent. The token is never echoed to the terminal.
if [ -n "${SKILLS_GIT_TOKEN:-}" ]; then
  printf 'SKILLS_GIT_TOKENS={"platform-skills":"%s"}\n' "$SKILLS_GIT_TOKEN" \
    >> "$SKILLS_SECRET_FILE"
  echo "SKILLS_GIT_TOKENS provisioned for source 'platform-skills'."
fi
sync_secret skills-hub-runtime-secrets "$SKILLS_SECRET_FILE"

# --- caller credential (in-place update, preserves existing secrets) ---------

TG_SECRET_FILE="$BASE_DIR/tool-gateway/runtime-secrets.env"
upsert_env_line "$TG_SECRET_FILE" GATEWAY_SKILLS_CLIENT_SECRET \
  "GATEWAY_SKILLS_CLIENT_SECRET=${SKILLS_QUERY_SECRET}"
sync_secret tool-gateway-runtime-secrets "$TG_SECRET_FILE"

# platform-gateway uses the same shared secret for its skills inventory
# proxy (SPEC-019 R-4).
PG_SECRET_FILE="$BASE_DIR/platform-gateway/runtime-secrets.env"
upsert_env_line "$PG_SECRET_FILE" PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET \
  "PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET=${SKILLS_QUERY_SECRET}"
sync_secret platform-gateway-runtime-secrets "$PG_SECRET_FILE"

# SPEC-044: agent-service validates generated skill drafts on skills-hub's
# own code path before handing them to the operator; it shares the registry
# query secret. The agent-platform-runtime-secrets Secret is owned by the
# active runtime profile file (sync-audit-secrets.sh and sync-otel-secrets.sh
# use the same source), so the key is upserted there and the whole file is
# re-synced — syncing a partial file would wipe the audit credential and the
# LLM provider keys provisioned by the sibling scripts.
AP_PROFILE_DIR=$(sed -n 's|^ *- *\.\./runtime-profiles/||p' \
  "$SCRIPT_DIR/dev-k8s/kustomization.yaml" | head -1)
AP_PROFILE_FILE="$SCRIPT_DIR/runtime-profiles/$AP_PROFILE_DIR/runtime-secrets.env"
if [ -n "$AP_PROFILE_DIR" ] && [ -f "$AP_PROFILE_FILE" ]; then
  upsert_env_line "$AP_PROFILE_FILE" AGENT_SKILLS_CLIENT_SECRET \
    "AGENT_SKILLS_CLIENT_SECRET=${SKILLS_QUERY_SECRET}"
  sync_secret agent-platform-runtime-secrets "$AP_PROFILE_FILE"
else
  echo "No local runtime-profile secret file (profile: ${AP_PROFILE_DIR:-none});"
  echo "merging the skills query key into the cluster Secret instead."
  merge_secret_key agent-platform-runtime-secrets \
    "AGENT_SKILLS_CLIENT_SECRET=${SKILLS_QUERY_SECRET}"
fi

# --- restart affected workloads ----------------------------------------------

kubectl -n "$NAMESPACE" rollout restart deployment/skills-hub
kubectl -n "$NAMESPACE" rollout restart deployment/tool-gateway
kubectl -n "$NAMESPACE" rollout restart deployment/platform-gateway
kubectl -n "$NAMESPACE" rollout restart deployment/agent-service

echo ""
echo "Skills query secrets provisioned. Waiting for rollout..."
kubectl -n "$NAMESPACE" rollout status deployment/skills-hub --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/tool-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/platform-gateway --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/agent-service --timeout=120s

echo ""
echo "Skills retrieval is now configured."
echo "Query skills via the agent's skills.search tool or GET skills-hub:8000/api/v1/skills."
