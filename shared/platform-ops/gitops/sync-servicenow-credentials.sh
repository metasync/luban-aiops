#!/bin/sh

# Provision the ServiceNow credential secrets for the dev-k8s overlay
# (SPEC-067 R-6).
#
# The tool-gateway's native REST connector resolves the named credential set
# GATEWAY_SERVICENOW_CREDENTIAL_SET ("servicenow-mock") from the JSON file
# mounted at GATEWAY_SERVICENOW_CREDENTIAL_SETS
# (/etc/luban/servicenow-credentials/credential-sets.json) out of the
# tool-gateway-servicenow-credentials secret. The set is an OAuth2
# client_credentials entry (OQ-1): the gateway's SPEC-068 token client POSTs
# client_id/client_secret to the set's token_url and rides the issued
# access_token as a bearer to the Table API. The thin mock
# (servicenow-mock-table-api) validates the very same client_id/client_secret at
# /oauth_token.do and returns the very same access_token. Values never travel
# through skills, prompts, or tool results.
#
# One generator, two sinks. The three values are generated once and written to
# BOTH consumers, so the client and the server cannot disagree about them:
#
#   tool-gateway-servicenow-credentials  credential-sets.json gains a
#                                        `servicenow-mock` oauth2_client_credentials
#                                        entry (token_url + client_id + client_secret)
#                                        — what the connector resolves and presents
#   servicenow-mock-credentials          client-id / client-secret / access-token,
#                                        read by the mock's OAuth + bearer gates
#
# Deriving the second from the first (rather than generating twice) is the only
# arrangement in which the gateway and the mock cannot drift.
#
# Point at a real ServiceNow PDI by supplying its OAuth client: set
# SERVICENOW_CLIENT_ID / SERVICENOW_CLIENT_SECRET / SERVICENOW_TOKEN_URL (and
# change GATEWAY_SERVICENOW_BASE_URL in the profile) — e.g. an operator wiring a
# live tenant per the runbook. Sink 2 (the mock's access-token) is then unused:
# a real instance issues its own tokens dynamically. Otherwise dev values are
# generated at random (never echoed, never committed).
#
# Usage:
#   shared/platform-ops/gitops/sync-servicenow-credentials.sh [namespace]
#
# Override for a real PDI target:
#   SERVICENOW_CLIENT_ID=<id> SERVICENOW_CLIENT_SECRET=<secret> \
#   SERVICENOW_TOKEN_URL=https://<instance>.service-now.com/oauth_token.do \
#     shared/platform-ops/gitops/sync-servicenow-credentials.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_SERVICENOW_CREDENTIALS=true make deploy
#
# Skipping leaves BOTH secrets unwritten. The mock then adopts unguessable
# credentials and fails every call closed (401), and the connector fails closed
# (CREDENTIAL_SET_NOT_FOUND) — neither runs open.

set -eu

NAMESPACE="${1:-dev-luban-aiops}"

# Must match GATEWAY_SERVICENOW_CREDENTIAL_SET in the profile's servicenow.env
# and the credential-sets mount the tool-gateway-servicenow-credentials.yaml
# patch declares; the coupling is the whole point of the single generator.
CREDENTIAL_SET_NAME="${SERVICENOW_CREDENTIAL_SET:-servicenow-mock}"
# Must match the mock Service DNS (servicenow-mock-service.yaml) so the gateway's
# token client reaches the mock's /oauth_token.do. Overridden for a real PDI.
TOKEN_URL="${SERVICENOW_TOKEN_URL:-http://servicenow-mock-table-api:8000/oauth_token.do}"

if [ "${SKIP_SERVICENOW_CREDENTIALS:-}" = "true" ]; then
  echo "SKIP_SERVICENOW_CREDENTIALS=true; skipping ServiceNow credential provisioning."
  exit 0
fi

# python3 builds the credential-set JSON so an operator-supplied secret is
# escaped correctly; it is the JSON parser the repository's other shell helpers
# use (shared/platform-ops/e2e/*.sh), and jq is not a precondition of `make deploy`.
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found; cannot build the ServiceNow credential-set JSON." >&2
  exit 1
fi

CLEANUP=""
add_cleanup() {
  if [ -n "$CLEANUP" ]; then
    CLEANUP="$CLEANUP $1"
  else
    CLEANUP="$1"
  fi
}

# These temp files carry the RAW client secret / access token and the rendered
# credential set, so they must not outlive the script. A plain trailing loop only
# runs on the happy path: under `set -eu` any failing kubectl/python3 step in
# between would leave them on disk. The trap runs on success, failure and signal
# alike (same shape as sync-ansible-credentials.sh).
cleanup() {
  for path in $CLEANUP; do
    rm -f "$path"
  done
  CLEANUP=""
}
trap cleanup EXIT INT TERM

