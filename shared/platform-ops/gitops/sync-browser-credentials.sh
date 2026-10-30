#!/bin/sh

# Provision the browser credential-set secret for the dev-k8s overlay
# (SPEC-049 R-5), and the matching application secret for the
# `acme-admin` sample app (SPEC-059 R-3).
#
# The tool-gateway's web.fill_credential and http.post tools resolve
# named credential sets from the JSON file mounted at
# GATEWAY_BROWSER_CREDENTIAL_SETS (/etc/luban/browser-credentials/
# credential-sets.json) out of the tool-gateway-browser-credentials
# secret. Values never travel through skills, prompts, or tool results.
#
# One generator, two sinks. The `acme-admin` password is generated once
# and written to BOTH consumers:
#
#   tool-gateway-browser-credentials  credential-sets.json gains an
#                                     `acme-admin` entry, which is what
#                                     web.fill_credential(credential_set=
#                                     "acme-admin") and http.post(
#                                     credential_set="acme-admin") resolve
#   acme-admin-credentials            ACME_ADMIN_PASSWORD, consumed by
#                                     the sample app's Deployment, which
#                                     seeds its `admin` user with it
#
# Deriving the second from the first (rather than generating twice) is
# the only arrangement in which the browser surface, the HTTP surface and
# the application cannot disagree about the password.
#
# Provide your own sets via BROWSER_CREDENTIAL_SETS_FILE (a JSON object
# mapping set name -> {"username": ..., "password": ...}); otherwise a
# dev set for the `acme-admin` sample app is generated with a random
# password (never echoed, never committed). An entry may instead carry an
# optional "scheme" — "bearer" (a "token") or "oauth2_client_credentials"
# ("token_url"/"client_id"/"client_secret") per SPEC-068 — for the http.*
# connectors; the full shape is documented in
# docs/guides/tool-configuration.md. The `acme-admin` entry must stay a
# basic username/password set regardless, because the app-side secret is
# derived from it. The override path still produces that app-side secret,
# taken from your file's `acme-admin` entry — an operator supplying their
# own sets supplies the app's password too, or the app cannot start.
#
# Usage:
#   shared/platform-ops/gitops/sync-browser-credentials.sh [namespace]
#
# Override with your own file:
#   BROWSER_CREDENTIAL_SETS_FILE=./cred-sets.json \
#     shared/platform-ops/gitops/sync-browser-credentials.sh
#
# Provision a SPEC-070 delegated config + administered mapping (default OFF;
# delegation stays disabled until the overlay enables it). The config is
# validated through the SAME versioned guard the runtime uses, BEFORE any
# secret is created:
#   DELEGATED_CONFIG_FILE=./delegated-sets.json \
#   DELEGATED_SET_ID=user \
#   DELEGATED_TRUSTED_CALLBACK=https://portal.example/api/v1/targets/authorizations/callback \
#     shared/platform-ops/gitops/sync-browser-credentials.sh
#
# Validate every input and exit WITHOUT creating any secret or rolling out:
#   ... shared/platform-ops/gitops/sync-browser-credentials.sh --validate-only
#
# Skip in CI when secrets are injected externally:
#   SKIP_BROWSER_CREDENTIALS=true make deploy
#
# Skipping leaves BOTH secrets unwritten. The sample app then fails
# closed at startup and names this script in its log, rather than
# starting against a well-known default password.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)

# --- arguments ------------------------------------------------------------
# Preserves the historical `[namespace]` positional and SKIP_BROWSER_CREDENTIALS
# behavior, and adds a validation-only mode (SPEC-070 R-6 provisioning): with
# --validate-only (or VALIDATE_ONLY=true) the script validates every input and
# exits BEFORE any `kubectl` mutation or rollout.
NAMESPACE="dev-luban-aiops"
VALIDATE_ONLY="${VALIDATE_ONLY:-false}"
while [ $# -gt 0 ]; do
  case "$1" in
    --validate-only) VALIDATE_ONLY=true; shift ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) NAMESPACE="$1"; shift ;;
  esac
done

