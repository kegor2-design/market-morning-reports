#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
[[ $# -gt 0 ]] && shift
[[ $# -gt 0 ]] && shift
[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }
set -a
source "$ENV_FILE"
set +a
cd "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/logs"
"${MMP_PYTHON:-python3}" -m market_morning_publisher.cli "$@" 2>&1 | tee -a "$PROJECT_DIR/logs/pipeline.log"

# Refresh official cross-border flow sensors and build shadow reasoning packets.
# Insight failure is isolated from the already-completed publication pipeline.
INSIGHT_DATE="$(TZ=Asia/Seoul date +%F)"
if ! "$PROJECT_DIR/ops/run_insight_engine_daily.sh" "$PROJECT_DIR" "$ENV_FILE" "$INSIGHT_DATE" >> "$PROJECT_DIR/logs/insight_engine_daily.log" 2>&1; then
  echo "[WARN] insight engine daily shadow run failed; see logs/insight_engine_daily.log" >&2
fi
