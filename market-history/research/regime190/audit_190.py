#!/usr/bin/env python3
"""Publish conservative per-indicator metadata for all 190 research specifications."""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from worker import DB_MAP, DEFAULT_STATE, FRED, HERE

DB_PRICE = {41, 42, 43, 44, 45, 46, 49, 51}
DB_RATES = {107, 108, 109, 110, 111}


def read_csv(path: Path) -> dict[int, dict]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    ids = [int(row['indicator_id']) for row in rows]
    if len(ids) != len(set(ids)) or sorted(ids) != list(range(1, 191)):
        raise RuntimeError(f'190 unique indicator IDs required in {path.name}')
    return {int(row['indicator_id']): row for row in rows}


def write_csv(path: Path, rows: list[dict]) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def candidate(i: int) -> tuple[str, str, str]:
    if i in DB_PRICE:
        return ('public.domestic_daily_price', 'market_date,symbol,market,open,high,low,close,volume,turnover,available_at',
                'Actual stock-level series; historic exchange membership unverified')
    if i in DB_RATES:
        return ('public.market_rates_snapshot', 'series_key,data_date,value,unit,available_at,released_at,vintage_date',
                'Actual 2025-2026 rate components; full history and release vintages missing')
    if 41 <= i <= 72:
        extra = {47: 'anchor definition and pre-anchor trade data',
                 48: 'trade-price histogram or tick prints',
                 50: 'shares outstanding as of each date',
                 52: 'as-of market membership and declining-stock turnover'}
        return ('public.domestic_daily_price', extra.get(i, 'OHLCV plus as-of KOSPI/KOSDAQ membership and required sector/cap fields'),
                'Candidate columns only; mostly empty historic market code')
    if 73 <= i <= 82:
        return ('public.orderbook_depth_snapshot', 'timestamped depth, order/trade events where required',
                'Recent component or access probe only; exact indicator and historic licensed coverage unverified')
    if 83 <= i <= 94:
        table = 'public.domestic_short_sale_daily' if i in (91, 92) else 'public.domestic_credit_daily' if i == 93 else 'public.domestic_investor_daily'
        return (table, 'indicator-specific investor, futures, ETF, short or credit series',
                'Candidate daily columns do not establish the specified market-wide indicator')
    if 95 <= i <= 106:
        return ('', 'options and futures contract observations, implied volatility and open interest',
                'Existing generic market_rates_snapshot.value mapping is unrelated to this definition')
    if 107 <= i <= 115:
        return ('public.market_rates_snapshot', 'exact series_key values, units, release and revision history',
                'Short current DB history; missing component series for the specified definition')
    if 129 <= i <= 137:
        return ('public.market_fx_snapshot or public.us_market_daily', 'exact market series and observation times',
                'Candidate table and scope require direct series validation')
    if 138 <= i <= 151:
        return ('', 'official export, activity, prices or macro release series',
                'Existing generic market_rates_snapshot.value mapping is unrelated to this definition')
    if 152 <= i <= 163:
        return ('', 'as-of listed-company universe, filings, revision and publication time',
                'One-company 2025 sample cannot establish market-wide history')
    if 164 <= i <= 181:
        return ('public.event_shadow_snapshot', 'dated source document, published_at and extracted event value',
                'Source page or text component is not an indicator time series')
    if 182 <= i <= 190:
        return ('', 'ETF holdings, derivatives, cross-asset or composite series',
                'Existing generic market_index_snapshot.value mapping is unrelated to this definition')
    if i in DB_MAP:
        table, field = DB_MAP[i]
        return ('public.' + table, field, 'Candidate field only; definition and data series unverified')
    return ('', '', 'Use the specified official source and verify actual observations')


