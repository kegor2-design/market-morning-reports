"""Evaluate a previously sealed, separate temporal market holdout."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path

from .data_recovery import verify_recovery
from .engine import write_state
from .isolated_codex import PRIVATE_ROOT
from .research_job import manifest_load, plan_for, verify_artifact
from .research_planner import SERIES


def evaluate(contract_path: Path, expected_sha256: str, training_report: Path,
             holdout_program: Path) -> dict:
    if (contract_path.is_symlink() or not contract_path.resolve().is_relative_to(PRIVATE_ROOT)
            or holdout_program.is_symlink() or
            not holdout_program.resolve().is_relative_to(PRIVATE_ROOT)):
        raise ValueError('Holdout outside private research state')
    raw_contract = contract_path.read_bytes()
    if hashlib.sha256(raw_contract).hexdigest() != expected_sha256:
        raise ValueError('Holdout contract was not sealed before evaluation')
    contract = json.loads(raw_contract)
    if (contract['model_tuning_allowed'] is not False or
            contract['official_market_claim'] is not False or
            contract['prediction_rule'] !=
            'UST_10Y minus UST_2Y > 0 predicts next-day SOFR increase' or
            contract['evaluation'] !=
            'all adjacent available weekdays; accuracy versus always no increase'):
        raise ValueError('Unreviewed holdout evaluation rule')
    if hashlib.sha256(training_report.read_bytes()).hexdigest() != contract['training_report_sha256']:
        raise ValueError('Prior training report changed after seal')
    training = json.loads(training_report.read_text())
    if (training['goal_id'] != contract['training_goal_id'] or
            max(training['analysis']['dates']) >= contract['holdout_start']):
        raise ValueError('Holdout overlaps prior research')
    state = json.loads((holdout_program / 'state.json').read_text())
    if state['status'] != 'RESEARCH_COMPLETED_EXPLORATORY' or \
            state['plan']['research_period']['start'] != contract['holdout_start'] or \
            state['plan']['research_period']['end'] != contract['holdout_end']:
        raise ValueError('Holdout research has no matching complete source tasks')
    from .research_planner import dates_for
    days = dates_for(state['plan'])
    values, source_hashes = {}, {}
    for series in SERIES:
        task_id = 'collect_' + series.lower()
        if state['records'][task_id]['status'] != 'VERIFIED':
            raise ValueError('Unverified holdout source task')
        manifest_path = holdout_program / 'manifests' / (task_id + '.json')
        job_dir = holdout_program / 'jobs' / task_id
        manifest, digest = manifest_load(manifest_path)
        verify_artifact(manifest, plan_for(manifest, digest), job_dir)
        recovered = verify_recovery(manifest['data_request'], job_dir / 'data_recovery')
        by_day = {row['observation_date']: Decimal(row['value'])
                  for row in recovered['source_records']
                  if row['source_id'] in {'US_TREASURY', 'NYFED_REFERENCE_RATES'}}
        if any(day not in by_day for day in days):
            raise ValueError('Incomplete holdout observation days')
        values[series] = by_day
        source_hashes[series] = recovered['content_sha256']
    actual_increases = 0
    correct = 0
    for today, tomorrow in zip(days, days[1:]):
        prediction = values['UST_10Y'][today] > values['UST_2Y'][today]
        actual = values['NYFED_SOFR'][tomorrow] > values['NYFED_SOFR'][today]
        correct += int(prediction == actual)
        actual_increases += int(actual)
    n = len(days) - 1
    baseline_correct = n - actual_increases
    accuracy = correct / n
    z = 1.96
    center = (accuracy + z*z/(2*n)) / (1 + z*z/n)
    radius = z*math.sqrt(accuracy*(1-accuracy)/n + z*z/(4*n*n)) / (1+z*z/n)
    result = {'schema_version': 1, 'status': 'EXPLORATORY_HOLDOUT_SUPPORTED'
              if correct > baseline_correct else 'EXPLORATORY_HOLDOUT_REJECTED',
              'contract_sha256': expected_sha256, 'training_goal_id': training['goal_id'],
              'holdout_goal_id': state['goal_id'], 'first_day': days[0], 'last_day': days[-1],
              'observation_days': len(days), 'pairs': n, 'correct': correct,
              'baseline_correct': baseline_correct, 'actual_increases': actual_increases,
              'accuracy': accuracy, 'baseline_accuracy': baseline_correct / n,
              'wilson_95_interval': [center-radius, center+radius],
              'source_sha256': source_hashes, 'pit_status': 'PIT_UNVERIFIED',
              'official_market_claim': False, 'independent_market_holdout': True,
              'next_action': 'ACQUIRE_HISTORICAL_FIRST_ACCESS_PIT_BEFORE_INVESTMENT_CLAIM'}
    write_state(contract_path.parent / 'holdout_result.json', result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--contract-sha256', required=True)
    parser.add_argument('--training-report', type=Path, required=True)
    parser.add_argument('--holdout-program', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.contract, args.contract_sha256,
                      args.training_report, args.holdout_program)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
