#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
[[ $# -gt 0 ]] && shift

[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
if [[ "${MMP_YOUTUBE_CHART_ENABLED:-0}" != "1" ]]; then
  echo "[STOP] set MMP_YOUTUBE_CHART_ENABLED=1 to run the shadow collector" >&2
  exit 2
fi

cd "$PROJECT_DIR"
COMMAND=("${MMP_PYTHON:-python3}" -m market_morning_publisher.youtube_chart.cli --root "$PROJECT_DIR")
[[ -n "${MMP_YT_DLP:-}" ]] && COMMAND+=(--yt-dlp "$MMP_YT_DLP")
[[ -n "${MMP_FFMPEG:-}" ]] && COMMAND+=(--ffmpeg "$MMP_FFMPEG")
[[ -n "${MMP_YOUTUBE_COOKIE_FILE:-}" ]] && COMMAND+=(--cookies "$MMP_YOUTUBE_COOKIE_FILE")

# Foreground execution is deliberate: the caller sees failures immediately.
exec "${COMMAND[@]}" "$@"

