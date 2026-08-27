#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="${1:-/home/kegor2/MarketMorningPublisher}"
cd "$PROJECT"

python3 - <<'PY'
from pathlib import Path
import json
for name, contract in [('config/rumor_intelligence.json','MMP_RUMOR_INTELLIGENCE_V1'), ('config/telegram_rumor_sources.json','MMP_TELEGRAM_RUMOR_SOURCE_V1'), ('config/rumor_event_extraction.json','MMP_RUMOR_EVENT_EXTRACTION_V1'), ('config/source_registry.json','MMP_SOURCE_REGISTRY_V1')]:
    obj = json.loads(Path(name).read_text(encoding='utf-8'))
    assert obj.get('contract') == contract, name
rumor = json.loads(Path('config/rumor_intelligence.json').read_text(encoding='utf-8'))
assert rumor.get('guardrails', {}).get('rumor_never_becomes_official_by_count_only') is True
registry = json.loads(Path('config/source_registry.json').read_text(encoding='utf-8'))
assert len(registry.get('sources', [])) >= 29
assert {'official_us_treasury','official_kansas_city_fed','official_us_congress','official_fec'} <= {x.get('id') for x in registry['sources']}
assert sum(1 for x in registry['sources'] if x.get('platform') == 'TELEGRAM') == 18
print('[PASS] rumor/telegram/extraction/source-registry config contracts')
PY

python3 -m py_compile \
  market_morning_publisher/event_lifecycle.py \
  market_morning_publisher/rumor_intelligence.py \
  market_morning_publisher/rumor_intelligence_cli.py \
  market_morning_publisher/telegram_rumor_collector.py \
  market_morning_publisher/source_registry.py \
  market_morning_publisher/source_performance.py

echo '[PASS] rumor intelligence compile'

python3 -m unittest -v \
  tests.test_event_lifecycle \
  tests.test_rumor_intelligence \
  tests.test_telegram_rumor_collector \
  tests.test_source_registry \
  tests.test_source_performance

echo '[PASS] rumor intelligence focused tests'
