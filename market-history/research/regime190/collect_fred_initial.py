#!/usr/bin/env python3
"""Fetch one FRED initial-release component per invocation into private storage."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import requests

from worker import DEFAULT_STATE, FRED, KEY_ENV, TARGET_END, TARGET_START, env_keys, utc_now

SERIES = tuple(sorted({series for group in FRED.values() for series in group}))
MIN_FREE = 5 * 1024**3
MAX_RESPONSE = 16 * 1024**2


def fetch_one(state_dir: Path = DEFAULT_STATE) -> dict:
    if shutil.disk_usage(state_dir).free < MIN_FREE:
        return {'state': 'DISK_WAIT'}
    key = env_keys(KEY_ENV).get('FRED_API_KEY')
    if not key:
        return {'state': 'KEY_MISSING'}
    output = state_dir / 'fred_initial_vintages'
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for series in SERIES:
        path = output / f'{series}.json'
        manifest = output / f'{series}.manifest.json'
        if path.exists() and manifest.exists():
            item = json.loads(manifest.read_text())
            if (path.stat().st_size == item.get('bytes') and
                    hashlib.sha256(path.read_bytes()).hexdigest() == item.get('sha256')):
                continue
        params = {'series_id': series, 'api_key': key, 'file_type': 'json',
                  'observation_start': TARGET_START, 'observation_end': TARGET_END,
                  'realtime_start': TARGET_START, 'realtime_end': TARGET_END,
                  'output_type': 4}
        try:
            session = requests.Session()
            session.trust_env = False
            response = session.get('https://api.stlouisfed.org/fred/series/observations',
                                   params=params, timeout=45, stream=True)
            if response.status_code != 200:
                return {'state': 'HTTP_RETRY', 'series': series, 'http_status': response.status_code}
            data = bytearray()
            for chunk in response.iter_content(1024 * 1024):
                data.extend(chunk)
                if len(data) > MAX_RESPONSE:
                    return {'state': 'RESPONSE_TOO_LARGE', 'series': series}
            payload = json.loads(data)
            rows = payload.get('observations', [])
            if not isinstance(rows, list) or not rows:
                return {'state': 'EMPTY_OR_INVALID', 'series': series}
            if any('realtime_start' not in row or 'date' not in row for row in rows):
                return {'state': 'VINTAGE_FIELDS_MISSING', 'series': series}
            temp = path.with_suffix('.json.tmp')
            with temp.open('wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(path)
            item = {'series': series, 'rows': len(rows), 'first_date': rows[0]['date'],
                    'last_date': rows[-1]['date'], 'sha256': hashlib.sha256(data).hexdigest(),
                    'bytes': len(data), 'retrieved_at_utc': utc_now(),
                    'source': 'FRED observations output_type=4',
                    'pit_status': 'PIT_UNVERIFIED_RELEASE_HOUR_AND_DEFINITION'}
            tmp_manifest = manifest.with_suffix('.json.tmp')
            tmp_manifest.write_text(json.dumps(item, indent=2) + '\n')
            tmp_manifest.replace(manifest)
            return {'state': 'ACQUIRED_INITIAL_VINTAGE', **item}
        except (requests.RequestException, ValueError, OSError) as exc:
            # RequestException text may contain a URL with api_key; never log it.
            return {'state': 'REQUEST_RETRY', 'series': series, 'error_type': type(exc).__name__}
    return {'state': 'COMPLETE', 'series_count': len(SERIES)}


if __name__ == '__main__':
    print(json.dumps(fetch_one()))
