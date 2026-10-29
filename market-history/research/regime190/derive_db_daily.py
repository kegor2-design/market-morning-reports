#!/usr/bin/env python3
"""Resumable private, per-symbol OHLCV derivation from the read-only KIS database.

This does not establish historical market membership or point-in-time availability.
The output stays under the private worker state and is never published to GitHub.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from worker import RO_ENV, DEFAULT_STATE, TARGET_END, env_keys

METRICS = {41: 'obv', 42: 'mfi14', 43: 'cmf20', 44: 'ad_line',
           45: 'chaikin_3_10', 46: 'daily_vwap_gap_pct',
           49: 'volume_z20', 51: 'amihud_krw_billion'}
MIN_FREE_BYTES = 5 * 1024**3
MAX_OUTPUT_BYTES = 2 * 1024**3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


def derive(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute close-of-day research values using current and earlier rows only."""
    frame = frame.copy()
    for col in ('open', 'high', 'low', 'close', 'volume', 'turnover'):
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    close, high, low = frame['close'], frame['high'], frame['low']
    volume, turnover = frame['volume'], frame['turnover']
    typical = (high + low + close) / 3
    direction = np.sign(close.diff()).fillna(0)
    frame['obv'] = (direction * volume).cumsum()

    flow = typical * volume
    positive = flow.where(typical.diff() > 0, 0.0).rolling(14, min_periods=14).sum()
    negative = flow.where(typical.diff() < 0, 0.0).rolling(14, min_periods=14).sum()
    frame['mfi14'] = (100 * positive / (positive + negative).replace(0, np.nan)).clip(0, 100)

    spread = (high - low).replace(0, np.nan)
    multiplier = ((close - low) - (high - close)) / spread
    money_volume = multiplier.fillna(0) * volume
    frame['cmf20'] = (money_volume.rolling(20, min_periods=20).sum()
                       / volume.rolling(20, min_periods=20).sum().replace(0, np.nan))
    frame['ad_line'] = money_volume.cumsum()
    frame['chaikin_3_10'] = (frame['ad_line'].ewm(span=3, adjust=False).mean()
                              - frame['ad_line'].ewm(span=10, adjust=False).mean())

    daily_vwap = turnover / volume.replace(0, np.nan)
    frame['daily_vwap_gap_pct'] = 100 * (close / daily_vwap - 1)
    vol_mean = volume.rolling(20, min_periods=20).mean()
    vol_std = volume.rolling(20, min_periods=20).std(ddof=0).replace(0, np.nan)
    frame['volume_z20'] = (volume - vol_mean) / vol_std
    frame['amihud_krw_billion'] = (close.pct_change().abs()
                                   / (turnover / 1e9).replace(0, np.nan))
    return frame.replace([np.inf, -np.inf], np.nan)


def load_completed(log: Path, output: Path) -> dict[str, dict]:
    completed = {}
    if log.exists():
        for line in log.read_text().splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            path = output / item['file']
            if path.is_file() and path.stat().st_size == item['bytes']:
                completed[item['symbol']] = item
    return completed


def append_record(path: Path, item: dict) -> None:
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def connection():
    import psycopg2
    values = env_keys(RO_ENV)
    needed = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    if any(not values.get(key) for key in needed):
        raise RuntimeError('Read-only DB credentials are incomplete')
    conn = psycopg2.connect(host=values['DB_HOST'], port=values['DB_PORT'],
                            dbname=values['DB_NAME'], user=values['DB_USER'],
                            password=values['DB_PASSWORD'], connect_timeout=5,
                            application_name='regime190_readonly_price_derivation')
    conn.set_session(readonly=True, autocommit=True)
    return conn


