"""Real index snapshot research, explicitly excluded from PIT-approved performance.

All rules are frozen hypotheses. No feature uses data after its signal date.
Official Regime190 performance must pass the independent PIT gate first.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from .historical_evaluation import walk_forward_indices

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'daily-index-validation-20261021'
STATES = ('RISK_ON_TREND', 'RISK_ON_SELECTIVE', 'CHOPPY', 'RISK_OFF_WEAK',
          'RISK_OFF_PANIC', 'RECOVERY_EARLY')
PARAMETERS = {'version': 'exploratory_v1_frozen_20261101', 'warmup_sessions': 60,
              'panic_drawdown': -0.15, 'panic_volatility': 0.025,
              'weak_momentum20': -0.04, 'weak_drawdown': -0.10,
              'recovery_drawdown': -0.08, 'recovery_momentum5': 0.03,
              'trend_momentum20': 0.04, 'crash_threshold': -0.10,
              'recovery_threshold': 0.08, 'false_rebound_threshold': -0.05,
              'transaction_fee_one_way': 0.001, 'slippage_one_way': 0.0005,
              'transaction_cost_one_way': 0.0015}
EXPOSURE = {'RISK_ON_TREND': 1.0, 'RISK_ON_SELECTIVE': 0.75, 'CHOPPY': 0.5,
            'RISK_OFF_WEAK': 0.25, 'RISK_OFF_PANIC': 0.0, 'RECOVERY_EARLY': 0.5}


def validate_parameters(value: dict) -> None:
    if (value.get('warmup_sessions', 0) < 60
            or not -1 < value.get('crash_threshold', 0) < 0
            or not -1 < value.get('panic_drawdown', 0) < 0
            or not 0 < value.get('recovery_threshold', 0) < 1
            or not 0 <= value.get('transaction_fee_one_way', -1) < .05
            or not 0 <= value.get('slippage_one_way', -1) < .05
            or abs(value['transaction_fee_one_way'] + value['slippage_one_way'] -
                   value.get('transaction_cost_one_way', -1)) > 1e-12
            or set(EXPOSURE) != set(STATES)
            or any(not 0 <= exposure <= 1 for exposure in EXPOSURE.values())):
        raise ValueError('Invalid exploratory parameter bounds')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_indices() -> tuple[list[dict], dict]:
    manifest = json.loads((SOURCE / 'naver_source_manifest.json').read_text())
    series = {}
    provenance = {}
    for entry in manifest:
        path = SOURCE / entry['csv_file']
        if _sha(path) != entry['csv_sha256']:
            raise ValueError('Index snapshot checksum changed')
        with path.open(newline='', encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != entry['rows'] or not rows:
            raise ValueError('Index row count changed')
        dates = [row['date'] for row in rows]
        if dates != sorted(set(dates)):
            raise ValueError('Index dates are duplicated or unordered')
        parsed = {}
        for row in rows:
            if row['date'] < '2010-01-01':
                continue
            values = {key: float(row[key]) for key in ('open', 'high', 'low', 'close', 'volume')}
            o, h, l, c, v = (values[key] for key in ('open', 'high', 'low', 'close', 'volume'))
            if (not all(math.isfinite(x) for x in values.values()) or min(o, h, l, c) <= 0
                    or v < 0 or h < max(o, c) - .011 or l > min(o, c) + .011):
                raise ValueError('Invalid index OHLCV row')
            parsed[row['date']] = values
        series[entry['index']] = parsed
        provenance[entry['index']] = {'source': 'Naver Finance chart snapshot',
            'first_date': dates[0], 'last_date': dates[-1], 'row_count': len(rows),
            'sha256': entry['csv_sha256'], 'frequency': 'daily',
            'publication_timestamp_status': 'UNVERIFIED', 'pit_status': 'PIT_UNVERIFIED'}
    dates = sorted(set(series['KOSPI']) & set(series['KOSDAQ']))
    if len(dates) < 500:
        raise ValueError('Insufficient common index sessions')
    return [{'date': day, 'kospi': series['KOSPI'][day], 'kosdaq': series['KOSDAQ'][day]}
            for day in dates], provenance


def pit_eligibility() -> dict:
    """Require independent published decision and current private DB flag."""
    import sqlite3
    matrix = HERE / 'pit_readiness_matrix_20261031.csv'
    with matrix.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    ids = [int(row['indicator_id']) for row in rows]
    if len(ids) != 190 or sorted(ids) != list(range(1, 191)):
        raise ValueError('Incomplete 190-indicator registry')
    path = Path.home() / 'MyDream2000/research/regime190/checkpoint.sqlite'
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=3) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA busy_timeout=3000')
        flags = dict(db.execute('SELECT indicator_id,pit_eligible FROM tasks'))
    eligible = [int(row['indicator_id']) for row in rows
                if row['pit_classification'] == 'PIT_VERIFIED'
                and row['backtest_eligible'] == 'YES' and flags.get(int(row['indicator_id'])) == 1]
    return {'indicator_total': len(rows), 'pit_verified': sum(row['pit_classification'] == 'PIT_VERIFIED'
                                                            for row in rows),
            'db_pit_flags': sum(flags.values()), 'eligible_indicator_ids': eligible,
            'matrix_sha256': _sha(matrix), 'status': 'ELIGIBLE' if eligible else 'BLOCKED_PIT'}


def _features(rows: list[dict], i: int) -> dict:
    close = [r['kospi']['close'] for r in rows[i - 60:i + 1]]
    secondary = [r['kosdaq']['close'] for r in rows[i - 20:i + 1]]
    returns = [close[j] / close[j - 1] - 1 for j in range(41, 61)]
    momentum20 = close[-1] / close[-21] - 1
    momentum5 = close[-1] / close[-6] - 1
    drawdown = close[-1] / max(close) - 1
    volatility = statistics.pstdev(returns)
    relative20 = secondary[-1] / secondary[0] - close[-1] / close[-21]
    return {'momentum20': momentum20, 'momentum5': momentum5,
            'drawdown60': drawdown, 'volatility20': volatility,
            'relative_kosdaq20': relative20,
            'above_sma20': close[-1] > sum(close[-20:]) / 20}


def classify(feature: dict) -> tuple[str, float]:
    p = PARAMETERS
    if feature['drawdown60'] <= p['panic_drawdown'] and feature['volatility20'] >= p['panic_volatility']:
        state = 'RISK_OFF_PANIC'
    elif (feature['drawdown60'] <= p['recovery_drawdown']
          and feature['momentum5'] >= p['recovery_momentum5']):
        state = 'RECOVERY_EARLY'
    elif feature['momentum20'] <= p['weak_momentum20'] or feature['drawdown60'] <= p['weak_drawdown']:
        state = 'RISK_OFF_WEAK'
    elif feature['momentum20'] >= p['trend_momentum20'] and feature['relative_kosdaq20'] >= -0.03:
        state = 'RISK_ON_TREND'
    elif feature['momentum20'] > 0 and feature['relative_kosdaq20'] > 0:
        state = 'RISK_ON_SELECTIVE'
    else:
        state = 'CHOPPY'
    # Heuristic strength, not a probability or calibrated confidence.
    strength = round(min(1.0, 0.5 + abs(feature['momentum20']) * 2), 3)
    return state, strength


def _metrics(returns: list[float], exposure: list[float], turnover: float) -> dict:
    if not returns:
        return {'sample_count': 0}
    wealth = peak = 1.0
    drawdown = 0.0
    underwater = longest_underwater = 0
    for value in returns:
        wealth *= 1 + value
        peak = max(peak, wealth)
        drawdown = min(drawdown, wealth / peak - 1)
        underwater = underwater + 1 if wealth < peak else 0
        longest_underwater = max(longest_underwater, underwater)
    ann = wealth ** (252 / len(returns)) - 1
    vol = statistics.pstdev(returns) * math.sqrt(252)
    downside = math.sqrt(sum(min(0, x) ** 2 for x in returns) / len(returns)) * math.sqrt(252)
    return {'sample_count': len(returns), 'cumulative_return': wealth - 1,
            'annualized_return': ann, 'annualized_volatility': vol,
            'sharpe_zero_rf': statistics.mean(returns) * 252 / vol if vol else None,
            'sortino_zero_rf': statistics.mean(returns) * 252 / downside if downside else None,
            'maximum_drawdown': drawdown, 'calmar': ann / abs(drawdown) if drawdown else None,
            'turnover_one_way': turnover, 'transaction_cost_fraction_of_capital':
                turnover * PARAMETERS['transaction_cost_one_way'],
            'mean_exposure': statistics.mean(exposure),
            'time_out_of_market_fraction': sum(x == 0 for x in exposure) / len(exposure),
            'worst_session_return': min(returns),
            'longest_underwater_sessions': longest_underwater}


def _warning(rows: list[dict], horizon: int) -> dict:
    tp = fp = fn = tn = 0
    for row in rows:
        actual = row['crash_outcomes'][str(horizon)]
        predicted = row['crash_warning']
        if predicted and actual: tp += 1
        elif predicted: fp += 1
        elif actual: fn += 1
        else: tn += 1
    return {'horizon_sessions': horizon, 'tp_days': tp, 'fp_days': fp,
            'fn_days': fn, 'tn_days': tn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'false_positive_rate': fp / (fp + tn) if fp + tn else None,
            'warning_day_frequency': (tp + fp) / len(rows) if rows else None,
            'overlap_caution': 'daily windows overlap; counts are not independent events'}


def _episode_detection(rows: list[dict]) -> dict:
    labels = [row['crash_outcomes']['20'] for row in rows]
    starts = [i for i, label in enumerate(labels) if label and (i == 0 or not labels[i - 1])]
    detected = 0
    lead = []
    for start in starts:
        warnings = [i for i in range(max(0, start - 20), start + 1)
                    if rows[i]['crash_warning']]
        if warnings:
            detected += 1
            lead.append(max(0, start - warnings[0]))
    stable = sum(a['crash_warning'] and b['crash_warning']
                 for a, b in zip(rows, rows[1:]))
    warning_days = sum(row['crash_warning'] for row in rows)
    return {'overlapping_label_clusters': len(starts), 'detected_clusters': detected,
            'missed_clusters': len(starts) - detected,
            'cluster_detection_rate': detected / len(starts) if starts else None,
            'first_warning_lead_sessions_proxy_mean': statistics.mean(lead) if lead else None,
            'first_warning_lead_sessions_proxy_median': statistics.median(lead) if lead else None,
            'warning_consecutive_day_fraction': stable / warning_days if warning_days else None,
            'caution': 'only warnings on or before the forecast-label cluster start count; cluster starts are not verified crash onsets'}


def execute_exploratory() -> dict:
    validate_parameters(PARAMETERS)
    eligibility = pit_eligibility()
    if eligibility['eligible_indicator_ids']:
        raise ValueError('Exploratory adapter cannot execute with approved features; review official plan')
    rows, provenance = load_indices()
    timeline = []
    returns = {name: [] for name in ('buy_hold', 'moving_average_filter', 'volatility_filter',
                                      'six_regime', 'crash_defense', 'recovery_reentry')}
    exposures = {name: [] for name in returns}
    turnover = {name: 0.0 for name in returns}
    previous = {name: 0.0 for name in returns}
    for i in range(PARAMETERS['warmup_sessions'], len(rows) - 21):
        f = _features(rows, i)
        regime, strength = classify(f)
        warning = regime in {'RISK_OFF_WEAK', 'RISK_OFF_PANIC'}
        recovery_signal = regime == 'RECOVERY_EARLY'
        close = rows[i]['kospi']['close']
        future = [rows[j]['kospi']['close'] / close - 1 for j in range(i + 1, i + 21)]
        crash = {str(h): min(future[:h]) <= PARAMETERS['crash_threshold'] for h in (1, 3, 5, 10, 20)}
        recovery_outcome = (f['drawdown60'] <= -0.1 and future[-1] >= PARAMETERS['recovery_threshold'])
        false_rebound = recovery_signal and min(future) <= PARAMETERS['false_rebound_threshold']
        positions = {'buy_hold': 1.0,
                     'moving_average_filter': 1.0 if f['above_sma20'] else 0.0,
                     'volatility_filter': 0.0 if f['volatility20'] >= 0.025 else 1.0,
                     'six_regime': EXPOSURE[regime],
                     'crash_defense': 0.0 if warning else 1.0,
                     'recovery_reentry': 1.0 if regime.startswith('RISK_ON') else
                                          0.5 if recovery_signal else 0.0}
        next_open = rows[i + 1]['kospi']['open']
        following_open = rows[i + 2]['kospi']['open']
        gross = following_open / next_open - 1
        for name, position in positions.items():
            change = abs(position - previous[name])
            returns[name].append(position * gross - PARAMETERS['transaction_cost_one_way'] * change)
            exposures[name].append(position)
            turnover[name] += change
            previous[name] = position
        timeline.append({'date': rows[i]['date'], 'regime': regime, 'confidence_heuristic': strength,
                         'feature_availability': ['kospi_close', 'kosdaq_close'],
                         'signal_after_close_date': rows[i]['date'],
                         'execution_open_date': rows[i + 1]['date'],
                         'settlement_open_date': rows[i + 2]['date'],
                         'crash_warning': warning, 'recovery_signal': recovery_signal,
                         'crash_outcomes': crash, 'recovery_outcome': recovery_outcome,
                         'false_rebound': false_rebound, 'positions': positions})
    segments = {'train': ('2010-01-01', '2017-12-31'),
                'validation': ('2018-01-01', '2021-12-31'),
                'final_holdout': ('2022-01-01', '2026-10-20')}
    strategy_metrics = {name: _metrics(values, exposures[name], turnover[name])
                        for name, values in returns.items()}
    segment_metrics = {label: {name: _metrics([ret for row, ret in zip(timeline, values)
                                                  if start <= row['date'] <= end],
                                              [exp for row, exp in zip(timeline, exposures[name])
                                               if start <= row['date'] <= end],
                                              sum(abs(exposures[name][i] -
                                                      (exposures[name][i - 1] if i else 0))
                                                  for i, row in enumerate(timeline)
                                                  if start <= row['date'] <= end))
                               for name, values in returns.items()}
                       for label, (start, end) in segments.items()}
    counts = dict(Counter(row['regime'] for row in timeline))
    transitions = Counter((a['regime'], b['regime']) for a, b in zip(timeline, timeline[1:])
                          if a['regime'] != b['regime'])
    warnings = {str(h): _warning(timeline, h) for h in (1, 3, 5, 10, 20)}
    recovery_signals = [row for row in timeline if row['recovery_signal']]
    recovery_tp = sum(row['recovery_signal'] and row['recovery_outcome'] for row in timeline)
    recovery_fp = sum(row['recovery_signal'] and not row['recovery_outcome'] for row in timeline)
    recovery_fn = sum(not row['recovery_signal'] and row['recovery_outcome'] for row in timeline)
    dates = [row['date'] for row in timeline]
    folds = walk_forward_indices(dates, train_size=1000, test_size=252, embargo=20)
    return {'schema_version': 1, 'status': 'EXPLORATORY_REAL_DATA_PIT_UNVERIFIED',
            'official_performance_claim': False, 'research_objective_id': 'regime190_first_cycle',
            'strategy_version': PARAMETERS['version'], 'parameters': PARAMETERS,
            'source_provenance': provenance, 'eligibility': eligibility,
            'timeline': timeline, 'timeline_first': timeline[0]['date'],
            'timeline_last': timeline[-1]['date'], 'regime_counts': counts,
            'transition_counts': {a + '->' + b: n for (a, b), n in transitions.items()},
            'walk_forward_diagnostic': {'train_sessions': 1000, 'test_sessions': 252,
                'embargo_sessions': 20,
                'folds': [{'train_start': dates[train.start], 'train_end': dates[train.stop - 1],
                           'test_start': dates[test.start], 'test_end': dates[test.stop - 1]}
                          for train, test in folds],
                'status': 'CHRONOLOGICAL_SPLITS_ONLY_NOT_OOS_VALIDATION'},
            'strategy_metrics_exploratory': strategy_metrics,
            'segment_metrics_exploratory': segment_metrics,
            'crash_warning_exploratory': warnings,
            'crash_episode_proxy_exploratory': _episode_detection(timeline),
            'recovery_exploratory': {'signal_days': len(recovery_signals),
                'future_outcome_days': sum(row['recovery_outcome'] for row in timeline),
                'false_rebound_signal_days': sum(row['false_rebound'] for row in timeline),
                'precision_days': recovery_tp / (recovery_tp + recovery_fp) if recovery_tp + recovery_fp else None,
                'recall_days': recovery_tp / (recovery_tp + recovery_fn) if recovery_tp + recovery_fn else None,
                'false_rebound_signal_fraction': sum(row['false_rebound'] for row in timeline) /
                    len(recovery_signals) if recovery_signals else None},
            'limitations': ['Naver historical publication and revisions unverified',
                            'No Regime190 indicator PIT eligible',
                            'Frozen heuristic thresholds were not independently calibrated',
                            'Overlapping event windows are not independent',
                            'Historical index calendar and fill assumptions unverified',
                            'Final holdout is exploratory, not valid OOS certification']}


def verify_exploratory(result: dict) -> None:
    if (result.get('status') != 'EXPLORATORY_REAL_DATA_PIT_UNVERIFIED'
            or result.get('official_performance_claim') is not False
            or result.get('eligibility', {}).get('eligible_indicator_ids') != []
            or not result.get('timeline') or len(result['timeline']) < 500
            or result['timeline_first'] != result['timeline'][0]['date']
            or result['timeline_last'] != result['timeline'][-1]['date']
            or any(row['execution_open_date'] <= row['signal_after_close_date']
                   for row in result['timeline'])):
        raise ValueError('Exploratory result contract failed')
