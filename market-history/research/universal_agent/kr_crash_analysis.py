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
