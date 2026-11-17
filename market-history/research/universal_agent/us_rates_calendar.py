"""Reviewed US rate observation closures; publication clocks remain PIT-unverified.

Dates are transcribed from SIFMA's historical full-close recommendations. The
NY Fed says SOFR is not calculated for full-close days. Treasury coverage is
independently checked against the archived source bytes before any repair.
Unreviewed years fail closed rather than being inferred from weekday rules.
"""
from __future__ import annotations

from datetime import date, timedelta

SIFMA_ARCHIVE = 'https://www.sifma.org/resources/guides-playbooks/us-holiday-archive'
NYFED_POLICY = ('https://www.newyorkfed.org/markets/reference-rates/'
                'additional-information-about-reference-rates')
TREASURY_ARCHIVE = ('https://home.treasury.gov/resource-center/data-chart-center/'
                    'interest-rates/daily-treasury-rate-archives')

# Full closures only. Early-close dates are intentionally excluded.
FULL_CLOSE = {
    2018: frozenset({'2018-01-01', '2018-01-15', '2018-02-19', '2018-03-30',
                     '2018-05-28', '2018-07-04', '2018-09-03', '2018-10-08',
                     '2018-11-12', '2018-11-22', '2018-12-25'}),
    2019: frozenset({'2019-01-01', '2019-01-21', '2019-02-18', '2019-04-19',
                     '2019-05-27', '2019-07-04', '2019-09-02', '2019-10-14',
                     '2019-11-11', '2019-11-28', '2019-12-25'}),
}
SOURCE = {'UST_2Y': 'US_TREASURY', 'UST_10Y': 'US_TREASURY',
          'NYFED_SOFR': 'NYFED_REFERENCE_RATES'}


def expected_observations(start: str, end: str, series: str) -> tuple[list[str], list[str]]:
    """Return reviewed observation dates and in-window official full closures."""
    if series not in SOURCE:
        raise ValueError('Unreviewed calendar series')
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or first.year != last.year or first.year not in FULL_CLOSE or \
            (last - first).days > 31:
        raise ValueError('No reviewed source calendar for period')
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    weekdays = [day.isoformat() for day in days if day.weekday() < 5]
    closures = [day for day in weekdays if day in FULL_CLOSE[first.year]]
    return [day for day in weekdays if day not in FULL_CLOSE[first.year]], closures


def publication_metadata(series: str) -> dict:
    """Describe the schedule without claiming historical first access."""
    if series not in SOURCE:
        raise ValueError('Unreviewed calendar series')
    return {'source_id': SOURCE[series], 'observation_calendar': SIFMA_ARCHIVE,
            'source_policy': NYFED_POLICY if series == 'NYFED_SOFR' else TREASURY_ARCHIVE,
            'publication_lag': 'next_business_day' if series == 'NYFED_SOFR' else
                               'historical_posting_time_unknown',
            'first_accessible_at': None, 'pit_status': 'PIT_UNVERIFIED'}
