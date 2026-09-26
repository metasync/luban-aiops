#!/bin/sh

# External admission-epoch rotation after a database restore (SPEC-063 R-7b).
#
# A same-era snapshot cannot be detected by a flag stored INSIDE that
# snapshot, so restoring the execution ledger database is a disabled-recovery
# operation whose interlock is MANDATORY and EXTERNAL: the restored catalog
# carries the OLD admission epoch, and until the operator rotates the EXTERNAL
# epoch to match the new deployment, every claim fails closed with
# `epoch_mismatch`. This never enables admission — it only records the new
# epoch with admission STILL disabled, so a restore can never silently return
# the platform to process-local execution or mint dispatch authority.
#
# `migrate()` deliberately refuses to change an existing epoch, so this is the
# only supported rotation path. It refuses an enabled catalog (disable it
# first) and an invalid schema, and is idempotent for the epoch already stored.
#
# Order of operations for a restore (see the runbook for the full procedure):
#   1. retain evidence OUTSIDE the restored snapshot,
#   2. stop every possible old sender,
#   3. rotate the external epoch (this script) AND the handoff credential,
#   4. wait out the old-validity window (900s from the last possible issuer
#      shutdown plus a bounded clock-disagreement margin),
#   5. investigate possibly running downstream work,
#   6. only then consider fresh, separately approved actions (admission is
#      enabled by a separate, explicit step — never by this script).
#
# Usage:
#   shared/platform-ops/gitops/rotate-execution-epoch.sh --epoch <uuid> [namespace]
#
# The DSN is read from EXECUTION_STATE_DB_URL (override with --dsn-env).
# Provide a fresh UUID; reusing the pre-restore epoch defeats the interlock.
#
# See docs/guides/execution-cutover-restore.md.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
NAMESPACE="${NAMESPACE:-dev-luban-aiops}"

EPOCH=""
DSN_ENV="EXECUTION_STATE_DB_URL"

while [ $# -gt 0 ]; do
  case "$1" in
    --epoch) EPOCH="${2:-}"; shift 2 ;;
    --dsn-env) DSN_ENV="${2:-}"; shift 2 ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) NAMESPACE="$1"; shift ;;
  esac
done

if [ -z "$EPOCH" ]; then
  echo "Usage: $0 --epoch <uuid> [--dsn-env VAR] [namespace]" >&2
  exit 2
fi

# The DSN is resolved by name inside the versioned guard (os.environ[DSN_ENV]);
# a missing/empty DSN makes the guard fail closed (store_unavailable) rather
# than being re-implemented here in shell. The guard also refuses an enabled
# catalog, an invalid schema, and a malformed epoch; on any refusal it exits
# non-zero and admission remains disabled.
set +e
RESULT=$(cd "$REPO_ROOT" && OTEL_SDK_DISABLED=true \
  uv run --offline --frozen --project products/execution-runtime \
  python -m execution_runtime.services.execution_cutover rotate-epoch \
  --epoch "$EPOCH" --dsn-env "$DSN_ENV" 2>&1)
STATUS=$?
set -e

printf '%s\n' "$RESULT"

if [ "$STATUS" -ne 0 ]; then
  echo "" >&2
  echo "REFUSED: external epoch rotation did not complete; admission remains DISABLED." >&2
  echo "Disable admission on the restored catalog first if it was enabled, verify the" >&2
  echo "schema, and re-run. See docs/guides/execution-cutover-restore.md." >&2
  exit 1
fi

echo ""
echo "External epoch recorded with admission STILL disabled. Rotate the handoff"
echo "credential, wait out the old-validity window, and investigate downstream work"
echo "before any fresh approved action. Enabling admission is a separate, explicit,"
echo "separately authorized step — this script never does it."
