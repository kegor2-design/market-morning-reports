#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="${PROJECT:-/home/kegor2/MarketMorningPublisher}"
cd "$PROJECT"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -m py_compile \
  market_morning_publisher/mi_prediction_scoreboard.py \
  market_morning_publisher/mi_prediction_scoreboard_cli.py \
  market_morning_publisher/mi_prediction_bridge.py
"$PYTHON" - <<'PY'
import json
from pathlib import Path
p=Path('config/mi_prediction_scoreboard.json')
o=json.loads(p.read_text(encoding='utf-8'))
assert o['contract']=='MMP_MI_PREDICTION_SCOREBOARD_V1'
assert o['evaluation']['point_in_time_only'] is True
assert o['evaluation']['score_only_after_horizon'] is True
print('MI_PREDICTION_SCOREBOARD_PREFLIGHT=PASS')
PY
