#!/bin/sh

# Provision the browser credential-set secret for the dev-k8s overlay
# (SPEC-049 R-5).
#
# The tool-gateway's web.fill_credential tool resolves named credential
# sets from the JSON file mounted at
# GATEWAY_BROWSER_CREDENTIAL_SETS (/etc/luban/browser-credentials/
# credential-sets.json) out of the tool-gateway-browser-credentials
# secret. Values never travel through skills, prompts, or tool results.
#
# Provide your own sets via BROWSER_CREDENTIAL_SETS_FILE (a JSON object
# mapping set name -> {"username": ..., "password": ...}); otherwise a
# dev set for the sample browser-check-target app is generated with a
# random password (never echoed, never committed).
#
# Usage:
#   shared/platform-ops/gitops/sync-browser-credentials.sh [namespace]
#
# Override with your own file:
#   BROWSER_CREDENTIAL_SETS_FILE=./cred-sets.json \
#     shared/platform-ops/gitops/sync-browser-credentials.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_BROWSER_CREDENTIALS=true make deploy

set -eu

NAMESPACE="${1:-dev-luban-aiops}"

if [ "${SKIP_BROWSER_CREDENTIALS:-}" = "true" ]; then
  echo "SKIP_BROWSER_CREDENTIALS=true; skipping browser credential provisioning."
  exit 0
fi

SOURCE_FILE="${BROWSER_CREDENTIAL_SETS_FILE:-}"
CLEANUP=""

if [ -n "$SOURCE_FILE" ]; then
  if [ ! -f "$SOURCE_FILE" ]; then
    echo "BROWSER_CREDENTIAL_SETS_FILE not found: $SOURCE_FILE" >&2
    exit 1
  fi
  CRED_FILE="$SOURCE_FILE"
else
  # Dev default: two credential sets for the sample target apps shipped
  # by runtime-profiles/browser-dev. Random passwords; stay inside the
  # cluster secret.
  CRED_FILE=$(mktemp)
  CLEANUP="$CRED_FILE"
  PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)
  ADMIN_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)
  cat > "$CRED_FILE" <<EOF
{
  "browser-check-target": {
    "username": "svc-check",
    "password": "${PASSWORD}"
  },
  "admin-portal": {
    "username": "admin",
    "password": "${ADMIN_PASSWORD}"
  }
}
EOF
fi

kubectl -n "$NAMESPACE" create secret generic tool-gateway-browser-credentials \
  --from-file=credential-sets.json="$CRED_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

if [ -n "$CLEANUP" ]; then
  rm -f "$CLEANUP"
fi

echo "Browser credential sets synced (secret: tool-gateway-browser-credentials)."

# The gateway reloads the mounted file by mtime, but restart anyway so a
# first deploy does not race the mount.
kubectl -n "$NAMESPACE" rollout restart deployment/tool-gateway >/dev/null
echo "tool-gateway rollout restarted in namespace '$NAMESPACE'."
