#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
[[ $# -gt 0 ]] && shift
[[ $# -gt 0 ]] && shift
[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }
set -a; source "$ENV_FILE"; set +a
[[ "${MMP_CHART_INSIGHT_ENABLED:-0}" == "1" ]] || { echo "[STOP] MMP_CHART_INSIGHT_ENABLED must be 1" >&2; exit 2; }
cd "$PROJECT_DIR"
# Foreground and read-only: this only reports whether the historical-research queue has a verified live adapter.
exec "${MMP_PYTHON:-python3}" -m market_morning_publisher.chart_insight.research_cli --root "$PROJECT_DIR" "$@"
