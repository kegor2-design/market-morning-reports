#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 - <<'PY'
import json
from pathlib import Path
from market_morning_publisher.official_calendar_coverage import assess_coverage
root=Path('.')
seed=json.loads((root/'config/official_calendar_seed_20260827.json').read_text())['events']
specs=json.loads((root/'config/official_forward_calendar_sources.json').read_text())['sources']
out=assess_coverage(seed,specs,now='2026-08-27T00:00:00Z')
print(json.dumps(out,ensure_ascii=False,indent=2))
PY
