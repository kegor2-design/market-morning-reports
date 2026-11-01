"""Reviewed, deterministic Agent 3.0 repair templates; exploratory only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .autonomous_diagnosis import BASELINE_STATE, FINAL_START, TRAIN_END, VALIDATION_END, run_diagnosis
from .eligibility_manifest import build_manifest
from .exploratory_backtest import EXPOSURE, PARAMETERS, _features, _metrics, load_indices, pit_eligibility
from .historical_evaluation import walk_forward_indices
from .worker import env_keys

PARENT_COMMIT = '09778943f57a739528fb01a7009cd0efda6020a6'
PATCH_ID = 'regime190_agent3_reviewed_templates_v1'


def patch_manifest() -> dict:
    path = Path(__file__).resolve()
    return {'schema_version': 1, 'patch_id': PATCH_ID, 'parent_commit': PARENT_COMMIT,
            'hypothesis_id': 'h_recovery_label_alignment',
            'target_files': ['market-history/research/regime190/agent3_experiments.py'],
            'code_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'change_description': 'Add fixed label-alignment and regime-hysteresis research templates',
            'expected_effect': 'Expose noncomparable label repair and test turnover reduction',
            'rollback_plan': 'Revert only this reviewed research commit in the isolated worktree',
            'test_plan': ['syntax', 'regime190 tests', 'universal_agent tests',
                          'baseline replay', 'bounded queue cycle'],
            'activation': 'REVIEWED_TEMPLATE_ONLY_NO_DYNAMIC_CODE_EXECUTION'}


def validate_patch(value: dict) -> None:
    expected = patch_manifest()
    if value != expected or any(not name.startswith('market-history/research/regime190/')
                                or '..' in Path(name).parts for name in value['target_files']):
        raise ValueError('Unreviewed or altered research patch')


def _db_sample() -> dict:
    """Inspect actual columns first; only bounded read-only metadata samples follow."""
    import psycopg2
    cfg = env_keys(Path.home() / 'mydream2000_backtest_ro.env')
    keys = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    if any(not cfg.get(key) for key in keys):
        return {'status': 'READ_ONLY_CREDENTIAL_UNAVAILABLE'}
    required = {
        'domestic_daily_price': {'market_date', 'symbol', 'market', 'available_at', 'collected_at'},
        'domestic_index_daily': {'market_date', 'available_at', 'collected_at'},
        'market_rates_snapshot': {'data_date', 'released_at', 'available_at', 'vintage_date'},
    }
    with psycopg2.connect(host=cfg['DB_HOST'], port=cfg['DB_PORT'], dbname=cfg['DB_NAME'],
                          user=cfg['DB_USER'], password=cfg['DB_PASSWORD'], connect_timeout=4,
                          application_name='regime190_agent3_pit_readonly') as connection:
        with connection.cursor() as cursor:
            cursor.execute('BEGIN READ ONLY')
            cursor.execute("SET LOCAL statement_timeout='5000ms'")
            cursor.execute("SELECT table_name,column_name FROM information_schema.columns "
                           "WHERE table_schema='public' AND table_name=ANY(%s) LIMIT 100",
                           (list(required),))
            present = {name: set() for name in required}
            for name, column in cursor.fetchall():
                present[name].add(column)
            if any(not columns <= present[name] for name, columns in required.items()):
                raise ValueError('Production DB schema changed')
            queries = {
                'historical_price': "SELECT market_date,market,available_at,collected_at FROM domestic_daily_price WHERE symbol='005930' AND market_date BETWEEN DATE '2020-01-01' AND DATE '2020-02-28' LIMIT 20",
                'recent_index': "SELECT market_date,available_at,collected_at FROM domestic_index_daily WHERE market_date >= DATE '2026-10-01' ORDER BY market_date DESC LIMIT 20",
                'recent_rates': "SELECT data_date,released_at,available_at,vintage_date FROM market_rates_snapshot WHERE data_date >= DATE '2026-10-01' ORDER BY data_date DESC LIMIT 20",
            }
            samples = {}
            for name, query in queries.items():
                cursor.execute(query)
                rows = cursor.fetchall()
                if name == 'historical_price':
                    samples[name] = {'rows': len(rows), 'market_missing': sum(not row[1] for row in rows),
                        'available_1630': sum(row[2] is not None and row[2].strftime('%H:%M') == '16:30' for row in rows),
                        'collected_after_available': sum(row[2] is not None and row[3] is not None and row[3] > row[2] for row in rows)}
                elif name == 'recent_index':
                    samples[name] = {'rows': len(rows), 'available_1630': sum(row[1] is not None and row[1].strftime('%H:%M') == '16:30' for row in rows),
                        'collected_after_available': sum(row[1] is not None and row[2] is not None and row[2] > row[1] for row in rows)}
                else:
                    samples[name] = {'rows': len(rows), 'released_missing': sum(row[1] is None for row in rows),
                        'vintage_missing': sum(row[3] is None for row in rows)}
        connection.rollback()
    return {'status': 'SCHEMA_VERIFIED_READ_ONLY_BOUNDED', 'sample_limit_per_table': 20,
            'statement_timeout_ms': 5000, 'samples': samples}


def investigate_pit() -> dict:
    manifest = build_manifest()
    gate = pit_eligibility()
    if gate['eligible_indicator_ids']:
        raise ValueError('PIT eligibility changed; stop Agent 3 exploratory plan')
    counts = {}
    for row in manifest['records']:
        key = row['pit_status']
        counts[key] = counts.get(key, 0) + 1
    candidate_sources = [
        {'source': 'KRX official index daily API', 'scope': 'KOSPI/KOSDAQ 2010+ candidate',
         'documentation': 'https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd',
         'status': 'CANDIDATE_ONLY', 'missing': ['licensed access review', 'historical release hour', 'row-level availability', 'independent comparison']},
        {'source': 'FRED/ALFRED vintage observations', 'scope': 'selected US macro components',
         'documentation': 'https://fred.stlouisfed.org/docs/api/fred/series_observations.html',
         'status': 'CANDIDATE_ONLY', 'missing': ['series-specific historical publication hour', 'KST decision alignment', 'full-period coverage']},
    ]
    return {'schema_version': 1, 'status': 'PIT_REPAIR_INVESTIGATED_NO_PROMOTION',
            'indicator_count': manifest['indicator_count'], 'classification_counts': counts,
            'eligible_before': 0, 'eligible_after': 0,
            'blocked_indicators': [{'indicator_id': row['indicator_id'],
                'state': row['current_state'], 'pit_status': row['pit_status'],
                'blocking_reason': row['blocking_reason']} for row in manifest['records']],
            'db_evidence': _db_sample(), 'candidate_sources': candidate_sources,
            'source_search_mode': 'CURATED_OFFICIAL_CATALOG_NO_AUTONOMOUS_WEB_CRAWL',
            'next_action': 'Acquire independent release/vintage and historical membership evidence',
            'approval_required': ['source license review before broader acquisition']}


def _baseline() -> tuple[list[dict], list[dict]]:
    diagnosis = run_diagnosis()
    artifact = json.loads(Path(BASELINE_STATE / 'artifacts/index_regime_exploratory_v1.json').read_text())['result']
    source, provenance = load_indices()
    if provenance != diagnosis['source_provenance']:
        raise ValueError('Baseline source changed')
    return artifact['timeline'], source


def label_alignment_experiment() -> dict:
    """Repair a measurement mismatch, never compare its precision as strategy gain."""
    validate_patch(patch_manifest())
    timeline, source = _baseline()
    by_date = {row['date']: i for i, row in enumerate(source)}
    segments = {'train': [], 'validation': []}
    for row in timeline:
        if row['date'] <= TRAIN_END:
            key = 'train'
        elif row['date'] <= VALIDATION_END:
            key = 'validation'
        else:
            continue
        i = by_date[row['date']]
        feature = _features(source, i)
        future20 = source[i + 20]['kospi']['close'] / source[i]['kospi']['close'] - 1
        aligned = feature['drawdown60'] <= -.08 and future20 >= PARAMETERS['recovery_threshold']
        segments[key].append({'signal': row['recovery_signal'], 'original': row['recovery_outcome'],
                              'aligned': aligned})
    segments['train'] = segments['train'][:-20]
    summary = {}
    for key, rows in segments.items():
        summary[key] = {'days': len(rows),
            'signal_days': sum(row['signal'] for row in rows),
            'original_positive_days': sum(row['original'] for row in rows),
            'aligned_positive_days': sum(row['aligned'] for row in rows),
            'original_true_positive_days': sum(row['signal'] and row['original'] for row in rows),
            'aligned_true_positive_days': sum(row['signal'] and row['aligned'] for row in rows)}
    return {'schema_version': 1, 'experiment_id': 'recovery_label_alignment_v1',
            'hypothesis_id': 'h_recovery_label_alignment', 'patch': patch_manifest(),
            'changed_variable': 'outcome_drawdown_eligibility:-0.10_to_-0.08',
            'unchanged_controls': ['signals', 'source', 'future_return_threshold', 'execution'],
            'train_validation': summary, 'final_holdout': 'FINAL_HOLDOUT_CONTAMINATED_NOT_EVALUATED',
            'decision': 'NONCOMPARABLE_MEASUREMENT_REPAIR',
            'failure_feedback': 'Changing the target label cannot establish strategy improvement',
            'next_hypothesis_id': 'h_switch_hysteresis',
            'official_improvement_claim': False}


def hysteresis_experiment(parent: dict) -> dict:
    if parent.get('decision') != 'NONCOMPARABLE_MEASUREMENT_REPAIR' or parent.get('next_hypothesis_id') != 'h_switch_hysteresis':
        raise ValueError('No justified automatic next experiment')
    timeline, source = _baseline()
    by_date = {row['date']: i for i, row in enumerate(source)}
    selected = [row for row in timeline if row['date'] < FINAL_START]
    candidate_regime = selected[0]['regime']
    previous_proposal = None
    previous_baseline = previous_candidate = 0.0
    samples = {'train': [], 'validation': []}
    for row in selected:
        proposed = row['regime']
        if proposed != candidate_regime and proposed == previous_proposal:
            candidate_regime = proposed
        previous_proposal = proposed
        i = by_date[row['date']]
        gross = source[i + 2]['kospi']['open'] / source[i + 1]['kospi']['open'] - 1
        baseline_pos = row['positions']['six_regime']
        candidate_pos = EXPOSURE[candidate_regime]
        baseline_turn = abs(baseline_pos - previous_baseline)
        candidate_turn = abs(candidate_pos - previous_candidate)
        baseline_ret = baseline_pos * gross - PARAMETERS['transaction_cost_one_way'] * baseline_turn
        candidate_ret = candidate_pos * gross - PARAMETERS['transaction_cost_one_way'] * candidate_turn
        if row['date'] <= TRAIN_END:
            key = 'train'
        else:
            key = 'validation'
        samples[key].append((row['date'], baseline_ret, candidate_ret,
                             baseline_pos, candidate_pos, baseline_turn, candidate_turn, gross))
        previous_baseline, previous_candidate = baseline_pos, candidate_pos
    samples['train'] = samples['train'][:-20]
    comparison = {}
    for key, rows in samples.items():
        comparison[key] = {'days': len(rows),
            'baseline': _metrics([r[1] for r in rows], [r[3] for r in rows], sum(r[5] for r in rows)),
            'candidate': _metrics([r[2] for r in rows], [r[4] for r in rows], sum(r[6] for r in rows))}
    all_rows = samples['train'] + samples['validation']
    dates = [row[0] for row in all_rows]
    folds = walk_forward_indices(dates, train_size=1000, test_size=252, embargo=20)
    fold_summary = []
    for training, testing in folds:
        test_rows = [all_rows[i] for i in testing]
        fold_summary.append({'train_start': dates[training.start],
            'train_end': dates[training.stop - 1],
            'test_start': dates[testing.start], 'test_end': dates[testing.stop - 1],
            'baseline_sharpe': _metrics([r[1] for r in test_rows], [r[3] for r in test_rows],
                                        sum(r[5] for r in test_rows))['sharpe_zero_rf'],
            'candidate_sharpe': _metrics([r[2] for r in test_rows], [r[4] for r in test_rows],
                                         sum(r[6] for r in test_rows))['sharpe_zero_rf']})
    cost_sensitivity = {}
    for fee in (0.0005, 0.0015, 0.003):
        rows = samples['validation']
        cost_sensitivity[str(fee)] = {
            'baseline_cumulative_return': _metrics([r[3] * r[7] - fee * r[5] for r in rows],
                                                   [r[3] for r in rows], sum(r[5] for r in rows))['cumulative_return'],
            'candidate_cumulative_return': _metrics([r[4] * r[7] - fee * r[6] for r in rows],
                                                    [r[4] for r in rows], sum(r[6] for r in rows))['cumulative_return']}
    improvement = (comparison['validation']['candidate']['sharpe_zero_rf'] or -999) > (comparison['validation']['baseline']['sharpe_zero_rf'] or -999)
    return {'schema_version': 1, 'experiment_id': 'regime_hysteresis_v1',
            'hypothesis_id': 'h_switch_hysteresis', 'parent_experiment_id': parent['experiment_id'],
            'patch': patch_manifest(), 'changed_variable': 'regime_transition_confirmation:1_to_2_days',
            'unchanged_controls': ['source', 'regime definitions', 'exposure map', 'costs', 'next-open execution'],
            'train_validation': comparison,
            'walk_forward': {'status': 'EXPLORATORY_PREVIOUSLY_EXAMINED_PERIODS',
                             'embargo_sessions': 20, 'folds': fold_summary},
            'cost_sensitivity_validation': cost_sensitivity,
            'walk_forward_status': 'PREVIOUSLY_EXAMINED_PERIODS_EXPLORATORY_ONLY',
            'final_holdout': 'FINAL_HOLDOUT_CONTAMINATED_NOT_EVALUATED',
            'decision': 'IMPROVEMENT_UNCONFIRMED' if improvement else 'HYPOTHESIS_REJECTED_EXPLORATORY',
            'official_improvement_claim': False, 'deployment_readiness': 'NOT_READY',
            'next_action': 'Require PIT evidence and a genuinely unused validation period'}
