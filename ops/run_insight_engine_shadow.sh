#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ $# -gt 0 ]]; then shift; fi
cd "$PROJECT_DIR"
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE"; exit 2; }
set -a
source "$ENV_FILE"
set +a
PY="${MMP_PYTHON:-python3}"
exec "$PY" -m market_morning_publisher.insight_engine.cli --root "$PROJECT_DIR" "$@"
