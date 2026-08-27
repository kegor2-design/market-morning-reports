#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
TARGET_DATE="${3:-$(TZ=Asia/Seoul date +%F)}"
REQUEST_FILE="$PROJECT_DIR/data/state/youtube_insight/chart_requests/$TARGET_DATE.json"

[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }
[[ -f "$REQUEST_FILE" ]] || { echo "[INFO] no chart request file: $REQUEST_FILE"; exit 0; }

set -a
source "$ENV_FILE"
set +a

[[ "${MMP_YOUTUBE_CHART_ENABLED:-0}" == "1" ]] || { echo "[STOP] MMP_YOUTUBE_CHART_ENABLED must be 1" >&2; exit 2; }

cd "$PROJECT_DIR"
mapfile -t REQUESTS < <("${MMP_PYTHON:-python3}" - "$REQUEST_FILE" <<'PY'
import json, sys
rows=json.load(open(sys.argv[1], encoding='utf-8'))
seen=set()
for row in rows:
    if row.get('status') != 'REQUESTED' or not row.get('channel_id') or not row.get('video_url'):
        continue
    key=(str(row['channel_id']), str(row['video_url']))
    if key in seen:
        continue
    seen.add(key)
    print(key[0] + '\t' + key[1])
PY
)

if [[ ${#REQUESTS[@]} -eq 0 ]]; then
  echo "[INFO] no pending chart requests"
  exit 0
fi

for REQUEST in "${REQUESTS[@]}"; do
  CHANNEL="${REQUEST%%$'\t'*}"
  VIDEO_URL="${REQUEST#*$'\t'}"
  echo "===== chart request: $CHANNEL / $TARGET_DATE / $VIDEO_URL ====="
  ARGS=(--date "$TARGET_DATE" --channel "$CHANNEL" --video-url "$VIDEO_URL" --frames)
  [[ "${MMP_YOUTUBE_CHART_OCR:-1}" == "1" ]] && ARGS+=(--ocr)
  [[ "${MMP_YOUTUBE_CHART_OHLCV:-1}" == "1" ]] && ARGS+=(--ohlcv)
  "$PROJECT_DIR/ops/run_youtube_chart_pipeline.sh" "$PROJECT_DIR" "${ARGS[@]}"
done

# Validation remains conservative: human review is still required where configured.
"$PROJECT_DIR/ops/run_youtube_chart_validation.sh" "$PROJECT_DIR" --init-review-template

echo "[OK] chart requests processed and human review template initialized."
echo "[NEXT] Review data/state/youtube_chart/human_reviews.csv, then run:"
echo "       $PROJECT_DIR/ops/run_youtube_chart_validation.sh $PROJECT_DIR --fetch-reviewed-ohlcv"
echo "[NEXT] If MMP_CHART_INSIGHT_ENABLED=1, validate historical expert claims against real OHLCV:"
echo "       $PROJECT_DIR/ops/run_chart_insight_validation.sh $PROJECT_DIR $ENV_FILE --fetch-yahoo"
echo "[NEXT] After validation, re-run YouTube insight cards to refresh publish eligibility and nightly synthesis."
