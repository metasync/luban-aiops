#!/bin/sh

# Execution-runtime version cutover / downgrade guard (SPEC-063 R-7b).
#
# Routine forward deploys (`make deploy`) only ever move execution-runtime
# to the same or a newer coordinated image tag, which this guard allows
# without interlock. This wrapper exists for the DELIBERATE, rare paths
# that must never happen silently:
#
#   * a binary DOWNGRADE (older execution-runtime than what is deployed), or
#   * any change whose relative version cannot be determined.
#
# Old binaries cannot be trusted to honor a new admission flag, so a
# mutation-enabled downgrade is REFUSED unless the operator explicitly
# selects `EXECUTION_RECOVERY_MODE=disabled-recovery`. In that mode the
# wrapper enforces the preconditions BEFORE any binary is replaced:
#
#   1. gateway mutations disabled (operator confirms by exporting
#      EXECUTION_MUTATIONS_DISABLED=true after removing the mutating
#      runtime profile / clearing EXECUTION_ADMISSION_ENABLED), and
#   2. the worker stopped (execution-runtime scaled to zero) with an
#      old-process inventory proving no execution-capable pod remains.
#
# The decision itself is made by the versioned Python guard
# (execution_runtime.services.execution_cutover) so the refusal logic is
# the same code the failure harness exercises at F-33 — this shell wrapper
# only wires it to kubectl and refuses on a denial. NOTHING here ever
# enables admission; enabling stays an explicit, separately authorized step.
#
# Usage:
#   shared/platform-ops/gitops/execution-cutover.sh \
#     --current <version> --target <version> [--admission-enabled] [namespace]
#
# Plan only (print the decision, mutate nothing):
#   EXECUTION_CUTOVER_PLAN_ONLY=true \
#     shared/platform-ops/gitops/execution-cutover.sh --current 0.42.0 --target 0.41.0
#
# Disabled-recovery downgrade (mutations already disabled by the operator):
#   EXECUTION_RECOVERY_MODE=disabled-recovery EXECUTION_MUTATIONS_DISABLED=true \
#     shared/platform-ops/gitops/execution-cutover.sh --current 0.42.0 --target 0.41.0
#
# See docs/guides/execution-cutover-restore.md for the full runbook, the
# old-validity wait, and the lost-evidence / no-universal-rollback limits.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
NAMESPACE="${NAMESPACE:-dev-luban-aiops}"
RECOVERY_MODE="${EXECUTION_RECOVERY_MODE:-normal}"
PLAN_ONLY="${EXECUTION_CUTOVER_PLAN_ONLY:-false}"

CURRENT_VERSION=""
TARGET_VERSION=""
ADMISSION_ENABLED=""

while [ $# -gt 0 ]; do
  case "$1" in
    --current) CURRENT_VERSION="${2:-}"; shift 2 ;;
    --target) TARGET_VERSION="${2:-}"; shift 2 ;;
    --admission-enabled) ADMISSION_ENABLED="--admission-enabled"; shift ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) NAMESPACE="$1"; shift ;;
  esac
done

if [ -z "$CURRENT_VERSION" ] || [ -z "$TARGET_VERSION" ]; then
  echo "Usage: $0 --current <version> --target <version> [--admission-enabled] [namespace]" >&2
  exit 2
fi

case "$RECOVERY_MODE" in
  normal|disabled-recovery) ;;
  *) echo "EXECUTION_RECOVERY_MODE must be 'normal' or 'disabled-recovery' (got '$RECOVERY_MODE')." >&2; exit 2 ;;
esac

# --- decision (versioned Python guard; same code F-33 exercises) --------------

# The guard prints its decision as JSON and exits non-zero when the change is
# refused. Capture both so a refusal is reported verbatim and never proceeds.
set +e
# shellcheck disable=SC2086
DECISION=$(cd "$REPO_ROOT" && OTEL_SDK_DISABLED=true \
  uv run --offline --frozen --project products/execution-runtime \
  python -m execution_runtime.services.execution_cutover plan-cutover \
  --current-version "$CURRENT_VERSION" --target-version "$TARGET_VERSION" \
  $ADMISSION_ENABLED --mode "$RECOVERY_MODE" 2>&1)
