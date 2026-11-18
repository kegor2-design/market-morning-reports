"""Predeclared exploratory US rate analysis over verified Research Job outputs."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .data_recovery import verify_recovery
from .isolated_codex import PRIVATE_ROOT
from .research_planner import SERIES


SIGNALS = {
    'positive_spread': 'Positive 10Y-2Y spread predicts next-day SOFR rise',
    'widening_spread': 'Widening 10Y-2Y spread predicts next-day SOFR rise',
}


def analyze(source_jobs: dict, dates: list[str], train_rows: int,
            signal: str = 'positive_spread') -> dict:
    if set(source_jobs) != set(SERIES) or not 5 <= train_rows < len(dates) - 2:
        raise ValueError('Invalid analysis source or chronological split')
    if signal not in SIGNALS:
        raise ValueError('Unreviewed rate prediction signal')
    values = {}
    hashes = {}
    fixture_only = False
    for series in SERIES:
        entry = source_jobs[series]
        manifest_path = Path(entry['manifest'])
        job_dir = Path(entry['job_dir'])
        if (manifest_path.is_symlink() or job_dir.is_symlink() or
                not manifest_path.resolve().is_relative_to(PRIVATE_ROOT) or
                not job_dir.resolve().is_relative_to(PRIVATE_ROOT)):
            raise ValueError('Analysis source outside private research root')
        from .research_job import manifest_load, plan_for, verify_artifact
        manifest, manifest_hash = manifest_load(manifest_path)
        if manifest['mode'] != 'data_recovery' or manifest['data_request']['series'] != series:
            raise ValueError('Analysis source manifest changed')
        job_state = json.loads((job_dir / 'job.json').read_text())
        if (job_state['status'] != 'RESEARCH_BLOCKED_WITH_EVIDENCE' or
                job_state['conclusion']['reason'] != 'DATA_RECOVERED_PIT_UNVERIFIED'):
            raise ValueError('Source job has no accepted exploratory data')
        verify_artifact(manifest, plan_for(manifest, manifest_hash), job_dir)
        source = verify_recovery(manifest['data_request'], job_dir / 'data_recovery')
        expected_source = ('NYFED_REFERENCE_RATES' if series == 'NYFED_SOFR'
                           else 'US_TREASURY')
        if manifest['data_request'].get('fixture_source_uri'):
            expected_source = 'LOCAL_HTTP_FIXTURE_' + expected_source
            fixture_only = True
        record_values = {row['observation_date']: Decimal(row['value'])
                         for row in source['source_records']
                         if row['source_id'] == expected_source}
        if any(day not in record_values for day in dates):
            raise ValueError('Source lacks a declared analysis observation')
        values[series] = [record_values[day] for day in dates]
        hashes[series] = source['content_sha256']
    spread = [a - b for a, b in zip(values['UST_10Y'], values['UST_2Y'])]
    sofr = values['NYFED_SOFR']
    predicted = ([value > 0 for value in spread[:-1]] if signal == 'positive_spread'
                 else [i > 0 and spread[i] > spread[i - 1]
                       for i in range(len(spread) - 1)])
    actual = [sofr[i + 1] > sofr[i] for i in range(len(sofr) - 1)]
    def metrics(start: int, end: int) -> dict:
        n = end - start
        correct = sum(predicted[i] == actual[i] for i in range(start, end))
        baseline = sum(not actual[i] for i in range(start, end))
        return {'pairs': n, 'accuracy': correct / n,
                'no_increase_baseline_accuracy': baseline / n,
                'actual_increase_count': sum(actual[start:end])}
    train = metrics(0, train_rows)
    validation = metrics(train_rows, len(actual))
    result = {'status': 'EXPLORATORY_ONLY', 'official_market_claim': False,
            'pit_status': 'PIT_UNVERIFIED', 'independent_holdout': 'NOT_AVAILABLE',
            'dates': dates, 'rows': len(dates), 'source_sha256': hashes,
            'spread_first': str(spread[0]), 'spread_last': str(spread[-1]),
            'sofr_first': str(sofr[0]), 'sofr_last': str(sofr[-1]),
            'hypothesis': SIGNALS[signal],
            'train': train, 'validation': validation,
            'hypothesis_result': 'SUPPORTED_EXPLORATORY' if validation['accuracy'] >
                validation['no_increase_baseline_accuracy'] else 'REJECTED_EXPLORATORY',
            'next_action': 'ACQUIRE_PIT_AND_SEALED_HOLDOUT_BEFORE_OFFICIAL_USE'}
    if fixture_only:
        result['fixture_only'] = True
        result['next_action'] = 'REPLACE_LOCAL_FIXTURE_WITH_APPROVED_OFFICIAL_EVIDENCE'
    if signal != 'positive_spread':
        result['signal'] = signal
    return result
