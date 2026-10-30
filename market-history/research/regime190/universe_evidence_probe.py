#!/usr/bin/env python3
"""Read-only coverage audit; never substitutes today's market for past membership."""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from derive_db_daily import connection

KRX_NEW = 'https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT200.jsp'
KRX_DELISTED = 'https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT238.jsp'
KRX_DETAIL = 'https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain'


def audit(symbol_csv: Path) -> dict:
    with symbol_csv.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    symbols = {row['symbol'] for row in rows}
    if len(symbols) != len(rows):
        raise ValueError('Duplicate source symbols')
    with closing(connection()) as db:
        with db.cursor() as cur:
            cur.execute("SET statement_timeout='15s'")
            cur.execute("SELECT symbol, market, mst_market, stck_lstn_date, updated_at "
                        "FROM public.symbol_master WHERE symbol = ANY(%s)", (list(symbols),))
            master = {symbol: (market, mst_market, listing, updated)
                      for symbol, market, mst_market, listing, updated in cur.fetchall()}
            cur.execute("SELECT count(*), count(*) FILTER (WHERE stck_lstn_date ~ '^[0-9]{8}$' "
                        "AND stck_lstn_date <> '00000000'), "
                        "count(*) FILTER (WHERE market IN ('KOSPI','KOSDAQ')) "
                        "FROM public.symbol_master")
            total, listing_dates, current_markets = cur.fetchone()
    current_overlap = sum(symbol in master for symbol in symbols)
    current_listing_covered = sum(bool(master[symbol][2] and len(master[symbol][2]) == 8
                                       and master[symbol][2].isdigit() and master[symbol][2] != '00000000')
                                  for symbol in symbols if symbol in master)
    source_market_latest = sum(row['last_market'] in {'KOSPI', 'KOSDAQ'} for row in rows)
    mst = [Path.home() / 'MyDream2000/data/kospi_code.mst',
           Path.home() / 'MyDream2000/data/kosdaq_code.mst']
    return {'schema_version': 1, 'collected_at_utc': datetime.now(timezone.utc).isoformat(),
            'source_identity': 'read-only symbol_master; source/export per-symbol lineage; local MST snapshots',
            'source_symbol_count': len(symbols), 'current_master_rows': total,
            'current_master_listing_date_rows': listing_dates,
            'current_master_market_rows': current_markets,
            'source_symbols_in_current_master': current_overlap,
            'source_symbols_with_current_listing_date': current_listing_covered,
            'source_symbols_with_market_in_latest_price_row': source_market_latest,
            'local_mst_snapshots': [{'path': str(path), 'exists': path.is_file(),
                                     'modified_at_utc': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                                     if path.is_file() else None} for path in mst],
            'historical_membership_status': 'UNVERIFIED',
            'current_master_status': 'PARTIAL',
            'coverage_classification': {'current_master_counts': 'VERIFIED',
                                        'current_master_as_historical_proxy': 'UNVERIFIED',
                                        'local_delisting_archive': 'UNAVAILABLE'},
            'locally_verified_asof_market_membership_rows': 0,
            'official_candidate_sources': [{'source': 'KRX new listings', 'url': KRX_NEW, 'status': 'UNVERIFIED_FOR_FULL_HISTORY'},
                                           {'source': 'KRX delistings', 'url': KRX_DELISTED, 'status': 'UNVERIFIED_FOR_FULL_HISTORY'},
                                           {'source': 'KIND listing and transfer notices', 'url': KRX_DETAIL, 'status': 'UNVERIFIED_FOR_FULL_HISTORY'}],
            'minimum_evidence': ['Dated KOSPI/KOSDAQ membership or listing/delisting/transfer events for every symbol',
                                 'Suspension intervals and first-tradable dates',
                                 'Stable symbol/ISIN mapping across corporate actions',
                                 'Source publication/availability timestamps and coverage of delisted securities'],
            'survivorship_risk': 'Current symbol_master and current MST snapshots do not establish historical membership'}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--per-symbol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.per_symbol)
    fd, name = tempfile.mkstemp(prefix='.universe-', dir=args.output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, args.output)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(json.dumps({'source_symbols': report['source_symbol_count'],
                      'current_master_overlap': report['source_symbols_in_current_master'],
                      'historical_membership': report['historical_membership_status']}))


if __name__ == '__main__':
    main()
