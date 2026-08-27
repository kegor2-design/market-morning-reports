#!/usr/bin/env bash
set -Eeuo pipefail
SOURCE_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
TARGET_DIR="${2:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${3:-$TARGET_DIR/.env}"
MYDREAM_ENV="${4:-/home/kegor2/mydream2000.env}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${TARGET_DIR}_backup_${STAMP}"

[[ -d "$SOURCE_DIR/market_morning_publisher" ]] || { echo "[FAIL] bad source: $SOURCE_DIR"; exit 2; }
[[ -d "$TARGET_DIR" ]] || { echo "[FAIL] target missing: $TARGET_DIR"; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] target env missing: $ENV_FILE"; exit 2; }
command -v rsync >/dev/null 2>&1 || { echo "[FAIL] rsync required"; exit 2; }

chmod +x "$SOURCE_DIR"/ops/*.sh 2>/dev/null || true

PYTHON="python3"
set -a
source "$ENV_FILE"
set +a
PYTHON="${MMP_PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || [[ -x "$PYTHON" ]] || { echo "[FAIL] python not found: $PYTHON"; exit 2; }

restore_backup() {
  echo "[ROLLBACK] restoring managed code from $BACKUP_DIR"
  for d in market_morning_publisher config ops scripts tests blogger_theme docs; do
    [[ -d "$BACKUP_DIR/$d" ]] && rsync -a --delete "$BACKUP_DIR/$d/" "$TARGET_DIR/$d/"
  done
  [[ -d "$BACKUP_DIR/public/market-history" ]] && rsync -a --delete "$BACKUP_DIR/public/market-history/" "$TARGET_DIR/public/market-history/"
}

echo "===== 1. SOURCE COMPILE / FULL TEST ====="
(cd "$SOURCE_DIR" && "$PYTHON" -m compileall -q market_morning_publisher scripts ops && "$PYTHON" -m unittest discover -s tests -v)

echo "===== 1A. SOURCE CONFIG / OPTIONAL YOUTUBE RUNTIME CONTRACT ====="
(cd "$SOURCE_DIR" && "$PYTHON" - <<'PYCFG'
import json
from pathlib import Path
for path in sorted(Path('config').glob('*.json')):
    json.loads(path.read_text(encoding='utf-8'))
    print('[OK]', path)
PYCFG
)
if [[ "${MMP_YOUTUBE_INSIGHT_ENABLED:-0}" == "1" ]]; then
  YTDLP="${MMP_YT_DLP:-yt-dlp}"
  CODEX="${MMP_CODEX_BIN:-codex}"
  command -v "$YTDLP" >/dev/null 2>&1 || [[ -x "$YTDLP" ]] || { echo "[FAIL] yt-dlp not found before overwrite: $YTDLP"; exit 2; }
  command -v "$CODEX" >/dev/null 2>&1 || [[ -x "$CODEX" ]] || { echo "[FAIL] codex not found before overwrite: $CODEX"; exit 2; }
  if [[ "${MMP_YOUTUBE_INSIGHT_PUBLISH:-0}" == "1" ]]; then
    for key in BLOGGER_BLOG_ID BLOGGER_CLIENT_ID BLOGGER_CLIENT_SECRET BLOGGER_REFRESH_TOKEN; do
      [[ -n "${!key:-}" ]] || { echo "[FAIL] $key required for YouTube insight publish"; exit 2; }
    done
  fi
  if [[ "${MMP_YOUTUBE_ASR_FALLBACK:-0}" == "1" ]]; then
    "$PYTHON" - <<'PYASR'
import importlib.util
if importlib.util.find_spec('faster_whisper') is None:
    raise SystemExit('[FAIL] MMP_YOUTUBE_ASR_FALLBACK=1 but faster_whisper is not installed')
print('[OK] faster_whisper available')
PYASR
  fi
fi

echo "===== 1B. SOURCE NIGHTLY / CHART INSIGHT CONTRACT ====="
(cd "$SOURCE_DIR" && "$PYTHON" - <<'PYCI'
import json
from pathlib import Path
from market_morning_publisher.chart_insight.primitives import map_expert_text
from market_morning_publisher.nightly_youtube.synthesis import build_nightly_synthesis
root=Path('.')
registry=json.loads((root/'config/chart_insight_primitives.json').read_text(encoding='utf-8'))
assert map_expert_text('전고점 돌파와 거래량이 증가', registry)
result=build_nightly_synthesis('2099-01-01',[
 {'claim_id':'a','channel_id':'x','importance':'HIGH','stance':'BULLISH','issue_tags':['TEST']},
 {'claim_id':'b','channel_id':'y','importance':'HIGH','stance':'BEARISH','issue_tags':['TEST']},
],[{'id':'x'},{'id':'y'}])
assert result['disagreement_issue_count'] == 1
print('[OK] source nightly/chart insight contracts')
PYCI
)

echo "===== 1C. SOURCE RESPONSIVE PUBLISHING CONTRACT ====="
"$SOURCE_DIR/ops/check_responsive_publish.sh" "$SOURCE_DIR"

echo "===== 1D. SOURCE RESEARCH PORTAL THEME CONTRACT ====="
"$SOURCE_DIR/ops/check_research_portal_theme.sh" "$SOURCE_DIR"

echo "===== 2. TARGET DB CONTRACT (STRICT / READ-ONLY) ====="
"$SOURCE_DIR/ops/check_closing_db_schema.sh" "$MYDREAM_ENV" --required

echo "===== 3. US STATE LIVE SOURCE CONNECTIVITY BEFORE OVERWRITE ====="
if ! "$SOURCE_DIR/ops/run_us_state_shadow.sh" "$SOURCE_DIR" "$ENV_FILE" >/tmp/mmp_us_state_source_preflight.json; then
  echo "[FAIL] US State source connectivity failed. Live code was NOT touched."
  exit 3
fi
cat /tmp/mmp_us_state_source_preflight.json

echo "===== 4. BACKUP MANAGED CODE ====="
mkdir -p "$BACKUP_DIR"
for d in market_morning_publisher config ops scripts tests blogger_theme docs public/market-history; do
  if [[ -e "$TARGET_DIR/$d" ]]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$d")"
    cp -a "$TARGET_DIR/$d" "$BACKUP_DIR/$d"
  fi
done
printf '%s\n' "$BACKUP_DIR" > "$TARGET_DIR/.last_code_backup"
echo "BACKUP=$BACKUP_DIR"

echo "===== 5. OVERWRITE MANAGED CODE ====="
for d in market_morning_publisher config ops scripts tests blogger_theme docs; do
  [[ -d "$SOURCE_DIR/$d" ]] || continue
  mkdir -p "$TARGET_DIR/$d"
  rsync -a --delete "$SOURCE_DIR/$d/" "$TARGET_DIR/$d/"
done
# Preserve the verified operator-only Blogger backfill utility that exists only
# in CURRENT. It is not part of the release archive, but rsync --delete must not
# remove an already deployed recovery/maintenance capability.
if [[ -f "$BACKUP_DIR/ops/backfill_responsive_blogger.py" && ! -f "$SOURCE_DIR/ops/backfill_responsive_blogger.py" ]]; then
  cp -a "$BACKUP_DIR/ops/backfill_responsive_blogger.py" "$TARGET_DIR/ops/backfill_responsive_blogger.py"
fi
if [[ -d "$SOURCE_DIR/public/market-history" ]]; then
  mkdir -p "$TARGET_DIR/public/market-history"
  rsync -a --delete "$SOURCE_DIR/public/market-history/" "$TARGET_DIR/public/market-history/"
fi
chmod +x "$TARGET_DIR"/ops/*.sh 2>/dev/null || true

echo "===== 6. TARGET REGRESSION TEST ====="
if ! (cd "$TARGET_DIR" && "$PYTHON" -m compileall -q market_morning_publisher scripts ops && "$PYTHON" -m unittest discover -s tests -v); then
  echo "[FAIL] regression test failed after overwrite."
  restore_backup
  exit 4
fi

echo "===== 7. TARGET US STATE SHADOW TEST ====="
if ! "$TARGET_DIR/ops/run_us_state_shadow.sh" "$TARGET_DIR" "$ENV_FILE"; then
  echo "[FAIL] target US State shadow run failed after overwrite."
  restore_backup
  exit 5
fi

echo "===== 8. TARGET INSIGHT ENGINE SHADOW TEST ====="
if ! (cd "$TARGET_DIR" && "$PYTHON" -m market_morning_publisher.insight_engine.cli --root "$TARGET_DIR" >/tmp/mmp_insight_engine_target.json); then
  echo "[FAIL] target insight engine shadow run failed after overwrite."
  restore_backup
  exit 6
fi
cat /tmp/mmp_insight_engine_target.json

echo "===== 9. TARGET NIGHTLY / CHART INSIGHT CONTRACT ====="
if ! (cd "$TARGET_DIR" && "$PYTHON" - <<'PYCI'
import json
from pathlib import Path
from market_morning_publisher.chart_insight.primitives import map_expert_text
from market_morning_publisher.nightly_youtube.synthesis import build_nightly_synthesis
registry=json.loads(Path('config/chart_insight_primitives.json').read_text(encoding='utf-8'))
assert map_expert_text('시가 회복 후 돌파', registry)
r=build_nightly_synthesis('2099-01-01',[
 {'claim_id':'a','channel_id':'x','importance':'HIGH','stance':'BULLISH','issue_tags':['TEST']},
 {'claim_id':'b','channel_id':'y','importance':'HIGH','stance':'BEARISH','issue_tags':['TEST']},
],[{'id':'x'},{'id':'y'}])
assert r['disagreement_issue_count'] == 1
print('[OK] target nightly/chart insight contracts')
PYCI
); then
  echo "[FAIL] target nightly/chart insight contract failed after overwrite."
  restore_backup
  exit 7
fi

echo "===== 10. TARGET RESPONSIVE PUBLISHING CONTRACT ====="
if ! "$TARGET_DIR/ops/check_responsive_publish.sh" "$TARGET_DIR"; then
  echo "[FAIL] target responsive publishing contract failed after overwrite."
  restore_backup
  exit 8
fi

echo "===== 11. TARGET RESEARCH PORTAL THEME CONTRACT ====="
if ! "$TARGET_DIR/ops/check_research_portal_theme.sh" "$TARGET_DIR"; then
  echo "[FAIL] target Research Portal theme contract failed after overwrite."
  restore_backup
  exit 9
fi

echo "[PASS] deployment complete. Existing .env/data/logs preserved. Cron was NOT modified."
echo "[INFO] Existing cron remains unchanged until separately inspected and approved."
echo "[INFO] IMPORTANT: server deployment does NOT change the live Blogger Theme."
echo "[INFO] Apply blogger_theme/market_morning_research_portal.xml in Blogger Theme only after backing up the current theme."