# --- delegated (SPEC-070) inputs ------------------------------------------
# All optional. When DELEGATED_CONFIG_FILE is unset the script provisions ONLY
# the existing browser/machine credential sets, exactly as before.
#   DELEGATED_CONFIG_FILE      local administered delegated config JSON (sets.json)
#   DELEGATED_MAPPING_FILE     local administered mapping JSON; defaults to the
#                              config's own absolute identity_mapping_path, so
#                              validation and provisioning read ONE source
#   DELEGATED_SET_ID           administered credential-set id (default: user)
#   DELEGATED_TRUSTED_CALLBACK exact deployment-trusted HTTPS callback; must equal
#                              the set's redirect_uri (guard: callback_mismatch)
#   DELEGATED_SECRET_NAME      target Secret (default: tool-gateway-delegated-config)
# identity_mapping_path is an absolute, administrator-controlled path (see
# docs/guides/configuration-reference.md). It must resolve where validation runs
# AND be the path the overlay mounts the mapping at, so the validated bytes are
# exactly the mounted bytes — the configuration fingerprint covers that path.
DELEGATED_CONFIG_FILE="${DELEGATED_CONFIG_FILE:-}"
DELEGATED_MAPPING_FILE="${DELEGATED_MAPPING_FILE:-}"
DELEGATED_SET_ID="${DELEGATED_SET_ID:-user}"
DELEGATED_TRUSTED_CALLBACK="${DELEGATED_TRUSTED_CALLBACK:-}"
DELEGATED_SECRET_NAME="${DELEGATED_SECRET_NAME:-tool-gateway-delegated-config}"

if [ "${SKIP_BROWSER_CREDENTIALS:-}" = "true" ]; then
  echo "SKIP_BROWSER_CREDENTIALS=true; skipping browser credential and acme-admin secret provisioning."
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
  # Dev default: one credential set, for the acme-admin sample app
  # (SPEC-061 retired the static browser-check-target mock and the two
  # sets that served it). Random password; stays inside the cluster
  # secrets.
  CRED_FILE=$(mktemp)
  CLEANUP="$CRED_FILE"
  ACME_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)
  cat > "$CRED_FILE" <<EOF
{
  "acme-admin": {
    "username": "admin",
    "password": "${ACME_PASSWORD}"
  }
}
EOF
fi

# --- validate BEFORE any mutation (SPEC-070 R-6) --------------------------
# Read-only checks; NEITHER calls kubectl, so a refusal aborts with zero cluster
# mutation. python3 is the repository's JSON parser for these helpers (jq is not
# a `make deploy` precondition).
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found; cannot validate credential inputs before mutation." >&2
  exit 1
fi

# 1. The browser credential-set file must parse and still carry the acme-admin
#    password the app-side secret is derived from. This mirrors the live
#    derivation's precondition but runs BEFORE the first secret is created, so a
#    bad file no longer leaves a half-applied browser secret behind.
python3 -c '
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    sets = json.load(handle)
entry = sets.get("acme-admin")
if not isinstance(entry, dict) or not entry.get("password"):
    sys.stderr.write("credential-set file carries no non-empty \"acme-admin\" password.\n")
    raise SystemExit(1)
' "$CRED_FILE"

