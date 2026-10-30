#!/usr/bin/env python3
"""Read-only, bounded source/export comparison for Regime190 prices."""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from psycopg2.extras import execute_values

from derive_db_daily import connection

DEFAULT_MANIFEST = Path.home() / 'MyDream2000/research/regime190/db_daily_price_derived_manifest.jsonl'
TARGET_END = '2026-10-27'
CUTOFF = '2026-09-15'


def atomic_text(path: Path, value: str) -> None:
    fd, name = tempfile.mkstemp(prefix='.source-lineage-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_manifest(path: Path) -> dict:
    result = {}
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row['symbol'] in result:
                raise ValueError('Duplicate manifest symbol')
            result[row['symbol']] = row
    return result


def reconcile(manifest_path: Path) -> tuple[dict, list[dict]]:
    exported = load_manifest(manifest_path)
    with closing(connection()) as db:
        with db.cursor() as cur:
            cur.execute("SET statement_timeout='60s'")
            cur.execute("SELECT symbol, min(market_date), max(market_date), count(*) "
                        "FROM public.domestic_daily_price WHERE market_date <= %s "
                        "GROUP BY symbol", (TARGET_END,))
            source = {symbol: {'first_date': first.isoformat(), 'last_date': last.isoformat(),
                               'rows': count} for symbol, first, last, count in cur.fetchall()}
            # Use the primary key for each aggregated last date. DISTINCT ON
            # across the full table exceeded the bounded statement timeout.
            latest_pairs = [(symbol, item['last_date']) for symbol, item in source.items()]
            latest_rows = execute_values(
                cur,
                "SELECT p.symbol, p.market_date, p.source_name, p.collected_at, "
                "p.available_at, p.market FROM public.domestic_daily_price p "
                "JOIN (VALUES %s) AS latest(symbol, market_date) "
                "ON p.symbol=latest.symbol AND p.market_date=latest.market_date",
                latest_pairs, template='(%s,%s::date)', page_size=500, fetch=True)
            last_metadata = {symbol: {'last_source_name': name,
                                       'last_collected_at': collected.isoformat() if collected else None,
                                       'last_available_at': available.isoformat() if available else None,
                                       'last_market': market}
                             for symbol, _, name, collected, available, market in latest_rows}
    rows = []
    for symbol in sorted(set(exported) | set(source)):
        out, raw = exported.get(symbol), source.get(symbol)
        row = {'symbol': symbol, 'export_first_date': out['first_date'] if out else '',
               'export_last_date': out['last_date'] if out else '',
               'export_rows': out['rows'] if out else '',
               'source_first_date': raw['first_date'] if raw else '',
               'source_last_date': raw['last_date'] if raw else '',
               'source_rows': raw['rows'] if raw else '',
               'last_source_name': last_metadata.get(symbol, {}).get('last_source_name') or '',
               'last_collected_at': last_metadata.get(symbol, {}).get('last_collected_at') or '',
               'last_available_at': last_metadata.get(symbol, {}).get('last_available_at') or '',
               'last_market': last_metadata.get(symbol, {}).get('last_market') or ''}
        if out is None:
            row['classification'] = 'SOURCE_ONLY'
        elif raw is None:
            row['classification'] = 'EXPORT_ONLY'
        elif (row['export_first_date'], row['export_last_date'], row['export_rows']) != (
                row['source_first_date'], row['source_last_date'], row['source_rows']):
            row['classification'] = 'SOURCE_EXPORT_MISMATCH'
        else:
            row['classification'] = 'SOURCE_EXPORT_MATCH'
        rows.append(row)
    counts = collections.Counter(row['classification'] for row in rows)
    cutoff = [row for row in rows if row['export_last_date'] == CUTOFF]
    cutoff_source_later = [row for row in cutoff if row['source_last_date'] > CUTOFF]
    report = {'schema_version': 1, 'collected_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_identity': 'public.domestic_daily_price via existing read-only role',
              'export_identity': str(manifest_path), 'target_end': TARGET_END,
              'source_symbols': len(source), 'export_symbols': len(exported),
              'source_rows': sum(item['rows'] for item in source.values()),
              'export_rows': sum(item['rows'] for item in exported.values()),
              'classification_counts': dict(sorted(counts.items())),
              'cutoff_export_symbols': len(cutoff),
              'cutoff_source_later_symbols': len(cutoff_source_later),
              'cutoff_source_same_symbols': sum(row['source_last_date'] == CUTOFF for row in cutoff),
              'cutoff_source_missing_symbols': sum(not row['source_last_date'] for row in cutoff),
              'causal_scope': 'Source/export boundary only; ingestion/provider/delisting causes need separate evidence',
              'pit_status': 'UNVERIFIED'}
    return report, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--per-symbol', type=Path, required=True)
    args = parser.parse_args()
    report, rows = reconcile(args.manifest)
    import io
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(args.per_symbol, output.getvalue())
    atomic_text(args.summary, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
