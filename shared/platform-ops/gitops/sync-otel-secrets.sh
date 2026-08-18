#!/bin/sh

# Provision OTLP ingest credentials for the OTel push pipeline (SPEC-005
# completion slice: OpenObserve backend).
#
# Every service pushes traces/metrics/logs over OTLP HTTP to the endpoint in
# the shared ConfigMap (OTEL_EXPORTER_OTLP_ENDPOINT). OpenObserve requires
# Basic auth on ingest, delivered via OTEL_EXPORTER_OTLP_HEADERS. This script
# computes the header from the OpenObserve root credentials and upserts it
# into every service's runtime-secrets.env (in place, preserving all other
# secrets), syncs the seven Kubernetes Secrets, and restarts the workloads.
#
# Usage:
#   OO_ROOT_USER_EMAIL=... OO_ROOT_USER_PASSWORD=... \
#     shared/platform-ops/gitops/sync-otel-secrets.sh [namespace]
#
# Dev credentials live in the luban-bootstrapper repo
# (openobserve/secrets/openobserve.env); source them at provision time only.
# They are never echoed and never committed.
#
# Unset variables: the script skips provisioning with a clear message. Push
# then authenticates as anonymous, OpenObserve answers 401, and the exporters
# fail open — services are unaffected.
#
# Skip in CI when secrets are injected externally:
#   SKIP_OTEL_SECRETS=true make deploy

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NAMESPACE="${1:-dev-luban-aiops}"

if [ "${SKIP_OTEL_SECRETS:-}" = "true" ]; then
  echo "SKIP_OTEL_SECRETS=true; skipping OTel secret provisioning."
  exit 0
fi

if [ -z "${OO_ROOT_USER_EMAIL:-}" ] || [ -z "${OO_ROOT_USER_PASSWORD:-}" ]; then
  echo "OO_ROOT_USER_EMAIL / OO_ROOT_USER_PASSWORD not exported; skipping."
  echo "OTLP push will authenticate as anonymous (OpenObserve answers 401)"
  echo "and the exporters fail open until the headers are provisioned."
  exit 0
fi

# base64 without line wrapping; the value never reaches the terminal.
AUTH_B64=$(printf '%s:%s' "$OO_ROOT_USER_EMAIL" "$OO_ROOT_USER_PASSWORD" \
  | base64 | tr -d '\n')
OTEL_HEADER_LINE="OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic ${AUTH_B64}"

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

# The agent-platform secret comes from the active runtime profile
# (runtime-profiles/<name>/runtime-secrets.env feeds
# agent-platform-runtime-secrets); resolve the profile from the overlay.
PROFILE_DIR=$(sed -n 's|^ *- *\.\./runtime-profiles/||p' \
  "$SCRIPT_DIR/dev-k8s/kustomization.yaml" | head -1)
PROFILE_FILE="$SCRIPT_DIR/runtime-profiles/$PROFILE_DIR/runtime-secrets.env"
if [ -n "$PROFILE_DIR" ] && [ -f "$PROFILE_FILE" ]; then
  upsert_env_line "$PROFILE_FILE" OTEL_EXPORTER_OTLP_HEADERS "$OTEL_HEADER_LINE"
  sync_secret agent-platform-runtime-secrets "$PROFILE_FILE"
elif kubectl -n "$NAMESPACE" get secret agent-platform-runtime-secrets \
    >/dev/null 2>&1; then
  # No local profile secret file, but the cluster Secret exists (provisioned
  # by Luban CI or an earlier run): merge the header in cluster-side,
  # preserving all existing keys.
  VALUE_B64=$(printf '%s' "${OTEL_HEADER_LINE#OTEL_EXPORTER_OTLP_HEADERS=}" \
    | base64 | tr -d '\n')
  kubectl -n "$NAMESPACE" patch secret agent-platform-runtime-secrets \
    --type merge \
    -p "{\"data\":{\"OTEL_EXPORTER_OTLP_HEADERS\":\"${VALUE_B64}\"}}"
  echo "Patched existing secret 'agent-platform-runtime-secrets' in namespace '$NAMESPACE'."
else
  echo "No local runtime-profile secret file (profile: ${PROFILE_DIR:-none})"
  echo "and no cluster secret; agent-service pushes anonymously (401s fail open)."
fi

for entry in \
  "audit-service-runtime-secrets|$BASE_DIR/audit-service/runtime-secrets.env" \
  "identity-service-runtime-secrets|$BASE_DIR/identity-broker/runtime-secrets.env" \
  "incident-service-runtime-secrets|$BASE_DIR/incident-service/runtime-secrets.env" \
  "platform-gateway-runtime-secrets|$BASE_DIR/platform-gateway/runtime-secrets.env" \
  "skills-hub-runtime-secrets|$BASE_DIR/skills-hub/runtime-secrets.env" \
  "tool-gateway-runtime-secrets|$BASE_DIR/tool-gateway/runtime-secrets.env"
do
  secret_name="${entry%%|*}"
  env_file="${entry#*|}"
  upsert_env_line "$env_file" OTEL_EXPORTER_OTLP_HEADERS "$OTEL_HEADER_LINE"
  sync_secret "$secret_name" "$env_file"
done

# --- restart all seven workloads ----------------------------------------------

for deployment in agent-service audit-service identity-service \
  incident-service platform-gateway skills-hub tool-gateway
do
  kubectl -n "$NAMESPACE" rollout restart "deployment/$deployment"
done

echo ""
echo "OTel ingest credentials provisioned. Waiting for rollout..."
for deployment in agent-service audit-service identity-service \
  incident-service platform-gateway skills-hub tool-gateway
do
  kubectl -n "$NAMESPACE" rollout status "deployment/$deployment" --timeout=120s
done

echo ""
echo "Telemetry push is now authenticated against OpenObserve."
echo "Traces/metrics/logs flow to OTEL_EXPORTER_OTLP_ENDPOINT (shared ConfigMap)."
