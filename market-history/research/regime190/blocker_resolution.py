"""Conservative, reproducible classification of the 190 PIT evidence gaps.

This module never changes an existing PIT decision or fetches provider data.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE_DB = Path.home() / 'MyDream2000/research/regime190/checkpoint.sqlite'
UNKNOWN = {'', 'absent', 'unverified', 'no_data', 'current snapshot only', 'unparsed'}
CLASSES = {'MISSING_SOURCE', 'MISSING_TIMESTAMP', 'MISSING_HISTORICAL_UNIVERSE',
           'MISSING_REVISION_HISTORY', 'MISSING_CORPORATE_ACTION', 'CALCULATION_PENDING',
           'LICENSE_RESTRICTED', 'SCHEMA_MISMATCH', 'INSUFFICIENT_EVIDENCE'}


def _rows(name: str) -> dict[int, dict]:
    with (ROOT / name).open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    index = {int(row['indicator_id']): row for row in rows}
    if len(rows) != 190 or set(index) != set(range(1, 191)):
        raise ValueError(f'{name}: expected unique IDs 1..190')
    return index


def _missing(value: str) -> bool:
    return value.strip().lower() in UNKNOWN


def classify(audit: dict, mapping: dict, pit: dict, prior: dict,
             local: dict | None = None) -> dict:
    gaps = []
    evidence = {}
    if prior['pit_classification'] == 'SOURCE_MISSING' or audit['raw_acquisition'] == '미확보':
        gaps.append('MISSING_SOURCE')
    for field in ('published_at', 'available_at'):
        if _missing(pit[field]):
            gaps.append('MISSING_TIMESTAMP')
            evidence[field] = pit[field]
    if mapping['market_scope_status'] != 'VERIFIED':
        gaps.append('MISSING_HISTORICAL_UNIVERSE')
    if _missing(pit['revision_history']) or _missing(pit['vintage']):
        gaps.append('MISSING_REVISION_HISTORY')
    if audit['calculation'] != '검증 완료':
        gaps.append('CALCULATION_PENDING')
    # Corporate actions apply to security-level price series, not all index or macro series.
    if '가격' in mapping['family'] and '종목' in (mapping['target_market'] + audit['name']):
        gaps.append('MISSING_CORPORATE_ACTION')
    if audit['mapping_status'] in {'SCHEMA_MISMATCH', 'FIELD_MISMATCH'}:
        gaps.append('SCHEMA_MISMATCH')
    if 'LICENSE_RESTRICTED' in audit['source_history_status']:
        gaps.append('LICENSE_RESTRICTED')
    gaps = list(dict.fromkeys(gaps)) or ['INSUFFICIENT_EVIDENCE']
    existing = {'source': audit['provider'], 'raw_acquisition': audit['raw_acquisition'],
                'generated_rows': audit['generated_rows'], 'local_checkpoint': local or {},
                'published_at': pit['published_at'], 'available_at': pit['available_at'],
                'vintage': pit['vintage'], 'revision_history': pit['revision_history']}
    priority = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}.get(audit['priority'], 4)
    executable = bool(local and local.get('derived_series_path'))
    return {'indicator_id': int(audit['indicator_id']), 'name': audit['name'],
            'prior_pit_classification': prior['pit_classification'],
            'required_fields': mapping['required_inputs'], 'existing_data': existing,
            'missing_evidence': gaps, 'root_cause': gaps[0],
            'possible_resolution': audit['next_action'],
            'alternative_sources': audit['alternative_provider'],
            'resolution_priority': priority,
            'execution_class': 'SERVER_EXECUTABLE' if executable else 'CODEX_REQUIRED',
            'validation_requirements': ['source rights', 'row-level observation date',
                                        'publication and decision timestamps', 'as-of universe',
                                        'delistings', 'corporate actions where applicable',
                                        'revision vintage', 'lineage', 'independent calculation'],
            'evidence_refs': prior['evidence_refs'], 'observed_evidence': evidence,
            'pit_approved_by_this_task': False}


def inventory(db_path: Path = PRIVATE_DB) -> dict:
    audits, mappings = _rows('indicator_audit_20261031.csv'), _rows('indicator_field_mapping.csv')
    pits, prior = _rows('pit_audit.csv'), _rows('pit_readiness_matrix_20261031.csv')
    uri = db_path.resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA busy_timeout=5000')
        local = {row[0]: {'state': row[1], 'raw_sha256': row[2], 'derived_series_path': row[3]}
                 for row in db.execute('SELECT indicator_id,state,raw_sha256,derived_series_path FROM tasks')}
    records = [classify(audits[key], mappings[key], pits[key], prior[key], local.get(key))
               for key in range(1, 191)]
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                     for name in ('indicator_audit_20261031.csv', 'indicator_field_mapping.csv',
                                  'pit_audit.csv', 'pit_readiness_matrix_20261031.csv')}
    return {'indicator_count': 190, 'records': records,
            'root_cause_counts': dict(Counter(item['root_cause'] for item in records)),
            'prior_pit_counts': dict(Counter(item['prior_pit_classification'] for item in records)),
            'source_sha256': source_hashes, 'pit_approvals_added': 0}


def check_local(indicator_id: int, db_path: Path = PRIVATE_DB) -> dict:
    """Bounded read-only inspection; a derived file is never publication proof."""
    if indicator_id not in range(1, 191):
        raise ValueError('Invalid indicator')
    uri = db_path.resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT state,raw_sha256,derived_series_path,pit_eligible '
                         'FROM tasks WHERE indicator_id=?', (indicator_id,)).fetchone()
    if row is None:
        raise ValueError('Indicator absent from checkpoint')
    allowed = Path.home() / 'MyDream2000/research/regime190'
    reference = row[2]
    if reference == 'private:db_daily_price_derived/':
        manifest = allowed / 'db_daily_price_derived_manifest.jsonl'
        data_dir = allowed / 'db_daily_price_derived'
        if (manifest.resolve().is_relative_to(allowed.resolve()) and manifest.is_file()
                and manifest.stat().st_size <= 32 * 1024 * 1024):
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            seen, counts = set(), Counter()
            example_verified = False
            for line in manifest.read_text().splitlines():
                item = json.loads(line)
                name = item['file']
                if name in seen or Path(name).name != name:
                    raise ValueError('Duplicate or unsafe derived file in manifest')
                seen.add(name)
                counts.update({key: int(value) for key, value in item['valid_counts'].items()})
                if not example_verified and int(item['valid_counts'].get(str(indicator_id), 0)) > 0:
                    sample = data_dir / name
                    if (not sample.resolve().is_relative_to(allowed.resolve()) or not sample.is_file()
                            or sample.stat().st_size != item['bytes']
                            or hashlib.sha256(sample.read_bytes()).hexdigest() != item['sha256']):
                        raise ValueError('Derived sample does not match manifest')
                    example_verified = True
            return {'indicator_id': indicator_id, 'checkpoint_state': row[0],
                    'checkpoint_raw_sha256': row[1], 'derived_file': reference,
                    'file_status': 'MANIFEST_SAMPLE_VALIDATED' if example_verified else 'NO_INDICATOR_ROWS',
                    'file_sha256': digest, 'file_bytes': manifest.stat().st_size,
                    'manifest_unique_files': len(seen),
                    'indicator_valid_rows': counts.get(str(indicator_id), 0),
                    'valid_rows_by_indicator': dict(counts),
                    'pit_approval': False,
                    'remaining_blocker': 'Publication, corporate actions, historical universe and revisions unverified'}
    if reference == 'private:db_rates_derived.csv.gz':
        manifest = allowed / 'db_rates_derived_manifest.json'
        data = allowed / 'db_rates_derived.csv.gz'
        if (manifest.resolve().is_relative_to(allowed.resolve()) and data.resolve().is_relative_to(allowed.resolve())
                and manifest.is_file() and data.is_file() and data.stat().st_size <= 32 * 1024 * 1024):
            item = json.loads(manifest.read_text())
            valid = int(item['valid_rows_by_indicator'].get(str(indicator_id), 0))
            good = (indicator_id in item['indicator_ids'] and data.stat().st_size == item['bytes']
                    and hashlib.sha256(data.read_bytes()).hexdigest() == item['sha256'])
            if not good:
                raise ValueError('Rates derived file does not match manifest')
            return {'indicator_id': indicator_id, 'checkpoint_state': row[0],
                    'checkpoint_raw_sha256': row[1], 'derived_file': reference,
                    'file_status': 'MANIFEST_SAMPLE_VALIDATED', 'file_sha256': item['sha256'],
                    'file_bytes': item['bytes'], 'indicator_valid_rows': valid,
                    'valid_rows_by_indicator': item['valid_rows_by_indicator'],
                    'first_date': item['first_date'], 'last_date': item['last_date'],
                    'pit_approval': False,
                    'remaining_blocker': 'History starts 2025; release timestamps and revisions unverified'}
    path = Path(reference) if reference else None
    result = {'indicator_id': indicator_id, 'checkpoint_state': row[0],
              'checkpoint_raw_sha256': row[1], 'derived_file': str(path) if path else None,
              'file_status': 'ABSENT', 'file_sha256': None, 'file_bytes': 0,
              'pit_approval': False, 'remaining_blocker': 'Publication, universe and revision evidence unverified'}
    if path and path.resolve().is_relative_to(allowed.resolve()) and path.is_file():
        size = path.stat().st_size
        if size > 32 * 1024 * 1024:
            result['file_status'] = 'TOO_LARGE_FOR_BOUNDED_CHECK'
        else:
            result['file_status'] = 'PRESENT'
            result['file_bytes'] = size
            result['file_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif path:
        result['file_status'] = 'MISSING_OR_OUTSIDE_RESEARCH_ROOT'
    return result
