#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

STATE_FILE="${STATE_FILE:-$SCRIPT_DIR/.images.env}" \
IMAGE_TAG_PREFIX="${IMAGE_TAG_PREFIX:-dev-k8s-native}" \
IMAGE_BUILD_LABEL="${IMAGE_BUILD_LABEL:-native overlay}" \
"$SCRIPT_DIR/../dev-k8s-transitional/build-images.sh"
