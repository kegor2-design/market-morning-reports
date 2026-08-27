#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
RUNNER="$PROJECT_DIR/ops/run_pipeline.sh"
EVENT_RUNNER="$PROJECT_DIR/ops/run_event_intelligence.sh"
CLOSING_RUNNER="$PROJECT_DIR/ops/run_closing_pipeline.sh"
RUMOR_RUNNER="$PROJECT_DIR/ops/run_rumor_pipeline.sh"
YOUTUBE_RUNNER="$PROJECT_DIR/ops/run_youtube_insight_cards.sh"
[[ -x "$RUNNER" ]] || { echo "[FAIL] runner is not executable: $RUNNER" >&2; exit 2; }
[[ -x "$EVENT_RUNNER" ]] || { echo "[FAIL] event runner is not executable: $EVENT_RUNNER" >&2; exit 2; }
[[ -x "$CLOSING_RUNNER" ]] || { echo "[FAIL] closing runner is not executable: $CLOSING_RUNNER" >&2; exit 2; }
[[ -x "$RUMOR_RUNNER" ]] || { echo "[FAIL] rumor runner is not executable: $RUMOR_RUNNER" >&2; exit 2; }
[[ -x "$YOUTUBE_RUNNER" ]] || { echo "[FAIL] YouTube insight runner is not executable: $YOUTUBE_RUNNER" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }
mkdir -p "$PROJECT_DIR/logs"

MAIN_MARKER="# MARKET_MORNING_PUBLISHER"
EVENT_MARKER="# MMP_EVENT_INTELLIGENCE"
CLOSING_MARKER="# MMP_CLOSING_PUBLISHER"
RUMOR_MARKER="# MMP_RUMOR_PIPELINE"
YOUTUBE_MARKER="# MMP_YOUTUBE_INSIGHT"
MAIN_LINE="10 8 * * * /usr/bin/flock -n /tmp/market_morning_publisher.lock $RUNNER $PROJECT_DIR $ENV_FILE $MAIN_MARKER"
CLOSING_LINE="20 16 * * 1-5 /usr/bin/flock -n /tmp/mmp_closing_publisher.lock $CLOSING_RUNNER $PROJECT_DIR $ENV_FILE $CLOSING_MARKER"
RUMOR_LINES=(
  "15 7 * * * /usr/bin/flock -n /tmp/mmp_rumor_pipeline.lock $RUMOR_RUNNER $PROJECT_DIR $ENV_FILE $RUMOR_MARKER"
  "10 12 * * 1-5 /usr/bin/flock -n /tmp/mmp_rumor_pipeline.lock $RUMOR_RUNNER $PROJECT_DIR $ENV_FILE $RUMOR_MARKER"
  "10 18 * * 1-5 /usr/bin/flock -n /tmp/mmp_rumor_pipeline.lock $RUMOR_RUNNER $PROJECT_DIR $ENV_FILE $RUMOR_MARKER"
)
YOUTUBE_LINE="30 1 * * * MMP_YOUTUBE_INSIGHT_ENABLED=1 MMP_YOUTUBE_INSIGHT_PUBLISH=0 MMP_YT_DLP=$PROJECT_DIR/tools/youtube_transcript_collector/.venv/bin/yt-dlp MMP_YOUTUBE_COOKIE_FILE=$PROJECT_DIR/cookies.txt /usr/bin/flock -n /tmp/mmp_youtube_insight.lock $YOUTUBE_RUNNER $PROJECT_DIR $ENV_FILE $YOUTUBE_MARKER"
# Full official-calendar/DART refresh several times a day. The 07:50 run supplies the 08:10 Morning pipeline,
# while afternoon/evening runs capture newly announced schedules and disclosures for the next session.
EVENT_LINES=(
  "20 0 * * * /usr/bin/flock -n /tmp/mmp_event_intelligence.lock $EVENT_RUNNER $PROJECT_DIR $ENV_FILE $EVENT_MARKER"
  "30 6 * * * /usr/bin/flock -n /tmp/mmp_event_intelligence.lock $EVENT_RUNNER $PROJECT_DIR $ENV_FILE $EVENT_MARKER"
  "50 7 * * * /usr/bin/flock -n /tmp/mmp_event_intelligence.lock $EVENT_RUNNER $PROJECT_DIR $ENV_FILE $EVENT_MARKER"
  "40 15 * * 1-5 /usr/bin/flock -n /tmp/mmp_event_intelligence.lock $EVENT_RUNNER $PROJECT_DIR $ENV_FILE $EVENT_MARKER"
  "30 18 * * 1-5 /usr/bin/flock -n /tmp/mmp_event_intelligence.lock $EVENT_RUNNER $PROJECT_DIR $ENV_FILE $EVENT_MARKER"
  "30 21 * * * /usr/bin/flock -n /tmp/mmp_event_intelligence.lock $EVENT_RUNNER $PROJECT_DIR $ENV_FILE $EVENT_MARKER"
)
CURRENT="$(crontab -l 2>/dev/null || true)"
CLEANED="$(printf '%s\n' "$CURRENT" | grep -Fv "$MAIN_MARKER" | grep -Fv "$EVENT_MARKER" | grep -Fv "$CLOSING_MARKER" | grep -Fv "$RUMOR_MARKER" | grep -Fv "$YOUTUBE_MARKER" || true)"
{
  printf '%s\n' "$CLEANED"
  printf '%s\n' "$MAIN_LINE"
  printf '%s\n' "$CLOSING_LINE"
  printf '%s\n' "${RUMOR_LINES[@]}"
  printf '%s\n' "$YOUTUBE_LINE"
  printf '%s\n' "${EVENT_LINES[@]}"
} | awk 'NF' | crontab -

echo "[OK] installed/updated Morning pipeline: $MAIN_LINE"
echo "[OK] installed/updated Closing pipeline: $CLOSING_LINE"
printf '[OK] installed/updated Rumor pipeline: %s\n' "${RUMOR_LINES[@]}"
echo "[OK] installed/updated YouTube insight: $YOUTUBE_LINE"
printf '[OK] installed/updated Event Intelligence: %s\n' "${EVENT_LINES[@]}"
