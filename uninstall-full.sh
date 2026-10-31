#!/usr/bin/env bash
# Full purge entry point. Preview by default; never runs install/uninstall implicitly.
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 "$SCRIPT_DIR/scripts/uninstall_full.py" --project-dir "$SCRIPT_DIR" "$@"
