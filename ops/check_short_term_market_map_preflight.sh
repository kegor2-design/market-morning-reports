#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 - <<'PY'
import json
from pathlib import Path
for p in [Path('config/short_term_market_map.json'), Path('config/blog_publication_views.json')]:
    json.loads(p.read_text(encoding='utf-8'))
    print('JSON_OK', p)
PY
PYTHONPATH="$ROOT" python3 -m unittest \
  tests.verification.test_short_term_market_map \
  tests.verification.test_publication_views -v
