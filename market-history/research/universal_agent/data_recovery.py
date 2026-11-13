"""Bounded source acquisition for research evidence, never a PIT approval gate.

Callers supply exact observation dates. A missing calendar day is not inferred to
be a missing market observation. Source adapters are reviewed, fixed-URI readers.
"""
from __future__ import annotations

import hashlib
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .engine import canonical, write_state
from .source_adapters import REGISTRY, select

MAX_BYTES = 2_000_000
RETRYABLE = {429, 500, 502, 503, 504}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return ('RATE_LIMIT' if exc.code == 429 else 'SOURCE_NOT_FOUND'
                if exc.code == 404 else 'SOURCE_UNAVAILABLE'
                if exc.code in {500, 502, 503, 504} else
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
                    'User-Agent': 'MyDream2000-research/1.0',
                    'Accept': 'text/csv, application/json, text/html'}),
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
    return (REGISTRY['US_TREASURY'].uri(series, f'{year}-01-01', f'{year}-12-31'),
            columns[series])


def parse_treasury(payload: bytes, column: str, dates: set[str]) -> dict[str, str]:
    series = {'2 Yr': 'UST_2Y', '10 Yr': 'UST_10Y'}.get(column)
    if series is None:
        raise ValueError('Unsupported Treasury column')
    return REGISTRY['US_TREASURY'].parse(series, payload, dates)


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
    try:
        start = datetime.strptime(request['start'], '%Y-%m-%d').date()
        end = datetime.strptime(request['end'], '%Y-%m-%d').date()
        parsed_dates = [datetime.strptime(day, '%Y-%m-%d').date() for day in dates]
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid observation date') from exc
    if (not isinstance(dates, list) or not 1 <= len(dates) <= 366 or
            len(dates) != len(set(dates)) or start > end or
            (end - start).days > 366 or
            any(not start <= day <= end for day in parsed_dates)):
        raise ValueError('Invalid bounded observation dates')
    adapter = select(request['series'], request['allowed_sources'])
    budget = request['budget']
    if (not 0 <= budget['max_network_requests'] <= 3 or
            not 1 <= budget['max_seconds'] <= 30 or
            not 0 <= budget['max_retries'] <= 2 or
            (budget['max_network_requests'] != 0 and
             budget['max_retries'] + 1 > budget['max_network_requests']) or
            budget['max_model_calls'] != 0):
        raise ValueError('Unsafe acquisition budget')
    uri = adapter.uri(request['series'], request['start'], request['end'])
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state_dir.is_symlink():
        raise ValueError('Symlinked checkpoint directory')
    identity = _sha(canonical(request))
    checkpoint = state_dir / 'data_recovery.json'
    raw_file = state_dir / ('source' + adapter.extension)
    if checkpoint.is_symlink() or raw_file.is_symlink():
        raise ValueError('Symlinked acquisition artifact')
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {
        'schema_version': 1, 'request_sha256': identity, 'goal_id': request['goal_id'],
        'job_id': request['job_id'], 'task_id': request['task_id'],
        'task_key': identity, 'current_phase': 'ANALYZE_REQUIREMENT',
        'completed_tasks': [], 'pending_tasks': [request['task_id']],
        'blocked_tasks': [], 'execution_budget': budget, 'network_requests': 0,
        'source_records': [], 'evidence_hashes': [], 'problem_history': [],
        'next_action': None}
    if state['request_sha256'] != identity:
        raise ValueError('Checkpoint input identity changed')
    if state.get('status') in {'DATA_RECOVERED_PIT_UNVERIFIED',
                               'DATA_MISMATCH_RESOLVED_PIT_UNVERIFIED', 'DATA_MISMATCH',
                               'BLOCKED_EVIDENCE', 'BLOCKED_ENV'}:
        if state.get('content_sha256') and (not raw_file.is_file() or
                _sha(raw_file.read_bytes()) != state['content_sha256']):
            raise ValueError('Saved source hash mismatch')
        return state
    existing = request['existing']
    gaps = [day for day in dates if day not in existing]
    if gaps:
        state['problem_history'].append({'problem_type': 'DATA_MISSING',
            'task_id': request['task_id'], 'evidence': {'missing_dates': gaps},
            'considered': ['CHECK_EXISTING_DATA', 'COLLECT_APPROVED_SOURCE'],
            'selected_action': 'COLLECT_APPROVED_SOURCE'})
    first_records = []
    if request.get('existing_source') == 'FRED_INITIAL_HASHED':
        if 'FRED_ALFRED' not in request['allowed_sources']:
            raise ValueError('First-vintage source not approved')
        from .revision_evidence import first_vintage
        try:
            first_records = [first_vintage(request['series'], day, str(existing[day]))
                             for day in dates if day in existing]
        except (OSError, ValueError, KeyError) as exc:
            state.update(status='BLOCKED_EVIDENCE', problem_type='DATA_MISMATCH',
                         failure_history=[{'type': type(exc).__name__, 'detail': str(exc)}],
                         next_action='REVALIDATE_EXISTING_SOURCE',
                         blocked_tasks=[request['task_id']])
            state['problem_history'].append({'problem_type': 'DATA_MISMATCH',
                'task_id': request['task_id'], 'cause': 'EXISTING_SOURCE_UNVERIFIED',
                'selected_action': 'BLOCK_UNVERIFIED_INPUT', 'verification': 'FAILED'})
            write_state(checkpoint, state)
            return state
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
            problem = classify_error(exc)
            next_action = ('REVIEW_AUTHORIZATION_OR_LICENSE' if problem == 'AUTHORIZATION_REQUIRED'
                           else 'RUN_INDEPENDENT_ALLOWED_TASK' if problem in
                           {'SOURCE_UNAVAILABLE', 'SOURCE_NOT_FOUND', 'RATE_LIMIT'}
                           else 'REVIEW_SOURCE_REQUEST')
            state.update(status='BLOCKED_ENV', problem_type=problem,
                         failure_history=[{'type': type(exc).__name__, 'attempt_budget': budget['max_retries'] + 1}],
                         next_action=next_action, blocked_tasks=[request['task_id']])
            state['problem_history'].append({'problem_type': state['problem_type'],
                'task_id': request['task_id'], 'selected_action': 'BLOCK_SOURCE_CALL',
                'verification': 'BLOCKED', 'next_action': state['next_action']})
            write_state(checkpoint, state)
            return state
        if not 1 <= attempts <= budget['max_network_requests']:
            raise ValueError('Source request count exceeds budget')
        if len(payload) > MAX_BYTES:
            raise ValueError('Source exceeds byte budget')
        state.update(content_sha256=_sha(payload), network_requests=attempts,
                     network_attempts=attempts,
                     retrieved_at=datetime.now(timezone.utc).isoformat())
        raw_file.write_bytes(payload)
        write_state(checkpoint, state)
    try:
        values = adapter.parse(request['series'], payload, set(dates))
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
    record = {'source_id': adapter.source_id, 'source_uri': uri,
              'observation_date': None, 'observation_time': None,
              'published_at': None, 'first_accessible_at': None,
              'vintage_date': None, 'retrieved_at': state.get('retrieved_at'),
              'content_sha256': state['content_sha256'],
              'license_terms': adapter.license_terms,
              'collection_status': 'COLLECTED', 'validation_status': 'VALUE_CHECKED_PIT_UNVERIFIED',
              'missing_time_reasons': {'observation_time': 'Date-only archive',
                  'published_at': 'Historical row-level posting not provided',
                  'first_accessible_at': 'Historical first access not provided',
                  'vintage_date': 'Revision history not supplied'}}
    state.update(source_records=[{**record, 'observation_date': day,
                                  'value': values[day], 'unit': 'percent'}
                                 for day in dates if day in values] + first_records,
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
    if mismatch:
        state['problem_history'].append({'problem_type': 'DATA_MISMATCH',
            'task_id': request['task_id'], 'evidence': mismatch,
            'considered': ['UNIT', 'DATE', 'REVISION'],
            'selected_action': 'CHECK_HASHED_VINTAGE_AND_OFFICIAL_REVISION'
            if first_records and 'FED_H15' in request['allowed_sources'] else
            'BLOCK_UNEXPLAINED_DIFFERENCE'})
    if (mismatch and first_records and 'FED_H15' in request['allowed_sources'] and
            budget['max_network_requests'] > state['network_requests']):
        from .revision_evidence import H15_NOTICES_URI, correction
        notice_file = state_dir / 'revision_notice.html'
        if notice_file.is_symlink() or notice_file.exists():
            raise ValueError('Existing unverified revision notice')
        state['current_phase'] = 'COLLECT_REVISION_EVIDENCE'
        state['network_requests'] += 1
        write_state(checkpoint, state)
        try:
            notice, attempts = fetch(H15_NOTICES_URI, 1, budget['max_seconds'])
            if attempts != 1 or len(notice) > MAX_BYTES:
                raise ValueError('Revision evidence request budget exceeded')
        except Exception as exc:
            state['failure_history'] = [{'type': type(exc).__name__,
                                         'problem_type': classify_error(exc)}]
            state['next_action'] = 'REVIEW_REVISION_EVIDENCE_OR_ALTERNATIVE_SOURCE'
            write_state(checkpoint, state)
            return state
        notice_file.write_bytes(notice)
        state['revision_notice_sha256'] = _sha(notice)
        confirmed = {}
        for day, pair in mismatch.items():
            item = correction(notice, request['series'], day, pair['existing'], pair['source'])
            if item:
                confirmed[day] = item
        if confirmed and len(confirmed) == len(mismatch):
            state['resolved_mismatches'] = confirmed
            state['source_records'].extend(confirmed.values())
            state['evidence_hashes'].append(_sha(notice))
            state['status'] = 'DATA_MISMATCH_RESOLVED_PIT_UNVERIFIED'
            state['next_action'] = 'USE_CORRECTED_CURRENT_VALUE_ONLY_WITH_PIT_REVIEW'
            state['blocked_tasks'] = []
            state['problem_history'][-1].update(cause='OFFICIAL_REVISION',
                verification='PASS', resolution='PRESERVE_FIRST_VINTAGE_AND_CORRECTED_CURRENT')
        else:
            state['next_action'] = 'REVIEW_UNEXPLAINED_SOURCE_DIFFERENCE'
            state['problem_history'][-1].update(cause='UNRESOLVED', verification='BLOCKED')
        state['current_phase'] = 'VERIFY_PIT'
    state['problem_history'].append({'problem_type': 'PIT_UNVERIFIED',
        'task_id': request['task_id'], 'cause': 'FIRST_ACCESS_TIME_NOT_ESTABLISHED',
        'selected_action': 'BLOCK_OFFICIAL_RESEARCH', 'verification': 'BLOCKED',
        'next_action': state['next_action']})
    write_state(checkpoint, state)
    return state


def verify_recovery(request: dict, state_dir: Path) -> dict:
    """Independently recompute accepted values from the immutable source bytes."""
    checkpoint = state_dir / 'data_recovery.json'
    adapter = select(request['series'], request['allowed_sources'])
    raw_file = state_dir / ('source' + adapter.extension)
    if checkpoint.is_symlink() or raw_file.is_symlink():
        raise ValueError('Symlinked recovery evidence')
    state = json.loads(checkpoint.read_text())
    if state['request_sha256'] != _sha(canonical(request)):
        raise ValueError('Recovery identity changed')
    if state['network_requests'] > request['budget']['max_network_requests']:
        raise ValueError('Recovery network budget exceeded')
    payload = raw_file.read_bytes()
    if _sha(payload) != state['content_sha256']:
        raise ValueError('Source content hash changed')
    uri = adapter.uri(request['series'], request['start'], request['end'])
    if state['source_records'][0]['source_uri'] != uri:
        raise ValueError('Source URI changed')
    values = adapter.parse(request['series'], payload, set(request['expected_dates']))
    gaps = [day for day in request['expected_dates'] if day not in request['existing']]
    recovered = {day: values[day] for day in gaps if day in values}
    mismatches = {day: {'existing': str(request['existing'][day]), 'source': values[day]}
                  for day in request['expected_dates'] if day in request['existing']
                  and day in values and Decimal(str(request['existing'][day])) != Decimal(values[day])}
    if state['recovered'] != recovered or state['mismatches'] != mismatches or \
            state['still_missing'] != [day for day in gaps if day not in values]:
        raise ValueError('Recovery result failed independent recomputation')
    missing = [day for day in gaps if day not in values]
    if not mismatches and state['status'] != ('BLOCKED_EVIDENCE' if missing else
                                             'DATA_RECOVERED_PIT_UNVERIFIED'):
        raise ValueError('Recovery status inconsistent with source values')
    if mismatches and state['status'] not in {'DATA_MISMATCH',
                                               'DATA_MISMATCH_RESOLVED_PIT_UNVERIFIED'}:
        raise ValueError('Mismatch status inconsistent with source values')
    if state['source_records'][0]['first_accessible_at'] is not None or \
            state['source_records'][0]['published_at'] is not None:
        raise ValueError('Unsupported PIT timestamp promotion')
    if request.get('existing_source') == 'FRED_INITIAL_HASHED':
        from .revision_evidence import first_vintage
        prior = [first_vintage(request['series'], day, str(request['existing'][day]))
                 for day in request['expected_dates'] if day in request['existing']]
        saved = [item for item in state['source_records'] if item['source_id'] == 'FRED_ALFRED']
        if prior != saved:
            raise ValueError('First-vintage source evidence changed')
    if state['status'] == 'DATA_MISMATCH_RESOLVED_PIT_UNVERIFIED':
        if request.get('existing_source') != 'FRED_INITIAL_HASHED':
            raise ValueError('Unverified revision source')
        from .revision_evidence import first_vintage, correction
        notice_file = state_dir / 'revision_notice.html'
        if notice_file.is_symlink():
            raise ValueError('Symlinked revision notice')
        notice = notice_file.read_bytes()
        if _sha(notice) != state['revision_notice_sha256']:
            raise ValueError('Revision notice hash changed')
        for day, pair in mismatches.items():
            first_vintage(request['series'], day, pair['existing'])
            if state['resolved_mismatches'].get(day) != correction(
                    notice, request['series'], day, pair['existing'], pair['source']):
                raise ValueError('Revision explanation failed independent verification')
    return state
