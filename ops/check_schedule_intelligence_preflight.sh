#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
import json
from pathlib import Path
for p in [
    Path('config/schedule_intelligence.json'),
    Path('config/calendar_decision_card.json'),
    Path('config/calendar_decision_card_schema.json'),
    Path('config/source_registry.json'),
]:
    json.loads(p.read_text(encoding='utf-8'))
print('schedule_intelligence_config=PASS')
PY
python3 -m unittest discover -s tests/verification -p 'test_schedule_discovery.py' -v
python3 -m unittest discover -s tests/verification -p 'test_calendar_decision_card.py' -v
