#!/usr/bin/env python3
"""Read-only, resumable ECOS history capture for five Korean rate components."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from worker import DEFAULT_STATE, KEY_ENV, env_keys

ITEMS = {
    'KTB_3Y': '010200000',
    'KTB_10Y': '010210000',
    'CD_91D': '010502000',
    'CP_A1': '010503000',
    'CORP_AA_3Y': '010300000',
}
STAT_CODE = '817Y002'
PAGE_SIZE = 1000
MIN_FREE = 5 * 1024**3
MAX_BYTES = 8 * 1024**2
START = '20100101'
END = '20261027'


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('wb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def verified(path: Path, manifest: Path) -> dict | None:
    if not path.is_file() or not manifest.is_file():
        return None
    item = json.loads(manifest.read_text())
    if path.stat().st_size != item.get('bytes') or digest(path) != item.get('sha256'):
        return None
    return item


def fetch(session, key: str, series: str, page: int) -> tuple[str, dict | None]:
    first = page * PAGE_SIZE + 1
    last = first + PAGE_SIZE - 1
    url = '/'.join(('https://ecos.bok.or.kr/api/StatisticSearch', quote(key),
                    'json', 'kr', str(first), str(last), STAT_CODE, 'D',
                    START, END, ITEMS[series])) + '/'
    try:
        response = session.get(url, timeout=45, stream=True)
        if response.status_code != 200:
            return f'HTTP_{response.status_code}', None
        chunks, size = [], 0
        for chunk in response.iter_content(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                return 'RESPONSE_TOO_LARGE', None
            chunks.append(chunk)
        payload = json.loads(b''.join(chunks))
        table = payload.get('StatisticSearch')
        if not isinstance(table, dict):
            return 'API_RESULT_NO_TABLE', None
        rows = table.get('row', [])
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return 'INVALID_ROWS', None
        total = int(table.get('list_total_count', len(rows)))
        if any(not isinstance(row, dict) or
               not {'TIME', 'DATA_VALUE', 'ITEM_CODE1'} <= row.keys() or
               row['ITEM_CODE1'] != ITEMS[series] for row in rows):
            return 'ITEM_CODE_MISMATCH', None
        if total < first - 1 or len(rows) > PAGE_SIZE:
            return 'PAGINATION_MISMATCH', None
        return 'ACQUIRED', {'rows': rows, 'total_count': total, 'first_row': first,
                            'last_row': first + len(rows) - 1}
    except (requests.RequestException, ValueError, OSError):
        # The request URL contains the API key. Never print exception text.
        return 'REQUEST_ERROR', None


def run(state_dir: Path = DEFAULT_STATE, series_ids: tuple[str, ...] | None = None,
        max_pages: int = 50, delay_seconds: float = 10) -> dict:
    key = env_keys(KEY_ENV).get('BOK_ECOS_API_KEY')
    if not key:
        return {'state': 'KEY_MISSING', 'pages_requested': 0}
    output = state_dir / 'ecos_rate_history'
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    session = requests.Session()
    session.trust_env = False
    requested, complete, rows_added = 0, 0, 0
    for series in (series_ids or tuple(ITEMS)):
        folder = output / series
        folder.mkdir(exist_ok=True, mode=0o700)
        page = 0
        while True:
            data_path = folder / f'page_{page:03d}.json'
            manifest_path = folder / f'page_{page:03d}.manifest.json'
            prior = verified(data_path, manifest_path)
            if prior:
                complete += 1
                if prior['last_row'] >= prior['total_count']:
                    break
                page += 1
                continue
            if shutil.disk_usage(state_dir).free < MIN_FREE:
                return {'state': 'DISK_WAIT', 'pages_complete': complete,
                        'pages_requested': requested, 'new_rows': rows_added}
            if requested >= max_pages:
                return {'state': 'REQUEST_BUDGET', 'pages_complete': complete,
                        'pages_requested': requested, 'new_rows': rows_added}
            result, payload = fetch(session, key, series, page)
            requested += 1
            now = datetime.now(timezone.utc).isoformat()
            if result != 'ACQUIRED':
                error = {'series': series, 'page': page, 'state': result, 'at_utc': now}
                atomic_write(folder / f'page_{page:03d}.error.json',
                             (json.dumps(error) + '\n').encode())
                return {'state': 'RETRY_OR_REVIEW', 'pages_complete': complete,
                        'pages_requested': requested, 'new_rows': rows_added,
                        'error': error}
            rows = payload['rows']
            if not rows and payload['total_count']:
                return {'state': 'EMPTY_PAGE_WITH_COUNT', 'series': series, 'page': page}
            content = (json.dumps({'series': series, 'stat_code': STAT_CODE,
                                   'item_code': ITEMS[series], 'rows': rows},
                                  ensure_ascii=False) + '\n').encode()
            atomic_write(data_path, content)
            item = {'series': series, 'stat_code': STAT_CODE,
                    'item_code': ITEMS[series], 'page': page,
                    'rows': len(rows), 'first_row': payload['first_row'],
                    'last_row': payload['last_row'],
                    'total_count': payload['total_count'],
                    'first_date': rows[0]['TIME'] if rows else '',
                    'last_date': rows[-1]['TIME'] if rows else '',
                    'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                    'retrieved_at_utc': now, 'pit_status': 'CURRENT_SNAPSHOT_RELEASE_TIME_UNVERIFIED'}
            atomic_write(manifest_path, (json.dumps(item, indent=2) + '\n').encode())
            complete += 1
            rows_added += len(rows)
            atomic_write(output / 'progress.json', (json.dumps({
                'updated_at_utc': now, 'series': series, 'page': page,
                'pages_complete_this_run': complete,
                'pages_requested_this_run': requested, 'new_rows_this_run': rows_added}) + '\n').encode())
            if item['last_row'] >= item['total_count']:
                break
            page += 1
            if delay_seconds:
                time.sleep(delay_seconds)
    return {'state': 'COMPLETE', 'pages_complete': complete,
            'pages_requested': requested, 'new_rows': rows_added}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--series', choices=ITEMS)
    parser.add_argument('--max-pages', type=int, default=50)
    parser.add_argument('--delay-seconds', type=float, default=10)
    args = parser.parse_args()
    print(json.dumps(run(series_ids=(args.series,) if args.series else None,
                         max_pages=args.max_pages, delay_seconds=args.delay_seconds)))
