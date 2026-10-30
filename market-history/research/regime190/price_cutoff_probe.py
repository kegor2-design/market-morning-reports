#!/usr/bin/env python3
"""Read-only price cohort profile from the private derivation manifest.

This profile does not establish a PIT release time or a causal explanation.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MANIFEST = Path.home() / 'MyDream2000/research/regime190/db_daily_price_derived_manifest.jsonl'


def profile(manifest: Path, data_dir: Path) -> dict:
    dates = collections.Counter()
    seen = set()
    total_rows = missing_market = missing_files = size_mismatch = 0
    sample = {}
    with manifest.open(encoding='utf-8') as stream:
        for raw in stream:
            if not raw.strip():
                continue
            item = json.loads(raw)
            symbol = item['symbol']
            if symbol in seen:
                raise ValueError('Duplicate symbol in manifest: ' + symbol)
            seen.add(symbol)
            dates[item['last_date']] += 1
            total_rows += item['rows']
            missing_market += item['missing_market_rows']
            path = (data_dir / item['file']).resolve()
            if not path.is_relative_to(data_dir.resolve()):
                raise ValueError('Manifest file escapes data directory')
            if not path.is_file():
                missing_files += 1
            elif path.stat().st_size != item['bytes']:
                size_mismatch += 1
            if symbol in {'000020', '000040', '000050'}:
                sample[symbol] = {'last_date': item['last_date'], 'rows': item['rows'],
                                  'source_file_sha256': item['sha256']}
    return {'schema_version': 1, 'source_identity': str(manifest),
            'source_timestamp_utc': datetime.fromtimestamp(manifest.stat().st_mtime, timezone.utc).isoformat(),
            'collected_at_utc': datetime.now(timezone.utc).isoformat(),
            'dataset_version': f'{manifest.stat().st_size}:{manifest.stat().st_mtime_ns}',
            'pit_available_at': None, 'epistemic_status': 'OBSERVED',
            'observed_counts': {'symbols': len(seen), 'rows': total_rows,
                                'missing_market_rows': missing_market,
                                'shared_cutoff_2026_09_15': dates['2026-09-15'],
                                'missing_files': missing_files, 'size_mismatch': size_mismatch},
            'last_date_counts': dict(sorted(dates.items())), 'sample_symbols': sample,
            'competing_causes': [
                {'hypothesis': 'Upstream provider or ingestion batch stopped for a cohort', 'status': 'UNVERIFIED'},
                {'hypothesis': 'Export filter or symbol-universe boundary omitted later rows', 'status': 'UNVERIFIED'},
                {'hypothesis': 'Trading suspensions or delistings explain some individual symbols', 'status': 'UNVERIFIED'}],
            'limitations': ['Manifest reflects a completed derivation, not current operating DB state',
                            'Historical exchange membership and source ingestion logs are not established',
                            'Uniform 16:30 availability is not a verified publication time']}


def source_sample() -> dict:
    # The existing adapter opens the dedicated RO role and sets readonly=True.
    from derive_db_daily import connection
    result = {}
    with closing(connection()) as db:
        with db.cursor() as cursor:
            cursor.execute("SET statement_timeout='20s'")
            cursor.execute("SELECT symbol, min(market_date), max(market_date), count(*), "
                           "max(collected_at), count(*) FILTER (WHERE market IS NULL OR market='') "
                           "FROM public.domestic_daily_price "
                           "WHERE symbol IN ('000020','000040','000050') GROUP BY symbol ORDER BY symbol")
            for symbol, first, last, rows, collected, missing_market in cursor.fetchall():
                result[symbol] = {'first_date': first.isoformat(), 'last_date': last.isoformat(),
                                  'rows': rows, 'max_collected_at': collected.isoformat() if collected else None,
                                  'missing_market_rows': missing_market}
    return {'source_identity': 'public.domestic_daily_price (read-only role)',
            'queried_at_utc': datetime.now(timezone.utc).isoformat(), 'samples': result,
            'scope': 'Three symbols only; cohort cause remains unverified'}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-db-sample', action='store_true')
    args = parser.parse_args()
    report = profile(args.manifest, args.data_dir or args.manifest.parent / 'db_daily_price_derived')
    if args.source_db_sample:
        report['source_db_sample'] = source_sample()
        report['limitations'][0] = 'Three source DB symbols match the manifest; remaining cohort and ingestion cause need review'
    fd, name = tempfile.mkstemp(prefix='.price-cutoff-', dir=args.output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, args.output)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(json.dumps(report['observed_counts']))


if __name__ == '__main__':
    main()
