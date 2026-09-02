#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROFILE="${1:-}"
PROFILE_DIR="$SCRIPT_DIR/runtime-profiles/$PROFILE"

if [ -z "$PROFILE" ]; then
  echo "Usage: $0 <default>" >&2
  exit 1
fi

if [ "$PROFILE" = "mutating-dev" ] || [ "$PROFILE" = "browser-dev" ]; then
  # mutating-dev (SPEC-022 R-3) and browser-dev (SPEC-049 R-7) are the
  # committed dev postures, always wired in below — they are never
  # switchable LLM provider profiles.
  echo "$PROFILE is not a switchable LLM runtime profile" >&2
  exit 1
fi

if [ ! -d "$PROFILE_DIR" ]; then
  echo "Unknown runtime profile: $PROFILE" >&2
  exit 1
fi

# The LLM provider profile is switchable; the mutating-dev (SPEC-022
# R-3) and browser-dev (SPEC-049 R-7) profiles are the committed dev
# postures and always stay wired in.
cat <<EOF > "$SCRIPT_DIR/dev-k8s/kustomization.yaml"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: dev-luban-aiops
resources:
  - base
  - ../runtime-profiles/$PROFILE
  - ../runtime-profiles/mutating-dev
  - ../runtime-profiles/browser-dev
configMapGenerator:
  - name: platform-runtime-config
    behavior: merge
    envs:
      - ../runtime-profiles/mutating-dev/mutating.env
      - ../runtime-profiles/browser-dev/browser.env
patches:
  # SPEC-049: chromium-headless-shell sidecar + credential-set mount on
  # the tool-gateway pod (browser-dev posture).
  - path: ../runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml
    target:
      kind: Deployment
      name: tool-gateway
EOF

echo "Selected runtime profile '$PROFILE' for dev-k8s overlay."