STATUS=$?
set -e

echo "Cutover decision ($CURRENT_VERSION -> $TARGET_VERSION, mode=$RECOVERY_MODE):"
printf '%s\n' "$DECISION"

if [ "$STATUS" -ne 0 ]; then
  echo "" >&2
  echo "REFUSED: execution-runtime cutover $CURRENT_VERSION -> $TARGET_VERSION is not" >&2
  echo "allowed in mode '$RECOVERY_MODE'. A mutation-enabled downgrade (or a change" >&2
  echo "whose version cannot be determined) requires EXECUTION_RECOVERY_MODE=disabled-recovery" >&2
  echo "with gateway mutations disabled and the worker stopped first. Admission was NOT" >&2
  echo "changed. See docs/guides/execution-cutover-restore.md." >&2
  exit 1
fi

if [ "$PLAN_ONLY" = "true" ]; then
  echo "EXECUTION_CUTOVER_PLAN_ONLY=true; decision printed, nothing mutated."
  exit 0
fi

# --- disabled-recovery preconditions (downgrade / unknown only) ---------------

# A plain upgrade/same change carries no interlock; the guard reports
# must_stop_worker=false and we hand off to the normal deploy path.
MUST_STOP=$(printf '%s\n' "$DECISION" | sed -n 's/.*"must_stop_worker":[ ]*\([a-z]*\).*/\1/p')
MUST_DISABLE=$(printf '%s\n' "$DECISION" | sed -n 's/.*"must_disable_mutations":[ ]*\([a-z]*\).*/\1/p')

if [ "$MUST_STOP" != "true" ] || [ "$MUST_DISABLE" != "true" ]; then
  echo "No downgrade interlock required; proceed with the normal deploy"
  echo "(make deploy). Admission is never enabled by this wrapper."
  exit 0
fi

if [ "${EXECUTION_MUTATIONS_DISABLED:-}" != "true" ]; then
  echo "" >&2
  echo "REFUSED: disabled-recovery requires gateway mutations to be disabled first." >&2
  echo "Remove the mutating runtime profile / clear EXECUTION_ADMISSION_ENABLED, then" >&2
  echo "re-run with EXECUTION_MUTATIONS_DISABLED=true to confirm. Admission was NOT changed." >&2
  exit 1
fi

echo "Mutations confirmed disabled; stopping the worker before the binary change..."
kubectl --request-timeout=15s -n "$NAMESPACE" scale deployment/execution-runtime --replicas=0
WORKERS=$(kubectl --request-timeout=15s -n "$NAMESPACE" get pods -l app=execution-runtime -o name)
if [ -n "$WORKERS" ]; then
  kubectl --request-timeout=15s -n "$NAMESPACE" wait --for=delete pods \
    -l app=execution-runtime --timeout=120s
fi

# --- old-process inventory ----------------------------------------------------
#
# Termination of a pod does NOT prove downstream work stopped, and it does not
# release any durable claim. List every remaining execution-capable pod so the
# operator can confirm none can still send; classify anything ambiguous as
# unresolved and investigate downstream before the old-validity wait expires.

echo ""
echo "Old-process inventory (must be empty before replacing the binary):"
WORKERS=$(kubectl --request-timeout=15s -n "$NAMESPACE" get pods -l app=execution-runtime -o name)
ISSUERS=$(kubectl --request-timeout=15s -n "$NAMESPACE" get pods -l app=agent-service -o name)
if [ -n "$WORKERS" ] || [ -n "$ISSUERS" ]; then
  echo "REFUSED: old execution-capable pods remain; stop and inventory every sender before replacement." >&2
  exit 1
fi

echo ""
echo "Worker stopped and mutations disabled. You may now replace the binary."
echo "Admission remains DISABLED. Before any fresh, separately approved action,"
echo "wait out the old-validity window (900s max request lifetime from the last"
echo "possible issuer shutdown, plus a bounded clock-disagreement margin) and"
echo "follow docs/guides/execution-cutover-restore.md (rotate the external epoch"
echo "with rotate-execution-epoch.sh after any restore). This wrapper never"
echo "re-enables admission and never claims universal rollback detection."
