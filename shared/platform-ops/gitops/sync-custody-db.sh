#!/bin/sh

# Provision the SPEC-070 delegated-custody database, its two SEPARATE
# least-privilege roles, and the runtime DSN secret for the dev-k8s overlay.
#
# Least privilege (plan line 166): the gateway send path connects as
# `custody_runtime` (DML only on gateway-owned tables); migration, key rotation,
# and recovery administration use `custody_operator` (DDL + key_policy value
# authority). The grant set is the committed mirror of the boundary the
# disposable-Postgres integration proof already tests (`make
# delegated-custody-test`).
#
# This script never enables delegation. Every GATEWAY_DELEGATED_*_ENABLED gate
# stays false until an operator provisions the keyring, the administered
# config/mapping (see sync-browser-credentials.sh --validate-only), and a real
# OAuth target, then flips the gates in the delegated-dev runtime-profile.
#
# Secrets discipline: role passwords are GENERATED here (or reused from the
# existing cluster secret), written only to 0600 temp files, and delivered via
# `--from-file` — never `--from-literal`, never argv, never committed, never
# logged. The DSNs are reconstructed from those files, so no credential appears
# in this process's argument list either.
#
# Order of operations (idempotent; safe to re-run):
#   1. ensure the `custody` database exists (fresh clusters also get it via the
#      postgres-initdb ConfigMap: infra/create-custody-db.sql),
#   2. create the two roles if absent (infra/custody-roles.sql) and set their
#      passwords from the environment, only when newly created,
#   3. run `custody_cli migrate` as custody_operator (creates the gateway_custody
#      schema/tables; requires CUSTODY_KEYRING_FILE),
#   4. apply the runtime table grants (infra/custody-grants.sql) AFTER migrate,
#   5. write the tool-gateway-custody-db (runtime) and custody-operator-dsn
#      (admin) secrets, both carrying in-cluster DSNs (host `postgres`),
#   6. publish the operator-supplied keyring as tool-gateway-custody-keyring so
#      the gateway can mount it read-only (delegated-dev overlay).
#
# The migration in step 3 runs from the repo root (the versioned guard lives in
# the tool-gateway project, not in the postgres pod), so it connects over
# CUSTODY_PG_HOST — default `localhost`, i.e. through a port-forward:
#   kubectl -n <ns> port-forward svc/postgres 5432:5432
#
# Usage:
#   CUSTODY_KEYRING_FILE=/secure/path/keyring.json \
#     shared/platform-ops/gitops/sync-custody-db.sh [namespace]
#
# Skip in CI when secrets are injected externally:
#   SKIP_CUSTODY_DB=true make deploy

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
INFRA_DIR="$SCRIPT_DIR/dev-k8s/base/infra"

NAMESPACE="dev-luban-aiops"
while [ $# -gt 0 ]; do
  case "$1" in
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) NAMESPACE="$1"; shift ;;
  esac
done

if [ "${SKIP_CUSTODY_DB:-}" = "true" ]; then
  echo "SKIP_CUSTODY_DB=true; skipping delegated-custody database provisioning."
  exit 0
fi

if [ -z "${CUSTODY_KEYRING_FILE:-}" ] || [ ! -f "${CUSTODY_KEYRING_FILE:-}" ]; then
  echo "CUSTODY_KEYRING_FILE must point at the versioned custody keyring JSON." >&2
  echo "The operator migration cannot run without it (it authenticates the key set)." >&2
  exit 1
fi

# Host the out-of-cluster migration connects through (a port-forward by default);
# the in-cluster DSNs stored in the secrets always use the `postgres` service.
CUSTODY_PG_HOST="${CUSTODY_PG_HOST:-localhost}"

POSTGRES_POD=$(kubectl -n "$NAMESPACE" get pods -l app=postgres \
  -o jsonpath='{.items[0].metadata.name}')
if [ -z "$POSTGRES_POD" ]; then
  echo "No postgres pod found in namespace '$NAMESPACE'; deploy the overlay first." >&2
  exit 1
fi

# Admin connection inside the pod uses the committed dev-local superuser; the
# generated role passwords below are what the runtime/operator DSNs carry.
PG="kubectl -n $NAMESPACE exec -i $POSTGRES_POD --"

# --- temp files (all 0600, all cleaned on exit) ----------------------------
PW_SQL=$(mktemp);            chmod 600 "$PW_SQL"
RUNTIME_PW_FILE=$(mktemp);   chmod 600 "$RUNTIME_PW_FILE"
OPERATOR_PW_FILE=$(mktemp);  chmod 600 "$OPERATOR_PW_FILE"
MIGRATE_DSN_FILE=$(mktemp);  chmod 600 "$MIGRATE_DSN_FILE"
RUNTIME_DSN_FILE=$(mktemp);  chmod 600 "$RUNTIME_DSN_FILE"
OPERATOR_DSN_FILE=$(mktemp); chmod 600 "$OPERATOR_DSN_FILE"
trap 'rm -f "$PW_SQL" "$RUNTIME_PW_FILE" "$OPERATOR_PW_FILE" "$MIGRATE_DSN_FILE" "$RUNTIME_DSN_FILE" "$OPERATOR_DSN_FILE"' EXIT

# --- 1. database (idempotent) ---------------------------------------------
$PG sh -c 'psql -U audit -tAc "SELECT 1 FROM pg_database WHERE datname = '\''custody'\''" | grep -q 1 \
  || psql -U audit -c "CREATE DATABASE custody"'
echo "Database 'custody' is present on $POSTGRES_POD."

# --- 2. roles (idempotent) + generated passwords --------------------------
$PG psql -U audit -d custody -v ON_ERROR_STOP=1 < "$INFRA_DIR/custody-roles.sql"

