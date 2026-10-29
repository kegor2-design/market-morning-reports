"""Read the collector checkpoint without taking its execution lock or writing files."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def snapshot(state_dir: Path) -> dict:
    db = state_dir / 'checkpoint.sqlite'
    conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=5)
    try:
        counts = dict(conn.execute('SELECT state,count(*) FROM tasks GROUP BY state'))
        latest_attempt = conn.execute('SELECT max(last_attempt_at) FROM tasks').fetchone()[0]
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        requests_24h, rows_24h = conn.execute(
            "SELECT count(*),coalesce(sum(row_count),0) FROM requests "
            "WHERE result='ACQUIRED' AND attempted_at>=?", (cutoff,)
        ).fetchone()
        request_total = conn.execute('SELECT count(*) FROM requests').fetchone()[0]
    finally:
        conn.close()
    progress_path = state_dir / 'progress.json'
    heartbeat = json.loads(progress_path.read_text()).get('updated_at_utc') if progress_path.exists() else None
    raw = list((state_dir / 'raw').glob('*'))
    newest_raw = max((p.stat().st_mtime for p in raw if p.is_file()), default=None)
    derived_log = state_dir / 'db_daily_price_derived_manifest.jsonl'
    derived = [json.loads(line) for line in derived_log.read_text().splitlines() if line.strip()] if derived_log.exists() else []
    unique_derived = {item['symbol']: item for item in derived}
    symbol_index = state_dir / 'db_daily_price_symbols.json'
    total_symbols = len(json.loads(symbol_index.read_text())['symbols']) if symbol_index.exists() else 0
    derived_24h = sum(item['rows'] for item in unique_derived.values()
                      if item['completed_at_utc'] >= cutoff)
    last_derived = max((item['completed_at_utc'] for item in unique_derived.values()), default=None)
    return {
        'state': 'IN_PROGRESS' if counts.get('PENDING', 0) or counts.get('RETRY_WAIT', 0)
                 or counts.get('NEEDS_REVIEW', 0) else 'ATTEMPTS_PROCESSED_NOT_FULLY_VERIFIED',
        'counts': counts, 'total': sum(counts.values()),
        'heartbeat_at': heartbeat, 'last_real_request_at': latest_attempt,
        'last_new_raw_at': datetime.fromtimestamp(newest_raw, timezone.utc).isoformat() if newest_raw else None,
        'last_new_derived_at': last_derived,
        'derived_symbols': len(unique_derived),
        'remaining_derived_symbols': max(0, total_symbols - len(unique_derived)),
        'derived_source_rows': sum(item['rows'] for item in unique_derived.values()),
        'new_derived_rows_24h': derived_24h,
        'verified_request_records_total': request_total,
        'new_verified_rows_24h': rows_24h,
        'successful_request_records_24h': requests_24h,
        'remaining_queue': counts.get('PENDING', 0) + counts.get('RETRY_WAIT', 0)
                           + counts.get('NEEDS_REVIEW', 0),
        'pit_ready': 0,
    }
