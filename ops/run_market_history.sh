#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"

[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }

set -a
source "$ENV_FILE"
MACRO_ENV_FILE="${MMP_MACRO_ENV_FILE:-/home/kegor2/mydream2000.env}"
if [[ -f "$MACRO_ENV_FILE" ]]; then
  source "$MACRO_ENV_FILE"
fi
set +a
HISTORY_PYTHON_BIN="${MMP_HISTORY_PYTHON:-$PROJECT_DIR/tools/market_history_env/bin/python}"
[[ -x "$HISTORY_PYTHON_BIN" ]] || { echo "[FAIL] missing history python: $HISTORY_PYTHON_BIN" >&2; exit 2; }
export MPLCONFIGDIR="$PROJECT_DIR/data/state/matplotlib"

cd "$PROJECT_DIR"
"$HISTORY_PYTHON_BIN" ops/build_market_history.py
