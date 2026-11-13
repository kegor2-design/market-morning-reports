"""Verify a local ALFRED first vintage and a dated official H.15 correction."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from html import unescape
from pathlib import Path

from .evidence_collector import SOURCE_ROOT

H15_NOTICES_URI = 'https://www.federalreserve.gov/feeds/h15.html'


def first_vintage(series: str, day: str, value: str) -> dict:
    name = {'UST_2Y': 'DGS2', 'UST_10Y': 'DGS10'}.get(series)
    if name is None:
        raise ValueError('First-vintage adapter unavailable for series')
    year = day[:4]
    raw = SOURCE_ROOT / name / f'{year}.json'
    manifest = SOURCE_ROOT / name / f'{year}.manifest.json'
    if raw.is_symlink() or manifest.is_symlink():
        raise ValueError('Symlinked first-vintage evidence')
    payload = raw.read_bytes()
    details = json.loads(manifest.read_text())
    digest = hashlib.sha256(payload).hexdigest()
    if (details['sha256'] != digest or details['series'] != name or
            details['year'] != int(year)):
        raise ValueError('First-vintage manifest mismatch')
    observations = [row for row in json.loads(payload)['observations']
                    if row['date'] == day]
    if len(observations) != 1 or Decimal(observations[0]['value']) != Decimal(value):
        raise ValueError('Claimed first-vintage value not in hashed source')
    return {'source_id': 'FRED_ALFRED', 'source_uri':
            f'https://api.stlouisfed.org/fred/series/observations?series_id={name}',
            'observation_date': day, 'value': observations[0]['value'],
            'vintage_date': observations[0]['realtime_start'],
            'content_sha256': digest, 'manifest_sha256':
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'published_at': None, 'first_accessible_at': None,
            'validation_status': 'HASH_VERIFIED_DATE_ONLY_PIT_UNVERIFIED'}


def correction(payload: bytes, series: str, day: str, before: str, after: str) -> dict | None:
    tenor = {'UST_2Y': '2', 'UST_10Y': '10'}.get(series)
    if tenor is None:
        return None
    plain = unescape(re.sub(r'<[^>]*>', ' ', payload.decode('utf-8', errors='strict')))
    plain = re.sub(r'\s+', ' ', plain)
    target = datetime.strptime(day, '%Y-%m-%d').strftime('%B %-d, %Y')
    title = f'Correction to the {tenor}-year Treasury constant maturity rate for {target}'
    index = plain.find(title)
    if index < 0:
        return None
    match = re.search(r'should have been ([0-9.]+) \(rather than ([0-9.]+)\)',
                      plain[index:index + 700])
    if not match or Decimal(match.group(1)) != Decimal(after) or \
            Decimal(match.group(2)) != Decimal(before):
        return None
    return {'source_id': 'FED_H15', 'source_uri': H15_NOTICES_URI,
            'observation_date': day, 'previous_value': before,
            'corrected_value': after, 'content_sha256': hashlib.sha256(payload).hexdigest(),
            'published_at': None, 'first_accessible_at': None,
            'reason': 'Official H.15 correction notice confirms earlier and corrected values',
            'validation_status': 'REVISION_CONFIRMED_PIT_UNVERIFIED'}
