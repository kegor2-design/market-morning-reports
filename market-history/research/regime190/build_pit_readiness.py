#!/usr/bin/env python3
"""Conservative per-indicator PIT matrix from existing audited metadata."""
from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = Path.home() / 'MyDream2000/research/regime190/checkpoint.sqlite'


def read_index(path: Path) -> dict[int, dict]:
    with path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    result = {}
    for row in rows:
        key = int(row['indicator_id'])
        if key in result:
            raise ValueError(f'Duplicate indicator {key} in {path.name}')
        result[key] = row
    return result


def classify(indicator: dict, pit: dict, pit_eligible: int) -> str:
    if pit_eligible != 0 and pit.get('pit_status') != 'PIT_VERIFIED':
        raise ValueError('Checkpoint PIT flag conflicts with published PIT audit')
    status = indicator['availability_status']
    if pit_eligible and status != '일부 확보':
        raise ValueError('PIT eligible flag conflicts with unavailable source or calculation')
    if status == '미확보(시도 실패)':
        return 'SOURCE_MISSING'
    if status == '원천 확보·계산 미완료':
        return 'CALCULATION_PENDING'
    if status != '일부 확보':
        raise ValueError('Unknown availability status: ' + status)
    publication = pit.get('published_at', '')
    availability = pit.get('available_at', '')
    vintage = pit.get('vintage', '')
    absent = {'', 'absent', 'unverified', 'no_data', 'current snapshot only'}
    traceable = bool(pit.get('evidence_ref'))
    if (pit_eligible == 1 and pit.get('pit_status') == 'PIT_VERIFIED' and traceable and
            publication not in absent and availability not in absent and vintage not in absent):
        return 'PIT_VERIFIED'
    if traceable and any(value not in absent for value in (publication, availability, vintage)):
        return 'PIT_PARTIAL'
    return 'PIT_BLOCKED'


def build(indicator_path: Path, pit_path: Path, db_path: Path) -> tuple[list[dict], dict]:
    indicators = read_index(indicator_path)
    pit_rows = read_index(pit_path)
    db = sqlite3.connect('file:' + str(db_path) + '?mode=ro', uri=True, timeout=2)
    try:
        db.execute('PRAGMA query_only=ON')
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        flags = dict(db.execute('SELECT indicator_id,pit_eligible FROM tasks'))
    finally:
        db.close()
    if integrity != 'ok' or len(indicators) != 190 or set(indicators) != set(pit_rows) != set(flags):
        raise ValueError('190-indicator source reconciliation or SQLite integrity failed')
    result = []
    for indicator_id in sorted(indicators):
        item, pit = indicators[indicator_id], pit_rows[indicator_id]
        status = classify(item, pit, flags[indicator_id])
        result.append({'indicator_id': indicator_id, 'name': item['name'], 'provider': item['provider'],
                       'source': pit['source'], 'raw_status': item['raw_acquisition'],
                       'calculation_status': item['calculation'],
                       'observation_timestamp': pit['observation_date'],
                       'publication_timestamp': pit['published_at'],
                       'actual_availability': pit['available_at'],
                       'revision_history': pit['revision_history'],
                       'historical_vintage': pit['vintage'],
                       'source_history_status': item['source_history_status'],
                       'data_completeness': item['availability_status'],
                       'last_collection_attempt_utc': item['last_collection_attempt_utc'],
                       'pit_classification': status, 'backtest_eligible': 'NO',
                       'evidence_refs': f'{indicator_path.name}:{indicator_id};{pit_path.name}:{indicator_id};checkpoint.sqlite:tasks:{indicator_id}',
                       'blocking_reason': item['error_or_incomplete_reason'],
                       'next_action': item['next_action']})
    counts = collections.Counter(row['pit_classification'] for row in result)
    for key in ('PIT_VERIFIED', 'PIT_PARTIAL', 'PIT_BLOCKED', 'SOURCE_MISSING', 'CALCULATION_PENDING'):
        counts.setdefault(key, 0)
    summary = {'schema_version': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
               'indicator_total': len(result), 'unique_ids': len(indicators),
               'sqlite_integrity': integrity, 'classification_counts': dict(counts),
               'pit_eligible_db_flags': sum(flags.values()), 'backtest_eligible': 0,
               'classification_policy': 'No PIT_VERIFIED without release, availability, vintage and independent checkpoint evidence',
               'source_files': [indicator_path.name, pit_path.name, 'private checkpoint.sqlite']}
    return result, summary


def atomic_write(path: Path, value: str) -> None:
    fd, name = tempfile.mkstemp(prefix='.pit-readiness-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--indicators', type=Path, default=ROOT / 'indicator_audit_20261031.csv')
    parser.add_argument('--pit', type=Path, default=ROOT / 'pit_audit.csv')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    args = parser.parse_args()
    rows, summary = build(args.indicators, args.pit, args.db)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(args.matrix, buffer.getvalue())
    atomic_write(args.summary, json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary['classification_counts'], ensure_ascii=False))


if __name__ == '__main__':
    main()
