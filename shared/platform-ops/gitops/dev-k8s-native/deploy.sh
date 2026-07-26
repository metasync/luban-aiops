#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
STATE_FILE="${STATE_FILE:-$SCRIPT_DIR/.images.env}"

STATE_FILE="$STATE_FILE" "$SCRIPT_DIR/../deploy-overlay.sh" "$SCRIPT_DIR"
