"""Exploratory KOSPI crash-window study over the Regime190 hashed snapshot."""
from __future__ import annotations

import statistics

from regime190.exploratory_backtest import load_indices


def analyze() -> dict:
    rows, provenance = load_indices('2010-01-01')
    return crash_windows(rows, provenance)


def crash_windows(rows, provenance):
    rows = [row for row in rows if row['date'] <= '2025-12-31']
    closes = [row['kospi']['close'] for row in rows]
    returns = [closes[i] / closes[i-1] - 1 for i in range(1, len(closes))]
    events = []
    controls = []
    for day_index in range(61, len(rows)):
        current_return = returns[day_index-1]
        # The 20 returns end at the preceding close, before the crash outcome.
        prior_vol = statistics.pstdev(returns[day_index-21:day_index-1])
        if current_return <= -.05:
            events.append({'date': rows[day_index]['date'],
                           'return': current_return, 'prior_20d_volatility': prior_vol})
        else:
            controls.append(prior_vol)
    if not events or not controls:
        raise ValueError('No comparable crash and non-crash windows')
    event_median = statistics.median(item['prior_20d_volatility'] for item in events)
    control_median = statistics.median(controls)
    return {'status': 'EXPLORATORY_ONLY', 'market': 'KR_EQUITY',
            'goal_type': 'CRASH_PRECEDING_VOLATILITY',
            'period': ['2010-01-01', '2025-12-31'],
            'crash_rule': 'KOSPI close-to-close return <= -5%',
            'feature_rule': 'population standard deviation of 20 prior close-to-close returns',
            'event_count': len(events), 'control_count': len(controls),
            'event_prior_volatility_median': event_median,
            'control_prior_volatility_median': control_median,
            'first_three_events': events[:3],
            'source_sha256': {key: value['sha256'] for key, value in provenance.items()},
            'pit_status': 'PIT_UNVERIFIED', 'official_market_claim': False,
            'data_quality_status': 'EXPLORATORY_SNAPSHOT_WITH_UNRESOLVED_PROVIDER_MISMATCHES',
            'next_action': 'ACQUIRE_OFFICIAL_KRX_PRICES_AND_MARKET_CALENDAR'}


def walk_forward():
    """Expanding annual evaluation with at least three calendar years of history."""
    rows, provenance = load_indices('2010-01-01')
    rows = [row for row in rows if row['date'] <= '2025-12-31']
    prices = [row['kospi']['close'] for row in rows]
    returns = [b / a - 1 for a, b in zip(prices, prices[1:])]
    observations = [(int(rows[i]['date'][:4]), statistics.pstdev(returns[i-21:i-1]),
                     int(returns[i-1] <= -.05)) for i in range(61, len(rows))]
    folds = []
    for year in range(2013, 2026):
        train = [(vol, crash) for date, vol, crash in observations if date < year]
        test = [(vol, crash) for date, vol, crash in observations if date == year]
        threshold = statistics.quantiles([v for v, _ in train], n=10, method='inclusive')[-1]
        base = (1 + sum(y for _, y in train)) / (2 + len(train))
        bins = [[y for v, y in train if (v >= threshold) == group] for group in (False, True)]
        probs = [(sum(group) + 2 * base) / (len(group) + 2) for group in bins]
        folds.append({'year': year, 'train_n': len(train), 'test_n': len(test),
                      'events': sum(y for _, y in test),
                      'brier_sum': sum((probs[v >= threshold] - y)**2 for v, y in test),
                      'baseline_sum': sum((base - y)**2 for _, y in test)})
    n = sum(f['test_n'] for f in folds)
    return {'status': 'EXPLORATORY_ONLY', 'official_market_claim': False,
            'pit_status': 'PIT_UNVERIFIED', 'holdout': 'PREVIOUSLY_STUDIED_SNAPSHOT',
            'source_sha256': {k: v['sha256'] for k, v in provenance.items()},
            'folds': folds, 'validation_n': n, 'crash_rule': 'KOSPI close-to-close <= -5%',
            'brier': sum(f['brier_sum'] for f in folds) / n,
            'baseline_brier': sum(f['baseline_sum'] for f in folds) / n}
