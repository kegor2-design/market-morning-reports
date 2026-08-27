#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT/.env}"
PYTHON_BIN="${MMP_TELEGRAM_PYTHON:-$PROJECT/.venv-telegram/bin/python}"

cd "$PROJECT"
[[ -f "$ENV_FILE" ]] || { echo "[BLOCK] env missing: $ENV_FILE"; exit 2; }
[[ -x "$PYTHON_BIN" ]] || { echo "[BLOCK] telegram python missing: $PYTHON_BIN"; exit 3; }

set -a
source "$ENV_FILE"
set +a

exec "$PYTHON_BIN" -m market_morning_publisher.telegram_rumor_collector \
  --config config/telegram_rumor_sources.json \
  --output data/private/telegram/normalized/messages.jsonl \
  --session data/private/telegram/session/mmp_telegram \
  --since-hours "${MMP_TELEGRAM_SINCE_HOURS:-48}"
