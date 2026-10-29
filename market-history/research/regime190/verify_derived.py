#!/usr/bin/env python3
"""Check every private derived artifact against its persisted manifest."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from worker import DEFAULT_STATE


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def verify(state_dir: Path = DEFAULT_STATE) -> dict:
    records = [json.loads(line) for line in
               (state_dir / 'db_daily_price_derived_manifest.jsonl').read_text().splitlines() if line]
    latest = {row['symbol']: row for row in records}
    failures = []
    rows = 0
    for symbol, record in latest.items():
        path = state_dir / 'db_daily_price_derived' / record['file']
        if not path.is_file() or path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            failures.append(symbol)
            continue
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            count = sum(1 for _ in stream) - 1
        if count != record['rows']:
            failures.append(symbol)
        else:
            rows += count
    rates = json.loads((state_dir / 'db_rates_derived_manifest.json').read_text())
    rate_path = state_dir / 'db_rates_derived.csv.gz'
    rate_valid = rate_path.is_file() and rate_path.stat().st_size == rates['bytes'] and digest(rate_path) == rates['sha256']
    if rate_valid:
        with gzip.open(rate_path, 'rt', encoding='utf-8') as stream:
            rate_valid = sum(1 for _ in stream) - 1 == rates['dates']
    result = {'unique_symbols': len(latest), 'verified_source_rows': rows,
              'price_hash_or_row_failures': failures[:20], 'rate_file_valid': rate_valid,
              'rate_dates': rates['dates']}
    if failures or not rate_valid:
        raise RuntimeError(json.dumps(result))
    return result


if __name__ == '__main__':
    print(json.dumps(verify()))
