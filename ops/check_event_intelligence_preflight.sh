#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${1:-/home/kegor2/MarketMorningPublisher}"
ENV_FILE="${2:-$PROJECT_DIR/.env}"
PYTHON_BIN="${MMP_PYTHON:-python3}"

[[ -d "$PROJECT_DIR" ]] || { echo "[FAIL] missing project: $PROJECT_DIR" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "[FAIL] missing env: $ENV_FILE" >&2; exit 2; }

set -a
source "$ENV_FILE"
set +a
cd "$PROJECT_DIR"

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
cfg = Path('config/event_intelligence.json')
obj = json.loads(cfg.read_text(encoding='utf-8'))
assert obj.get('contract') == 'MMP_EVENT_INTELLIGENCE_V1'
assert obj.get('seed_events')
print('[OK] event_intelligence config parse')
PY

"$PYTHON_BIN" -m py_compile \
  market_morning_publisher/event_intelligence.py \
  market_morning_publisher/disclosure_intelligence.py \
  market_morning_publisher/event_intelligence_cli.py

echo "[OK] python compile"

"$PYTHON_BIN" -m market_morning_publisher.event_intelligence_cli --no-network --calendar-only >/tmp/mmp_event_preflight.json
cat /tmp/mmp_event_preflight.json
rm -f /tmp/mmp_event_preflight.json

if [[ -n "${OPENDART_API_KEY:-${DART_API_KEY:-}}" ]]; then
  echo "[OK] OpenDART key present"
else
  echo "[WARN] OpenDART key missing: production disclosure intelligence will be incomplete"
fi

echo "[INFO] Event Intelligence 1.6.5 does not require a new PostgreSQL table or schema migration."
echo "[INFO] MyDream2000 DB remains optional/read-only for later reaction validation; this collector uses OpenDART as the primary disclosure source."
