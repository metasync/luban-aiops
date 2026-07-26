#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROFILE="${1:-}"
TARGET="${2:-both}"
PROFILE_DIR="$SCRIPT_DIR/runtime-profiles/$PROFILE"

if [ -z "$PROFILE" ]; then
  echo "Usage: $0 <deepseek|dashscope|openai> [transitional|native|both]" >&2
  exit 1
fi

if [ ! -d "$PROFILE_DIR" ]; then
  echo "Unknown runtime profile: $PROFILE" >&2
  exit 1
fi

write_transitional() {
  cat <<EOF > "$SCRIPT_DIR/dev-k8s-transitional/kustomization.yaml"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - base
  - ../runtime-profiles/$PROFILE
EOF
}

write_native() {
  cat <<EOF > "$SCRIPT_DIR/dev-k8s-native/kustomization.yaml"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - base
  - ../runtime-profiles/$PROFILE
EOF
}

case "$TARGET" in
  transitional)
    write_transitional
    ;;
  native)
    write_native
    ;;
  both)
    write_transitional
    write_native
    ;;
  *)
    echo "Unknown target: $TARGET" >&2
    exit 1
    ;;
esac

echo "Selected runtime profile '$PROFILE' for target '$TARGET'."
