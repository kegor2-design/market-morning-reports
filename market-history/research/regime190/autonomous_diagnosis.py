"""Deterministic diagnosis and one controlled Regime190 exploratory experiment.

The 2022+ period was already examined. It is never used to select or validate
the candidate below. No output is PIT-approved or a causal claim.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from pathlib import Path

from .exploratory_backtest import (_features, execute_exploratory, load_indices,
                                   pit_eligibility)
from .historical_evaluation import walk_forward_indices

BASELINE_STATE = Path('/home/kegor2/agent2_research_state/regime190_exploratory_v4_20261101')
TRAIN_END = '2017-12-31'
VALIDATION_START = '2018-01-01'
VALIDATION_END = '2021-12-31'
FINAL_START = '2022-01-01'
EMBARGO_SESSIONS = 20


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _rates(labels: list[bool], signals: list[bool]) -> dict:
    if len(labels) != len(signals) or not labels:
        raise ValueError('Misaligned metric inputs')
    tp = sum(a and p for a, p in zip(labels, signals))
    fp = sum(not a and p for a, p in zip(labels, signals))
    fn = sum(a and not p for a, p in zip(labels, signals))
    tn = len(labels) - tp - fp - fn
    return {'days': len(labels), 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'prevalence': (tp + fn) / len(labels),
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'specificity': tn / (tn + fp) if tn + fp else None,
            'false_positive_rate': fp / (tn + fp) if tn + fp else None,
            'false_alarms_per_252_sessions': fp / len(labels) * 252,
            'precision_recall_auc': None,
            'auc_reason': 'binary warning only; no calibrated continuous score'}


def _bootstrap_precision_delta(labels: list[bool], old: list[bool], new: list[bool],
                               seed: int = 190, repetitions: int = 300) -> dict:
    if len(labels) != len(old) or len(labels) != len(new):
        raise ValueError('Misaligned bootstrap rows')
    size = len(labels)
    if size < 100:
        return {'status': 'INSUFFICIENT_SAMPLE', 'interval_95': None}
    if not any(label and (a or b) for label, a, b in zip(labels, old, new)):
        return {'status': 'NO_TRUE_POSITIVE_SIGNALS', 'interval_95': None}
    rng = random.Random(seed)
    values = []
    for _ in range(repetitions):
        indices = []
        while len(indices) < size:
            start = rng.randrange(max(1, size - EMBARGO_SESSIONS + 1))
            indices.extend(range(start, min(start + EMBARGO_SESSIONS, size)))
        indices = indices[:size]
        before = _rates([labels[i] for i in indices], [old[i] for i in indices])['precision']
        after = _rates([labels[i] for i in indices], [new[i] for i in indices])['precision']
        if before is not None and after is not None:
            values.append(after - before)
    if len(values) < repetitions // 2:
        return {'status': 'INSUFFICIENT_POSITIVE_BOOTSTRAP_SAMPLES', 'interval_95': None}
    values.sort()
    return {'status': 'EXPLORATORY_BLOCK_BOOTSTRAP', 'seed': seed,
            'block_sessions': EMBARGO_SESSIONS, 'replicates': len(values),
            'interval_95': [values[int(.025 * (len(values) - 1))],
                            values[int(.975 * (len(values) - 1))]]}


def _bootstrap_warning(labels: list[bool], signals: list[bool], seed: int = 191,
                       repetitions: int = 300) -> dict:
    size = len(labels)
    rng = random.Random(seed)
    estimates = {'precision': [], 'recall': []}
    for _ in range(repetitions):
        indices = []
        while len(indices) < size:
            start = rng.randrange(max(1, size - EMBARGO_SESSIONS + 1))
            indices.extend(range(start, min(start + EMBARGO_SESSIONS, size)))
        sample = _rates([labels[i] for i in indices[:size]],
                        [signals[i] for i in indices[:size]])
        for key in estimates:
            if sample[key] is not None:
                estimates[key].append(sample[key])
    return {'status': 'EXPLORATORY_BLOCK_BOOTSTRAP', 'seed': seed,
            'block_sessions': EMBARGO_SESSIONS,
            'interval_95': {key: [sorted(values)[int(.025 * (len(values) - 1))],
                                  sorted(values)[int(.975 * (len(values) - 1))]]
                            if len(values) >= repetitions // 2 else None
                            for key, values in estimates.items()},
            'caution': 'dependent labels and few independent episodes limit inference'}


def _diagnosis(category: str, evidence: dict, action: str, method: str,
               severity: str = 'REVIEW', confidence: str = 'OBSERVED') -> dict:
    return {'schema_version': 1, 'diagnosis_id': category.lower(),
            'experiment_id': 'index_regime_exploratory_v1', 'failure_category': category,
            'evidence': evidence, 'severity': severity, 'confidence': confidence,
            'recommended_action': action, 'verification_method': method,
            'causality_claimed': False}


def _log_decomposition(timeline: list[dict], source: list[dict]) -> dict:
    by_date = {row['date']: i for i, row in enumerate(source)}
    fee = .0015
    prev_benchmark = prev_strategy = 0.0
    opportunity = strategy_cost = benchmark_cost = positive = avoided = 0.0
    benchmark_log = strategy_log = 0.0
    for row in timeline:
        i = by_date[row['date']]
        if (source[i + 1]['date'] != row['execution_open_date']
                or source[i + 2]['date'] != row['settlement_open_date']):
            raise ValueError('Execution timestamp alignment changed')
        gross = source[i + 2]['kospi']['open'] / source[i + 1]['kospi']['open'] - 1
        exposure = row['positions']['six_regime']
        benchmark_net = 1 + gross - fee * abs(1 - prev_benchmark)
        strategy_net = 1 + exposure * gross - fee * abs(exposure - prev_strategy)
        if min(benchmark_net, strategy_net, 1 + exposure * gross) <= 0:
            raise ValueError('Invalid log-return decomposition')
        day_opportunity = math.log1p(gross) - math.log1p(exposure * gross)
        opportunity += day_opportunity
        positive += max(0, day_opportunity)
        avoided += min(0, day_opportunity)
        strategy_cost += math.log1p(exposure * gross) - math.log(strategy_net)
        benchmark_cost += math.log1p(gross) - math.log(benchmark_net)
        benchmark_log += math.log(benchmark_net)
        strategy_log += math.log(strategy_net)
        prev_benchmark, prev_strategy = 1, exposure
    gap = benchmark_log - strategy_log
    if abs(gap - (opportunity + strategy_cost - benchmark_cost)) > 1e-9:
        raise ValueError('Return attribution identity failed')
    return {'log_wealth_gap_buyhold_minus_six': gap,
            'log_opportunity_cost': opportunity,
            'missed_upside_log_contribution': positive,
            'avoided_downside_log_contribution': avoided,
            'six_regime_trading_cost_log': strategy_cost,
            'buyhold_trading_cost_log': benchmark_cost,
            'identity_error': gap - (opportunity + strategy_cost - benchmark_cost),
            'interpretation': 'exact log-wealth accounting, not causal attribution'}


def _recovery_metrics(rows: list[dict], signals: list[bool]) -> dict:
    labels = [bool(row['recovery_outcome']) for row in rows]
    base = _rates(labels, signals)
    false = sum(signal and row['false_rebound'] for signal, row in zip(signals, rows))
    base['false_rebound_signals'] = false
    base['false_rebound_fraction'] = false / sum(signals) if any(signals) else None
    return base


def run_diagnosis(baseline_state: Path = BASELINE_STATE) -> dict:
    memory = json.loads((baseline_state / 'research_memory.json').read_text())
    artifact = Path(memory['artifact_path'])
    raw = artifact.read_bytes()
    if hashlib.sha256(raw).hexdigest() != memory['artifact_sha256']:
        raise ValueError('Baseline artifact checksum mismatch')
    result = json.loads(raw)['result']
    if (memory['code_commit'] != '7009996f407dcf2266e7a4d64d3fa745fcb4a48d'
            or result['status'] != 'EXPLORATORY_REAL_DATA_PIT_UNVERIFIED'
            or result['official_performance_claim'] is not False
            or result != execute_exploratory()):
        raise ValueError('REPRODUCTION_FAILED')
    timeline = result['timeline']
    source, provenance = load_indices()
    if provenance != memory['source_provenance']:
        raise ValueError('Source provenance changed')
    by_date = {row['date']: i for i, row in enumerate(source)}
    if any(row['signal_after_close_date'] != row['date']
           or not row['date'] < row['execution_open_date'] < row['settlement_open_date']
           for row in timeline):
        raise ValueError('Signal timing invalid')
    labels = [row['crash_outcomes']['20'] for row in timeline]
    warnings = [row['crash_warning'] for row in timeline]
    crash = _rates(labels, warnings)
    if (crash['tp'], crash['fp'], crash['fn'], crash['tn']) != (51, 621, 159, 3221):
        raise ValueError('Baseline crash confusion matrix changed')
    features = [_features(source, by_date[row['date']]) for row in timeline]
    baselines = {'always_negative': [False] * len(timeline),
                 'moving_average': [not f['above_sma20'] for f in features],
                 'volatility': [f['volatility20'] >= .025 for f in features],
                 'momentum': [f['momentum20'] <= -.04 for f in features]}
    comparators = {key: _rates(labels, signal) for key, signal in baselines.items()}
    uncertainty = _bootstrap_warning(labels, warnings)
    recover = _recovery_metrics(timeline, [row['recovery_signal'] for row in timeline])
    mismatch = sum(row['recovery_signal'] and features[i]['drawdown60'] > -.1
                   for i, row in enumerate(timeline))
    attribution = _log_decomposition(timeline, source)
    gate = pit_eligibility()
    if gate['eligible_indicator_ids']:
        raise ValueError('PIT decision changed; review before diagnosis')
    diagnoses = [
        _diagnosis('PIT_FAILURE', {'eligible_indicators': 0,
                                   'publication_status': 'UNVERIFIED',
                                   'revision_status': 'UNVERIFIED'},
                   'Obtain row-level release/vintage evidence', 'independent source and as-of audit',
                   'BLOCKING'),
        _diagnosis('CLASS_IMBALANCE', {'positive_days': crash['tp'] + crash['fn'],
                                     'prevalence': crash['prevalence'],
                                     'precision': crash['precision']},
                   'Compare lift against prevalence and event episodes',
                   'same-period baseline and block bootstrap', 'REVIEW'),
        _diagnosis('LOW_PREDICTIVE_POWER', {'regime_warning_precision': crash['precision'],
                                            'volatility_warning_precision': comparators['volatility']['precision'],
                                            'regime_warning_recall': crash['recall'],
                                            'volatility_warning_recall': comparators['volatility']['recall']},
                   'Test whether regime warning adds value beyond a fixed volatility baseline',
                   'chronological PIT-eligible comparison', 'REVIEW', 'ASSOCIATION_ONLY'),
        _diagnosis('LABEL_DEFINITION_PROBLEM', {'recovery_signals': sum(row['recovery_signal'] for row in timeline),
                                                'signals_in_outcome_ineligible_drawdown_band': mismatch},
                   'Align recovery signal and outcome eligibility in a controlled experiment',
                   'inspect signal-day drawdown and future-only labels', 'REVIEW'),
        _diagnosis('EXCESSIVE_TRANSACTION_COST', {'six_turnover_one_way':
                    memory['strategy_metrics_exploratory']['six_regime']['turnover_one_way'],
                    'log_cost_drag': attribution['six_regime_trading_cost_log']},
                   'Test one transition persistence rule without changing prices or costs',
                   'exact log-wealth decomposition', 'REVIEW'),
        _diagnosis('INSUFFICIENT_SAMPLE', {'recovery_signals': sum(row['recovery_signal'] for row in timeline),
                                          'recovery_true_positive_days': recover['tp']},
                   'Treat recovery precision as unstable', 'count independent episodes', 'REVIEW'),
        _diagnosis('UNKNOWN_CAUSE', {'unresolved': ['causal reason for low forecast skill',
                                                   'historical PIT and calendar validity']},
                   'Do not attribute causation from associations', 'new independent evidence',
                   'REVIEW', 'UNDETERMINED')]
    return {'schema_version': 1, 'research_cycle_id': 'regime190_autoval_20261101',
            'baseline_experiment_id': memory['experiment_id'],
            'baseline_artifact_sha256': memory['artifact_sha256'],
            'baseline_result_sha256': _digest(result), 'baseline_code_commit': memory['code_commit'],
            'source_provenance': provenance, 'data_validity': 'SNAPSHOT_REPRODUCED',
            'pit_validity': 'BLOCKED', 'model_status': 'DETERMINISTIC_NON_AI',
            'crash20': crash, 'crash_baselines': comparators,
            'crash20_uncertainty': uncertainty,
            'crash_label_clusters': result['crash_episode_proxy_exploratory'],
            'recovery': recover, 'recovery_definition_mismatch_days': mismatch,
            'strategy_attribution': attribution,
            'regime_counts': result['regime_counts'],
            'regime_transition_counts': result['transition_counts'],
            'total_regime_transitions': sum(result['transition_counts'].values()),
            'baseline_strategy_metrics': {key: memory['strategy_metrics_exploratory'][key]
                for key in ('buy_hold', 'six_regime')},
            'diagnoses': diagnoses,
            'timeline': timeline}


def controlled_experiment(diagnosis: dict) -> dict:
    """One prespecified change: require two consecutive early-recovery signals."""
    timeline = diagnosis['timeline']
    original = [row['recovery_signal'] for row in timeline]
    candidate = [signal and (original[i - 1] if i else False)
                 for i, signal in enumerate(original)]
    train_indices = [i for i, row in enumerate(timeline) if row['date'] <= TRAIN_END]
    validation_indices = [i for i, row in enumerate(timeline)
                          if VALIDATION_START <= row['date'] <= VALIDATION_END]
    if len(train_indices) <= EMBARGO_SESSIONS or len(validation_indices) < 100:
        raise ValueError('Insufficient chronological split')
    train_indices = train_indices[:-EMBARGO_SESSIONS]
    def compare(indices):
        rows = [timeline[i] for i in indices]
        before = [original[i] for i in indices]
        after = [candidate[i] for i in indices]
        labels = [row['recovery_outcome'] for row in rows]
        return {'baseline': _recovery_metrics(rows, before),
                'candidate': _recovery_metrics(rows, after),
                'precision_delta_block_bootstrap': _bootstrap_precision_delta(labels, before, after)}
    train, validation = compare(train_indices), compare(validation_indices)
    prefinal_indices = [i for i, row in enumerate(timeline) if row['date'] < FINAL_START]
    prefinal_dates = [timeline[i]['date'] for i in prefinal_indices]
    walk_forward = []
    for train_fold, test_fold in walk_forward_indices(prefinal_dates, 1000, 252, EMBARGO_SESSIONS):
        test_indices = [prefinal_indices[i] for i in test_fold]
        fold = compare(test_indices)
        walk_forward.append({'train_start': prefinal_dates[train_fold.start],
                             'train_end': prefinal_dates[train_fold.stop - 1],
                             'test_start': prefinal_dates[test_fold.start],
                             'test_end': prefinal_dates[test_fold.stop - 1],
                             'baseline': fold['baseline'], 'candidate': fold['candidate']})
    if not any(row['date'] >= FINAL_START for row in timeline):
        raise ValueError('Expected previously examined final period absent')
    plan = {'schema_version': 1, 'experiment_id': 'recovery_two_day_confirmation_v1',
            'hypothesis_id': 'h_recovery_confirmation',
            'parent_hypothesis_id': 'index_regime_exploratory_v1',
            'diagnostic_evidence': {'recovery_signals': diagnosis['recovery']['tp'] +
                diagnosis['recovery']['fp'], 'false_rebound_signals': diagnosis['recovery']['false_rebound_signals']},
            'proposed_mechanism': 'one-day rebounds may be unstable',
            'required_features': ['historical early-recovery signal'],
            'pit_requirements': 'EXPLORATORY_PIT_UNVERIFIED',
            'expected_observable_effect': 'fewer false rebound signal days',
            'test_method': 'two consecutive recovery signal days',
            'acceptance_criteria': 'validation precision rises without material recall collapse',
            'rejection_criteria': 'no stable validation gain or too few independent events',
            'estimated_cost': {'max_iterations': 1, 'max_seconds': 30, 'external_calls': 0},
            'priority': 1, 'baseline_version': diagnosis['baseline_code_commit'],
            'changed_variables': ['recovery_signal_persistence_days:1_to_2'],
            'unchanged_controls': ['source hashes', 'outcome labels', 'fee and slippage',
                                   'crash warning', 'regime classification'],
            'train_end': TRAIN_END, 'validation_start': VALIDATION_START,
            'validation_end': VALIDATION_END, 'embargo_sessions': EMBARGO_SESSIONS,
            'validation_status': 'VALIDATION_CONTAMINATED_BY_PRIOR_BASELINE_REVIEW',
            'final_holdout_start': FINAL_START, 'random_seed': 190,
            'final_holdout_status': 'FINAL_HOLDOUT_CONTAMINATED'}
    decision = ('HYPOTHESIS_REJECTED_EXPLORATORY' if
                (validation['candidate']['precision'] is None or
                 validation['baseline']['precision'] is None or
                 validation['candidate']['precision'] <= validation['baseline']['precision'])
                else 'IMPROVEMENT_UNCONFIRMED')
    return {'schema_version': 1, 'plan': plan, 'plan_sha256': _digest(plan),
            'train': train, 'validation': validation,
            'walk_forward': {'status': 'EXPLORATORY_PREVIOUSLY_EXAMINED_PERIODS',
                             'embargo_sessions': EMBARGO_SESSIONS,
                             'folds': walk_forward},
            'final_holdout': {'status': 'FINAL_HOLDOUT_CONTAMINATED',
                              'candidate_metrics': None,
                              'reason': 'prior experiment examined 2022+ and PIT is unverified'},
            'execution_success': True, 'data_validity': diagnosis['data_validity'],
            'pit_validity': 'BLOCKED', 'statistical_validity': 'INSUFFICIENT_INDEPENDENT_EVENTS',
            'out_of_sample_validity': 'NOT_VALIDATED', 'research_value': 'EXPLORATORY_ONLY',
            'deployment_readiness': 'NOT_READY', 'decision': decision,
            'next_action': 'Obtain PIT evidence and a genuinely unexamined validation sample'}


def additional_hypotheses(diagnosis: dict) -> list[dict]:
    return [
        {'schema_version': 1, 'hypothesis_id': 'h_switch_hysteresis',
         'parent_hypothesis_id': 'index_regime_exploratory_v1',
         'diagnostic_evidence': {'six_turnover_one_way': 221,
            'six_log_trading_cost': diagnosis['strategy_attribution']['six_regime_trading_cost_log']},
         'proposed_mechanism': 'frequent regime changes may increase cost drag',
         'required_features': ['historical regime timeline'],
         'pit_requirements': 'PIT_VERIFIED_BEFORE_OFFICIAL_TEST',
         'expected_observable_effect': 'lower turnover without losing downside protection',
         'test_method': 'one prespecified transition hysteresis rule',
         'acceptance_criteria': 'validation risk-adjusted gain with stable drawdown',
         'rejection_criteria': 'cost reduction offset by worse drawdown or no validation gain',
         'estimated_cost': {'max_iterations': 1, 'max_seconds': 30, 'external_calls': 0},
         'priority': 2, 'status': 'PROPOSED_NOT_EXECUTED'},
        {'schema_version': 1, 'hypothesis_id': 'h_volatility_warning_increment',
         'parent_hypothesis_id': 'index_regime_exploratory_v1',
         'diagnostic_evidence': {'regime_precision': diagnosis['crash20']['precision'],
            'volatility_precision': diagnosis['crash_baselines']['volatility']['precision']},
         'proposed_mechanism': 'volatility may explain more of the warning association',
         'required_features': ['PIT-valid index volatility'],
         'pit_requirements': 'PIT_VERIFIED_BEFORE_OFFICIAL_TEST',
         'expected_observable_effect': 'incremental warning value beyond volatility',
         'test_method': 'fixed comparison on a new eligible period',
         'acceptance_criteria': 'positive independently validated incremental value',
         'rejection_criteria': 'no gain over volatility after costs and uncertainty',
         'estimated_cost': {'max_iterations': 1, 'max_seconds': 30, 'external_calls': 0},
         'priority': 3, 'status': 'PROPOSED_NOT_EXECUTED'}]


def execute() -> dict:
    diagnosis = run_diagnosis()
    experiment = controlled_experiment(diagnosis)
    timeline = diagnosis.pop('timeline')  # Diagnostic result is bounded; original artifact owns the timeline.
    return {'schema_version': 1, 'status': 'EXPLORATORY_DIAGNOSIS_COMPLETE',
            'official_improvement_claim': False,
            'baseline_timeline_rows': len(timeline),
            'diagnosis': diagnosis, 'hypotheses': [experiment['plan']] +
                additional_hypotheses(diagnosis),
            'experiment': experiment, 'model_status': 'DETERMINISTIC_NON_AI',
            'research_decision': experiment['decision'],
            'next_action': experiment['next_action']}


def verify(result: dict) -> None:
    if (result.get('schema_version') != 1
            or result.get('status') != 'EXPLORATORY_DIAGNOSIS_COMPLETE'
            or result.get('official_improvement_claim') is not False
            or result.get('model_status') != 'DETERMINISTIC_NON_AI'
            or result.get('diagnosis', {}).get('pit_validity') != 'BLOCKED'
            or result.get('experiment', {}).get('final_holdout', {}).get('candidate_metrics') is not None
            or result.get('experiment', {}).get('deployment_readiness') != 'NOT_READY'):
        raise ValueError('Diagnosis result violates safety contract')
