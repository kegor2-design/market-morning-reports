#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
"$SCRIPT_DIR/check_research_portal_theme.sh" "$ROOT"
exec "$SCRIPT_DIR/preflight_us_state_release.sh" "$@"
