#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
[[ $# -gt 0 ]] && shift

[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
if [[ "${MMP_YOUTUBE_CHART_ENABLED:-0}" != "1" ]]; then
  echo "[STOP] set MMP_YOUTUBE_CHART_ENABLED=1 to run shadow validation" >&2
  exit 2
fi

cd "$PROJECT_DIR"

# Foreground execution is deliberate.  This stage reads local JSON/OHLCV only
# and should expose validation or schema failures immediately.
exec "${MMP_PYTHON:-python3}" \
  -m market_morning_publisher.youtube_chart.validation_cli \
  --root "$PROJECT_DIR" \
  "$@"
