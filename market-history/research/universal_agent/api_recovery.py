"""Host-reviewed, separately approved retry after a definite source HTTP failure.

Only loopback fault fixtures are executable here. External providers require a
separate approval mechanism; a model or blocked task cannot mint that approval.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from .engine import canonical, now, write_state
from .research_job import manifest_load, plan_for, verify_artifact
from .research_planner import _task, validate_plan
from .source_adapters import select

RETRYABLE = {429, 500, 502, 503, 504}


def retry_after_at(value: str | None, observed_at: str) -> str | None:
    """Bounded, persistent next request time for a definite HTTP 429."""
    if value is None or not isinstance(value, str):
        return None
    observed = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
    if observed.tzinfo is None:
        return None
    try:
        if value.isdecimal():
            delay = int(value)
            eligible = observed + timedelta(seconds=delay)
        else:
            eligible = parsedate_to_datetime(value)
            if eligible.tzinfo is None:
                return None
            delay = (eligible - observed).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None
    if not 0 <= delay <= 25:
        return None
    return eligible.astimezone(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked API recovery evidence')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _saved(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked API recovery transaction')
    value = json.loads(path.read_text())
    value.pop('updated_at_utc', None)
    return value


def _write_or_verify(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise ValueError('Symlinked API recovery transaction artifact')
    if path.exists():
        prior = _saved(path)
        if prior != value:
            raise ValueError('API recovery transaction artifact changed')
    else:
        write_state(path, value)


def _transaction_identity(value: dict) -> str:
    stable = {key: item for key, item in value.items() if key not in {
        'transaction_state', 'created_at_utc', 'committed_at_utc',
        'rolled_back_at_utc'}}
    return hashlib.sha256(canonical(stable)).hexdigest()


def diagnose(plan: dict, state: dict, program_dir: Path) -> dict | None:
    if (plan['market'] != 'US_RATES' or state['status'] != 'RESEARCH_BLOCKED' or
            state['goal_id'] != plan['goal_id'] or state.get('api_recovery_revision')):
        return None
    for series in ('UST_2Y', 'UST_10Y', 'NYFED_SOFR'):
        task_id = 'collect_' + series.lower()
        record = state['records'].get(task_id, {})
        if (record.get('status') != 'BLOCKED_ENV' or record.get('attempts') != 1 or
                record.get('network_call_outcome') != 'DEFINITE_HTTP_ERROR'):
            continue
        manifest_path = program_dir / 'manifests' / (task_id + '.json')
        manifest, digest = manifest_load(manifest_path)
        old_dir = program_dir / 'jobs' / task_id
        verify_artifact(manifest, plan_for(manifest, digest), old_dir)
        request = manifest['data_request']
        source_path = old_dir / 'data_recovery' / 'data_recovery.json'
        source_sha = _sha(source_path)
        source = json.loads(source_path.read_text())
        failure = source.get('failure_history', [{}])[0]
        adapter = select(series, request['allowed_sources'])
        if (request['series'] != series or source['status'] != 'BLOCKED_ENV' or
                source['request_sha256'] != hashlib.sha256(canonical(request)).hexdigest() or
                source.get('network_call_outcome') != 'DEFINITE_HTTP_ERROR' or
                failure.get('http_status') not in RETRYABLE or
                (failure.get('http_status') == 429 and retry_after_at(
                    failure.get('retry_after'), source['updated_at_utc']) is None) or
                source.get('network_requests') != 1 or
                request['budget'] != {'max_network_requests': 1, 'max_seconds': 25,
                                      'max_retries': 0, 'max_model_calls': 0} or
                adapter.source_id not in plan['allowed_sources']):
            continue
        return {'schema_version': 1, 'problem_type': 'API_ERROR',
                'goal_id': plan['goal_id'], 'original_goal': plan['research_goal'],
                'original_plan_sha256': state['plan_sha256'],
                'goal_contract_sha256': state['goal_contract_sha256'],
                'original_task_id': task_id, 'series': series,
                'source_id': adapter.source_id,
                'source_uri': request.get('fixture_source_uri') or adapter.uri(
                    series, request['start'], request['end']),
                'requested_period': plan['research_period'],
                'original_request_sha256': source['request_sha256'],
                'original_job_sha256': _sha(old_dir / 'job.json'),
                'error_evidence_sha256': source_sha,
                'http_status': failure['http_status'],
                'retry_after': failure.get('retry_after'),
                'next_eligible_retry_at': (retry_after_at(
                    failure.get('retry_after'), source['updated_at_utc']) if
                    failure['http_status'] == 429 else None),
                'network_call_outcome': 'DEFINITE_HTTP_ERROR',
                'recovery_reason': 'Definite retryable HTTP failure',
                'solution_action': 'RETRY_APPROVED_SOURCE_NEW_REQUEST',
                'verification_rule': 'independent_source_recompute',
                'rollback_rule': 'retain_original_failed_task_and_block',
                'resume_rule': 'replace_analysis_dependency_after_verified_recovery'}
    return None


def authorize_local(plan: dict, state: dict, program_dir: Path, *,
                    approved_by: str, valid_until_utc: str) -> dict:
    """Record explicit fixture approval; never approves a public provider URI."""
    evidence = diagnose(plan, state, program_dir)
    if evidence is None or not approved_by.strip():
        raise ValueError('No eligible API failure or approver')
    uri = urlparse(evidence['source_uri'])
    if uri.scheme != 'http' or uri.hostname != '127.0.0.1' or uri.username or uri.password:
        raise ValueError('Local fixture approval cannot authorize external source')
    expiry = datetime.fromisoformat(valid_until_utc.replace('Z', '+00:00'))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError('API recovery approval expired')
    approval = {'schema_version': 1, 'scope': 'LOCAL_LOOPBACK_TEST',
                'status': 'APPROVED', 'approved_by': approved_by,
                'valid_until_utc': valid_until_utc,
                'goal_id': plan['goal_id'],
                'original_task_id': evidence['original_task_id'],
                'evidence_sha256': hashlib.sha256(canonical(evidence)).hexdigest(),
                'source_id': evidence['source_id'], 'source_uri': evidence['source_uri'],
                'max_network_requests': 1, 'max_seconds': 25,
                'max_model_calls': 0, 'max_cost_usd': 0,
                'reason': 'One new request after definite fixture HTTP error'}
    path = program_dir / 'api_recovery_approval.json'
    if path.is_symlink() or path.exists():
        raise ValueError('API recovery approval already exists')
    write_state(path, approval)
    return approval


def validate_approval(evidence: dict, program_dir: Path) -> dict | None:
    approval_path = program_dir / 'api_recovery_approval.json'
    if not approval_path.is_file() or approval_path.is_symlink():
        return None
    approval = json.loads(approval_path.read_text())
    approval.pop('updated_at_utc', None)
    uri = urlparse(evidence['source_uri'])
    expiry = datetime.fromisoformat(approval['valid_until_utc'].replace('Z', '+00:00'))
    if (approval.get('scope') != 'LOCAL_LOOPBACK_TEST' or
            approval.get('status') != 'APPROVED' or
            not approval.get('approved_by') or
            approval.get('goal_id') != evidence['goal_id'] or
            approval.get('original_task_id') != evidence['original_task_id'] or
            approval.get('evidence_sha256') != hashlib.sha256(canonical(evidence)).hexdigest() or
            approval.get('source_id') != evidence['source_id'] or
            approval.get('source_uri') != evidence['source_uri'] or
            uri.scheme != 'http' or uri.hostname != '127.0.0.1' or
            type(approval.get('max_network_requests')) is not int or
            approval['max_network_requests'] != 1 or
            type(approval.get('max_seconds')) is not int or
            approval['max_seconds'] != 25 or
            type(approval.get('max_model_calls')) is not int or
            approval['max_model_calls'] != 0 or
            type(approval.get('max_cost_usd')) not in (int, float) or
            approval['max_cost_usd'] != 0 or
            expiry.tzinfo is None or expiry <= datetime.now(timezone.utc)):
        raise ValueError('API recovery approval or evidence changed')
    return approval


def replan(plan: dict, state: dict, program_dir: Path) -> bool:
    evidence = diagnose(plan, state, program_dir)
    if evidence is None:
        return False
    approval = validate_approval(evidence, program_dir)
    if approval is None:
        return False
    approval_path = program_dir / 'api_recovery_approval.json'
    approval_sha = _sha(approval_path)
    task_id = 'api_recover_' + evidence['series'].lower()
    request_id = hashlib.sha256(canonical({'goal_id': plan['goal_id'],
        'original_request_sha256': evidence['original_request_sha256'],
        'approval_sha256': approval_sha, 'task_id': task_id})).hexdigest()[:24]
    revision = {**evidence, 'approval_sha256': approval_sha,
                'approval_path': str(approval_path), 'recovery_task_id': task_id,
                'new_request_id': request_id, 'additional_network_budget': 1,
                'retry_count': 0, 'maximum_duration_seconds': 25}
    revision_path = program_dir / 'api_recovery_revision_v1.json'
    _write_or_verify(revision_path, revision)
    revision_sha = _sha(revision_path)
    candidate = deepcopy(state)
    analysis = next(t for t in candidate['tasks'] if t['task_id'] == 'analyze_rates')
    if candidate['records']['analyze_rates']['attempts'] != 0:
        raise ValueError('Cannot rewire executed analysis')
    previous_analysis = deepcopy(analysis)
    previous_record = deepcopy(candidate['records']['analyze_rates'])
    previous_dag_sha = hashlib.sha256(canonical(candidate['tasks'])).hexdigest()
    task = _task(task_id, 'API_RECOVERY_RETRY', 25,
                 dependencies=['discover_' + evidence['series'].lower()],
                 inputs={'series': evidence['series'],
                         'api_recovery_revision_sha256': revision_sha,
                         'original_task_id': evidence['original_task_id'],
                         'original_request_sha256': evidence['original_request_sha256'],
                         'new_request_id': request_id})
    analysis['dependencies'] = [task_id if dep == evidence['original_task_id'] else dep
                                for dep in analysis['dependencies']]
    analysis['inputs']['api_recovery_revision_sha256'] = revision_sha
    candidate['tasks'].append(task)
    candidate['records'][task_id] = {'status': 'PENDING', 'attempts': 0}
    candidate['records']['analyze_rates']['status'] = 'PENDING'
    validate_plan(dict(plan, tasks=candidate['tasks']))
    proposed_dag_sha = hashlib.sha256(canonical(candidate['tasks'])).hexdigest()
    tx_path = program_dir / 'api_recovery_transaction_v1.json'
    transaction = {'schema_version': 1, 'revision_id': revision_sha[:24],
        'transaction_state': 'REVISION_PREPARED', 'original_plan_sha256':
        state['plan_sha256'], 'goal_contract_sha256': state['goal_contract_sha256'],
        'previous_active_revision': state.get('active_revision_sha256'),
        'previous_dag_sha256': previous_dag_sha,
        'proposed_dag_sha256': proposed_dag_sha,
        'changed_task_ids': [task_id, 'analyze_rates'],
        'changed_dependencies': {'analyze_rates': {
            'before': previous_analysis['dependencies'],
            'after': analysis['dependencies']}},
        'approval_sha256': approval_sha,
        'recovery_evidence_sha256': evidence['error_evidence_sha256'],
        'revision_sha256': revision_sha, 'rollback_target': 'PREVIOUS_BLOCKED_DAG',
        'previous_analysis_task': previous_analysis,
        'previous_analysis_record': previous_record,
        'completed_task_hashes': {key: value.get('checkpoint_sha256')
            for key, value in state['records'].items() if value['status'] in
            {'VERIFIED', 'COMPLETED_EXPLORATORY'}},
        'original_network_requests_reserved': state['network_requests_reserved'],
        'created_at_utc': now(), 'committed_at_utc': None,
        'validation_result': 'PASS'}
    if tx_path.is_symlink():
        raise ValueError('Symlinked API recovery transaction')
    if tx_path.exists():
        prior = _saved(tx_path)
        if prior.get('transaction_state') != 'REVISION_PREPARED':
            raise ValueError('API recovery transaction is not preparable')
        for key in ('created_at_utc', 'committed_at_utc', 'transaction_state'):
            prior.pop(key, None)
            transaction.pop(key, None)
        if prior != transaction:
            raise ValueError('API recovery transaction changed')
    else:
        write_state(tx_path, transaction)
    candidate['api_recovery_revision'] = {'path': str(revision_path), 'sha256': revision_sha,
                                      'approval_sha256': approval_sha,
                                      'status': 'REVISION_PREPARED',
                                      'transaction_path': str(tx_path),
                                      'transaction_identity_sha256': _transaction_identity(
                                          _saved(tx_path))}
    candidate.setdefault('plan_versions', []).append({'version': 2,
        'original_plan_sha256': state['plan_sha256'], 'revision_sha256': revision_sha,
        'reason': evidence['recovery_reason'], 'added_tasks': [task_id],
        'network_requests_added': 1, 'approval_sha256': approval_sha})
    candidate['replanning_history'].append({'cause': 'API_ERROR',
        'evidence_sha256': evidence['error_evidence_sha256'],
        'solution_action': evidence['solution_action'],
        'resume_original_goal_id': plan['goal_id']})
    state.clear()
    state.update(candidate)
    return True


def finalize_transaction(state: dict, program_dir: Path) -> None:
    """Finish a prepared journal only after the active DAG checkpoint is saved."""
    revision = state.get('api_recovery_revision')
    if not revision or not revision.get('transaction_path'):
        return
    path = program_dir / 'api_recovery_transaction_v1.json'
    revision_path = program_dir / 'api_recovery_revision_v1.json'
    if (revision['transaction_path'] != str(path) or
            revision['path'] != str(revision_path) or
            _sha(revision_path) != revision['sha256']):
        raise ValueError('API recovery revision identity changed')
    tx = _saved(path)
    if (_transaction_identity(tx) != revision['transaction_identity_sha256'] or
            tx['original_plan_sha256'] != state['plan_sha256'] or
            tx['goal_contract_sha256'] != state['goal_contract_sha256'] or
            tx['revision_sha256'] != revision['sha256']):
        raise ValueError('API recovery transaction identity changed')
    if revision['status'] == 'REVISION_ROLLED_BACK':
        if hashlib.sha256(canonical(state['tasks'])).hexdigest() != tx['previous_dag_sha256']:
            raise ValueError('Rolled-back DAG changed')
        if tx['transaction_state'] != 'REVISION_ROLLED_BACK':
            tx.update(transaction_state='REVISION_ROLLED_BACK',
                      rolled_back_at_utc=now())
            write_state(path, tx)
        return
    if hashlib.sha256(canonical(state['tasks'])).hexdigest() != tx['proposed_dag_sha256']:
        # Completed tasks may append independent data-recovery tasks only after
        # the revision was committed; an uncommitted proposal must match exactly.
        if tx['transaction_state'] == 'REVISION_PREPARED':
            raise ValueError('Prepared API DAG changed before commit')
    if tx['transaction_state'] == 'REVISION_PREPARED':
        tx.update(transaction_state='REVISION_COMMITTED', committed_at_utc=now())
        write_state(path, tx)
    elif tx['transaction_state'] != 'REVISION_COMMITTED':
        raise ValueError('Invalid API recovery transaction state')
    revision['status'] = 'REVISION_ACTIVE'
    state['active_revision_sha256'] = revision['sha256']


def rollback_failed_recovery(plan: dict, state: dict, program_dir: Path) -> bool:
    """Restore the previous active DAG; retain the failed request and artifacts."""
    revision = state.get('api_recovery_revision')
    if not revision or not revision.get('transaction_path') or \
            revision['status'] == 'REVISION_ROLLED_BACK':
        return False
    revision_path = program_dir / 'api_recovery_revision_v1.json'
    if (revision['path'] != str(revision_path) or
            revision['transaction_path'] != str(program_dir /
                'api_recovery_transaction_v1.json') or
            _sha(revision_path) != revision['sha256']):
        raise ValueError('API recovery revision identity changed')
    tx = _saved(program_dir / 'api_recovery_transaction_v1.json')
    task_id = 'api_recover_' + _saved(revision_path)['series'].lower()
    record = state['records'].get(task_id, {})
    analysis_record = state['records']['analyze_rates']
    if (record.get('status') not in {'BLOCKED_ENV', 'BLOCKED_EVIDENCE', 'FAILED'} and
            analysis_record.get('status') not in {'BLOCKED_ENV', 'BLOCKED_EVIDENCE', 'FAILED'}):
        return False
    if (_transaction_identity(tx) != revision['transaction_identity_sha256'] or
            tx['original_plan_sha256'] != state['plan_sha256'] or
            tx['goal_contract_sha256'] != state['goal_contract_sha256'] or
            tx['revision_sha256'] != revision['sha256'] or
            any(state['records'].get(key, {}).get('checkpoint_sha256') != digest
                for key, digest in tx['completed_task_hashes'].items())):
        raise ValueError('Cannot rollback changed original research evidence')
    candidate = deepcopy(state)
    recovery_task = next(t for t in candidate['tasks'] if t['task_id'] == task_id)
    candidate['retired_recovery_tasks'] = candidate.get('retired_recovery_tasks', []) + [{
        'task': deepcopy(recovery_task), 'record': deepcopy(candidate['records'][task_id]),
        'analysis_record': deepcopy(candidate['records']['analyze_rates'])}]
    candidate['tasks'] = [t for t in candidate['tasks'] if t['task_id'] != task_id]
    candidate['records'].pop(task_id)
    analysis = next(t for t in candidate['tasks'] if t['task_id'] == 'analyze_rates')
    analysis.clear()
    analysis.update(deepcopy(tx['previous_analysis_task']))
    candidate['records']['analyze_rates'] = deepcopy(tx['previous_analysis_record'])
    candidate['active_revision_sha256'] = tx['previous_active_revision']
    candidate['api_recovery_revision']['status'] = 'REVISION_ROLLED_BACK'
    candidate['plan_versions'][-1]['status'] = 'REVISION_ROLLED_BACK'
    candidate['status'] = 'RESEARCH_BLOCKED'
    candidate['next_action'] = 'REVIEW_FAILED_API_RECOVERY_EVIDENCE'
    validate_plan(dict(plan, tasks=candidate['tasks']))
    if hashlib.sha256(canonical(candidate['tasks'])).hexdigest() != tx['previous_dag_sha256']:
        raise ValueError('Rollback did not restore previous DAG')
    state.clear()
    state.update(candidate)
    return True


def verify_task(plan: dict, task: dict, program_dir: Path) -> dict:
    """Recheck the sealed approval immediately before a recovery request."""
    revision_path = program_dir / 'api_recovery_revision_v1.json'
    if _sha(revision_path) != task['inputs']['api_recovery_revision_sha256']:
        raise ValueError('API recovery revision changed')
    revision = json.loads(revision_path.read_text())
    revision.pop('updated_at_utc', None)
    approval_path = program_dir / 'api_recovery_approval.json'
    if (_sha(approval_path) != revision['approval_sha256'] or
            revision['goal_id'] != plan['goal_id'] or
            revision['goal_contract_sha256'] != hashlib.sha256(
                canonical(plan['goal_contract'])).hexdigest() or
            revision['recovery_task_id'] != task['task_id'] or
            revision['new_request_id'] != task['inputs']['new_request_id'] or
            revision['original_request_sha256'] != task['inputs']['original_request_sha256'] or
            revision['original_task_id'] != task['inputs']['original_task_id']):
        raise ValueError('API recovery identity changed')
    approval = json.loads(approval_path.read_text())
    uri = urlparse(revision['source_uri'])
    expiry = datetime.fromisoformat(approval['valid_until_utc'].replace('Z', '+00:00'))
    if (approval['status'] != 'APPROVED' or approval['scope'] != 'LOCAL_LOOPBACK_TEST' or
            approval['goal_id'] != plan['goal_id'] or
            approval['evidence_sha256'] != hashlib.sha256(canonical({key: value
                for key, value in revision.items() if key not in {
                    'updated_at_utc', 'approval_sha256', 'approval_path',
                    'recovery_task_id', 'new_request_id', 'additional_network_budget',
                    'retry_count', 'maximum_duration_seconds'}})).hexdigest() or
            uri.scheme != 'http' or uri.hostname != '127.0.0.1' or
            approval['source_uri'] != revision['source_uri'] or
            expiry.tzinfo is None or expiry <= datetime.now(timezone.utc)):
        raise ValueError('API recovery approval invalid before execution')
    return revision
