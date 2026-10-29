#!/usr/bin/env python3
"""Derive short historical rate components from the read-only research DB."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from worker import DEFAULT_STATE, RO_ENV, env_keys

SERIES = ('KTB_3Y', 'KTB_10Y', 'CD_91D', 'CP_A1', 'CORP_AA_3Y')
INDICATORS = (107, 108, 109, 110, 111)


def run(state_dir: Path = DEFAULT_STATE) -> dict:
    if shutil.disk_usage(state_dir).free < 5 * 1024**3:
        return {'state': 'DISK_WAIT', 'indicator_ids': list(INDICATORS)}
    from psycopg2 import connect
    credentials = env_keys(RO_ENV)
    required = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    if any(not credentials.get(key) for key in required):
        raise RuntimeError('Read-only DB credentials are incomplete')
    connection = connect(host=credentials['DB_HOST'], port=credentials['DB_PORT'],
                         dbname=credentials['DB_NAME'], user=credentials['DB_USER'],
                         password=credentials['DB_PASSWORD'], connect_timeout=5,
                         application_name='regime190_readonly_rate_derivation')
    connection.set_session(readonly=True, autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout='30s'")
            cursor.execute('''SELECT series_key,data_date,value,unit,available_at,
                              released_at,vintage_date,revision_no,collected_at
                              FROM public.market_rates_snapshot
                              WHERE series_key=ANY(%s) AND data_date IS NOT NULL
                                AND value IS NOT NULL ORDER BY series_key,data_date,collected_at''',
                           (list(SERIES),))
            rows = cursor.fetchall()
            columns = [item.name for item in cursor.description]
    finally:
        connection.close()
    if not rows:
        return {'state': 'NO_SOURCE_ROWS', 'indicator_ids': list(INDICATORS)}
    frame = pd.DataFrame(rows, columns=columns)
    frame['value'] = pd.to_numeric(frame['value'], errors='coerce')
    frame = frame.drop_duplicates(['series_key', 'data_date'], keep='last')
    units = sorted(set(frame['unit'].dropna().astype(str)))
    if units != ['PCT']:
        raise RuntimeError(f'Unexpected rate units: {units}')
    wide = frame.pivot(index='data_date', columns='series_key', values='value').sort_index()
    for name in SERIES:
        if name not in wide:
            wide[name] = float('nan')
    wide['kr_curve_10y_minus_3y_pctpoint'] = wide['KTB_10Y'] - wide['KTB_3Y']
    wide['corp_aa_minus_ktb3_pctpoint'] = wide['CORP_AA_3Y'] - wide['KTB_3Y']
    wide['cp_minus_cd_pctpoint'] = wide['CP_A1'] - wide['CD_91D']
    availability = frame.groupby('data_date')['available_at'].max()
    wide['available_at_candidate'] = availability
    wide['pit_status'] = 'PIT_UNVERIFIED'
    wide['definition_limit'] = '109 lacks MSB; 110 lacks BBB; available_at and vintages unverified'
    wide.index.name = 'data_date'
    output = state_dir / 'db_rates_derived.csv.gz'
    temp = state_dir / 'db_rates_derived.csv.gz.part'
    with gzip.open(temp, 'wt', encoding='utf-8', newline='') as stream:
        wide.to_csv(stream, na_rep='')
    digest = hashlib.sha256(temp.read_bytes()).hexdigest()
    temp.replace(output)
    valid = {
        '107': int(wide[['KTB_3Y', 'KTB_10Y']].notna().all(axis=1).sum()),
        '108': int(wide['kr_curve_10y_minus_3y_pctpoint'].notna().sum()),
        '109': int(wide[['CD_91D', 'CP_A1']].notna().all(axis=1).sum()),
        '110': int(wide['corp_aa_minus_ktb3_pctpoint'].notna().sum()),
        '111': int(wide['cp_minus_cd_pctpoint'].notna().sum()),
    }
    manifest = {'state': 'PARTIAL_DERIVED', 'indicator_ids': list(INDICATORS),
                'source_table': 'public.market_rates_snapshot',
                'source_rows': len(rows), 'unique_source_rows': len(frame),
                'dates': len(wide), 'first_date': str(wide.index.min()),
                'last_date': str(wide.index.max()), 'valid_rows_by_indicator': valid,
                'bytes': output.stat().st_size, 'sha256': digest,
                'pit_status': 'PIT_UNVERIFIED',
                'market_scope': 'Korean rate series, not a stock universe',
                'completed_at_utc': datetime.now(timezone.utc).isoformat()}
    path = state_dir / 'db_rates_derived_manifest.json'
    temp_manifest = path.with_suffix('.json.tmp')
    temp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    temp_manifest.replace(path)
    return manifest


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False))
