#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROFILE="${1:-}"
PROFILE_DIR="$SCRIPT_DIR/runtime-profiles/$PROFILE"

if [ -z "$PROFILE" ]; then
  echo "Usage: $0 <deepseek|dashscope|openai>" >&2
  exit 1
fi

if [ "$PROFILE" = "mutating-dev" ]; then
  # mutating-dev is the committed dev posture (SPEC-022 R-3), always
  # wired in below — it is never a switchable LLM provider profile.
  echo "mutating-dev is not a switchable LLM runtime profile" >&2
  exit 1
fi

if [ ! -d "$PROFILE_DIR" ]; then
  echo "Unknown runtime profile: $PROFILE" >&2
  exit 1
fi

# The LLM provider profile is switchable; the mutating-dev profile is the
# committed dev posture (SPEC-022 R-3) and always stays wired in.
cat <<EOF > "$SCRIPT_DIR/dev-k8s/kustomization.yaml"
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: dev-luban-aiops
resources:
  - base
  - ../runtime-profiles/$PROFILE
  - ../runtime-profiles/mutating-dev
configMapGenerator:
  - name: platform-runtime-config
    behavior: merge
    envs:
      - ../runtime-profiles/mutating-dev/mutating.env
EOF

echo "Selected runtime profile '$PROFILE' for dev-k8s overlay."
