#!/bin/sh

# Provision the execution-request signing key for the dev-k8s overlay
# (SPEC-037 R-2).
#
# agent-service signs every approved mutating execution request and
# verifies the invocation-boundary argument digest against the same key
# (AGENT_EXECUTION_SIGNING_KEY). A missing key never degrades to
# unsigned execution — the resume path fails closed with an audited
# signing_unavailable rejection — but provisioning keeps approved
# batches executable:
#
#   agent-service → execution-signing-secret (AGENT_EXECUTION_SIGNING_KEY)
#
# The script reuses the key already stored in the cluster secret when
# present (issued signatures stay verifiable across redeploys); export
# EXECUTION_SIGNING_KEY to force a specific value.
#
# Usage:
#   shared/platform-ops/gitops/sync-execution-signing-secret.sh [namespace]
#
# Override the generated key:
#   EXECUTION_SIGNING_KEY=my-key shared/platform-ops/gitops/sync-execution-signing-secret.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_EXECUTION_SIGNING_SECRET=true make deploy

set -eu

NAMESPACE="${1:-dev-luban-aiops}"

if [ "${SKIP_EXECUTION_SIGNING_SECRET:-}" = "true" ]; then
  echo "SKIP_EXECUTION_SIGNING_SECRET=true; skipping execution signing-key provisioning."
  exit 0
fi

# --- key selection -----------------------------------------------------------

if [ -z "${EXECUTION_SIGNING_KEY:-}" ]; then
  EXISTING_KEY=$(kubectl -n "$NAMESPACE" get secret execution-signing-secret \
    -o jsonpath='{.data.AGENT_EXECUTION_SIGNING_KEY}' 2>/dev/null \
    | base64 -d 2>/dev/null || true)
  if [ -n "$EXISTING_KEY" ]; then
    EXECUTION_SIGNING_KEY="$EXISTING_KEY"
    echo "Reusing the existing execution signing key from the cluster secret."
  else
    EXECUTION_SIGNING_KEY=$(openssl rand -hex 32)
    echo "Generated a new execution signing key."
  fi
fi

# --- secret sync --------------------------------------------------------------

KEY_FILE=$(mktemp)
printf 'AGENT_EXECUTION_SIGNING_KEY=%s\n' "$EXECUTION_SIGNING_KEY" > "$KEY_FILE"
kubectl -n "$NAMESPACE" create secret generic execution-signing-secret \
  --from-env-file="$KEY_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f "$KEY_FILE"
echo "Synced secret 'execution-signing-secret' in namespace '$NAMESPACE'."

# --- restart the signer --------------------------------------------------------

echo ""
echo "Restarting agent-service to pick up the signing key..."
kubectl -n "$NAMESPACE" rollout restart deployment/agent-service
kubectl -n "$NAMESPACE" rollout status deployment/agent-service --timeout=120s

echo ""
echo "Execution signing is now configured; approved mutating executions are"
echo "signed at resume and verified at the invocation boundary (SPEC-037)."
