"""Conservative, metadata-only Regime190 eligibility manifest."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from universal_agent.engine import write_state

from .exploratory_backtest import HERE, pit_eligibility


def _csv(name: str) -> dict[int, dict]:
    with (HERE / name).open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    result = {int(row['indicator_id']): row for row in rows}
    if len(rows) != 190 or set(result) != set(range(1, 191)):
        raise ValueError('Incomplete indicator inventory: ' + name)
    return result


def build_manifest() -> dict:
    registry = _csv('indicator_spec.csv')
    coverage = _csv('data_coverage.csv')
    audit = _csv('pit_readiness_matrix_20261031.csv')
    inventory = _csv('inventory_190.csv')
    gate = pit_eligibility()
    records = []
    for key in range(1, 191):
        spec, data, pit, source = (mapping[key] for mapping in
                                   (registry, coverage, audit, inventory))
        observed = int(data['actual_indicator_series_rows'] or 0)
        components = int(data['recorded_component_or_summary_rows'] or 0)
        eligible = key in gate['eligible_indicator_ids']
        if eligible:
            state = 'BACKTEST_ELIGIBLE'
        elif pit['pit_classification'] == 'PIT_VERIFIED':
            state = 'PIT_VALID'
        elif observed or components:
            state = 'DATA_AVAILABLE'
        else:
            state = 'DATA_UNAVAILABLE'
        records.append({'indicator_id': key, 'name': spec['name'],
            'current_state': state, 'source': data['source_kind'],
            'first_date': data['first_date'], 'last_date': data['last_date'],
            'frequency': data['frequency'], 'market': data['target_market'],
            'actual_indicator_series_rows': observed, 'component_or_summary_rows': components,
            'missing_ratio_reported_pct': source['missing_pct'],
            'calculation_status': pit['calculation_status'],
            'input_dependencies': spec['source_candidate'],
            'publication_timestamp_status': pit['publication_timestamp'],
            'revision_policy_status': pit['revision_history'],
            'pit_status': pit['pit_classification'],
            'backtest_eligible': eligible,
            'blocking_reason': '' if eligible else pit['blocking_reason'],
            'lookahead_risk': spec['pit_caution']})
    return {'schema_version': 1, 'research_objective_id': 'regime190_first_cycle',
            'classification_policy': 'No automatic promotion from data availability to PIT validity',
            'indicator_count': 190, 'pit_eligible_count': len(gate['eligible_indicator_ids']),
            'source_sha256': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                              for name in ('indicator_spec.csv', 'data_coverage.csv',
                                           'pit_readiness_matrix_20261031.csv', 'inventory_190.csv')},
            'records': records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_state(args.output, value)
    print(json.dumps({'indicator_count': value['indicator_count'],
                      'pit_eligible_count': value['pit_eligible_count'],
                      'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
