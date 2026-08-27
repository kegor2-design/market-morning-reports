#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"

[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }

set -a
source "$ENV_FILE"
set +a

cd "$PROJECT_DIR"
mkdir -p logs

if [[ -z "${OPENDART_API_KEY:-${DART_API_KEY:-}}" ]]; then
  echo "[WARN] OPENDART_API_KEY/DART_API_KEY is not set; calendar refresh will run but DART disclosure collection will be incomplete." >&2
fi

"${MMP_PYTHON:-python3}" -m market_morning_publisher.event_intelligence_cli 2>&1 \
  | tee -a "$PROJECT_DIR/logs/event_intelligence.log"

if [[ "${MMP_CALENDAR_AUTO_PUBLISH:-1}" == "1" ]]; then
  "${MMP_PYTHON:-python3}" ops/publish_market_calendar_page.py 2>&1 \
    | tee -a "$PROJECT_DIR/logs/event_intelligence.log"
fi