# 2. If delegated inputs were supplied, validate the administered config +
#    mapping through the versioned guard (the SAME authority the runtime uses:
#    tool_gateway.services.custody_cli validate-config → load_snapshot), never
#    re-implemented in shell. Any refusal exits non-zero BEFORE mutation, and
#    delegation stays disabled until this passes.
if [ -n "$DELEGATED_CONFIG_FILE" ]; then
  if [ ! -f "$DELEGATED_CONFIG_FILE" ]; then
    echo "DELEGATED_CONFIG_FILE not found: $DELEGATED_CONFIG_FILE" >&2
    exit 1
  fi
  if [ -z "$DELEGATED_TRUSTED_CALLBACK" ]; then
    echo "DELEGATED_TRUSTED_CALLBACK is required to validate a delegated config." >&2
    exit 1
  fi
  # Resolve the mapping source for provisioning: an explicit override, else the
  # config's own absolute identity_mapping_path (single source of truth, so the
  # validated bytes and the provisioned bytes are the same bytes).
  if [ -z "$DELEGATED_MAPPING_FILE" ]; then
    DELEGATED_MAPPING_FILE=$(python3 -c '
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    raw = json.load(handle)
entry = raw.get(sys.argv[2])
sys.stdout.write(entry.get("identity_mapping_path", "") if isinstance(entry, dict) else "")
' "$DELEGATED_CONFIG_FILE" "$DELEGATED_SET_ID")
  fi
  if [ -z "$DELEGATED_MAPPING_FILE" ] || [ ! -f "$DELEGATED_MAPPING_FILE" ]; then
    echo "Delegated mapping not resolvable/readable: '${DELEGATED_MAPPING_FILE:-<empty>}'." >&2
    echo "The config's identity_mapping_path must be an absolute path that exists where validation runs." >&2
    exit 1
  fi
  set +e
  VALIDATE_RESULT=$(cd "$REPO_ROOT" && OTEL_SDK_DISABLED=true \
    uv run --offline --frozen --project products/tool-gateway \
    python -m tool_gateway.services.custody_cli validate-config \
    --config-file "$DELEGATED_CONFIG_FILE" --set-id "$DELEGATED_SET_ID" \
    --callback "$DELEGATED_TRUSTED_CALLBACK" 2>&1)
  VALIDATE_STATUS=$?
  set -e
  printf '%s\n' "$VALIDATE_RESULT"
  if [ "$VALIDATE_STATUS" -ne 0 ]; then
    echo "" >&2
    echo "REFUSED: delegated configuration failed validation; NO secret was created and NO rollout occurred." >&2
    echo "Fix the administered config/mapping and re-run. Delegation stays disabled until this passes." >&2
    exit 1
  fi
fi

# --- validation-only mode: stop here, before any cluster mutation ----------
if [ "$VALIDATE_ONLY" = "true" ]; then
  for path in $CLEANUP; do
    rm -f "$path"
  done
  echo "validation-only: all supplied inputs are valid; no secret created, no rollout."
  exit 0
fi

kubectl -n "$NAMESPACE" create secret generic tool-gateway-browser-credentials \
  --from-file=credential-sets.json="$CRED_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

# Second sink: the app-side secret, taken from the same file so the two
# surfaces cannot drift. python3 is the JSON parser the repository's
# other shell helpers use (shared/platform-ops/e2e/*.sh); jq is not a
# precondition of `make deploy`.
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found; cannot derive ACME_ADMIN_PASSWORD from the credential-set file." >&2
  echo "Install python3, or create the acme-admin-credentials secret yourself." >&2
  exit 1
fi

# Written to a temp file rather than passed as --from-literal so the
# value never appears in this process's argv (visible to `ps`).
ACME_SECRET_FILE=$(mktemp)
if [ -n "$CLEANUP" ]; then
  CLEANUP="$CLEANUP $ACME_SECRET_FILE"
else
  CLEANUP="$ACME_SECRET_FILE"
fi

python3 -c '
import json, sys

with open(sys.argv[1], encoding="utf-8") as handle:
    sets = json.load(handle)

entry = sets.get("acme-admin")
if not isinstance(entry, dict) or not entry.get("password"):
    sys.stderr.write(
        "credential-set file carries no non-empty \"acme-admin\" password, so the "
        "acme-admin sample app has nothing to authenticate its operator account "
        "with. Add an \"acme-admin\": {\"username\": ..., \"password\": ...} entry "
        "to BROWSER_CREDENTIAL_SETS_FILE.\n"
    )
    raise SystemExit(1)

# No trailing newline: the app compares this value verbatim.
with open(sys.argv[2], "w", encoding="utf-8") as out:
    out.write(entry["password"])
' "$CRED_FILE" "$ACME_SECRET_FILE"

kubectl -n "$NAMESPACE" create secret generic acme-admin-credentials \
  --from-file=ACME_ADMIN_PASSWORD="$ACME_SECRET_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

# --- delegated config + administered mapping secret (SPEC-070, live path) ---
# Reached only after the guard validation above passed. Both files are mounted
# read-only by the overlay: the config at GATEWAY_DELEGATED_CUSTODY_CONFIG_PATH
# and the mapping at the config's absolute identity_mapping_path. Values are
# written from files (never --from-literal), so no secret enters this process's
# argv. This never enables delegation — the feature flags stay off until the
# overlay turns them on.
if [ -n "$DELEGATED_CONFIG_FILE" ]; then
  kubectl -n "$NAMESPACE" create secret generic "$DELEGATED_SECRET_NAME" \
    --from-file=delegated-sets.json="$DELEGATED_CONFIG_FILE" \
    --from-file=linkage.json="$DELEGATED_MAPPING_FILE" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo "Delegated configuration synced (secret: $DELEGATED_SECRET_NAME)."
fi

for path in $CLEANUP; do
  rm -f "$path"
done

echo "Browser credential sets synced (secret: tool-gateway-browser-credentials)."
echo "acme-admin app password synced (secret: acme-admin-credentials)."

# The gateway reloads the mounted file by mtime, but restart anyway so a
# first deploy does not race the mount.
kubectl -n "$NAMESPACE" rollout restart deployment/tool-gateway >/dev/null
echo "tool-gateway rollout restarted in namespace '$NAMESPACE'."

# The app reads ACME_ADMIN_PASSWORD from its environment at startup, so a
# regenerated secret only takes effect on a new pod. Restart it when it
# is deployed — it is absent on a plain `make deploy`, because samples
# install out-of-band (SPEC-050 R-11).
if kubectl -n "$NAMESPACE" get deployment acme-admin >/dev/null 2>&1; then
  kubectl -n "$NAMESPACE" rollout restart deployment/acme-admin >/dev/null
  echo "acme-admin rollout restarted in namespace '$NAMESPACE'."
fi
