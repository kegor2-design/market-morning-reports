"""Bounded, reproducible Agent 4.1 research. No production writes or PIT promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from universal_agent.engine import locked_state, write_state
from .agent4_market import (EMBARGO, FINAL_START, HORIZONS, SMOOTHING, TRAIN_END,
                            VALIDATION_END, VALIDATION_START, _labels, _score, _signal)
from .eligibility_manifest import build_manifest
from .exploratory_backtest import HERE, load_indices, pit_eligibility

INPUTS = ('indicator_spec.csv', 'inventory_190.csv', 'data_coverage.csv',
          'pit_readiness_matrix_20261031.csv')
SOURCE_FILES = ('naver_source_manifest.json', 'naver_kospi_daily.csv',
                'naver_kosdaq_daily.csv')
CODE_FILES = ('agent41_research.py', 'agent4_market.py', 'exploratory_backtest.py',
              'eligibility_manifest.py')
STATE = 'agent41_research_memory.json'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hashes() -> dict:
    source = HERE.parent / 'daily-index-validation-20261021'
    return {str(path.relative_to(HERE.parent)): _sha(path) for path in
            [*(HERE / name for name in INPUTS + CODE_FILES),
             *(source / name for name in SOURCE_FILES)]}


def _problem(pid: str, category: str, evidence: list, cause: str | None,
             confidence: str, solutions: list[str], priority: int,
             resources: list[str], status: str) -> dict:
    return dict(problem_id=pid, category=category, evidence=evidence,
                root_cause=cause, confidence=confidence, possible_solutions=solutions,
                priority=priority, required_resources=resources, resolution_status=status)


def pit_research() -> dict:
    manifest = build_manifest()
    gate = pit_eligibility()
    if manifest['indicator_count'] != 190 or gate['eligible_indicator_ids']:
        raise ValueError('PIT baseline changed; manual review required')
    records = []
    problems = []
    for row in manifest['records']:
        missing = []
        if row['publication_timestamp_status'] != 'verified':
            missing.append('row-level publication timestamp')
        if row['revision_policy_status'] != 'verified':
            missing.append('historical revision/vintage evidence')
        if row['calculation_status'] not in ('verified', 'VERIFIED'):
            missing.append('independently checked formula')
        if not row['actual_indicator_series_rows']:
            missing.append('observed indicator series')
        status = 'BLOCKED_EVIDENCE' if missing else 'BLOCKED_INDEPENDENT_REPRODUCTION'
        records.append({'indicator_id': row['indicator_id'], 'source': row['source'],
                        'source_candidate': row['input_dependencies'],
                        'pit_classification': row['pit_status'],
                        'calculation_status': row['calculation_status'],
                        'publication_timestamp_status': row['publication_timestamp_status'],
                        'revision_history_status': row['revision_policy_status'],
                        'indicator_rows': row['actual_indicator_series_rows'],
                        'evidence_gap': missing, 'repair_status': status,
                        'approved': False})
        if missing:
            problems.append(_problem(f"PIT-{row['indicator_id']:03}", 'PIT_VALIDATION_FAILURE',
                [f"pit_readiness_matrix_20261031.csv:{row['indicator_id']}",
                 f"source={row['source']}", f"blocking_reason={row['blocking_reason']}"],
                None, 'INSUFFICIENT_FOR_ROOT_CAUSE',
                ['obtain primary release and vintage records', 'verify source values and formula'],
                1 if row['actual_indicator_series_rows'] else 2,
                missing, status))
    counts = dict(Counter(row['pit_classification'] for row in records))
    return {'status': 'PIT_RECHECKED_NO_PROMOTION', 'counts': counts,
            'approved_before': 0, 'approved_after': 0, 'records': records,
            'problems': problems, 'repair_attempt': 'metadata cross-check of four 190-row sources',
            'limitation': 'Historical row-level publication and vintage evidence absent'}


def _hypothesis(hid: str, problem_id: str, statement: str, evidence: list,
                method: str) -> dict:
    return {'hypothesis_id': hid, 'problem_id': problem_id, 'hypothesis': statement,
            'supporting_evidence': evidence, 'required_data': ['hashed KOSPI/KOSDAQ snapshots'],
            'expected_effect': 'lower 20-session crash Brier than frozen simple baseline',
            'test_method': method,
            'failure_criteria': 'validation Brier is not lower than baseline or PIT/holdout gate fails',
            'generation_method': 'DETERMINISTIC_RULE_TEMPLATE', 'llm_runtime': 'NOT_CONNECTED'}


def _observations() -> tuple[list[dict], dict]:
    rows, provenance = load_indices('1996-01-01', skip_invalid_pre2010=True)
    signals = {i: _signal(rows, i) for i in range(60, len(rows))}
    future_regimes = {i: signal['regime'] for i, signal in signals.items()}
    observations = []
    for i in range(60, len(rows) - max(HORIZONS)):
        signal = signals[i]
        observations.append({**signal, 'labels': _labels(rows, i, signal, future_regimes)})
    return observations, provenance


def _bin(row: dict, name: str) -> str:
    f = row['feature']
    if name == 'drawdown':
        return 'DEEP' if f['drawdown60'] <= -.10 else 'OTHER'
    if name == 'volatility_drawdown':
        return f"{f['volatility20'] >= .025}:{f['drawdown60'] <= -.10}"
    if name == 'momentum_drawdown':
        return f"{f['momentum20'] <= -.04}:{f['drawdown60'] <= -.10}"
    raise ValueError('Experiment is not allowlisted')


def _predict(train: list[dict], validation: list[dict], name: str) -> list[float]:
    positives = sum(row['labels']['20']['crash'] for row in train)
    prior = positives / len(train)
    groups: dict[str, list[int]] = {}
    for row in train:
        count = groups.setdefault(_bin(row, name), [0, 0])
        count[0] += int(row['labels']['20']['crash'])
        count[1] += 1
    return [(groups.get(_bin(row, name), [0, 0])[0] + SMOOTHING * prior) /
            (groups.get(_bin(row, name), [0, 0])[1] + SMOOTHING)
            for row in validation]


def forecast_research() -> dict:
    observations, provenance = _observations()
    train = [r for r in observations if r['date'] <= TRAIN_END][:-EMBARGO]
    validation = [r for r in observations if VALIDATION_START <= r['date'] <= VALIDATION_END][:-EMBARGO]
    if len(train) < 500 or len(validation) < 200 or validation[-1]['date'] >= FINAL_START:
        raise ValueError('Research split invalid')
    labels = [r['labels']['20']['crash'] for r in validation]
    evidence = ['Agent 4.0 20-session crash Brier .0470 vs drawdown .0455',
                f"validation={validation[0]['date']}..{validation[-1]['date']}",
                f'positive_days={sum(labels)}']
    problem = _problem('FORECAST-CRASH20', 'BASELINE_UNDERPERFORMANCE', evidence,
                       None, 'INSUFFICIENT_FOR_CAUSAL_ROOT_CAUSE',
                       ['test volatility and drawdown interaction',
                        'test momentum and drawdown interaction'], 1,
                       ['PIT evidence', 'unexamined independent holdout'], 'EXPLORATORY')
    hypotheses = [
        _hypothesis('H-CRASH-VOL-DD', problem['problem_id'],
                    'Joint high volatility and deep drawdown may separate crash risk',
                    evidence, 'frozen 2x2 bins, 20-session crash, train through 2017, validate 2018-2021'),
        _hypothesis('H-CRASH-MOM-DD', problem['problem_id'],
                    'Joint weak momentum and deep drawdown may separate crash risk',
                    evidence, 'frozen 2x2 bins; fallback if first hypothesis fails')]
    experiments = []
    baseline = _score(labels, _predict(train, validation, 'drawdown'), .1)
    for name, hid in [('volatility_drawdown', 'H-CRASH-VOL-DD'),
                      ('momentum_drawdown', 'H-CRASH-MOM-DD')]:
        score = _score(labels, _predict(train, validation, name), .1)
        improvement = score['brier'] < baseline['brier']
        experiments.append({'hypothesis_id': hid, 'model': name,
            'validation_metrics': {key: score[key] for key in
                ('n', 'positive_days', 'tp', 'fp', 'fn', 'precision', 'recall',
                 'pr_auc_average_precision', 'brier')},
            'baseline_brier': baseline['brier'],
            'brier_delta': score['brier'] - baseline['brier'],
            'exploratory_brier_improved': improvement,
            'decision': 'EXPLORATORY_ONLY' if improvement else 'REJECTED_ON_VALIDATION',
            'independent_validation': 'NOT_VERIFIED', 'pit_verified': False})
        if improvement:
            break
    return {'status': 'EXPLORATORY_FORECAST_RESEARCH', 'problem': problem,
            'hypotheses': hypotheses, 'experiments': experiments,
            'fallback_executed': len(experiments) > 1,
            'baseline_metrics': {key: baseline[key] for key in
                ('n', 'positive_days', 'precision', 'recall', 'pr_auc_average_precision', 'brier')},
            'train': [train[0]['date'], train[-1]['date'], len(train)],
            'validation': [validation[0]['date'], validation[-1]['date'], len(validation)],
            'final_holdout': 'CONTAMINATED_NOT_REUSED',
            'independent_validation': 'BLOCKED_NO_UNEXAMINED_PIT_VERIFIED_DATA',
            'official_prediction_claim': False, 'source_provenance': provenance,
            'regime_detection_delay': 'NOT_VERIFIED_NO_INDEPENDENT_REGIME_TRUTH',
            'regime_false_alarms': 'NOT_VERIFIED_NO_INDEPENDENT_REGIME_TRUTH'}


def cycle(state_dir: Path) -> dict:
    state_dir = state_dir.resolve()
    if state_dir == HERE or HERE in state_dir.parents:
        raise ValueError('State must be outside tracked research source')
    with locked_state(state_dir):
        if (state_dir / 'STOP').exists():
            return {'status': 'STOPPED'}
        memory_path = state_dir / STATE
        hashes = _hashes()
        if memory_path.exists():
            memory = json.loads(memory_path.read_text())
            if memory['input_sha256'] != hashes or any(
                    not (state_dir / name).is_file() or _sha(state_dir / name) != digest
                    for name, digest in memory['artifacts_sha256'].items()):
                raise ValueError('Agent 4.1 memory integrity mismatch')
            return {'status': 'ALREADY_EVALUATED', 'decision': memory['decision']}
        pit = pit_research()
        forecast = forecast_research()
        if pit['approved_after'] or forecast['official_prediction_claim']:
            raise ValueError('Research approval gate failed')
        write_state(state_dir / 'pit_research.json', pit)
        write_state(state_dir / 'forecast_research.json', forecast)
        memory = {'schema_version': 1, 'cycle_id': 'regime190_agent41_first_cycle',
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'input_sha256': hashes,
            'artifacts_sha256': {name: _sha(state_dir / name) for name in
                                 ('pit_research.json', 'forecast_research.json')},
            'problems_detected': len(pit['problems']) + 1,
            'hypotheses_generated': len(forecast['hypotheses']),
            'experiments_run': len(forecast['experiments']),
            'llm_runtime': 'NOT_CONNECTED', 'code_generation': 'NOT_IMPLEMENTED',
            'independent_validation': forecast['independent_validation'],
            'decision': 'BLOCKED_PIT_AND_INDEPENDENT_HOLDOUT',
            'next_priority': ['obtain row-level release/vintage evidence',
                              'acquire genuinely unexamined validation data']}
        write_state(memory_path, memory)
        return {'status': 'RESEARCH_CYCLE_RECORDED', 'decision': memory['decision'],
                'problems': memory['problems_detected'],
                'experiments': memory['experiments_run']}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(cycle(args.state_dir), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
