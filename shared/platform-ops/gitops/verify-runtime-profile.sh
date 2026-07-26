#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TRANSITIONAL_DIR="$SCRIPT_DIR/dev-k8s-transitional"
NATIVE_DIR="$SCRIPT_DIR/dev-k8s-native"

current_profile() {
  grep '\.\./runtime-profiles/' "$1/kustomization.yaml" | sed 's/.*runtime-profiles\///'
}

TRANSITIONAL_PROFILE=$(current_profile "$TRANSITIONAL_DIR")
NATIVE_PROFILE=$(current_profile "$NATIVE_DIR")

echo "Transitional profile: $TRANSITIONAL_PROFILE"
echo "Native profile: $NATIVE_PROFILE"

kubectl kustomize "$TRANSITIONAL_DIR" >/dev/null
kubectl kustomize "$NATIVE_DIR" >/dev/null

echo "Kustomize render succeeded for dev-k8s-transitional and dev-k8s-native."
