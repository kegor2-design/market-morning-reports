"""Host-reviewed, separately approved retry after a definite source HTTP failure.

Only loopback fault fixtures are executable here. External providers require a
separate approval mechanism; a model or blocked task cannot mint that approval.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .engine import canonical, write_state
from .research_job import manifest_load, plan_for, verify_artifact
from .research_planner import _task, validate_plan
from .source_adapters import select

RETRYABLE = {429, 500, 502, 503, 504}


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked API recovery evidence')
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
                (failure.get('http_status') == 429 and
                 failure.get('retry_after') != '0') or
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
    if revision_path.is_symlink() or revision_path.exists():
        raise ValueError('API recovery revision already exists')
    write_state(revision_path, revision)
    revision_sha = _sha(revision_path)
    analysis = next(t for t in state['tasks'] if t['task_id'] == 'analyze_rates')
    if state['records']['analyze_rates']['attempts'] != 0:
        raise ValueError('Cannot rewire executed analysis')
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
    state['tasks'].append(task)
    state['records'][task_id] = {'status': 'PENDING', 'attempts': 0}
    state['records']['analyze_rates']['status'] = 'PENDING'
    validate_plan(dict(plan, tasks=state['tasks']))
    state['api_recovery_revision'] = {'path': str(revision_path), 'sha256': revision_sha,
                                      'approval_sha256': approval_sha,
                                      'status': 'APPROVED_LOCAL_FIXTURE'}
    state.setdefault('plan_versions', []).append({'version': 2,
        'original_plan_sha256': state['plan_sha256'], 'revision_sha256': revision_sha,
        'reason': evidence['recovery_reason'], 'added_tasks': [task_id],
        'network_requests_added': 1, 'approval_sha256': approval_sha})
    state['replanning_history'].append({'cause': 'API_ERROR',
        'evidence_sha256': evidence['error_evidence_sha256'],
        'solution_action': evidence['solution_action'],
        'resume_original_goal_id': plan['goal_id']})
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
