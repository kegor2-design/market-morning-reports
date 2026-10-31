#!/usr/bin/env python3
"""Read-only Regime190 evidence inventory and cutoff-ingestion reconciliation."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from build_pit_readiness import ROOT, build, read_index
from derive_db_daily import connection
from source_lineage_reconcile import atomic_text


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indicator_inventory(matrix: list[dict], audits: dict[int, dict],
                        mappings: dict[int, dict], pits: dict[int, dict]) -> list[dict]:
    result = []
    for item in matrix:
        key = int(item['indicator_id'])
        audit, mapping, pit = audits[key], mappings[key], pits[key]
        missing = []
        for field, value in (('publication_timestamp', pit['published_at']),
                             ('decision_time_availability', pit['available_at']),
                             ('historical_vintage', pit['vintage'])):
            if value.strip().lower() in {'', 'absent', 'unverified', 'no_data', 'current snapshot only'}:
                missing.append(field)
        if mapping['market_scope_status'] != 'VERIFIED':
            missing.append('historical_security_universe')
        if audit['calculation'] != '검증 완료':
            missing.append('calculation_validation')
        if item['pit_classification'] != 'PIT_VERIFIED':
            missing.append('independent_pit_approval')
        result.append({
            'indicator_id': key, 'name': item['name'],
            'pit_classification': item['pit_classification'],
            'required_historical_fields': mapping['required_inputs'],
            'original_provider': item['provider'],
            'event_date_evidence': 'UNVERIFIED',
            'observation_date_evidence': pit['observation_date'],
            'publication_timestamp_evidence': pit['published_at'],
            'ingestion_timestamp_evidence': pit['ingested_at'],
            'revision_date_evidence': pit['revision_history'],
            'effective_market_date_evidence': 'UNVERIFIED',
            'decision_timestamp_evidence': 'UNVERIFIED',
            'decision_time_availability_evidence': pit['available_at'],
            'historical_revision_policy': pit['revision_history'],
            'historical_vintage_evidence': pit['vintage'],
            'historical_security_universe': mapping['market_scope_status'],
            'survivorship_bias_exposure': audit['survivorship_risk'],
            'corporate_action_adjustment_policy': 'UNVERIFIED',
            'licensing_restrictions': 'UNVERIFIED; check provider terms before retrieval or redistribution',
            'alternative_source_candidate': audit['alternative_provider'],
            'missing_evidence': ';'.join(missing),
            'backtest_eligible': 'NO',
            'evidence_refs': item['evidence_refs'] + f';indicator_field_mapping.csv:{key}',
        })
    return result


def cutoff_snapshot(source_rows: list[dict], db_rows: list[tuple], runs: list[tuple]) -> dict:
    cohort = [row for row in source_rows if row['export_last_date'] == '2026-09-15'
              and row['source_last_date'] == '2026-09-15']
    by_day = dict(sorted(collections.Counter(row['last_collected_at'][:10]
                                             for row in cohort).items()))
    bulk = [row for row in db_rows if row[0] == '2026-09-17' and row[1] == 'kis']
    return {
        'schema_version': 1, 'queried_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_table': 'public.domestic_daily_price',
        'run_table': 'public.historical_backfill_run',
        'source_snapshot_cutoff_symbols': len(cohort),
        'cutoff_last_collected_date_counts': by_day,
        'collection_day_counts': [{'collection_date': day, 'source_name': name,
                                   'rows': count, 'symbols': symbols}
                                  for day, name, count, symbols in db_rows],
        'recorded_price_runs': [{'started_at': str(started), 'requested_symbols': requested,
                                 'success_symbols': success, 'inserted_rows': inserted,
                                 'status': status, 'details_keys': sorted((details or {}).keys())}
                                for started, requested, success, inserted, status, details in runs],
        'overnight_bulk_load_observed': bool(bulk and bulk[0][2] > 1_000_000),
        'cause_status': 'PARTIALLY_CONFIRMED',
        'cause_finding': 'A large KIS-labelled overnight load stopped at 2026-09-15; '
                         'the recorded later daily price run had a much smaller candidate scope. '
                         'The original bulk request, provider response and target ledger are unavailable.',
        'pit_status': 'UNVERIFIED',
        'limitations': ['collected_at is an ingestion/update timestamp, not publication time',
                        'UPSERT can replace earlier collected_at and raw_json',
                        'historical_backfill_run stores aggregate counts, not requested symbol IDs',
                        'source/export comparison is a snapshot; the operating source can advance'],
    }


def query_collection() -> tuple[list[tuple], list[tuple], tuple]:
    db = connection()
    try:
        with db.cursor() as cur:
            cur.execute("SET statement_timeout='30s'")
            cur.execute("SELECT collected_at::date::text,source_name,count(*),count(DISTINCT symbol) "
                        "FROM public.domestic_daily_price "
                        "WHERE collected_at >= %s AND collected_at < %s "
                        "GROUP BY 1,2 ORDER BY 1,2", ('2026-09-15', '2026-09-19'))
            daily = cur.fetchall()
            cur.execute("SELECT started_at,requested_symbols,success_symbols,inserted_rows,status,details_json "
                        "FROM public.historical_backfill_run "
                        "WHERE dataset=%s AND started_at >= %s AND started_at < %s "
                        "ORDER BY started_at", ('price', '2026-09-15', '2026-09-19'))
            runs = cur.fetchall()
            cur.execute("SELECT count(*),count(*) FILTER (WHERE status='OK'),"
                        "count(*) FILTER (WHERE released_at IS NOT NULL),"
                        "min(vintage_date),max(vintage_date) "
                        "FROM public.economic_indicator_vintage")
            vintages = cur.fetchone()
        return daily, runs, vintages
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, default=Path.home() / 'MyDream2000/research/regime190/checkpoint.sqlite')
    parser.add_argument('--cutoff-output', type=Path, required=True)
    parser.add_argument('--indicator-output', type=Path, required=True)
    parser.add_argument('--summary-output', type=Path, required=True)
    args = parser.parse_args()
    matrix, pit_summary = build(ROOT / 'indicator_audit_20261031.csv', ROOT / 'pit_audit.csv', args.db)
    inventory = indicator_inventory(matrix, read_index(ROOT / 'indicator_audit_20261031.csv'),
                                    read_index(ROOT / 'indicator_field_mapping.csv'),
                                    read_index(ROOT / 'pit_audit.csv'))
    with (ROOT / 'source_lineage_symbols_20261031.csv').open(newline='', encoding='utf-8') as stream:
        source_rows = list(csv.DictReader(stream))
    daily, runs, vintages = query_collection()
    cutoff = cutoff_snapshot(source_rows, daily, runs)
    cutoff['source_lineage_sha256'] = sha256(ROOT / 'source_lineage_symbols_20261031.csv')
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(inventory[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(inventory)
    summary = {'schema_version': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
               'indicator_count': len(inventory), 'classification_counts': pit_summary['classification_counts'],
               'pit_verified': sum(row['pit_classification'] == 'PIT_VERIFIED' for row in inventory),
               'backtest_status': 'BLOCKED' if not any(row['backtest_eligible'] == 'YES' for row in inventory) else 'REVIEW_REQUIRED',
               'sqlite_integrity': pit_summary['sqlite_integrity'],
               'source_sha256': {name: sha256(ROOT / name) for name in
                                 ('indicator_audit_20261031.csv', 'indicator_field_mapping.csv',
                                  'pit_audit.csv')},
               'candidate_source_urls': {
                   'KRX_listing': 'https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT200.jsp',
                   'KRX_delisting': 'https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT238.jsp',
                   'FRED_vintage_api': 'https://fred.stlouisfed.org/docs/api/fred/series_observations.html'},
               'candidate_sources_status': 'NOT_ACQUIRED_FOR_ROW_LEVEL_PIT',
               'economic_vintage_db_finding': {
                   'rows': vintages[0], 'ok_rows': vintages[1],
                   'rows_with_released_at': vintages[2],
                   'first_vintage_date': str(vintages[3]) if vintages[3] else None,
                   'last_vintage_date': str(vintages[4]) if vintages[4] else None},
               'approval_policy': 'No PIT promotion from observation dates, ingestion dates, or assumed availability'}
    atomic_text(args.cutoff_output, json.dumps(cutoff, ensure_ascii=False, indent=2) + '\n')
    atomic_text(args.indicator_output, buffer.getvalue())
    atomic_text(args.summary_output, json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'cutoff': cutoff['cause_status'], 'pit_verified': summary['pit_verified'],
                      'backtest_status': summary['backtest_status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
