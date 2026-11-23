"""Reviewed source discovery. Catalog entries give requirements, never execution authority."""
import hashlib
import json
import os
import re

from .isolated_codex import PRIVATE_ROOT
from .source_adapters import REGISTRY

ARCHIVES = {
    'par-yield-curve-rates-2010-2019.csv': 'a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254',
    'par-yield-curve-rates-2020-2023.csv': '25877e5541442e8c8c642a3cf9709d8c20eb2c1603556e3ebd84545f1f0acfe2',
}
CATALOG = {
    'KOSPI': ('domestic_index_daily', 'KRX', 'KOSPI series daily index'),
    'KOSDAQ': ('domestic_index_daily', 'KRX', 'KOSDAQ series daily index'),
    'MARKET_BREADTH': ('market_breadth_summary', 'KRX', 'Market-wide issues advancing and declining'),
    'FOREIGN_SPOT': ('domestic_investor_daily', 'KRX', 'Investor trading by market'),
    'FOREIGN_FUTURES': (None, 'KRX', 'Derivatives investor trading'),
    'KRX_CALENDAR': (None, 'KRX', 'Exchange trading calendar'),
    'KOSPI200_MEMBERS': (None, 'KRX', 'Historical index membership and effective dates'),
    'CORPORATE_ACTIONS': (None, 'KRX', 'Dated corporate actions and adjustment factors'),
    'KOREAN_MACRO': (None, 'ECOS', 'Statistical series and publication vintage'),
}


def discover(requirement):
    for source, adapter in REGISTRY.items():
        if requirement in adapter.series:
            return dict(requirement=requirement, source=source, status='REVIEWED_ADAPTER',
                        pit='REQUIRES_ROW_RELEASE_AND_ACCESS_EVIDENCE')
    if requirement not in CATALOG:
        return dict(requirement=requirement, status='UNSUPPORTED', source=None)
    table, source, product = CATALOG[requirement]
    return dict(requirement=requirement, candidate_table=table, source=source, product=product,
                status='REQUIRES_ACCESS_AND_ADAPTER_REVIEW', pit='UNVERIFIED')


def korean_requirements():
    return [discover(name) for name in CATALOG if name != 'KOREAN_MACRO']


def capability_review(requirements, methods):
    sources = [discover(name) for name in requirements]
    return {'required_data': requirements, 'required_methods': methods, 'sources': sources,
            'execution_authorized': False,
            'next_action': 'REVIEW_OFFICIAL_PRODUCT_TERMS_ACCESS_AND_ADAPTER',
            'resume_condition': 'Host registers missing capabilities and validates the original goal'}


def explicit_requirements(goal):
    # Optional structured annotations preserve names the researcher supplied.
    def labels(kind):
        return list(dict.fromkeys(re.findall(r'\[' + kind + r':([^\]\n]{1,120})\]', goal)))
    return capability_review(labels('data'), labels('method'))


def inspect_database(items):
    import psycopg2
    from psycopg2 import sql
    # The CLI receives the read-only research account from its caller.
    # Only fixed registry identifiers can enter a query. Raw provider JSON stays private.
    fields = {'domestic_index_daily': ('market_date', 'index_code', 'market_division', 'source_name', 'available_at', 'collected_at'),
              'domestic_investor_daily': ('market_date', 'symbol', 'source_name', 'available_at', 'collected_at'),
              'market_breadth_summary': ('snapshot_time', 'universe_count', 'advance_count', 'decline_count')}
    connection = psycopg2.connect(host=os.environ['DB_HOST'], port=os.environ['DB_PORT'],
        dbname=os.environ['DB_NAME'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
        connect_timeout=3, options='-c default_transaction_read_only=on -c statement_timeout=2000')
    try:
        with connection, connection.cursor() as cur:
            tables = sorted({x['candidate_table'] for x in items if x.get('candidate_table') in fields})
            for table in tables:
                cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' "
                            "AND table_name=%s ORDER BY ordinal_position LIMIT 128", (table,))
                columns = dict(cur)
                if not set(fields[table]) <= columns.keys():
                    continue
                cur.execute("SELECT has_table_privilege(current_user, %s, 'SELECT')", ('public.' + table,))
                if not cur.fetchone()[0]:
                    continue
                cur.execute(sql.SQL('SELECT {} FROM public.{} LIMIT 3').format(
                    sql.SQL(', ').join(map(sql.Identifier, fields[table])), sql.Identifier(table)))
                rows = [dict(zip(fields[table], row)) for row in cur]
                date_col = sql.Identifier(fields[table][0])
                bounds = []
                for ordering in ('ASC', 'DESC'):
                    stmt = sql.SQL('SELECT {d} FROM public.{t} WHERE {d} IS NOT NULL '
                                   'ORDER BY {d} {order} LIMIT 1').format(
                        d=date_col, t=sql.Identifier(table), order=sql.SQL(ordering))
                    cur.execute(sql.SQL('EXPLAIN (FORMAT JSON) ') + stmt)
                    # Avoid an unbounded sort/scan even when estimates are stale.
                    plan = cur.fetchone()[0][0]['Plan']
                    child = plan.get('Plans', [{}])[0]
                    if child.get('Node Type') in ('Index Scan', 'Index Only Scan'):
                        cur.execute(stmt)
                        row = cur.fetchone()
                        bounds.append(str(row[0]) if row else None)
                    else:
                        bounds.append(None)
                cur.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                            "AND tablename=%s ORDER BY indexname LIMIT 12", (table,))
                indexes = [r[0] for r in cur]
                for item in items:
                    if item.get('candidate_table') == table:
                        item.update(db_sample=rows, column_types=columns, select_privilege=True,
                                    observed_table_bounds=bounds, indexes=indexes,
                                    historical_coverage='UNVERIFIED', revision_history='UNVERIFIED',
                                    pit_contract={
                                        'observation': fields[table][0], 'publication': None,
                                        'first_access': None, 'collection': 'collected_at'
                                        if 'collected_at' in columns else None, 'revision': None,
                                        'decision': None, 'eligible': False})
    finally:
        connection.close()


def archived_treasury(uri, state_dir):
    """Only use a host-staged, previously verified exact archive in this program."""
    archive = uri.rsplit('/', 1)[-1]
    digest = ARCHIVES.get(archive)
    if not digest or not uri.startswith('https://home.treasury.gov/'):
        return None
    if state_dir.parent.parent.name != 'jobs':
        return None
    directory = state_dir.parents[2] / 'official_sources'
    if directory.is_symlink() or not directory.resolve().is_relative_to(PRIVATE_ROOT):
        raise ValueError('Invalid local source directory')
    path = directory / archive
    if path.is_symlink():
        raise ValueError('Symlinked source archive')
    if not path.exists():
        return None
    if path.stat().st_size > 2000000:
        raise ValueError('Archive byte budget exceeded')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError('Historical Treasury archive hash mismatch')
    return payload


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('requirements', nargs='+')
    parser.add_argument('--inspect-db', action='store_true')
    args = parser.parse_args()
    items = [discover(item) for item in args.requirements]
    if args.inspect_db:
        inspect_database(items)
    print(json.dumps(items, indent=2, default=str))
