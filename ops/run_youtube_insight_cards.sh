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

if [[ "${MMP_YOUTUBE_INSIGHT_ENABLED:-0}" != "1" ]]; then
  echo "[STOP] set MMP_YOUTUBE_INSIGHT_ENABLED=1 to run YouTube market-view cards" >&2
  exit 2
fi

cd "$PROJECT_DIR"
mkdir -p logs

ARGS=(--root "$PROJECT_DIR")
[[ "${MMP_YOUTUBE_INSIGHT_PUBLISH:-0}" == "1" ]] && ARGS+=(--publish)
[[ -n "${MMP_YT_DLP:-}" ]] && ARGS+=(--yt-dlp "$MMP_YT_DLP")
[[ -n "${MMP_YOUTUBE_COOKIE_FILE:-}" ]] && ARGS+=(--cookies "$MMP_YOUTUBE_COOKIE_FILE")

# Foreground by default so collection/Codex/publish failures are immediately visible.
exec "${MMP_PYTHON:-python3}" -m market_morning_publisher.youtube_insight.cli "${ARGS[@]}" "$@" \
  2>&1 | tee -a "$PROJECT_DIR/logs/youtube_insight_cards.log"
