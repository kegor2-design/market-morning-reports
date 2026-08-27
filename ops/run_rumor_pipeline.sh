#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT/.env}"
set -a
source "$ENV_FILE"
set +a
cd "$PROJECT"
mkdir -p logs
if [[ -x "${MMP_TELEGRAM_PYTHON:-$PROJECT/.venv-telegram/bin/python}" && -f "$PROJECT/data/private/telegram/session/mmp_telegram.session" ]]; then
  "$PROJECT/ops/run_telegram_rumor_collector.sh" "$PROJECT" "$ENV_FILE"
else
  echo "[WARN] Telegram runtime/session unavailable; processing existing article/YouTube inputs." >&2
fi
"${MMP_PYTHON:-python3}" -m market_morning_publisher.rumor_extraction_cli
"${MMP_PYTHON:-python3}" -m market_morning_publisher.event_intelligence_cli --no-network
if [[ "${MMP_CALENDAR_AUTO_PUBLISH:-1}" == "1" ]]; then
  "${MMP_PYTHON:-python3}" ops/publish_market_calendar_page.py
fi
if [[ "${MMP_BLOGGER_PUBLISH:-0}" == "1" ]]; then
  "${MMP_PYTHON:-python3}" ops/publish_rumor_watch_page.py
fi
