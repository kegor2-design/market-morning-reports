#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/home/kegor2/MarketMorningPublisher"
SUMMARY="$ROOT/youtube_sources/plainbagel/collection_summary.json"

if [[ -f "$SUMMARY" ]] && grep -q '"pending": 0' "$SUMMARY"; then
  exit 0
fi

exec "$ROOT/tools/youtube_transcript_collector/run_collect.sh" \
  --channel-url "https://www.youtube.com/@ThePlainBagel/videos" \
  --source-id plainbagel \
  --output-root "$ROOT/youtube_sources" \
  --sub-langs en-orig,en \
  --yt-dlp "$ROOT/tools/youtube_transcript_collector/.venv/bin/yt-dlp" \
  --cookies "$ROOT/cookies.txt" \
  --sleep-seconds 1.5 \
  --min-free-gb 5
