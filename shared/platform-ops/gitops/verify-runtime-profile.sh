#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OVERLAY_DIR="$SCRIPT_DIR/dev-k8s"

current_profile() {
  grep '\.\.\/runtime-profiles\/' "$1/kustomization.yaml" | sed 's/.*runtime-profiles\///'
}

PROFILE=$(current_profile "$OVERLAY_DIR")

echo "Active profile: $PROFILE"

kubectl kustomize "$OVERLAY_DIR" >/dev/null

echo "Kustomize render succeeded for dev-k8s overlay."
