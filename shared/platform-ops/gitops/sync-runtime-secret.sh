#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROFILE="${1:-}"
NAMESPACE="${2:-dev-luban-aiops}"
SECRET_NAME="${SECRET_NAME:-agent-platform-runtime-secrets}"

if [ -z "$PROFILE" ]; then
  echo "Usage: $0 <default> [namespace]" >&2
  exit 1
fi

SECRET_FILE="$SCRIPT_DIR/runtime-profiles/$PROFILE/runtime-secrets.env"

if [ ! -f "$SECRET_FILE" ]; then
  echo "Missing secret file: $SECRET_FILE" >&2
  echo "Copy runtime-secrets.example.env to runtime-secrets.env for the selected profile first." >&2
  echo "If Luban CI injects secrets for this environment, you can skip this script." >&2
  exit 1
fi

kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
  --from-env-file="$SECRET_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Synced secret '$SECRET_NAME' for profile '$PROFILE' in namespace '$NAMESPACE'."
