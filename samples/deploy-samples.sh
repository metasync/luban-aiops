#!/bin/sh

# Install/uninstall tutorial sample skills into the dev cluster (SPEC-050 R-11).
#
# Samples are self-contained: each sample directory under samples/ ships its
# skill document(s) in a skill/ subdirectory and nothing else. This script is
# the ONLY thing that couples a sample to a running cluster — it packs the
# selected samples' skill files into the optional `skills-samples` ConfigMap
# that the skills-hub base deployment mounts (read-only) at /skills/samples,
# then restarts skills-hub so the `samples` local source re-ingests.
#
# The base overlay never names a specific sample: it declares the generic
# `samples` source and an empty/absent ConfigMap, so `make deploy` works with
# zero samples installed. Dependency direction stays tutorial -> platform.
#
# Resulting skill ids are `samples/<slug>`, where <slug> is the mounted file
# name lowercased with every run of non-alphanumerics collapsed to '-':
#   samples/web-checks/password-reset/skill/ResetUserPassword.md
#     -> ConfigMap key  password-reset-ResetUserPassword.md
#     -> skill_id       samples/password-reset-resetuserpassword
#
# Usage:
#   samples/deploy-samples.sh [namespace]                 # install ALL samples
#   SAMPLE=web-checks/password-reset \
#     samples/deploy-samples.sh [namespace]               # install ONE sample
#   ACTION=undeploy samples/deploy-samples.sh [namespace] # remove ALL samples
#
# The ConfigMap is declarative: it always ends up holding exactly the selected
# set. `SAMPLE=<one>` therefore installs only that sample (dropping others);
# re-run without SAMPLE to restore all. Idempotent and re-runnable. The
# ConfigMap is not base-managed, so it survives `make deploy` (which applies
# the base overlay without prune); run this once the cluster is up, i.e. after
# `make deploy` has created skills-hub.
#
# Environment overrides:
#   NAMESPACE / $1  (default dev-luban-aiops)
#   ACTION          (deploy | undeploy; default deploy)
#   SAMPLE          (path under samples/, e.g. web-checks/password-reset;
#                    empty = all samples)

set -eu

NAMESPACE="${1:-${NAMESPACE:-dev-luban-aiops}}"
ACTION="${ACTION:-deploy}"
SAMPLE="${SAMPLE:-}"

CONFIGMAP="skills-samples"
DEPLOYMENT="skills-hub"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SAMPLES_DIR="$SCRIPT_DIR"

TMPDIR_WORK=$(mktemp -d)
trap 'rm -rf "$TMPDIR_WORK"' EXIT
ROOTS_FILE="$TMPDIR_WORK/roots"
ARGS_FILE="$TMPDIR_WORK/args"

restart_skills_hub() {
  kubectl -n "$NAMESPACE" rollout restart "deployment/$DEPLOYMENT"
  kubectl -n "$NAMESPACE" rollout status "deployment/$DEPLOYMENT" --timeout=180s
}

require_skills_hub() {
  kubectl -n "$NAMESPACE" get "deployment/$DEPLOYMENT" >/dev/null 2>&1 || {
    echo "skills-hub deployment not found in namespace '$NAMESPACE'." >&2
    echo "Run 'make deploy' first, then re-run this." >&2
    exit 1
  }
}

# --- undeploy: drop every sample skill -------------------------------------
if [ "$ACTION" = "undeploy" ]; then
  require_skills_hub
  echo "==> undeploy-samples: removing '$CONFIGMAP' from $NAMESPACE"
  kubectl -n "$NAMESPACE" delete configmap "$CONFIGMAP" --ignore-not-found
  restart_skills_hub
  echo "all sample skills removed; skills-hub re-ingested without the samples source content"
  exit 0
fi

if [ "$ACTION" != "deploy" ]; then
  echo "unknown ACTION='$ACTION' (expected deploy|undeploy)" >&2
  exit 2
fi

require_skills_hub

# --- discover sample roots (any dir under samples/ with a skill/ subdir) ----
if [ -n "$SAMPLE" ]; then
  candidate="$SAMPLES_DIR/$SAMPLE"
  if [ ! -d "$candidate/skill" ]; then
    echo "SAMPLE='$SAMPLE' has no skill/ directory under $SAMPLES_DIR" >&2
    exit 1
  fi
  printf '%s\n' "$candidate" > "$ROOTS_FILE"
else
  find "$SAMPLES_DIR" -type d -name skill | while IFS= read -r d; do
    dirname "$d"
  done | sort > "$ROOTS_FILE"
fi

if [ ! -s "$ROOTS_FILE" ]; then
  echo "no samples with a skill/ directory found under $SAMPLES_DIR" >&2
  exit 1
fi

# --- build --from-file args: key = <sample-leaf>-<relpath, '/' -> '-'> ------
: > "$ARGS_FILE"
while IFS= read -r root; do
  leaf=$(basename "$root")
  skilldir="$root/skill"
  find "$skilldir" -type f -name '*.md' | sort | while IFS= read -r f; do
    rel=${f#"$skilldir/"}
    flat=$(printf '%s' "$rel" | tr '/' '-')
    printf '%s\n' "--from-file=$leaf-$flat=$f"
  done >> "$ARGS_FILE"
done < "$ROOTS_FILE"

if [ ! -s "$ARGS_FILE" ]; then
  echo "selected sample(s) contain no skill/*.md files" >&2
  exit 1
fi

# --- (re)create the ConfigMap with exactly the selected set -----------------
set --
while IFS= read -r line; do
  set -- "$@" "$line"
done < "$ARGS_FILE"

echo "==> deploy-samples: packing $# skill file(s) into '$CONFIGMAP' ($NAMESPACE)"
while IFS= read -r line; do
  echo "    ${line#--from-file=}"
done < "$ARGS_FILE"

kubectl -n "$NAMESPACE" create configmap "$CONFIGMAP" "$@" \
  --dry-run=client -o yaml | kubectl -n "$NAMESPACE" apply -f -

restart_skills_hub

echo "sample skills installed under source_id 'samples' (skill_id samples/<slug>);"
echo "skills-hub restarted to re-ingest. Verify with:"
echo "  kubectl -n $NAMESPACE exec deployment/$DEPLOYMENT -- ls -1 /skills/samples"