# Reuse existing passwords when the secrets already exist so a re-run never
# rotates a live password out from under the mounted runtime DSN.
if kubectl -n "$NAMESPACE" get secret tool-gateway-custody-db >/dev/null 2>&1; then
  echo "Reusing the existing custody role passwords from the cluster secrets."
  kubectl -n "$NAMESPACE" get secret tool-gateway-custody-db \
    -o jsonpath='{.data.custody-runtime-password}' | base64 --decode > "$RUNTIME_PW_FILE"
  kubectl -n "$NAMESPACE" get secret custody-operator-dsn \
    -o jsonpath='{.data.custody-operator-password}' | base64 --decode > "$OPERATOR_PW_FILE"
else
  openssl rand -hex 24 | tr -d '\n' > "$RUNTIME_PW_FILE"
  openssl rand -hex 24 | tr -d '\n' > "$OPERATOR_PW_FILE"
  echo "Generated new custody role passwords (stored only in the cluster secrets)."
fi
RUNTIME_PW=$(cat "$RUNTIME_PW_FILE")
OPERATOR_PW=$(cat "$OPERATOR_PW_FILE")

# Passwords are handed to psql through the environment (\getenv), never argv.
cat > "$PW_SQL" <<'SQL'
\getenv operator_pw CUSTODY_OPERATOR_PASSWORD
\getenv runtime_pw CUSTODY_RUNTIME_PASSWORD
ALTER ROLE custody_operator LOGIN PASSWORD :'operator_pw';
ALTER ROLE custody_runtime LOGIN PASSWORD :'runtime_pw';
SQL
CUSTODY_OPERATOR_PASSWORD="$OPERATOR_PW" CUSTODY_RUNTIME_PASSWORD="$RUNTIME_PW" \
  $PG psql -U audit -d custody -v ON_ERROR_STOP=1 -f - < "$PW_SQL"

# In-cluster DSNs (stored in the secrets) and the out-of-cluster migration DSN.
printf 'postgresql://custody_runtime:%s@postgres:5432/custody' "$RUNTIME_PW" > "$RUNTIME_DSN_FILE"
printf 'postgresql://custody_operator:%s@postgres:5432/custody' "$OPERATOR_PW" > "$OPERATOR_DSN_FILE"
printf 'postgresql://custody_operator:%s@%s:5432/custody' "$OPERATOR_PW" "$CUSTODY_PG_HOST" > "$MIGRATE_DSN_FILE"

# --- 3. operator migration (creates gateway_custody schema/tables) ---------
# Runs from the repo as custody_operator via the versioned guard; the DSN is
# read from a 0600 file (--dsn-file), never passed as a literal.
(cd "$REPO_ROOT" && OTEL_SDK_DISABLED=true \
  uv run --offline --frozen --project products/tool-gateway \
  python -m tool_gateway.services.custody_cli migrate \
  --dsn-file "$MIGRATE_DSN_FILE" --keyring-file "$CUSTODY_KEYRING_FILE")

# --- 4. runtime table grants (AFTER migrate creates the tables) ------------
$PG psql -U audit -d custody -v ON_ERROR_STOP=1 < "$INFRA_DIR/custody-grants.sql"
echo "Applied least-privilege runtime grants (custody_runtime: DML only)."

# --- 5. secrets (from files, never --from-literal) -------------------------
# The runtime secret is the gateway's envFrom source (GATEWAY_DELEGATED_CUSTODY_DB_URL);
# the raw password key is what the idempotent re-run path reads back.
kubectl -n "$NAMESPACE" create secret generic tool-gateway-custody-db \
  --from-file=GATEWAY_DELEGATED_CUSTODY_DB_URL="$RUNTIME_DSN_FILE" \
  --from-file=custody-runtime-password="$RUNTIME_PW_FILE" \
  --dry-run=client -o yaml | kubectl -n "$NAMESPACE" apply -f -
echo "Synced secret 'tool-gateway-custody-db' (runtime DSN) in namespace '$NAMESPACE'."

# The operator DSN is a SEPARATE admin-only secret; it is never mounted by the
# gateway pod and never part of the gateway's envFrom.
kubectl -n "$NAMESPACE" create secret generic custody-operator-dsn \
  --from-file=custody-operator-dsn="$OPERATOR_DSN_FILE" \
  --from-file=custody-operator-password="$OPERATOR_PW_FILE" \
  --dry-run=client -o yaml | kubectl -n "$NAMESPACE" apply -f -
echo "Synced secret 'custody-operator-dsn' (admin DSN) in namespace '$NAMESPACE'."

# --- 6. keyring secret (the gateway mounts this read-only) -----------------
# Published from the SAME operator-supplied file the migration authenticated
# with, via --from-file (never argv), so the versioned key material is never
# committed, logged, or exposed in this process's argument list. The
# delegated-dev overlay mounts it at GATEWAY_DELEGATED_CUSTODY_KEYRING_PATH.
kubectl -n "$NAMESPACE" create secret generic tool-gateway-custody-keyring \
  --from-file=keyring.json="$CUSTODY_KEYRING_FILE" \
  --dry-run=client -o yaml | kubectl -n "$NAMESPACE" apply -f -
echo "Synced secret 'tool-gateway-custody-keyring' (versioned custody key set)."

echo ""
echo "Delegated-custody database provisioned with least-privilege roles."
echo "Delegation remains DISABLED: flip the GATEWAY_DELEGATED_*_ENABLED gates in the"
echo "delegated-dev runtime-profile only after the keyring, the administered"
echo "config/mapping, and a real OAuth target are provisioned."
