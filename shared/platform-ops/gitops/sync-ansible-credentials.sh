#!/bin/sh

# Provision the Ansible MCP credential secrets for the dev-k8s overlay
# (SPEC-069 R-6).
#
# The tool-gateway's server-agnostic MCP-ingestion connector resolves the
# named credential set GATEWAY_ANSIBLE_MCP_CREDENTIAL_SET ("ansible-mock")
# from the JSON file mounted at GATEWAY_ANSIBLE_MCP_CREDENTIAL_SETS
# (/etc/luban/ansible-credentials/credential-sets.json) out of the
# tool-gateway-ansible-credentials secret, and rides the resolved bearer to
# the Ansible MCP server. The thin mock (ansible-mock-mcp) requires the very
# same bearer on every request. Values never travel through skills, prompts,
# or tool results.
#
# One generator, two sinks. The bearer is generated once and written to BOTH
# consumers, so the client and the server cannot disagree about it:
#
#   tool-gateway-ansible-credentials  credential-sets.json gains an
#                                     `ansible-mock` bearer entry — what the
#                                     connector resolves and presents
#   ansible-mock-credentials          bearer-token, read by the mock's
#                                     ANSIBLE_MOCK_BEARER_FILE gate
#
# Deriving the second from the first (rather than generating twice) is the
# only arrangement in which the gateway and the mock cannot drift.
#
# Point at a real server by supplying its token: set ANSIBLE_MCP_BEARER_TOKEN
# (and change GATEWAY_ANSIBLE_MCP_URL in the profile) — e.g. an operator
# wiring licensed AAP or lycorp-jp/awx-mcp per the runbook. Otherwise a dev
# bearer is generated at random (never echoed, never committed).
#
# Usage:
#   shared/platform-ops/gitops/sync-ansible-credentials.sh [namespace]
#
# Override the shared bearer (real AAP / AWX target):
#   ANSIBLE_MCP_BEARER_TOKEN=<token> \
#     shared/platform-ops/gitops/sync-ansible-credentials.sh
#
# Skip in CI when secrets are injected externally:
#   SKIP_ANSIBLE_CREDENTIALS=true make deploy
#
# Skipping leaves BOTH secrets unwritten. The mock then adopts an
# unguessable token and fails every call closed (401), and the connector
# fails closed (CREDENTIAL_SET_NOT_FOUND) — neither runs open.

set -eu

NAMESPACE="${1:-dev-luban-aiops}"

# Must match GATEWAY_ANSIBLE_MCP_CREDENTIAL_SET in the profile's ansible.env
# and the credential-sets mount the tool-gateway-ansible-credentials.yaml
# patch declares; the coupling is the whole point of the single generator.
CREDENTIAL_SET_NAME="${ANSIBLE_MCP_CREDENTIAL_SET:-ansible-mock}"

if [ "${SKIP_ANSIBLE_CREDENTIALS:-}" = "true" ]; then
  echo "SKIP_ANSIBLE_CREDENTIALS=true; skipping Ansible MCP credential provisioning."
  exit 0
fi

# python3 builds the credential-set JSON so an operator-supplied token is
# escaped correctly; it is the JSON parser the repository's other shell
# helpers use (shared/platform-ops/e2e/*.sh), and jq is not a precondition
# of `make deploy`.
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found; cannot build the Ansible credential-set JSON." >&2
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

# These temp files carry the RAW bearer and the rendered credential set, so they
# must not outlive the script. A plain trailing loop only runs on the happy path:
# under `set -eu` any failing kubectl/python3 step in between would leave both on
# disk. The trap runs on success, failure and signal alike (same shape as
# shared/platform-ops/e2e/ansible-mcp-check.sh).
cleanup() {
  for path in $CLEANUP; do
    rm -f "$path"
  done
  # Idempotent: the explicit call below empties the list, so the EXIT trap that
  # stays armed as the failure safety net becomes a no-op.
  CLEANUP=""
}
trap cleanup EXIT INT TERM

# The bearer is written to a temp file, never passed as --from-literal, so it
# never appears in this process's argv (visible to `ps`).
TOKEN_FILE=$(mktemp)
add_cleanup "$TOKEN_FILE"

if [ -n "${ANSIBLE_MCP_BEARER_TOKEN:-}" ]; then
  # Operator-supplied token (real AAP / AWX target). No trailing newline: the
  # mock strips, the connector presents the value verbatim.
  printf '%s' "$ANSIBLE_MCP_BEARER_TOKEN" > "$TOKEN_FILE"
else
  # Dev default: a random bearer that stays inside the cluster secrets.
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 > "$TOKEN_FILE"
fi

CRED_FILE=$(mktemp)
add_cleanup "$CRED_FILE"

# Reads the token from TOKEN_FILE (argv carries only paths and the non-secret
# set name) and emits the SPEC-068 bearer credential-set shape.
python3 -c '
import json, sys

token_path, out_path, set_name = sys.argv[1], sys.argv[2], sys.argv[3]
with open(token_path, encoding="utf-8") as handle:
    token = handle.read().strip()
if not token:
    sys.stderr.write("generated/overrides bearer is empty; refusing to write an empty credential set.\n")
    raise SystemExit(1)
with open(out_path, "w", encoding="utf-8") as out:
    json.dump({set_name: {"scheme": "bearer", "token": token}}, out)
    out.write("\n")
' "$TOKEN_FILE" "$CRED_FILE" "$CREDENTIAL_SET_NAME"

# Sink 1: the gateway's credential-set file.
kubectl -n "$NAMESPACE" create secret generic tool-gateway-ansible-credentials \
  --from-file=credential-sets.json="$CRED_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

# Sink 2: the mock's bearer gate, from the same token so the two cannot drift.
kubectl -n "$NAMESPACE" create secret generic ansible-mock-credentials \
  --from-file=bearer-token="$TOKEN_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

# Both sinks are written: drop the raw bearer and the rendered credential set
# from disk now, rather than leaving them around until the exit trap fires.
cleanup

echo "Ansible MCP credential set synced (secret: tool-gateway-ansible-credentials, set: $CREDENTIAL_SET_NAME)."
echo "Ansible mock bearer synced (secret: ansible-mock-credentials)."

# The gateway reloads the mounted file by mtime, but restart anyway so a first
# deploy does not race the mount. The mock reads its bearer once at startup, so
# it must restart to adopt a regenerated token — restart it only when present
# (it is absent on overlays that do not ship the ansible-dev profile).
kubectl -n "$NAMESPACE" rollout restart deployment/tool-gateway >/dev/null
echo "tool-gateway rollout restarted in namespace '$NAMESPACE'."
if kubectl -n "$NAMESPACE" get deployment ansible-mock-mcp >/dev/null 2>&1; then
  kubectl -n "$NAMESPACE" rollout restart deployment/ansible-mock-mcp >/dev/null
  echo "ansible-mock-mcp rollout restarted in namespace '$NAMESPACE'."
fi
