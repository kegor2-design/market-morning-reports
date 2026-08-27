#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
cd "$PROJECT_DIR"

echo "===== MarketMorningPublisher integrated preflight ====="
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE"; exit 2; }
for required in \
  config/us_state_metrics.json \
  config/us_issue_playbooks.json \
  config/us_event_calendar.json \
  config/insight_metric_registry.json \
  config/insight_reasoning_playbooks.json \
  config/insight_background_knowledge.json \
  config/historical_cases.json \
  config/source_lenses.json \
  config/insight_hypothesis_seeds.json \
  config/expert_method_evidence.json \
  config/youtube_insight_channels.json \
  config/youtube_insight_analysis_schema.json \
  config/youtube_chart_channels.json \
  config/nightly_youtube_intelligence.json \
  config/chart_insight_policy.json \
  config/chart_insight_primitives.json \
  config/chart_insight_expert_lenses.json \
  config/publishing_ui.json; do
  [[ -f "$required" ]] || { echo "[FAIL] missing $required"; exit 2; }
done

set -a
source "$ENV_FILE"
set +a
PY="${MMP_PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]] || { echo "[FAIL] python not found: $PY"; exit 2; }

echo "[1/10] compile"
"$PY" -m compileall -q market_morning_publisher scripts ops

echo "[2/10] existing + new tests"
"$PY" -m unittest discover -s tests -v

echo "[3/10] config parse"
"$PY" - <<'PY'
import json
from pathlib import Path
for p in sorted(Path('config').glob('*.json')):
    json.loads(p.read_text(encoding='utf-8'))
    print('[OK]', p)
PY

echo "[4/10] shell syntax"
for script in ops/*.sh; do
  bash -n "$script"
  echo "[OK] $script"
done

echo "[5/10] YouTube insight runtime contract"
if [[ "${MMP_YOUTUBE_INSIGHT_ENABLED:-0}" == "1" ]]; then
  YTDLP="${MMP_YT_DLP:-yt-dlp}"
  CODEX="${MMP_CODEX_BIN:-codex}"
  command -v "$YTDLP" >/dev/null 2>&1 || [[ -x "$YTDLP" ]] || { echo "[FAIL] yt-dlp not found: $YTDLP"; exit 2; }
  command -v "$CODEX" >/dev/null 2>&1 || [[ -x "$CODEX" ]] || { echo "[FAIL] codex not found: $CODEX"; exit 2; }
  if [[ "${MMP_YOUTUBE_INSIGHT_PUBLISH:-0}" == "1" ]]; then
    for key in BLOGGER_BLOG_ID BLOGGER_CLIENT_ID BLOGGER_CLIENT_SECRET BLOGGER_REFRESH_TOKEN; do
      [[ -n "${!key:-}" ]] || { echo "[FAIL] $key is required when MMP_YOUTUBE_INSIGHT_PUBLISH=1"; exit 2; }
    done
  fi
  if [[ "${MMP_YOUTUBE_ASR_FALLBACK:-0}" == "1" ]]; then
    "$PY" - <<'PYASR'
import importlib.util
if importlib.util.find_spec('faster_whisper') is None:
    raise SystemExit('[FAIL] MMP_YOUTUBE_ASR_FALLBACK=1 but faster_whisper is not installed')
print('[OK] faster_whisper available for explicit ASR fallback')
PYASR
  fi
  echo "[OK] YouTube insight enabled; binaries/required publish env are present"
else
  echo "[OK] YouTube insight is disabled by default; code/config contract only"
fi
if [[ "${MMP_YOUTUBE_CHART_ENABLED:-0}" == "1" ]]; then
  FFMPEG="${MMP_FFMPEG:-ffmpeg}"
  command -v "$FFMPEG" >/dev/null 2>&1 || [[ -x "$FFMPEG" ]] || { echo "[FAIL] ffmpeg not found: $FFMPEG"; exit 2; }
  echo "[OK] YouTube chart runtime enabled; ffmpeg present"
fi

echo "[6/10] chart insight + nightly deterministic contracts"
"$PY" - <<'PYCI'
import json
from pathlib import Path
from market_morning_publisher.chart_insight.primitives import map_expert_text
from market_morning_publisher.nightly_youtube.synthesis import build_nightly_synthesis
root=Path('.')
registry=json.loads((root/'config/chart_insight_primitives.json').read_text(encoding='utf-8'))
assert map_expert_text('전고점 돌파', registry)
result=build_nightly_synthesis('2099-01-01',[
 {'claim_id':'a','channel_id':'x','importance':'HIGH','stance':'BULLISH','issue_tags':['TEST']},
 {'claim_id':'b','channel_id':'y','importance':'HIGH','stance':'BEARISH','issue_tags':['TEST']},
],[{'id':'x'},{'id':'y'}])
assert result['disagreement_issue_count'] == 1
print('[OK] chart insight and nightly synthesis contracts')
PYCI

echo "[6A/10] responsive publishing deterministic contract"
"$PROJECT_DIR/ops/check_responsive_publish.sh" "$PROJECT_DIR"

echo "[7/10] cron inventory (read-only)"
crontab -l 2>/dev/null || true

echo "[8/10] MyDream2000 closing DB schema contract (read-only)"
"$PROJECT_DIR/ops/check_closing_db_schema.sh" /home/kegor2/mydream2000.env --required

echo "[9/10] shadow state collector connectivity"
if "$PY" -m market_morning_publisher.us_state.cli --root "$PROJECT_DIR" >/tmp/mmp_us_state_preflight.json; then
  cat /tmp/mmp_us_state_preflight.json
else
  echo "[FAIL] US State collector failed; existing production cron must not be changed"
  exit 3
fi

echo "[10/10] insight engine shadow contract"
if "$PY" -m market_morning_publisher.insight_engine.cli --root "$PROJECT_DIR" >/tmp/mmp_insight_engine_preflight.json; then
  cat /tmp/mmp_insight_engine_preflight.json
else
  echo "[FAIL] insight engine shadow contract failed; existing production cron must not be changed"
  exit 4
fi

echo "[PASS] preflight complete. This script does not install/modify cron or publish YouTube cards."
