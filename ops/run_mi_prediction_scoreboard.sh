#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="${PROJECT:-/home/kegor2/MarketMorningPublisher}"
PYTHON="${PYTHON:-python3}"
STATE_ROOT="${STATE_ROOT:-$PROJECT/data/state/mi_prediction_scoreboard}"
mkdir -p "$STATE_ROOT"
cd "$PROJECT"
exec "$PYTHON" -m market_morning_publisher.mi_prediction_scoreboard_cli "$@"
