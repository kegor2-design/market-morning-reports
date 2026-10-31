"""PIT-gated, chronological evaluation primitives; no data acquisition or trading."""
from __future__ import annotations

import math
from datetime import datetime


REQUIRED_EVIDENCE = ('source_id', 'observation_date', 'observed_at', 'published_at',
                     'available_at', 'decision_at', 'vintage_id',
                     'universe_snapshot_id', 'lineage_sha256',
                     'calculation_sha256')


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone required for PIT timestamps')
    return parsed


def pit_gate(features: list[dict]) -> None:
    """Fail closed on unavailable, revised or survivorship-exposed features."""
    if not features:
        raise ValueError('BACKTEST_BLOCKED: no features')
    for item in features:
        if item.get('pit_status') != 'PIT_VERIFIED':
            raise ValueError('BACKTEST_BLOCKED: indicator is not PIT verified')
        if any(not item.get(key) for key in REQUIRED_EVIDENCE):
            raise ValueError('BACKTEST_BLOCKED: incomplete PIT evidence')
        if item.get('historical_membership_verified') is not True or item.get('delisted_included') is not True:
            raise ValueError('BACKTEST_BLOCKED: historical universe incomplete')
        if item.get('revision_asof_verified') is not True:
            raise ValueError('BACKTEST_BLOCKED: vintage unavailable')
        if item.get('security_price') and item.get('corporate_action_verified') is not True:
            raise ValueError('BACKTEST_BLOCKED: corporate actions unverified')
        observed, published, available, decision = (_time(item[key]) for key in
                                                     ('observed_at', 'published_at', 'available_at', 'decision_at'))
        if not observed <= published <= available <= decision:
            raise ValueError('BACKTEST_BLOCKED: look-ahead timestamp')


def walk_forward_indices(dates: list[str], train_size: int, test_size: int,
                         embargo: int) -> list[tuple[range, range]]:
    """Fixed-size chronological folds with a row embargo at the outcome horizon."""
    if len(dates) != len(set(dates)) or dates != sorted(dates):
        raise ValueError('Dates must be unique and chronological')
    if train_size < 2 or test_size < 1 or embargo < 0:
        raise ValueError('Invalid fold sizes')
    folds = []
    start = train_size + embargo
    while start + test_size <= len(dates):
        folds.append((range(start - embargo - train_size, start - embargo),
                      range(start, start + test_size)))
        start += test_size
    return folds


def _precision_recall(rows: list[dict], signal: str, outcome: str) -> dict:
    tp = sum(bool(row[signal]) and bool(row[outcome]) for row in rows)
    fp = sum(bool(row[signal]) and not bool(row[outcome]) for row in rows)
    fn = sum(not bool(row[signal]) and bool(row[outcome]) for row in rows)
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None}


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def evaluate_test_rows(rows: list[dict], features: list[dict]) -> dict:
    """Pure metric calculation for fixtures or already-authorized test data."""
    pit_gate(features)
    dates = [row['date'] for row in rows]
    if not rows or dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError('Test rows must be nonempty and chronological')
    crash = _precision_recall(rows, 'crash_warning', 'crash_event')
    recovery = _precision_recall(rows, 'recovery_signal', 'recovery_event')
    rebound_signals = [row for row in rows if row['recovery_signal']]
    false_rebounds = sum(bool(row['false_rebound']) for row in rebound_signals)
    returns = [float(row['forward_return']) for row in rows if row.get('forward_return') is not None]
    if any(not math.isfinite(value) for value in returns):
        raise ValueError('Non-finite forward return')
    delays = []
    for index, row in enumerate(rows):
        if row['regime_transition']:
            detection = next((j for j in range(index, len(rows)) if rows[j]['transition_detected']), None)
            if detection is not None:
                delays.append(detection - index)
    peak, max_drawdown = 1.0, 0.0
    wealth = 1.0
    for row in rows:
        ret = row.get('strategy_return')
        if ret is None:
            continue
        ret = float(ret)
        if not math.isfinite(ret) or ret <= -1:
            raise ValueError('Invalid strategy return')
        wealth *= 1 + ret
        peak = max(peak, wealth)
        max_drawdown = min(max_drawdown, wealth / peak - 1)
    return {'status': 'EVALUATED', 'sample_count': len(rows), 'crash_warning': crash,
            'recovery_detection': recovery,
            'false_rebound_frequency': false_rebounds / len(rebound_signals) if rebound_signals else None,
            'transition_delay_rows': {'count': len(delays), 'median': _quantile(delays, .5)},
            'forward_return': {'count': len(returns), 'median': _quantile(returns, .5),
                               'p05': _quantile(returns, .05), 'p95': _quantile(returns, .95)},
            'maximum_drawdown': max_drawdown}


def evaluate_project_test_rows(rows: list[dict], features: list[dict],
                               indicator_ids: list[int]) -> dict:
    """Project entrypoint: require current independent Regime190 PIT decisions."""
    from .blocker_resolution import inventory
    approved = {row['indicator_id'] for row in inventory()['records']
                if row['prior_pit_classification'] == 'PIT_VERIFIED'}
    if (not indicator_ids or len(indicator_ids) != len(set(indicator_ids))
            or not set(indicator_ids) <= approved
            or {item.get('indicator_id') for item in features} != set(indicator_ids)):
        raise ValueError('BACKTEST_BLOCKED: indicator absent from approved PIT inventory')
    return evaluate_test_rows(rows, features)
