"""Reviewed, fixed-host source adapter registry for bounded research collection."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

TREASURY_BASE = ('https://home.treasury.gov/resource-center/data-chart-center/'
                 'interest-rates/daily-treasury-rate-archives/')
NYFED_BASE = 'https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?'


@dataclass(frozen=True)
class SourceAdapter:
    source_id: str
    series: tuple[str, ...]
    media_type: str
    extension: str
    license_terms: str

    def uri(self, series: str, start: str, end: str) -> str:
        if series not in self.series:
            raise ValueError('Series unsupported by source adapter')
        if self.source_id == 'US_TREASURY':
            year = int(start[:4])
            if year != int(end[:4]) or not 2010 <= year <= 2029:
                raise ValueError('Treasury task must cover one supported year')
            decade = year // 10 * 10
            return f'{TREASURY_BASE}par-yield-curve-rates-{decade}-{decade + 9}.csv'
        if self.source_id == 'NYFED_REFERENCE_RATES':
            params = {'startDate': datetime.strptime(start, '%Y-%m-%d').strftime('%m/%d/%Y'),
                      'endDate': datetime.strptime(end, '%Y-%m-%d').strftime('%m/%d/%Y')}
            return NYFED_BASE + urlencode(params)
        raise ValueError('Unreviewed source adapter')

    def parse(self, series: str, payload: bytes, dates: set[str]) -> dict[str, str]:
        if series not in self.series:
            raise ValueError('Series unsupported by source adapter')
        if self.source_id == 'US_TREASURY':
            columns = {'UST_2Y': '2 Yr', 'UST_10Y': '10 Yr'}
            rows = csv.DictReader(io.StringIO(payload.decode('utf-8-sig')))
            if not rows.fieldnames or 'Date' not in rows.fieldnames or columns[series] not in rows.fieldnames:
                raise ValueError('Official CSV columns changed')
            items = []
            for row in rows:
                try:
                    day = datetime.strptime(row['Date'], '%m/%d/%y').date().isoformat()
                except (TypeError, ValueError) as exc:
                    raise ValueError('Invalid source observation date') from exc
                items.append((day, row[columns[series]]))
        elif self.source_id == 'NYFED_REFERENCE_RATES':
            response = json.loads(payload)
            if not isinstance(response, dict) or not isinstance(response.get('refRates'), list):
                raise ValueError('NY Fed response shape changed')
            items = []
            for row in response['refRates']:
                if row.get('type') != 'SOFR' or 'effectiveDate' not in row:
                    raise ValueError('NY Fed rate type or date changed')
                day = datetime.strptime(row['effectiveDate'], '%Y-%m-%d').date().isoformat()
                items.append((day, str(row['percentRate'])))
        else:
            raise ValueError('Unreviewed source adapter')
        values = {}
        for day, raw in items:
            if day not in dates:
                continue
            if day in values:
                raise ValueError('Duplicate source observation')
            if raw is None or str(raw).strip().upper() in {'', 'N/A', 'ND'}:
                continue
            try:
                value = Decimal(str(raw).strip())
            except InvalidOperation as exc:
                raise ValueError('Invalid source observation value') from exc
            if not value.is_finite():
                raise ValueError('Nonfinite source observation')
            values[day] = str(value)
        return values


REGISTRY = {
    'US_TREASURY': SourceAdapter('US_TREASURY', ('UST_2Y', 'UST_10Y'), 'text/csv', '.csv',
                                 'Official public archive; redistribution terms not reviewed'),
    'NYFED_REFERENCE_RATES': SourceAdapter('NYFED_REFERENCE_RATES', ('NYFED_SOFR',),
        'application/json', '.json',
        'NY Fed Terms of Use and reference-rate conditions apply; private research only'),
}


def select(series: str, allowed_sources: list[str]) -> SourceAdapter:
    if len(allowed_sources) != len(set(allowed_sources)):
        raise ValueError('Duplicate source approval')
    if any(source_id not in REGISTRY and source_id not in {'FED_H15', 'FRED_ALFRED'}
           for source_id in allowed_sources):
        raise ValueError('Unknown source approval')
    for source_id in allowed_sources:
        adapter = REGISTRY.get(source_id)
        if adapter and series in adapter.series:
            return adapter
    raise ValueError('No approved reviewed adapter for series')
