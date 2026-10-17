#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OVERLAY_DIR="$SCRIPT_DIR/dev-k8s"

current_profile() {
  # mutating-dev (SPEC-022 R-3), browser-dev (SPEC-049 R-7), secrets-dev
  # (SPEC-062 R-7) and ansible-dev (SPEC-069 R-6) are the committed dev
  # postures, not switchable LLM provider profiles, so they stay out of the
  # report.
  grep '\.\.\/runtime-profiles\/' "$1/kustomization.yaml" | grep -Ev 'mutating-dev|browser-dev|secrets-dev|ansible-dev' | sed 's/.*runtime-profiles\///'
}

PROFILE=$(current_profile "$OVERLAY_DIR")

echo "Active profile: $PROFILE"

# The base loads skill files from outside the overlay root, matching the
# root Makefile's overlays gate.
kubectl kustomize --load-restrictor LoadRestrictionsNone "$OVERLAY_DIR" >/dev/null

echo "Kustomize render succeeded for dev-k8s overlay."
