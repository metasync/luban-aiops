#!/bin/sh

# Provision the execution handoff token for the dev-k8s overlay
# (SPEC-038 R-2/R-6).
#
# agent-service presents the token on the internal handoff to the
# execution-runtime worker, which compares it constant-time against the
# same value (EXECUTION_HANDOFF_TOKEN) before any verification or
# execution. A missing token fails closed on both sides — agent-service
# rejects mutating resumes with an audited worker_unavailable rejection,
# and the worker rejects every handoff as unauthorized — but
# provisioning keeps approved batches executable:
#
#   agent-service      → execution-handoff-secret (AGENT_EXECUTION_HANDOFF_TOKEN)
#   execution-runtime  → execution-handoff-secret (EXECUTION_HANDOFF_TOKEN)
#
# The script reuses the token already stored in the cluster secret when
# present; export EXECUTION_HANDOFF_TOKEN to force a specific value.
#
# Usage:
#   shared/platform-ops/gitops/sync-execution-handoff-secret.sh [namespace]
#
# Override the generated token:
#   EXECUTION_HANDOFF_TOKEN=my-token shared/platform-ops/gitops/sync-execution-handoff-secret.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_EXECUTION_HANDOFF_SECRET=true make deploy

set -eu

NAMESPACE="${1:-dev-luban-aiops}"

if [ "${SKIP_EXECUTION_HANDOFF_SECRET:-}" = "true" ]; then
  echo "SKIP_EXECUTION_HANDOFF_SECRET=true; skipping execution handoff-token provisioning."
  exit 0
fi

# --- token selection ---------------------------------------------------------

if [ -z "${EXECUTION_HANDOFF_TOKEN:-}" ]; then
  EXISTING_TOKEN=$(kubectl -n "$NAMESPACE" get secret execution-handoff-secret \
    -o jsonpath='{.data.EXECUTION_HANDOFF_TOKEN}' 2>/dev/null \
    | base64 -d 2>/dev/null || true)
  if [ -n "$EXISTING_TOKEN" ]; then
    EXECUTION_HANDOFF_TOKEN="$EXISTING_TOKEN"
    echo "Reusing the existing execution handoff token from the cluster secret."
  else
    EXECUTION_HANDOFF_TOKEN=$(openssl rand -hex 32)
    echo "Generated a new execution handoff token."
  fi
fi

# --- secret sync --------------------------------------------------------------

KEY_FILE=$(mktemp)
printf 'EXECUTION_HANDOFF_TOKEN=%s\n' "$EXECUTION_HANDOFF_TOKEN" > "$KEY_FILE"
kubectl -n "$NAMESPACE" create secret generic execution-handoff-secret \
  --from-env-file="$KEY_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f "$KEY_FILE"
echo "Synced secret 'execution-handoff-secret' in namespace '$NAMESPACE'."

# --- restart both sides of the handoff ----------------------------------------

echo ""
echo "Restarting agent-service and execution-runtime to pick up the token..."
kubectl -n "$NAMESPACE" rollout restart deployment/agent-service
kubectl -n "$NAMESPACE" rollout restart deployment/execution-runtime
kubectl -n "$NAMESPACE" rollout status deployment/agent-service --timeout=120s
kubectl -n "$NAMESPACE" rollout status deployment/execution-runtime --timeout=120s

echo ""
echo "Execution handoff is now configured; approved mutating executions run"
echo "in the execution-runtime worker behind the authenticated handoff (SPEC-038)."
