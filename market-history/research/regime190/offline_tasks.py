"""Whitelisted read-only Regime190 tasks for the offline research worker."""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from .build_pit_readiness import ROOT, build
from .worker import RO_ENV, env_keys
from . import blocker_resolution

PRIVATE_DB = Path.home() / 'MyDream2000/research/regime190/checkpoint.sqlite'


def connection():
    import psycopg2
    values = env_keys(RO_ENV)
    needed = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    if any(not values.get(key) for key in needed):
        raise RuntimeError('Read-only DB credentials incomplete')
    db = psycopg2.connect(host=values['DB_HOST'], port=values['DB_PORT'],
                          dbname=values['DB_NAME'], user=values['DB_USER'],
                          password=values['DB_PASSWORD'], connect_timeout=5,
                          application_name='regime190_offline_research')
    db.set_session(readonly=True, autocommit=True)
    return db


def execute(task: dict, queue: dict) -> dict:
    kind = task['task_type']
    if kind == 'blocker_classify':
        result = blocker_resolution.inventory()
        # Check declared local checkpoint references; existence is verified by the follow-up.
        candidates = [row for row in result['records'] if row['execution_class'] == 'SERVER_EXECUTABLE']
        selected, refs = [], set()
        for row in sorted(candidates, key=lambda row: (row['resolution_priority'], row['indicator_id'])):
            ref = row['existing_data']['local_checkpoint']['derived_series_path']
            if ref not in refs:
                selected.append(row['indicator_id'])
                refs.add(ref)
            if len(selected) == 12:
                break
        result['followup_indicator_ids'] = selected
        return result
    if kind == 'local_evidence_check':
        return blocker_resolution.check_local(int(task['indicator_id']))
    if kind == 'source_snapshot':
        db = connection()
        try:
            with db.cursor() as cur:
                cur.execute("SET statement_timeout='15s'")
                cur.execute('SELECT max(market_date), count(*), count(DISTINCT symbol) '
                            'FROM public.domestic_daily_price WHERE market_date >= %s',
                            (date.today() - timedelta(days=7),))
                latest, rows, symbols = cur.fetchone()
                cur.execute('SELECT max(started_at), count(*) FROM public.historical_backfill_run '
                            'WHERE dataset=%s AND started_at >= %s',
                            ('price', date.today() - timedelta(days=7)))
                last_run, runs = cur.fetchone()
            return {'source': 'public.domestic_daily_price', 'latest_market_date': str(latest) if latest else None,
                    'recent_rows': rows, 'recent_symbols': symbols,
                    'recent_price_runs': runs, 'last_price_run': str(last_run) if last_run else None,
                    'query_window_start': str(date.today() - timedelta(days=7)),
                    'source_role': 'read_only', 'pit_approval': False}
        finally:
            db.close()
    if kind == 'pit_recheck':
        rows, summary = build(ROOT / 'indicator_audit_20261031.csv', ROOT / 'pit_audit.csv', PRIVATE_DB)
        statuses = {str(row['indicator_id']): row['pit_classification'] for row in rows}
        prior = next((json.loads(Path(record['output_artifacts'][0]).read_text())['result'].get('indicator_statuses', {})
                      for record in reversed(list(queue['tasks'].values()))
                      if record['task_type'] == 'pit_recheck' and record['status'] == 'COMPLETED'
                      and record['output_artifacts']), {})
        return {'indicator_count': len(rows), 'classification_counts': summary['classification_counts'],
                'pit_verified': summary['classification_counts']['PIT_VERIFIED'],
                'indicator_statuses': statuses,
                'status_changes': {key: {'before': prior.get(key), 'after': value}
                                   for key, value in statuses.items() if prior and prior.get(key) != value},
                'sqlite_integrity': summary['sqlite_integrity'],
                'input_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in ('indicator_audit_20261031.csv', 'pit_audit.csv')},
                'pit_approval': False}
    if kind == 'backtest_gate':
        dependency = task['dependencies'][0]
        record = queue['tasks'][dependency]
        result = json.loads(Path(record['output_artifacts'][0]).read_text())['result']
        return {'status': 'BACKTEST_BLOCKED' if result['pit_verified'] == 0 else 'REVIEW_REQUIRED',
                'reason': 'No PIT-approved indicator' if result['pit_verified'] == 0
                          else 'Subset still needs source, universe and leakage review',
                'pit_verified': result['pit_verified'], 'backtest_executed': False}
    raise ValueError('Unregistered offline task type')


def verify(task: dict, result: dict) -> None:
    kind = task['task_type']
    if kind == 'blocker_classify':
        if (result.get('indicator_count') != 190 or len(result.get('records', [])) != 190
                or {row['indicator_id'] for row in result['records']} != set(range(1, 191))
                or result.get('pit_approvals_added') != 0
                or len(result.get('followup_indicator_ids', [])) > 12):
            raise ValueError('Blocker inventory invalid')
    elif kind == 'local_evidence_check':
        if (result.get('indicator_id') != task.get('indicator_id') or result.get('pit_approval') is not False
                or result.get('file_status') not in {'PRESENT', 'MANIFEST_SAMPLE_VALIDATED', 'NO_INDICATOR_ROWS',
                                                     'ABSENT', 'TOO_LARGE_FOR_BOUNDED_CHECK',
                                                     'MISSING_OR_OUTSIDE_RESEARCH_ROOT'}):
            raise ValueError('Local evidence check invalid')
    elif kind == 'source_snapshot':
        if result.get('source_role') != 'read_only' or result.get('recent_rows', -1) < 0:
            raise ValueError('Source snapshot invalid')
    elif kind == 'pit_recheck':
        if (result.get('indicator_count') != 190 or result.get('sqlite_integrity') != 'ok'
                or sum(result['classification_counts'].values()) != 190
                or len(result['indicator_statuses']) != 190
                or result['pit_verified'] != result['classification_counts']['PIT_VERIFIED']):
            raise ValueError('PIT reconciliation failed')
    elif kind == 'backtest_gate':
        if result.get('status') not in {'BACKTEST_BLOCKED', 'REVIEW_REQUIRED'} or result.get('backtest_executed'):
            raise ValueError('Backtest gate invalid')
    else:
        raise ValueError('Unregistered offline task type')
