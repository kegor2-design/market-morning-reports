#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
RUNNER="$PROJECT_DIR/ops/update_market_history.sh"
MARKER="# MARKET_HISTORY_WEEKLY"
LINE="20 7 * * 6 /usr/bin/flock -n /tmp/market_history.lock $RUNNER $PROJECT_DIR $ENV_FILE >> $PROJECT_DIR/logs/market_history.log 2>&1 $MARKER"

[[ -x "$RUNNER" ]] || { echo "[FAIL] runner is not executable: $RUNNER" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }
mkdir -p "$PROJECT_DIR/logs"
CURRENT="$(crontab -l 2>/dev/null || true)"
if grep -Fq "$MARKER" <<<"$CURRENT"; then
  echo "[OK] market history cron already installed"
else
  { printf '%s\n' "$CURRENT"; printf '%s\n' "$LINE"; } | crontab -
  echo "[OK] installed: $LINE"
fi