def symbols(conn, state_dir: Path) -> list[str]:
    index_path = state_dir / 'db_daily_price_symbols.json'
    if index_path.exists():
        data = json.loads(index_path.read_text())
        if data.get('target_end') == TARGET_END:
            return data['symbols']
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout='120s'")
        cur.execute('SELECT DISTINCT symbol FROM public.domestic_daily_price '
                    'WHERE market_date <= %s AND symbol IS NOT NULL ORDER BY symbol', (TARGET_END,))
        result = [row[0] for row in cur.fetchall()]
    temp = index_path.with_suffix('.json.tmp')
    temp.write_text(json.dumps({'target_end': TARGET_END, 'symbols': result,
                                'created_at_utc': utc_now()}, ensure_ascii=False))
    temp.replace(index_path)
    return result


def run_batch(state_dir: Path = DEFAULT_STATE, max_symbols: int = 100) -> dict:
    if max_symbols < 1:
        raise ValueError('max_symbols must be positive')
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = state_dir / 'db_daily_price_derived'
    output.mkdir(exist_ok=True, mode=0o700)
    log = state_dir / 'db_daily_price_derived_manifest.jsonl'
    completed = load_completed(log, output)
    if shutil.disk_usage(state_dir).free < MIN_FREE_BYTES:
        return {'state': 'DISK_WAIT', 'completed_symbols': len(completed),
                'new_symbols': 0, 'new_source_rows': 0}
    conn = connection()
    try:
        all_symbols = symbols(conn, state_dir)
        pending = [symbol for symbol in all_symbols if symbol not in completed]
        new_symbols = 0
        new_rows = 0
        for symbol in pending[:max_symbols]:
            if shutil.disk_usage(state_dir).free < MIN_FREE_BYTES:
                break
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', symbol):
                raise RuntimeError('Unexpected symbol characters')
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout='60s'")
                cur.execute('''SELECT market_date,symbol,market,open,high,low,close,
                               volume,turnover,available_at
                               FROM public.domestic_daily_price
                               WHERE symbol=%s AND market_date<=%s ORDER BY market_date''',
                            (symbol, TARGET_END))
                data = cur.fetchall()
                columns = [item.name for item in cur.description]
            if not data:
                continue
            frame = derive(pd.DataFrame(data, columns=columns))
            frame['pit_status'] = 'PIT_UNVERIFIED'
            frame['market_mapping_status'] = np.where(
                frame['market'].fillna('').eq(''), 'MARKET_MAPPING_UNVERIFIED', 'RECORDED_MARKET_UNVERIFIED')
            frame['source_id'] = 'public.domestic_daily_price:kis'
            fields = ['market_date', 'symbol', 'market', 'available_at', 'source_id',
                      'pit_status', 'market_mapping_status', *METRICS.values()]
            filename = f'{symbol}.csv.gz'
            path = output / filename
            temp = output / (filename + '.part')
            with gzip.open(temp, 'wt', encoding='utf-8', newline='') as stream:
                frame[fields].to_csv(stream, index=False, na_rep='')
            if temp.stat().st_size > MAX_OUTPUT_BYTES:
                temp.unlink()
                raise RuntimeError('Per-symbol output exceeds size limit')
            digest = sha256_file(temp)
            temp.replace(path)
            item = {'symbol': symbol, 'file': filename, 'sha256': digest,
                    'bytes': path.stat().st_size, 'rows': len(frame),
                    'first_date': str(frame['market_date'].min()),
                    'last_date': str(frame['market_date'].max()),
                    'missing_market_rows': int(frame['market'].isna().sum() + frame['market'].eq('').sum()),
                    'valid_counts': {str(i): int(frame[col].notna().sum()) for i, col in METRICS.items()},
                    'completed_at_utc': utc_now(), 'pit_status': 'PIT_UNVERIFIED'}
            append_record(log, item)
            completed[symbol] = item
            new_symbols += 1
            new_rows += len(frame)
        return {'state': 'COMPLETE' if len(completed) == len(all_symbols) else 'IN_PROGRESS',
                'total_symbols': len(all_symbols), 'completed_symbols': len(completed),
                'new_symbols': new_symbols, 'new_source_rows': new_rows,
                'indicator_ids': sorted(METRICS)}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--max-symbols', type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(run_batch(args.state_dir, args.max_symbols), ensure_ascii=False))


if __name__ == '__main__':
    main()