# Each value is written to a temp file, never passed as --from-literal, so it
# never appears in this process's argv (visible to `ps`).
CLIENT_ID_FILE=$(mktemp)
CLIENT_SECRET_FILE=$(mktemp)
ACCESS_TOKEN_FILE=$(mktemp)
CRED_FILE=$(mktemp)
add_cleanup "$CLIENT_ID_FILE"
add_cleanup "$CLIENT_SECRET_FILE"
add_cleanup "$ACCESS_TOKEN_FILE"
add_cleanup "$CRED_FILE"

if [ -n "${SERVICENOW_CLIENT_ID:-}" ]; then
  printf '%s' "$SERVICENOW_CLIENT_ID" > "$CLIENT_ID_FILE"
else
  printf 'servicenow-mock-%s' \
    "$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 12)" > "$CLIENT_ID_FILE"
fi

if [ -n "${SERVICENOW_CLIENT_SECRET:-}" ]; then
  printf '%s' "$SERVICENOW_CLIENT_SECRET" > "$CLIENT_SECRET_FILE"
else
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40 > "$CLIENT_SECRET_FILE"
fi

# The mock returns this exact token from /oauth_token.do and requires it as the
# Table-API bearer, so the two legs of the grant agree. A real PDI issues its own
# tokens; this value is then unused (sink 2 is not deployed without the profile).
if [ -n "${SERVICENOW_ACCESS_TOKEN:-}" ]; then
  printf '%s' "$SERVICENOW_ACCESS_TOKEN" > "$ACCESS_TOKEN_FILE"
else
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40 > "$ACCESS_TOKEN_FILE"
fi

# Reads the client_id/client_secret from their temp files (argv carries only paths
# and the non-secret set name / token_url) and emits the SPEC-068
# oauth2_client_credentials credential-set shape.
python3 -c '
import json, sys

client_id_path, client_secret_path, out_path, set_name, token_url = sys.argv[1:6]


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read().strip()


client_id = read(client_id_path)
client_secret = read(client_secret_path)
if not client_id or not client_secret:
    sys.stderr.write("generated/override client_id or client_secret is empty; refusing to write an incomplete credential set.\n")
    raise SystemExit(1)
with open(out_path, "w", encoding="utf-8") as out:
    json.dump({set_name: {
        "scheme": "oauth2_client_credentials",
        "token_url": token_url,
        "client_id": client_id,
        "client_secret": client_secret,
    }}, out)
    out.write("\n")
' "$CLIENT_ID_FILE" "$CLIENT_SECRET_FILE" "$CRED_FILE" "$CREDENTIAL_SET_NAME" "$TOKEN_URL"

# Sink 1: the gateway's credential-set file.
kubectl -n "$NAMESPACE" create secret generic tool-gateway-servicenow-credentials \
  --from-file=credential-sets.json="$CRED_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

# Sink 2: the mock's OAuth + bearer gates, from the same values so the two cannot
# drift.
kubectl -n "$NAMESPACE" create secret generic servicenow-mock-credentials \
  --from-file=client-id="$CLIENT_ID_FILE" \
  --from-file=client-secret="$CLIENT_SECRET_FILE" \
  --from-file=access-token="$ACCESS_TOKEN_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

# Both sinks are written: drop the raw values and the rendered credential set from
# disk now, rather than leaving them around until the exit trap fires.
cleanup

echo "ServiceNow credential set synced (secret: tool-gateway-servicenow-credentials, set: $CREDENTIAL_SET_NAME)."
echo "ServiceNow mock credentials synced (secret: servicenow-mock-credentials)."

# The gateway reloads the mounted file by mtime, but restart anyway so a first
# deploy does not race the mount. The mock reads its credentials once at startup,
# so it must restart to adopt regenerated values — restart it only when present
# (it is absent on overlays that do not ship the servicenow-dev profile).
kubectl -n "$NAMESPACE" rollout restart deployment/tool-gateway >/dev/null
echo "tool-gateway rollout restarted in namespace '$NAMESPACE'."
if kubectl -n "$NAMESPACE" get deployment servicenow-mock-table-api >/dev/null 2>&1; then
  kubectl -n "$NAMESPACE" rollout restart deployment/servicenow-mock-table-api >/dev/null
  echo "servicenow-mock-table-api rollout restarted in namespace '$NAMESPACE'."
fi
