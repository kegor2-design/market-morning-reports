"""Frozen market intelligence study. Historical snapshot results are exploratory only."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .exploratory_backtest import (SOURCE, _features, classify, load_indices,
                                   pit_eligibility)

VERSION = 'agent4_market_intelligence_v1_20261101'
HORIZONS = (5, 10, 20)
TARGETS = ('up', 'crash', 'recovery', 'transition')
MODELS = ('six_regime', 'moving_average', 'momentum', 'volatility', 'drawdown',
          'regime_persistence')
TRAIN_END = '2017-12-31'
VALIDATION_START = '2018-01-01'
VALIDATION_END = '2021-12-31'
FINAL_START = '2022-01-01'
EMBARGO = 20
SMOOTHING = 20
EVENTS = {'crash': 'minimum future close / signal close - 1 <= -0.10',
          'recovery': 'signal-day 60-session drawdown <= -0.10 AND horizon terminal close / signal close - 1 >= 0.08',
          'up': 'horizon terminal close > signal close',
          'transition': 'causal regime calculated on future horizon date differs from signal-date regime'}
THRESHOLD = {'up': .5, 'crash': .1, 'recovery': .05, 'transition': .2}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bins(regime: str, feature: dict) -> dict:
    return {'six_regime': regime,
            'moving_average': 'ABOVE' if feature['above_sma20'] else 'BELOW',
            'momentum': 'WEAK' if feature['momentum20'] <= -.04 else 'OTHER',
            'volatility': 'HIGH' if feature['volatility20'] >= .025 else 'OTHER',
            'drawdown': 'DEEP' if feature['drawdown60'] <= -.10 else 'OTHER',
            'regime_persistence': 'PERSIST'}


def _signal(rows: list[dict], i: int) -> dict:
    if i < 60 or i >= len(rows):
        raise ValueError('Insufficient causal history')
    feature = _features(rows, i)
    regime, heuristic = classify(feature)
    return {'date': rows[i]['date'], 'regime': regime, 'heuristic_strength': heuristic,
            'bins': _bins(regime, feature), 'feature': feature}


def _labels(rows: list[dict], i: int, signal: dict, future_regimes: dict[int, str]) -> dict:
    if i + max(HORIZONS) >= len(rows):
        raise ValueError('Future outcome unavailable')
    close = rows[i]['kospi']['close']
    answer = {}
    for horizon in HORIZONS:
        future = [rows[j]['kospi']['close'] / close - 1 for j in range(i + 1, i + horizon + 1)]
        answer[str(horizon)] = {'up': future[-1] > 0,
            'crash': min(future) <= -.10,
            'recovery': signal['feature']['drawdown60'] <= -.10 and future[-1] >= .08,
            'transition': future_regimes[i + horizon] != signal['regime']}
    return answer


def _fit(train: list[dict]) -> dict:
    if len(train) < 500:
        raise ValueError('Insufficient training observations')
    fitted = {}
    for horizon in HORIZONS:
        for target in TARGETS:
            labels = [int(row['labels'][str(horizon)][target]) for row in train]
            prior = sum(labels) / len(labels)
            for model in MODELS:
                groups = defaultdict(lambda: [0, 0])
                if model != 'regime_persistence' or target != 'transition':
                    for row, label in zip(train, labels):
                        entry = groups[row['bins'][model]]
                        entry[0] += label
                        entry[1] += 1
                fitted[f'{horizon}:{target}:{model}'] = {
                    'prior': prior, 'groups': dict(groups), 'training_count': len(train)}
    return fitted


def _predict(fitted: dict, row: dict, horizon: int, target: str, model: str) -> float:
    if model == 'regime_persistence' and target == 'transition':
        return 0.0
    spec = fitted[f'{horizon}:{target}:{model}']
    positives, count = spec['groups'].get(row['bins'][model], [0, 0])
    value = (positives + SMOOTHING * spec['prior']) / (count + SMOOTHING)
    if not 0 <= value <= 1 or not math.isfinite(value):
        raise ValueError('Invalid forecast probability')
    return value


def _average_precision(labels: list[bool], probabilities: list[float]) -> float | None:
    positives = sum(labels)
    if not positives:
        return None
    ranked = sorted(zip(probabilities, labels), reverse=True)
    tp = seen = 0
    score = 0.0
    for probability in sorted(set(probabilities), reverse=True):
        group = [label for value, label in ranked[seen:] if value == probability]
        tp += sum(group)
        seen += len(group)
        score += sum(group) / positives * tp / seen
    return score


def _score(labels: list[bool], probabilities: list[float], threshold: float) -> dict:
    if (not labels or len(labels) != len(probabilities)
            or not math.isfinite(threshold) or not 0 <= threshold <= 1
            or any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities)):
        raise ValueError('Invalid evaluation rows')
    decision = [value >= threshold for value in probabilities]
    tp = sum(a and p for a, p in zip(labels, decision))
    fp = sum(not a and p for a, p in zip(labels, decision))
    fn = sum(a and not p for a, p in zip(labels, decision))
    tn = len(labels) - tp - fp - fn
    calibration = []
    for index in range(5):
        selected = [(a, p) for a, p in zip(labels, probabilities)
                    if min(4, int(p * 5)) == index]
        if selected:
            calibration.append({'bin': index, 'count': len(selected),
                'predicted_mean': sum(p for _, p in selected) / len(selected),
                'observed_frequency': sum(a for a, _ in selected) / len(selected)})
    ece = sum(item['count'] / len(labels) *
              abs(item['predicted_mean'] - item['observed_frequency']) for item in calibration)
    return {'n': len(labels), 'positive_days': sum(labels), 'prevalence': sum(labels) / len(labels),
            'threshold_frozen': threshold, 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'accuracy': (tp + tn) / len(labels),
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'pr_auc_average_precision': _average_precision(labels, probabilities),
            'brier': sum((float(a) - p) ** 2 for a, p in zip(labels, probabilities)) / len(labels),
            'calibration_ece_five_bins': ece, 'calibration_bins': calibration,
            'overlap_caution': 'horizon labels overlap; daily rows are not independent events'}


def _evaluate(rows: list[dict], fitted: dict) -> dict:
    output = {}
    for horizon in HORIZONS:
        output[str(horizon)] = {}
        for target in TARGETS:
            labels = [row['labels'][str(horizon)][target] for row in rows]
            output[str(horizon)][target] = {
                model: _score(labels, [_predict(fitted, row, horizon, target, model)
                                       for row in rows], THRESHOLD[target])
                for model in MODELS}
    return output


def _case(rows: list[dict], start: str, end: str) -> dict:
    selected = [row for row in rows if start <= row['date'] <= end]
    return {'first': selected[0]['date'] if selected else None,
            'last': selected[-1]['date'] if selected else None,
            'sessions': len(selected),
            'regime_counts': dict(Counter(row['regime'] for row in selected)),
            'crash20_positive_days': sum(row['labels']['20']['crash'] for row in selected)}


def study() -> dict:
    gate = pit_eligibility()
    if gate['eligible_indicator_ids']:
        raise ValueError('PIT state changed; review research plan before execution')
    rows, provenance = load_indices('1996-01-01', skip_invalid_pre2010=True)
    signals = {i: _signal(rows, i) for i in range(60, len(rows))}
    regime_by_index = {i: item['regime'] for i, item in signals.items()}
    observations = []
    for i in range(60, len(rows) - max(HORIZONS)):
        signal = signals[i]
        observations.append({**signal, 'labels': _labels(rows, i, signal, regime_by_index)})
    train = [row for row in observations if row['date'] <= TRAIN_END]
    validation = [row for row in observations if VALIDATION_START <= row['date'] <= VALIDATION_END]
    post = [row for row in observations if row['date'] >= FINAL_START]
    if len(train) < 500 or len(validation) < 200:
        raise ValueError('Chronological samples insufficient')
    train = train[:-EMBARGO]
    validation = validation[:-EMBARGO]
    fitted = _fit(train)
    metrics = _evaluate(validation, fitted)
    comparison = {}
    for horizon in HORIZONS:
        comparison[str(horizon)] = {}
        for target in TARGETS:
            scores = metrics[str(horizon)][target]
            baseline_name = min((name for name in MODELS if name != 'six_regime'),
                                key=lambda name: scores[name]['brier'])
            comparison[str(horizon)][target] = {
                'six_regime_brier': scores['six_regime']['brier'],
                'best_baseline': baseline_name,
                'best_baseline_brier': scores[baseline_name]['brier'],
                'six_minus_baseline_brier':
                    scores['six_regime']['brier'] - scores[baseline_name]['brier']}
    asof = signals[len(rows) - 1]
    exploratory = {str(h): {target: _predict(fitted, asof, h, target, 'six_regime')
                             for target in TARGETS} for h in HORIZONS}
    latest = date.fromisoformat(asof['date'])
    age_days = (date.today() - latest).days
    if age_days < 0:
        raise ValueError('Index snapshot date is in the future')
    stale = age_days > 5
    retrievals = json.loads((SOURCE / 'naver_source_manifest.json').read_text())
    report = {'기준 거래일': asof['date'],
              '데이터 기준 시각': '원본 발표 시각 미검증; 스냅샷 수집 ' +
                  max(item['retrieved_at_utc'] for item in retrievals),
              '현재 시장 국면': None if stale else asof['regime'],
              '최근 관측 국면': asof['regime'], '국면 판단 신뢰도': None,
              '향후 5일 상승 확률': None, '향후 10일 상승 확률': None,
              '향후 20일 상승 확률': None, '급락 위험': None, '회복 가능성': None,
              '국면 전환 가능성': None,
              '탐색 추정치_공식확률아님': exploratory,
              '주요 판단 근거': asof['feature'],
              '데이터 누락 및 PIT 상태': 'PIT_VERIFIED 0/190; source vintage/publication unverified',
              '모델 검증 상태': 'EXPLORATORY_VALIDATION_ONLY_FINAL_HOLDOUT_CONTAMINATED',
              '자료 경과일': age_days, '자료 지연': stale}
    return {'schema_version': 1, 'status': 'EXPLORATORY_MARKET_INTELLIGENCE',
            'version': VERSION, 'official_prediction_claim': False,
            'model_runtime': 'DETERMINISTIC_NON_AI', 'event_definitions': EVENTS,
            'horizons': list(HORIZONS), 'smoothing': SMOOTHING, 'thresholds': THRESHOLD,
            'features': ['KOSPI daily OHLCV', 'KOSDAQ daily OHLCV'],
            'excluded_features': ['market breadth', 'foreign cash flows', 'futures positioning',
                                  'sector relative strength', 'FX', 'rates', 'US market'],
            'source_provenance': provenance, 'pit': gate,
            'common_history': {'first': rows[0]['date'], 'last': rows[-1]['date'],
                               'sessions': len(rows), 'missing_ratio_vs_union':
                               1 - len(rows) / (sum(item['row_count'] for item in provenance.values()) - len(rows))},
            'split': {'train_first': train[0]['date'], 'train_last': train[-1]['date'],
                      'train_days': len(train), 'validation_first': validation[0]['date'],
                      'validation_last': validation[-1]['date'], 'validation_days': len(validation),
                      'embargo_sessions': EMBARGO, 'post2021_descriptive_days': len(post),
                      'final_holdout': 'CONTAMINATED_NOT_INDEPENDENT'},
            'validation_exploratory': metrics,
            'baseline_comparison_exploratory': comparison,
            'failure_diagnosis': {
                'category': 'NO_INCREMENTAL_DIRECTION_OR_CRASH_BRIER_GAIN'
                    if all(comparison[str(h)][target]['six_minus_baseline_brier'] >= 0
                           for h in HORIZONS for target in ('up', 'crash'))
                    else 'MIXED_EXPLORATORY_EVIDENCE',
                'causality_claimed': False,
                'evidence': {str(h): {target: comparison[str(h)][target]
                                      for target in ('up', 'crash')} for h in HORIZONS},
                'next_hypothesis': 'PIT-verified breadth or flow may add directional information',
                'experiment_status': 'BLOCKED_PIT_AND_INDEPENDENT_HOLDOUT'},
            'historical_cases_descriptive': {
                '2008_financial_crisis': _case(observations, '2008-01-01', '2009-03-31'),
                '2020_covid': _case(observations, '2020-01-01', '2020-06-30'),
                '2022_bear': _case(observations, '2022-01-01', '2022-12-31')},
            'timeline': [{'date': item['date'], 'regime': item['regime']}
                         for item in signals.values()],
            'daily_report': report,
            'regime_truth_status': 'NO_INDEPENDENT_GROUND_TRUTH',
            'transition_detection_delay': None,
            'research_decision': 'MORE_PIT_EVIDENCE_AND_INDEPENDENT_DATA_REQUIRED'}


def verify(result: dict) -> None:
    if (result.get('status') != 'EXPLORATORY_MARKET_INTELLIGENCE'
            or result.get('version') != VERSION
            or result.get('official_prediction_claim') is not False
            or result.get('model_runtime') != 'DETERMINISTIC_NON_AI'
            or result.get('pit', {}).get('eligible_indicator_ids') != []
            or result.get('split', {}).get('final_holdout') != 'CONTAMINATED_NOT_INDEPENDENT'
            or 'final_holdout_metrics' in result
            or result.get('research_decision') != 'MORE_PIT_EVIDENCE_AND_INDEPENDENT_DATA_REQUIRED'
            or len(result.get('timeline', [])) < 500
            or result['timeline'][-1]['date'] != result.get('daily_report', {}).get('기준 거래일')
            or any(result.get('daily_report', {}).get(f'향후 {h}일 상승 확률') is not None
                   for h in HORIZONS)
            or result.get('daily_report', {}).get('국면 판단 신뢰도') is not None
            or set(result.get('validation_exploratory', {})) != {str(h) for h in HORIZONS}
            or any(set(result['validation_exploratory'][str(h)]) != set(TARGETS)
                   for h in HORIZONS)):
        raise ValueError('Agent 4.0 official claim gate failed')
