#!/usr/bin/env python3
"""Resumable, bounded initial-vintage collection for six over-limit FRED series."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from worker import DEFAULT_STATE, KEY_ENV, TARGET_END, env_keys

SERIES = ('DFEDTARL', 'DFEDTARU', 'DGS10', 'DGS2', 'RRPONTSYD', 'VIXCLS')
MIN_FREE = 5 * 1024**3
MAX_BYTES = 8 * 1024**2
YEARS = range(2010, 2027)
URL = 'https://api.stlouisfed.org/fred/series/observations'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def valid_record(data_path: Path, manifest_path: Path) -> bool:
    if not data_path.is_file() or not manifest_path.is_file():
        return False
    item = json.loads(manifest_path.read_text())
    return data_path.stat().st_size == item.get('bytes') and sha(data_path) == item.get('sha256')


def atomic_write(path: Path, content: bytes) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('wb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def request_year(session, key: str, series: str, year: int) -> tuple[str, dict | None, bytes | None]:
    end = min(f'{year}-12-31', TARGET_END)
    params = {'series_id': series, 'api_key': key, 'file_type': 'json',
              'observation_start': '2010-01-01', 'observation_end': TARGET_END,
              'realtime_start': f'{year}-01-01', 'realtime_end': end,
              'output_type': 4}
    try:
        response = session.get(URL, params=params, timeout=45, stream=True)
        if response.status_code != 200:
            return f'HTTP_{response.status_code}', None, None
        chunks, size = [], 0
        for chunk in response.iter_content(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                return 'RESPONSE_TOO_LARGE', None, None
            chunks.append(chunk)
        raw = b''.join(chunks)
        payload = json.loads(raw)
        rows = payload.get('observations', [])
        if not isinstance(rows, list) or int(payload.get('count', -1)) != len(rows):
            return 'TRUNCATED_OR_INVALID', None, None
        if any(not {'date', 'value', 'realtime_start', 'realtime_end'} <= row.keys()
               or not (f'{year}-01-01' <= row['realtime_start'] <= end) for row in rows):
            return 'VINTAGE_FIELDS_INVALID', None, None
        return 'ACQUIRED', {'rows': len(rows),
                            'first_date': rows[0]['date'] if rows else '',
                            'last_date': rows[-1]['date'] if rows else ''}, raw
    except (requests.RequestException, ValueError, OSError):
        # Request exceptions may contain the URL and API key; omit their text.
        return 'REQUEST_ERROR', None, None


def run(state_dir: Path = DEFAULT_STATE, max_requests: int = 102, delay_seconds: float = 15,
        series_ids: tuple[str, ...] | None = None, years: range | None = None) -> dict:
    key = env_keys(KEY_ENV).get('FRED_API_KEY')
    if not key:
        return {'state': 'KEY_MISSING', 'requests': 0}
    output = state_dir / 'fred_initial_yearly'
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    session = requests.Session()
    session.trust_env = False
    completed, new_rows, requests_made, errors = 0, 0, 0, []
    for series in (series_ids if series_ids is not None else SERIES):
        folder = output / series
        folder.mkdir(exist_ok=True, mode=0o700)
        for year in (years if years is not None else YEARS):
            data_path = folder / f'{year}.json'
            manifest_path = folder / f'{year}.manifest.json'
            if valid_record(data_path, manifest_path):
                completed += 1
                continue
            if shutil.disk_usage(state_dir).free < MIN_FREE:
                return {'state': 'DISK_WAIT', 'completed_windows': completed,
                        'new_rows': new_rows, 'requests': requests_made, 'errors': errors}
            if requests_made >= max_requests:
                return {'state': 'REQUEST_BUDGET', 'completed_windows': completed,
                        'new_rows': new_rows, 'requests': requests_made, 'errors': errors}
            result, info, raw = request_year(session, key, series, year)
            requests_made += 1
            now = datetime.now(timezone.utc).isoformat()
            if result == 'ACQUIRED':
                atomic_write(data_path, raw)
                item = {'series': series, 'year': year, 'rows': info['rows'],
                        'first_date': info['first_date'], 'last_date': info['last_date'],
                        'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'retrieved_at_utc': now, 'pit_status': 'RELEASE_DATE_ONLY_UNVERIFIED_HOUR'}
                atomic_write(manifest_path, (json.dumps(item, indent=2) + '\n').encode())
                completed += 1
                new_rows += info['rows']
            else:
                error = {'series': series, 'year': year, 'state': result, 'at_utc': now}
                errors.append(error)
                atomic_write(folder / f'{year}.error.json', (json.dumps(error) + '\n').encode())
                if result in ('HTTP_429', 'REQUEST_ERROR', 'RESPONSE_TOO_LARGE'):
                    return {'state': 'RETRY_REQUIRED', 'completed_windows': completed,
                            'new_rows': new_rows, 'requests': requests_made, 'errors': errors}
            atomic_write(output / 'progress.json', (json.dumps({
                'updated_at_utc': now, 'completed_windows': completed,
                'new_rows_this_run': new_rows, 'requests_this_run': requests_made,
                'last_series': series, 'last_year': year, 'last_result': result}) + '\n').encode())
            if delay_seconds:
                time.sleep(delay_seconds)
    return {'state': 'COMPLETE_WITH_ERRORS' if errors else 'COMPLETE',
            'completed_windows': completed, 'new_rows': new_rows,
            'requests': requests_made, 'errors': errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--series', choices=SERIES)
    parser.add_argument('--year', type=int, choices=YEARS)
    parser.add_argument('--max-requests', type=int, default=102)
    parser.add_argument('--delay-seconds', type=float, default=15)
    args = parser.parse_args()
    print(json.dumps(run(max_requests=args.max_requests, delay_seconds=args.delay_seconds,
                         series_ids=(args.series,) if args.series else None,
                         years=range(args.year, args.year + 1) if args.year else None)))
