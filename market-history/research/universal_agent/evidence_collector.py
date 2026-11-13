"""Bounded, read-only source evidence adapter for existing research jobs.

This adapter emits metadata only. A date-only vintage or a scheduled release
clock never becomes an actual publication or first-access timestamp.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .engine import canonical

REPO = Path(__file__).resolve().parents[3]
SOURCE_ROOT = Path.home() / 'MyDream2000/research/regime190/fred_initial_yearly'
MATRIX = REPO / 'market-history/research/regime190/indicator116_20261112/ASOF_AVAILABILITY_MATRIX.csv'
MATRIX_SHA256 = '0f871aa585f2aa73223c0b809621808e9e0b47fc3430375628eee11ee3fc3ceb'
MANIFEST_CHAIN_SHA256 = 'cb5f72997725e6557ad8f1bc1d9d587b6b97d9bb1f7d54eca34cbba36eb90350'
FRED_URI = 'https://fred.stlouisfed.org/docs/api/fred/series_observations.html'
H15_URI = 'https://www.federalreserve.gov/releases/h15/'
TREASURY_URI = 'https://home.treasury.gov/treasury-daily-interest-rate-xml-feed'


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked source')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(request: dict) -> dict:
    """Return an explicit blocked record when a requested capability is absent."""
    basis = {key: request[key] for key in ('goal_id', 'task_id', 'indicator',
        'source', 'data_requirement', 'as_of', 'allowed_sources', 'budget', 'policy')}
    common = {'schema_version': 1, 'request_sha256': hashlib.sha256(canonical(basis)).hexdigest(),
              'goal_id': request['goal_id'], 'task_id': request['task_id'],
              'indicator': request['indicator'], 'source': request['source'],
              'as_of': request['as_of'], 'observation_time': None,
              'actual_publication_time': None, 'first_accessible_time': None,
              'time_field_reasons': {
                  'observation_time': 'Observation dates are recorded; row-level measurement clocks are not',
                  'actual_publication_time': 'No historical row-level H.15 posting timestamp',
                  'first_accessible_time': 'No historical row-level FRED access timestamp'},
              'license_terms': None, 'content_sha256': None,
              'confidence': 'NONE', 'evidence_type': 'NONE',
              'vintage_revision': None, 'source_uri': None,
              'data': None, 'gaps': [], 'next_action': None}
    if request['source'] not in request['allowed_sources']:
        return {**common, 'status': 'BLOCKED_APPROVAL',
                'gaps': ['Source not in approved allowlist'],
                'next_action': 'AUTHORIZE_SOURCE_OR_CHOOSE_ALLOWED_SOURCE'}
    if request['indicator'] != '116' or request['source'] != 'FRED_ALFRED':
        return {**common, 'status': 'NOT_SUPPORTED',
                'gaps': ['No reviewed collector for this indicator/source pair'],
                'next_action': 'IMPLEMENT_REVIEWED_SOURCE_ADAPTER'}
    if request['data_requirement'] != 'first_vintage_pit':
        return {**common, 'status': 'NOT_SUPPORTED',
                'gaps': ['No reviewed adapter for requested data requirement'],
                'next_action': 'IMPLEMENT_REVIEWED_REQUIREMENT'}
    if request['budget']['max_network_requests'] != 0 or request['budget']['max_model_calls'] != 0:
        return {**common, 'status': 'BLOCKED_APPROVAL',
                'gaps': ['This offline adapter permits zero network and model calls'],
                'next_action': 'USE_OFFLINE_BUDGET_OR_AUTHORIZE_SEPARATE_COLLECTOR'}
    import importlib.util
    script = REPO / 'market-history/research/regime190/indicator116_20261112/build_asof_matrix.py'
    spec = importlib.util.spec_from_file_location('indicator116_asof_audit', script)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    load_series = audit.load_series
    try:
        d2, h2 = load_series(SOURCE_ROOT, 'DGS2')
        d10, h10 = load_series(SOURCE_ROOT, 'DGS10')
        if hashlib.sha256(canonical({'DGS2': h2, 'DGS10': h10})).hexdigest() != MANIFEST_CHAIN_SHA256:
            raise ValueError('Annual source manifest chain changed')
        matrix_sha = _sha(MATRIX)
        if matrix_sha != MATRIX_SHA256:
            raise ValueError('Tracked as-of matrix hash changed')
        with MATRIX.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        paired = {day for day in d2.keys() & d10.keys()
                  if d2[day]['value'] != '.' and d10[day]['value'] != '.'}
        if len(h2) != 17 or len(h10) != 17 or len(paired) != 4204 or len(rows) != 4204:
            raise ValueError('Source count or paired dates changed')
        if {row['observation_date'] for row in rows} != paired or any(
                row['strict_pit_status'] != 'BLOCKED' for row in rows):
            raise ValueError('As-of matrix row identity or PIT status changed')
    except OSError as exc:
        return {**common, 'status': 'BLOCKED_ENV', 'gaps': [type(exc).__name__],
                'next_action': 'RESTORE_HASHED_LOCAL_INPUTS'}
    except (ValueError, TypeError, AssertionError, KeyError, IndexError) as exc:
        return {**common, 'status': 'BLOCKED_EVIDENCE', 'gaps': [type(exc).__name__],
                'next_action': 'REVALIDATE_SOURCE_MANIFEST_AND_MATRIX'}
    return {**common, 'status': 'PIT_BLOCKED', 'source_uri': FRED_URI,
            'license_terms': 'Public Domain: Citation Requested (FRED series pages)',
            'content_sha256': matrix_sha, 'confidence': 'HIGH_FOR_DATES_LOW_FOR_INTRADAY',
            'evidence_type': 'HASHED_LOCAL_INITIAL_VINTAGE_AND_ASOF_MATRIX',
            'observation_date_range': ['2010-01-04', '2026-10-26'],
            'vintage_revision': {'initial_vintage_date_granularity': 'DAY',
                'full_revision_sequence': None, 'full_revision_reason': 'Not acquired'},
            'data': {'paired_numeric_dates': 4204, 'source_file_count': 34,
                     'manifest_sha256': {'DGS2': h2, 'DGS10': h10},
                     'strict_pit_blocked_rows': 4204},
            'gaps': ['Historical actual H.15 daily publication timestamps unavailable',
                     'Historical actual FRED first-access timestamps unavailable',
                     'Complete dated revision sequence unavailable',
                     'Mature independent Korean-market holdout unavailable'],
            'next_action': 'RUN_INDEPENDENT_ALLOWED_TASK',
            'source_context_uris': [H15_URI, TREASURY_URI],
            'official_backtest_status': 'OFFICIAL_BACKTEST_SKIPPED'}
