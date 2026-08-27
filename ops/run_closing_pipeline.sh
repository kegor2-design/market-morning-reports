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
"${MMP_PYTHON:-python3}" -m market_morning_publisher.closing_cli "$@" 2>&1 | tee -a "$PROJECT_DIR/logs/closing_pipeline.log"
