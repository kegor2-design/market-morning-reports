"""Bounded source acquisition for research evidence, never a PIT approval gate.

Callers supply exact observation dates. A missing calendar day is not inferred to
be a missing market observation. Source adapters are reviewed, fixed-URI readers.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .engine import canonical, write_state

TREASURY_BASE = ('https://home.treasury.gov/resource-center/data-chart-center/'
                 'interest-rates/daily-treasury-rate-archives/')
MAX_BYTES = 2_000_000
RETRYABLE = {429, 500, 502, 503, 504}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return ('RATE_LIMIT' if exc.code == 429 else 'SOURCE_UNAVAILABLE'
                if exc.code in {404, 500, 502, 503, 504} else
                'AUTHORIZATION_REQUIRED' if exc.code in {401, 403} else 'INVALID_REQUEST')
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return 'SOURCE_UNAVAILABLE'
    if isinstance(exc, urllib.error.URLError):
        return 'SOURCE_UNAVAILABLE'
    return 'ENVIRONMENT_ERROR'


def _fetch(uri: str, attempts: int, timeout: float) -> tuple[bytes, int]:
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(uri, headers={
                    'User-Agent': 'MyDream2000-research/1.0', 'Accept': 'text/csv'}),
                    timeout=timeout) as response:
                if response.geturl() != uri:
                    raise ValueError('Source redirect rejected')
                payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise ValueError('Source exceeds byte budget')
                return payload, attempt + 1
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            retry = (isinstance(exc, urllib.error.HTTPError) and exc.code in RETRYABLE
                     or not isinstance(exc, urllib.error.HTTPError))
            if not retry or attempt + 1 == attempts:
                raise
            time.sleep(min(2 ** attempt, 2))
    raise AssertionError('unreachable')


def treasury_adapter(series: str, year: int) -> tuple[str, str]:
    """Map a reviewed Treasury series to one official decade archive and column."""
    columns = {'UST_2Y': '2 Yr', 'UST_10Y': '10 Yr'}
    if series not in columns or not 2010 <= year <= 2029:
        raise ValueError('Unsupported Treasury series or year')
    start = year // 10 * 10
    return (f'{TREASURY_BASE}par-yield-curve-rates-{start}-{start + 9}.csv',
            columns[series])


def parse_treasury(payload: bytes, column: str, dates: set[str]) -> dict[str, str]:
    rows = csv.DictReader(io.StringIO(payload.decode('utf-8-sig')))
    if not rows.fieldnames or 'Date' not in rows.fieldnames or column not in rows.fieldnames:
        raise ValueError('Official CSV columns changed')
    values = {}
    for row in rows:
        try:
            day = datetime.strptime(row['Date'], '%m/%d/%y').date().isoformat()
        except (TypeError, ValueError) as exc:
            raise ValueError('Invalid source observation date') from exc
        if day not in dates:
            continue
        if day in values:
            raise ValueError('Duplicate source observation')
        raw = row[column].strip()
        if not raw or raw.upper() in {'N/A', 'ND'}:
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError('Invalid source observation value') from exc
        if not value.is_finite():
            raise ValueError('Nonfinite source observation')
        values[day] = str(value)
    return values


def recover(request: dict, state_dir: Path, *, fetch=_fetch) -> dict:
    """Acquire only absent dates, compare existing values, and seal source evidence.

    An uncertain network call is never replayed automatically. A saved response
    may be resumed after its digest and request identity have been checked.
    """
    required = {'goal_id', 'job_id', 'task_id', 'series', 'market', 'start', 'end',
                'expected_dates', 'existing', 'unit', 'allowed_sources', 'budget'}
    if not required <= request.keys():
        raise ValueError('Incomplete data requirement')
    if request['market'] != 'US' or request['unit'] != 'percent':
        raise ValueError('Unsupported market or unit')
    dates = request['expected_dates']
    if (not isinstance(dates, list) or len(dates) > 366 or len(dates) != len(set(dates))
            or any(not request['start'] <= day <= request['end'] for day in dates)):
        raise ValueError('Invalid bounded observation dates')
    if request['allowed_sources'] != ['US_TREASURY']:
        raise ValueError('Source approval required')
    budget = request['budget']
    if (not 0 <= budget['max_network_requests'] <= 3 or
            not 1 <= budget['max_seconds'] <= 30 or
            not 0 <= budget['max_retries'] <= 2 or
            (budget['max_network_requests'] != 0 and
             budget['max_retries'] + 1 > budget['max_network_requests']) or
            budget['max_model_calls'] != 0):
        raise ValueError('Unsafe acquisition budget')
    years = {int(day[:4]) for day in dates}
    if len(years) != 1:
        raise ValueError('One year per bounded recovery task')
    uri, column = treasury_adapter(request['series'], next(iter(years)))
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state_dir.is_symlink():
        raise ValueError('Symlinked checkpoint directory')
    identity = _sha(canonical(request))
    checkpoint = state_dir / 'data_recovery.json'
    raw_file = state_dir / 'source.csv'
    if checkpoint.is_symlink() or raw_file.is_symlink():
        raise ValueError('Symlinked acquisition artifact')
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {
        'schema_version': 1, 'request_sha256': identity, 'goal_id': request['goal_id'],
        'job_id': request['job_id'], 'task_id': request['task_id'],
        'task_key': identity, 'current_phase': 'ANALYZE_REQUIREMENT',
        'completed_tasks': [], 'pending_tasks': [request['task_id']],
        'blocked_tasks': [], 'execution_budget': budget, 'network_requests': 0,
        'source_records': [], 'evidence_hashes': [], 'next_action': None}
    if state['request_sha256'] != identity:
        raise ValueError('Checkpoint input identity changed')
    if state.get('status') in {'DATA_RECOVERED_PIT_UNVERIFIED', 'DATA_MISMATCH',
                               'BLOCKED_EVIDENCE', 'BLOCKED_ENV'}:
        if state.get('content_sha256') and (not raw_file.is_file() or
                _sha(raw_file.read_bytes()) != state['content_sha256']):
            raise ValueError('Saved source hash mismatch')
        return state
    existing = request['existing']
    gaps = [day for day in dates if day not in existing]
    state.update(current_phase='IDENTIFY_GAPS', gaps=gaps,
                 considered_actions=['CHECK_EXISTING_DATA', 'COLLECT_APPROVED_SOURCE',
                                     'COMPARE_SOURCE_VALUES', 'VERIFY_PIT'])
    write_state(checkpoint, state)
    if not gaps and not request.get('cross_validate', False):
        state.update(status='EXISTING_DATA_UNVERIFIED', next_action='VERIFY_EXISTING_PROVENANCE',
                     current_phase='TERMINAL', pending_tasks=[], blocked_tasks=[request['task_id']])
        write_state(checkpoint, state)
        return state
    if raw_file.exists():
        if not state.get('content_sha256') or _sha(raw_file.read_bytes()) != state['content_sha256']:
            raise ValueError('Unverified source artifact')
        payload = raw_file.read_bytes()
    elif state['network_requests']:
        state.update(status='BLOCKED_UNCERTAIN_API_CALL', next_action='REVIEW_REQUEST_BEFORE_RETRY')
        write_state(checkpoint, state)
        return state
    elif budget['max_network_requests'] == 0:
        state.update(status='BLOCKED_ENV', next_action='ALLOW_ONE_OFFICIAL_REQUEST',
                     blocked_tasks=[request['task_id']])
        write_state(checkpoint, state)
        return state
    else:
        state.update(current_phase='COLLECT_DATA',
                     network_requests=budget['max_retries'] + 1)
        write_state(checkpoint, state)
        try:
            payload, attempts = fetch(uri, budget['max_retries'] + 1, budget['max_seconds'])
        except Exception as exc:
            state.update(status='BLOCKED_ENV', problem_type=classify_error(exc),
                         failure_history=[{'type': type(exc).__name__, 'attempt_budget': budget['max_retries'] + 1}],
                         next_action='REVIEW_SOURCE_OR_CREDENTIALS', blocked_tasks=[request['task_id']])
            write_state(checkpoint, state)
            return state
        if len(payload) > MAX_BYTES:
            raise ValueError('Source exceeds byte budget')
        state.update(content_sha256=_sha(payload), network_requests=attempts,
                     network_attempts=attempts,
                     retrieved_at=datetime.now(timezone.utc).isoformat())
        raw_file.write_bytes(payload)
        write_state(checkpoint, state)
    try:
        values = parse_treasury(payload, column, set(dates))
    except (UnicodeError, ValueError) as exc:
        state.update(status='BLOCKED_EVIDENCE', problem_type='DATA_MISMATCH',
                     failure_history=[{'type': type(exc).__name__, 'detail': str(exc)}],
                     next_action='REVIEW_SOURCE_FORMAT', blocked_tasks=[request['task_id']])
        write_state(checkpoint, state)
        return state
    mismatch = {day: {'existing': str(existing[day]), 'source': values[day]}
                for day in dates if day in existing and day in values
                and Decimal(str(existing[day])) != Decimal(values[day])}
    missing = [day for day in gaps if day not in values]
    record = {'source_id': 'US_TREASURY', 'source_uri': uri,
              'observation_date': None, 'observation_time': None,
              'published_at': None, 'first_accessible_at': None,
              'vintage_date': None, 'retrieved_at': state.get('retrieved_at'),
              'content_sha256': state['content_sha256'],
              'license_terms': 'Official public Treasury archive; redistribution terms not reviewed',
              'collection_status': 'COLLECTED', 'validation_status': 'VALUE_CHECKED_PIT_UNVERIFIED',
              'missing_time_reasons': {'observation_time': 'Date-only archive',
                  'published_at': 'Historical row-level posting not provided',
                  'first_accessible_at': 'Historical first access not provided',
                  'vintage_date': 'Revision history not supplied'}}
    state.update(source_records=[{**record, 'observation_date': day,
                                  'value': values[day], 'unit': 'percent'}
                                 for day in dates if day in values],
                 evidence_hashes=[state['content_sha256']],
                 recovered={day: values[day] for day in gaps if day in values},
                 mismatches=mismatch, still_missing=missing,
                 current_phase='VERIFY_PIT', completed_tasks=[request['task_id']], pending_tasks=[])
    state['status'] = ('DATA_MISMATCH' if mismatch else 'DATA_RECOVERED_PIT_UNVERIFIED'
                       if not missing else 'BLOCKED_EVIDENCE')
    state['next_action'] = ('REVIEW_UNIT_DATE_AND_REVISION' if mismatch else
                            'COLLECT_OTHER_APPROVED_SOURCE' if missing else
                            'CONTINUE_NON_PIT_RESEARCH_OR_SEEK_PIT_EVIDENCE')
    state['blocked_tasks'] = [request['task_id']] if mismatch or missing else []
    write_state(checkpoint, state)
    return state


def verify_recovery(request: dict, state_dir: Path) -> dict:
    """Independently recompute accepted values from the immutable source bytes."""
    checkpoint = state_dir / 'data_recovery.json'
    raw_file = state_dir / 'source.csv'
    if checkpoint.is_symlink() or raw_file.is_symlink():
        raise ValueError('Symlinked recovery evidence')
    state = json.loads(checkpoint.read_text())
    if state['request_sha256'] != _sha(canonical(request)):
        raise ValueError('Recovery identity changed')
    payload = raw_file.read_bytes()
    if _sha(payload) != state['content_sha256']:
        raise ValueError('Source content hash changed')
    uri, column = treasury_adapter(request['series'], int(request['expected_dates'][0][:4]))
    if state['source_records'][0]['source_uri'] != uri:
        raise ValueError('Source URI changed')
    values = parse_treasury(payload, column, set(request['expected_dates']))
    gaps = [day for day in request['expected_dates'] if day not in request['existing']]
    recovered = {day: values[day] for day in gaps if day in values}
    mismatches = {day: {'existing': str(request['existing'][day]), 'source': values[day]}
                  for day in request['expected_dates'] if day in request['existing']
                  and day in values and Decimal(str(request['existing'][day])) != Decimal(values[day])}
    if state['recovered'] != recovered or state['mismatches'] != mismatches or \
            state['still_missing'] != [day for day in gaps if day not in values]:
        raise ValueError('Recovery result failed independent recomputation')
    if state['source_records'][0]['first_accessible_at'] is not None or \
            state['source_records'][0]['published_at'] is not None:
        raise ValueError('Unsupported PIT timestamp promotion')
    return state