def run(state_dir: Path = DEFAULT_STATE) -> dict:
    spec = read_csv(HERE / 'indicator_spec.csv')
    inventory = read_csv(HERE / 'inventory_190.csv')
    conn = sqlite3.connect(f'file:{state_dir/"checkpoint.sqlite"}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    tasks = {row['indicator_id']: dict(row) for row in conn.execute('SELECT * FROM tasks')}
    conn.close()
    if sorted(tasks) != list(range(1, 191)):
        raise RuntimeError('Checkpoint must contain exactly 190 unique IDs')
    fred_manifests = {}
    for path in (state_dir / 'fred_initial_vintages').glob('*.manifest.json'):
        item = json.loads(path.read_text())
        fred_manifests[item['series']] = item
    mapping, attempts, coverage, quality = [], [], [], []
    for i in range(1, 191):
        definition, source, task = spec[i], inventory[i], tasks[i]
        if definition['name'] != source['name'] or definition['priority'] != source['priority']:
            raise RuntimeError(f'Inventory and specification differ for ID {i}')
        table, required, caveat = candidate(i)
        vintage_rows = sum(fred_manifests[series]['rows'] for series in FRED.get(i, [])
                           if series in fred_manifests)
        series_rows = int(source['valid_count'] or 0) if source['derived_series_path'] else 0
        if i in DB_PRICE and task['state'] == 'PARTIAL':
            mapping_state = 'DERIVED_SYMBOL_SERIES_MARKET_UNVERIFIED'
        elif i in DB_RATES and task['state'] == 'PARTIAL':
            mapping_state = 'DERIVED_SHORT_HISTORY_PIT_UNVERIFIED'
        elif i <= 40 and series_rows:
            mapping_state = 'DERIVED_INDEX_SERIES_PIT_UNVERIFIED'
        elif task['state'] == 'PARTIAL':
            mapping_state = 'RAW_COMPONENT_OR_SOURCE_PAGE_ONLY'
        elif i in (77, 79, 80, 81, 123, 124, 172, 173, 176, 177, 179, 180):
            mapping_state = 'SOURCE_ACCESS_ONLY'
        elif 157 <= i <= 163:
            mapping_state = 'AS_OF_UNIVERSE_MISSING'
        else:
            mapping_state = 'CANDIDATE_UNVERIFIED'
        market_status = ('MARKET_MAPPING_UNVERIFIED' if 41 <= i <= 72 else
                         'AS_OF_UNIVERSE_MISSING' if 152 <= i <= 163 else
                         'SOURCE_SCOPE_UNVERIFIED')
        mapping.append(dict(indicator_id=i, name=definition['name'], priority=definition['priority'],
                            family=definition['family'], target_market=source['target_market'],
                            required_inputs=required or definition['source_candidate'], candidate_table=table,
                            mapping_status=mapping_state, actual_indicator_series_rows=series_rows,
                            source_caveat=caveat, market_scope_status=market_status,
                            pit_status=source['pit_status'], next_action=task['next_action'] or ''))
        mapping[-1]['initial_vintage_component_rows'] = vintage_rows
        attempts.append(dict(indicator_id=i, name=definition['name'],
                             worker_state=task['state'], attempt_count=task['attempt_count'],
                             provider_request_count=task['provider_attempt_count'],
                             fallback_or_local_attempt_count=task['fallback_attempt_count'],
                             last_attempt_at=task['last_attempt_at'] or '',
                             last_result=task['http_or_db_result'] or '',
                             evidence=task['blocking_evidence'] or '',
                             next_retry_or_action=task['next_retry_at'] or task['next_action'] or '',
                             collection_attempt_complete='no'))
        attempts[-1]['initial_vintage_component_rows'] = vintage_rows
        coverage.append(dict(indicator_id=i, name=definition['name'],
                             availability_status=source['availability_status'],
                             actual_indicator_series_rows=series_rows,
                             recorded_component_or_summary_rows=source['row_count'] or '0',
                             first_date=source['first_date'], last_date=source['last_date'],
                             frequency=source['frequency'], target_market=source['target_market'],
                             market_scope_status=market_status,
                             source_kind=source['actual_source'],
                             pit_eligible_rows=0, backtest_eligible='no'))
        coverage[-1]['initial_vintage_component_rows'] = vintage_rows
        quality.append(dict(indicator_id=i, name=definition['name'],
                            actual_indicator_series_rows=series_rows,
                            source_history_status=('SHORT_HISTORY' if i in DB_RATES else
                                                   'MARKET_MAPPING_UNVERIFIED' if i in DB_PRICE else
                                                   'UNVERIFIED'),
                            missing_pct=source['missing_pct'],
                            duplicate_check='NOT_ROW_AUDITED' if not series_rows else 'SOURCE_KEY_OR_DERIVATION_CHECKED',
                            market_mapping_status=market_status,
                            formula_status='RESEARCH_DERIVATION' if i in DB_PRICE | DB_RATES else 'UNVERIFIED',
                            publication_vintage_status='UNVERIFIED',
                            pit_status=source['pit_status'],
                            final_quality_status='PARTIAL' if series_rows else 'NOT_VALIDATED',
                            blocking_evidence=task['blocking_evidence'] or caveat))
    write_csv(HERE / 'indicator_field_mapping.csv', mapping)
    write_csv(HERE / 'provider_attempts.csv', attempts)
    write_csv(HERE / 'data_coverage.csv', coverage)
    write_csv(HERE / 'quality_report.csv', quality)
    summary = {'generated_at_utc': datetime.now(timezone.utc).isoformat(),
               'indicator_ids': 190, 'duplicate_ids': 0,
               'worker_states': dict(Counter(task['state'] for task in tasks.values())),
               'derived_symbol_series_indicators': sorted(i for i in DB_PRICE if tasks[i]['state'] == 'PARTIAL'),
               'derived_rate_indicators': sorted(i for i in DB_RATES if tasks[i]['state'] == 'PARTIAL'),
               'actual_indicator_series_rows_total': sum(x['actual_indicator_series_rows'] for x in coverage),
               'provider_requests_unattempted': sum(task['provider_attempt_count'] == 0 for task in tasks.values()),
               'fred_initial_vintage_series': len(fred_manifests),
               'pit_ready': 0, 'backtest': 'NOT_RUN_PIT_GATE',
               'collection_attempts_complete': False, 'all_data_acquired': False}
    (HERE / 'audit_190_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False))
