#!/usr/bin/env python3
"""Bounded, resumable research collector. Never writes to the operating database."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import random
import signal
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
DEFAULT_STATE = Path.home() / 'MyDream2000/research/regime190'
RO_ENV = Path.home() / 'mydream2000_backtest_ro.env'
KEY_ENV = Path.home() / 'mydream2000.env'
TARGET_START = '2010-01-01'
TARGET_END = '2026-10-27'
FRED = {
    116: ['DGS2', 'DGS10'], 117: ['DGS2', 'DGS10'],
    118: ['BAMLH0A0HYM2'], 119: ['BAMLC0A0CM'], 120: ['SOFR'],
    121: ['STLFSI4'], 122: ['WRESBAL', 'RRPONTSYD', 'WTREGEN'],
    125: ['DFEDTARL', 'DFEDTARU'], 126: ['DEXKOUS'],
    127: ['DTWEXBGS'], 133: ['VIXCLS'],
    134: ['DCOILWTICO', 'DCOILBRENTEU'],
}
MONTHLY = {116: 'macro-cpi-rates-monthly.csv', 126: 'korea-market-monthly.csv',
           128: 'macro-cpi-rates-monthly.csv', 131: 'us-stock-market-monthly.csv',
           134: 'macro-commodities-monthly.csv', 135: 'macro-commodities-monthly.csv',
           143: 'macro-cpi-rates-monthly.csv'}
DB_MAP = {}
for lo, hi, table, field in [
    (41, 52, 'domestic_daily_price', 'volume'),
    (53, 72, 'domestic_daily_price', 'close'),
    (83, 95, 'domestic_investor_daily', 'foreign_net_amount'),
    (96, 105, 'domestic_short_sale_daily', 'short_amount'),
    (106, 115, 'market_rates_snapshot', 'value'),
    (126, 130, 'market_fx_snapshot', 'rate'),
    (131, 137, 'us_market_daily', 'close'),
    (138, 151, 'market_rates_snapshot', 'value'),
    (182, 190, 'market_index_snapshot', 'value'),
]:
    DB_MAP.update({i: (table, field) for i in range(lo, hi + 1)})
DB_MAP.update({
    73: ('orderbook_depth_snapshot', 'bid_qty_1'),
    74: ('orderbook_depth_snapshot', 'bid_qty_1'),
    75: ('orderbook_depth_snapshot', 'spread_bps'),
    76: ('orderbook_depth_snapshot', 'bid_qty_10'),
    78: ('orderbook_depth_snapshot', 'spread_bps'),
    82: ('orderbook_depth_snapshot', 'bid_qty_10'),
    174: ('event_shadow_snapshot', 'title'),
    175: ('event_shadow_snapshot', 'summary'),
    178: ('event_shadow_snapshot', 'title'),
    181: ('event_shadow_snapshot', 'title'),
})
DATE_COLUMN = {'market_rates_snapshot': 'data_date', 'market_fx_snapshot': 'trade_date',
               'market_index_snapshot': 'trade_date', 'orderbook_depth_snapshot': 'quote_time',
               'event_shadow_snapshot': 'event_date'}
DB_FILTER = {174: 'news', 175: 'news', 178: 'disclosure', 181: 'news'}
EXACT_DB_COMPONENT_IDS = {73, 74, 75, 76, 78, 82, 174, 175, 178, 181}
STOP = False

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def on_stop(_signum, _frame):
    global STOP
    STOP = True

def env_keys(path: Path):
    if not path.exists(): return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith('export '): line = line[7:]
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip().strip('"\'')
    return result

def atomic_json(path: Path, obj):
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    temp.replace(path)

def append_jsonl(path: Path, obj):
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())

def open_state(state_dir: Path):
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_dir, 0o700)
    (state_dir / 'raw').mkdir(exist_ok=True, mode=0o700)
    conn = sqlite3.connect(state_dir / 'checkpoint.sqlite', timeout=10)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
      indicator_id INTEGER PRIMARY KEY, priority INTEGER NOT NULL, name TEXT NOT NULL,
      state TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0,
      provider_attempt_count INTEGER NOT NULL DEFAULT 0,
      fallback_attempt_count INTEGER NOT NULL DEFAULT 0,
      last_attempt_at TEXT, http_or_db_result TEXT, blocking_evidence TEXT,
      next_action TEXT, raw_sha256 TEXT, derived_series_path TEXT,
      pit_eligible INTEGER NOT NULL DEFAULT 0, next_retry_at TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS requests (
      indicator_id INTEGER, provider TEXT, series_id TEXT, result TEXT,
      attempted_at TEXT, raw_sha256 TEXT, row_count INTEGER,
      PRIMARY KEY(indicator_id,provider,series_id))''')
    conn.execute("UPDATE tasks SET state='PENDING' WHERE state='RUNNING'")
    with (HERE / 'indicator_spec.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            conn.execute('INSERT OR IGNORE INTO tasks(indicator_id,priority,name,state) VALUES(?,?,?,?)',
                         (int(row['indicator_id']), int(row['priority'][1:]), row['name'], 'PENDING'))
    conn.commit()
    return conn

def progress(conn, state_dir):
    counts = dict(conn.execute('SELECT state,count(*) FROM tasks GROUP BY state').fetchall())
    obj = {'updated_at_utc': utc_now(), 'state': 'IN_PROGRESS' if counts.get('PENDING', 0) or counts.get('RETRY_WAIT', 0) or counts.get('RUNNING', 0) or counts.get('NEEDS_REVIEW', 0) else 'ATTEMPTS_PROCESSED_NOT_FULLY_VERIFIED',
           'counts': counts, 'total': sum(counts.values()), 'pit_eligible': conn.execute('SELECT count(*) FROM tasks WHERE pit_eligible=1').fetchone()[0]}
    atomic_json(state_dir / 'progress.json', obj)
    md=state_dir/'progress.md';md_tmp=state_dir/'progress.md.tmp'
    md_tmp.write_text('# Regime190 collector progress\n\n' + json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    md_tmp.replace(md)
    review=state_dir/'needs_review.csv';review_tmp=state_dir/'needs_review.csv.tmp'
    with review_tmp.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['indicator_id', 'name', 'state', 'blocking_evidence', 'next_action'])
        writer.writerows(conn.execute("SELECT indicator_id,name,state,blocking_evidence,next_action FROM tasks WHERE state IN ('NEEDS_REVIEW','BLOCKED_VERIFIED') ORDER BY indicator_id"))
    review_tmp.replace(review)
    return obj

def attempt_local(indicator_id: int):
    if indicator_id <= 40:
        paths = [HERE.parent / 'daily-index-validation-20261021' / f'naver_{m}_raw.xml'
                 for m in ('kospi', 'kosdaq')]
    elif indicator_id in MONTHLY:
        paths = [HERE.parents[1] / 'data' / MONTHLY[indicator_id]]
    else:
        return None
    if not all(path.exists() for path in paths): return {'result': 'LOCAL_FILES_MISSING'}
    evidence = []
    for path in paths:
        evidence.append({'file': path.name, 'bytes': path.stat().st_size,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'result': 'LOCAL_HASH_VERIFIED', 'files': evidence}

def attempt_db(indicator_id: int, state_dir: Path):
    if indicator_id not in DB_MAP: return None
    table, field = DB_MAP[indicator_id]
    family = DB_FILTER.get(indicator_id)
    cache = state_dir / 'raw' / (f'db_component_{table}_{field}' + (f'_{family}.json' if family else '.json'))
    if cache.exists():
        try:
            cached = json.loads(cache.read_text())
            if (datetime.now(timezone.utc) - datetime.fromisoformat(cached['query_time_utc'])).total_seconds() < 86400:
                return {'result': 'DB_CACHED_QUERY_OK' if cached['nonnull_rows'] else 'DB_CACHED_NO_ROWS',
                        'rows': cached['nonnull_rows'], 'sha256': hashlib.sha256(cache.read_bytes()).hexdigest(),
                        'path': cache.name}
        except (ValueError, KeyError, TypeError): pass
    try:
        import psycopg2
        from psycopg2 import sql
        d = env_keys(RO_ENV)
        needed = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
        if not all(d.get(k) for k in needed): return {'result': 'DB_CREDENTIALS_MISSING'}
        date_col = DATE_COLUMN.get(table, 'market_date')
        conn = psycopg2.connect(host=d['DB_HOST'], port=d['DB_PORT'], dbname=d['DB_NAME'],
                                user=d['DB_USER'], password=d['DB_PASSWORD'], connect_timeout=4)
        try:
            with conn.cursor() as cur:
                cur.execute('BEGIN READ ONLY')
                cur.execute("SET LOCAL statement_timeout='8000ms'")
                upper = sql.SQL("< (%s::date + interval '1 day')") if date_col == 'quote_time' else sql.SQL('<= %s')
                query = sql.SQL('SELECT count(*),count({}),min({}),max({}) FROM {} WHERE {} >= %s AND {} ').format(
                    sql.Identifier(field), sql.Identifier(date_col), sql.Identifier(date_col),
                    sql.Identifier(table), sql.Identifier(date_col), sql.Identifier(date_col)) + upper
                params = [TARGET_START, TARGET_END]
                if family:
                    query += sql.SQL(' AND source_family=%s')
                    params.append(family)
                cur.execute(query, params)
                count, nonnull, first, last = cur.fetchone()
                conn.rollback()
        finally: conn.close()
        data = {'source': 'trading_read_only', 'table': table, 'required_component': field,
                'source_family_filter': family,
                'rows': count, 'nonnull_rows': nonnull, 'first': str(first), 'last': str(last),
                'query_time_utc': utc_now(), 'scope_warning': 'Field relevance, market identity, and PIT not yet verified'}
        path = cache
        atomic_json(path, data)
        return {'result': 'DB_QUERY_OK' if nonnull else 'DB_NO_COMPONENT_ROWS', 'rows': nonnull,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'path': path.name}
    except Exception as exc:
        return {'result': 'DB_' + type(exc).__name__}

def attempt_fred(indicator_id: int, state_dir: Path, conn: sqlite3.Connection, max_requests: int):
    series = FRED.get(indicator_id, [])
    if not series: return {'result': 'NO_VERIFIED_FRED_MAPPING', 'provider_attempts': 0}
    key = env_keys(KEY_ENV).get('FRED_API_KEY')
    if not key: return {'result': 'FRED_KEY_MISSING', 'provider_attempts': 0}
    done = 0; outcomes = []
    for series_id in series:
        if STOP or done >= max_requests: break
        prior = conn.execute('SELECT result,row_count,raw_sha256 FROM requests WHERE indicator_id=? AND provider=? AND series_id=?',
                             (indicator_id, 'FRED', series_id)).fetchone()
        if prior and prior[0] == 'ACQUIRED':
            outcomes.append({'series_id': series_id, 'result': 'ALREADY_ACQUIRED', 'rows': prior[1]}); continue
        try:
            response = requests.get('https://api.stlouisfed.org/fred/series/observations',
                params={'series_id': series_id, 'api_key': key, 'file_type': 'json',
                        'observation_start': TARGET_START, 'observation_end': TARGET_END}, timeout=(5, 20))
            done += 1
            if response.status_code == 429:
                retry = int(response.headers.get('Retry-After', '300')) if response.headers.get('Retry-After', '300').isdigit() else 300
                outcomes.append({'series_id': series_id, 'result': 'HTTP_429', 'retry_after_seconds': min(retry, 3600)})
                break
            if response.status_code != 200:
                outcomes.append({'series_id': series_id, 'result': 'HTTP_' + str(response.status_code)}); continue
            data = response.json(); rows = data.get('observations', [])
            if not rows:
                outcomes.append({'series_id': series_id, 'result': 'EMPTY_OBSERVATIONS'}); continue
            # Never persist the request URL: it contains the API key.
            path = state_dir / 'raw' / f'fred_{series_id}.json'
            atomic_json(path, {'series_id': series_id, 'retrieved_at_utc': utc_now(),
                               'observations': rows, 'source': 'FRED observations API',
                               'pit_warning': 'Current-vintage values; release time not established'})
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            conn.execute('INSERT OR REPLACE INTO requests VALUES(?,?,?,?,?,?,?)',
                         (indicator_id, 'FRED', series_id, 'ACQUIRED', utc_now(), digest, len(rows)))
            conn.commit()
            outcomes.append({'series_id': series_id, 'result': 'ACQUIRED', 'rows': len(rows), 'sha256': digest})
            time.sleep(1 + random.random() * .2)
        except Exception as exc:
            outcomes.append({'series_id': series_id, 'result': type(exc).__name__})
    return {'result': 'FRED_COMPONENTS_CHECKED', 'provider_attempts': done, 'outcomes': outcomes}

def process_one(conn, state_dir, row, max_requests):
    indicator_id = row[0]; before = utc_now()
    conn.execute("UPDATE tasks SET state='RUNNING',attempt_count=attempt_count+1,last_attempt_at=? WHERE indicator_id=?", (before, indicator_id)); conn.commit()
    local = attempt_local(indicator_id)
    db = attempt_db(indicator_id, state_dir)
    fred = attempt_fred(indicator_id, state_dir, conn, max_requests)
    acquired = (local and local.get('result') == 'LOCAL_HASH_VERIFIED') or (indicator_id in EXACT_DB_COMPONENT_IDS and db and db.get('rows', 0) > 0) or any(x.get('result') in ('ACQUIRED', 'ALREADY_ACQUIRED') for x in fred.get('outcomes', []))
    if acquired:
        state, reason, next_action = 'PARTIAL', 'Components observed; exact indicator and PIT unverified', 'Validate market/field mapping, add missing components and as-of release history'
    elif fred.get('result') == 'FRED_KEY_MISSING':
        state, reason, next_action = 'BLOCKED_VERIFIED', 'FRED API key absent from approved environment file', 'Provide an authorized FRED key'
    elif not db and not local and not FRED.get(indicator_id):
        state, reason, next_action = 'NEEDS_REVIEW', 'No implemented official data adapter or local source for this indicator', 'Identify a licensed official data endpoint and independent fallback'
    elif db and db.get('rows', 0) > 0:
        state, reason, next_action = 'NEEDS_REVIEW', 'DB field candidate observed but indicator-specific mapping is unverified', 'Validate field, instrument universe, dates, and market before acquisition claim'
    else:
        state, reason, next_action = 'RETRY_WAIT', 'No verified data component acquired in bounded attempt', 'Review official provider adapter or accessible licensed fallback'
    retry = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat() if state == 'RETRY_WAIT' else None
    result = {'indicator_id': indicator_id, 'attempted_at_utc': before, 'local': local, 'db': db, 'fred': fred,
              'state': state, 'blocking_evidence': reason, 'next_action': next_action}
    append_jsonl(state_dir / 'attempts.jsonl', result)
    conn.execute('''UPDATE tasks SET state=?,provider_attempt_count=provider_attempt_count+?,
       fallback_attempt_count=fallback_attempt_count+?,http_or_db_result=?,blocking_evidence=?,next_action=?,raw_sha256=?,next_retry_at=? WHERE indicator_id=?''',
       (state, fred.get('provider_attempts', 0), (1 if db else 0) + (1 if local else 0),
        json.dumps({'local': local.get('result') if local else None, 'db': db.get('result') if db else None, 'fred': fred.get('result')}, ensure_ascii=False),
        reason, next_action, (db or {}).get('sha256') or ((local or {}).get('files') or [{}])[0].get('sha256'), retry, indicator_id))
    conn.commit()
    return result

def advance_daily_price_derivation(conn, state_dir):
    """Advance the new read-only DB adapter without revisiting exhausted sources."""
    from derive_db_daily import METRICS, run_batch
    try:
        result = run_batch(state_dir, max_symbols=25)
        atomic_json(state_dir / 'db_derive_progress.json',
                    {'updated_at_utc': utc_now(), **result})
        if result['state'] == 'COMPLETE':
            ids = tuple(METRICS)
            placeholders = ','.join('?' for _ in ids)
            conn.execute(f'''UPDATE tasks SET state='PARTIAL',
                attempt_count=attempt_count+1,
                fallback_attempt_count=fallback_attempt_count+1,
                last_attempt_at=?, derived_series_path='private:db_daily_price_derived/',
                blocking_evidence='Actual per-symbol OHLCV derived; historical market identity and PIT remain unverified',
                next_action='Verify as-of market membership, KIS adjustments, exact formula and release time'
                WHERE indicator_id IN ({placeholders}) AND derived_series_path IS NULL''',
                (utc_now(), *ids))
            conn.commit()
        return result['new_symbols'] > 0
    except Exception as exc:
        append_jsonl(state_dir / 'derived_errors.jsonl',
                     {'at_utc': utc_now(), 'error_type': type(exc).__name__,
                      'message': str(exc)[:240]})
        return False

def advance_rate_derivation(conn, state_dir):
    """Complete the short-history Korean rate adapter once per checkpoint."""
    ids = (107, 108, 109, 110, 111)
    remaining = conn.execute('SELECT count(*) FROM tasks WHERE indicator_id IN (107,108,109,110,111) '
                             'AND derived_series_path IS NULL').fetchone()[0]
    if not remaining:
        return False
    from derive_db_rates import run
    try:
        result = run(state_dir)
        if result['state'] != 'PARTIAL_DERIVED':
            return False
        conn.execute('''UPDATE tasks SET state='PARTIAL',
            attempt_count=attempt_count+1,
            fallback_attempt_count=fallback_attempt_count+1,
            last_attempt_at=?, derived_series_path='private:db_rates_derived.csv.gz',
            blocking_evidence='2025-2026 rate series derived; missing subcomponents, full history and PIT vintages',
            next_action='Acquire earlier official history and release vintages; verify missing MSB and BBB series'
            WHERE indicator_id IN (107,108,109,110,111) AND derived_series_path IS NULL''',
            (utc_now(),))
        conn.commit()
        return True
    except Exception as exc:
        append_jsonl(state_dir / 'derived_errors.jsonl',
                     {'at_utc': utc_now(), 'adapter': 'rates',
                      'error_type': type(exc).__name__, 'message': str(exc)[:240]})
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', type=Path, default=DEFAULT_STATE)
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--since', default=TARGET_START)
    ap.add_argument('--until', default=TARGET_END)
    ap.add_argument('--max-runtime', type=int, default=3600)
    ap.add_argument('--max-attempts-per-source', type=int, default=2)
    ap.add_argument('--max-requests', type=int, default=30)
    ap.add_argument('--concurrency', type=int, default=1)
    ap.add_argument('--max-tasks', type=int, default=190)
    ap.add_argument('--indicator-id', type=int)
    ap.add_argument('--service-loop', action='store_true')
    ap.add_argument('--poll-seconds', type=int, default=300)
    args = ap.parse_args()
    if args.concurrency != 1: ap.error('Only concurrency=1 is supported for provider rate safety')
    if args.since != TARGET_START or args.until != TARGET_END: ap.error('Date override is not yet implemented; use audited target bounds')
    if args.max_runtime < 0 or args.max_attempts_per_source < 1 or args.max_requests < 0 or args.poll_seconds < 1: ap.error('Invalid limit')
    if args.status:
        from status_snapshot import snapshot
        print(json.dumps(snapshot(args.output_dir), ensure_ascii=False))
        return 0
    lock_path = args.output_dir / 'worker.lock'; args.output_dir.mkdir(parents=True, exist_ok=True)
    with lock_path.open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: print('WORKER_ALREADY_RUNNING'); return 2
        conn = open_state(args.output_dir)
        if args.dry_run:
            print(json.dumps({'queued': conn.execute("SELECT count(*) FROM tasks WHERE state='PENDING'").fetchone()[0],
                              'fred_mapped': len(FRED), 'db_mapped': len(DB_MAP), 'output_dir': str(args.output_dir)}, ensure_ascii=False)); return 0
        signal.signal(signal.SIGTERM, on_stop); signal.signal(signal.SIGINT, on_stop)
        deadline = time.monotonic() + args.max_runtime if args.max_runtime else float('inf')
        processed = 0; request_budget = args.max_requests
        while not STOP and (args.service_loop or processed < args.max_tasks) and time.monotonic() < deadline:
            if args.indicator_id:
                row = conn.execute("SELECT indicator_id,state FROM tasks WHERE indicator_id=? AND state='PENDING'", (args.indicator_id,)).fetchone()
            else:
                row = conn.execute('''SELECT indicator_id,state FROM tasks WHERE state='PENDING'
                    OR (state='RETRY_WAIT' AND next_retry_at<=?) ORDER BY priority,indicator_id LIMIT 1''', (utc_now(),)).fetchone()
            if not row:
                if not args.service_loop: break
                if advance_rate_derivation(conn, args.output_dir):
                    progress(conn, args.output_dir)
                    continue
                if advance_daily_price_derivation(conn, args.output_dir):
                    progress(conn, args.output_dir)
                    continue
                progress(conn, args.output_dir)
                if conn.execute("SELECT count(*) FROM tasks WHERE state IN ('PENDING','RETRY_WAIT','NEEDS_REVIEW')").fetchone()[0] == 0: break
                for _ in range(args.poll_seconds):
                    if STOP or time.monotonic() >= deadline: break
                    time.sleep(1)
                request_budget = args.max_requests
                continue
            if conn.execute('SELECT attempt_count FROM tasks WHERE indicator_id=?',(row[0],)).fetchone()[0] >= args.max_attempts_per_source:
                conn.execute("UPDATE tasks SET state='NEEDS_REVIEW',blocking_evidence='Bounded attempts exhausted; data not acquired',next_action='Manual provider review' WHERE indicator_id=?",(row[0],));conn.commit();continue
            result = process_one(conn, args.output_dir, row, request_budget)
            request_budget -= result['fred'].get('provider_attempts', 0)
            processed += 1
            if processed % 10 == 0: progress(conn, args.output_dir)
        snapshot = progress(conn, args.output_dir)
        print(json.dumps({'processed_this_run': processed, 'remaining_request_budget': request_budget, **snapshot}, ensure_ascii=False))
        conn.close()
        return 0

if __name__ == '__main__': sys.exit(main())
