"""Two bounded tasks in the existing Research Job checkpoint and action registry."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .agent2_synthetic import execute as synthetic_execute, verify as synthetic_verify
from .engine import canonical, write_state
from .problem_solver import collect_indicator_evidence


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked workflow artifact')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(manifest: dict) -> str:
    return hashlib.sha256(canonical((manifest['evidence_request'],
                                     manifest['next_task']))).hexdigest()


def verify(manifest: dict, state_dir: Path) -> dict:
    """Independently re-run read-only evidence checks and fixture arithmetic."""
    workflow = state_dir / 'workflow.json'
    if workflow.is_symlink():
        raise ValueError('Symlinked workflow checkpoint')
    state = json.loads(workflow.read_text())
    if state['identity_sha256'] != _identity(manifest):
        raise ValueError('Workflow input identity changed')
    if state['steps'][0]['task_id'] != manifest['evidence_request']['task_id']:
        raise ValueError('Evidence task identity changed')
    evidence_path = state_dir / 'evidence_result.json'
    if _sha(evidence_path) != state['steps'][0]['output_sha256']:
        raise ValueError('Evidence result hash mismatch')
    evidence = json.loads(evidence_path.read_text())
    evidence.pop('updated_at_utc', None)
    if evidence.get('status') not in {'PIT_BLOCKED', 'BLOCKED_EVIDENCE',
                                      'BLOCKED_ENV', 'BLOCKED_APPROVAL', 'NOT_SUPPORTED'}:
        raise ValueError('Unapproved evidence or PIT promotion')
    if evidence != collect_indicator_evidence(manifest['evidence_request']):
        raise ValueError('Independent source evidence mismatch')
    if len(state['steps']) == 1:
        return state
    next_task = manifest['next_task']
    if (state['steps'][1]['task_id'] != next_task['task_id'] or
            next_task['independent_of'] != manifest['evidence_request']['indicator'] or
            state['steps'][1]['autonomous'] is not True):
        raise ValueError('Unsafe next-task transition')
    result_path = state_dir / 'next_result.json'
    if _sha(result_path) != state['steps'][1]['output_sha256']:
        raise ValueError('Next-task result hash mismatch')
    result = json.loads(result_path.read_text())
    synthetic_verify({'synthetic_values': next_task['synthetic_values']}, result)
    if result['mean'] != sum(next_task['synthetic_values']) / len(next_task['synthetic_values']):
        raise ValueError('Next-task independent recomputation failed')
    if state['status'] != 'EXPLORATORY_ONLY' or result.get('official_market_claim') is not False:
        raise ValueError('Fixture promoted to official research')
    return state


def run(manifest: dict, state_dir: Path) -> dict:
    """Persist each task before selecting the next, so a crash can resume."""
    workflow = state_dir / 'workflow.json'
    if workflow.is_symlink():
        raise ValueError('Symlinked workflow checkpoint')
    identity = _identity(manifest)
    state = json.loads(workflow.read_text()) if workflow.exists() else {
        'schema_version': 1, 'identity_sha256': identity, 'status': 'RUNNING',
        'phase': 'DETECT', 'steps': [], 'transitions': [], 'model_calls': 0,
        'network_requests': 0, 'incremental_model_cost': 0,
        'provider_billing_detail': 'UNKNOWN', 'autonomous': True,
        'selection_origin': 'REVIEWED_RULE', 'operator_followup_commands': 0}
    if state['identity_sha256'] != identity:
        raise ValueError('Workflow identity changed')
    if state['steps']:
        verify(manifest, state_dir)
    else:
        request = manifest['evidence_request']
        state['phase'] = 'CLASSIFY'
        state['transitions'].append({'from': 'DETECT', 'to': 'CLASSIFY',
            'reason': 'Indicator source requires point-in-time evidence'})
        state['phase'] = 'COLLECT_EVIDENCE'
        state['transitions'].append({'from': 'CLASSIFY', 'to': 'COLLECT_EVIDENCE',
            'reason': 'Approved offline FRED/ALFRED input and matrix'})
        write_state(workflow, state)
        evidence = collect_indicator_evidence(request)
        write_state(state_dir / 'evidence_result.json', dict(evidence))
        state['steps'].append({'task_id': request['task_id'], 'task_key': evidence['request_sha256'],
            'status': evidence['status'], 'output_sha256': _sha(state_dir / 'evidence_result.json'),
            'autonomous': True, 'model_calls': 0, 'network_requests': 0,
            'selected_action': 'COLLECT_INDICATOR_EVIDENCE',
            'unselected_actions': ['ASSUME_SCHEDULED_POSTING_TIME', 'PROMOTE_SEVEN_DAY_LAG'],
            'reason': 'Hash-checked source dates cannot prove intraday access'})
        state['phase'] = 'PROPOSE_OPTIONS'
        state['transitions'].append({'from': 'COLLECT_EVIDENCE', 'to': 'PROPOSE_OPTIONS',
            'reason': evidence['status'], 'evidence_sha256': state['steps'][0]['output_sha256']})
        write_state(workflow, state)
    if len(state['steps']) == 1:
        next_task = manifest['next_task']
        if (next_task['task_id'] == manifest['evidence_request']['task_id'] or
                next_task['independent_of'] != manifest['evidence_request']['indicator']):
            raise ValueError('Duplicate or dependent fallback task')
        state['phase'] = 'POLICY_AND_BUDGET_GATE'
        state['transitions'].append({'from': 'PROPOSE_OPTIONS', 'to': 'POLICY_AND_BUDGET_GATE',
            'reason': 'Only allowlisted offline fixture remains independent'})
        write_state(workflow, state)
        if manifest['max_model_calls'] != 0:
            raise ValueError('Offline workflow model budget must be zero')
        state['phase'] = 'NEXT_SAFE_TASK'
        state['transitions'].append({'from': 'POLICY_AND_BUDGET_GATE', 'to': 'NEXT_SAFE_TASK',
            'reason': 'PIT task blocked; fixture has no market-PIT dependency',
            'blocked_task_id': manifest['evidence_request']['task_id'],
            'selected_task_id': next_task['task_id']})
        write_state(workflow, state)
        delay = manifest.get('fixture_delay_after_evidence_seconds', 0)
        if delay:
            time.sleep(delay)
        result = synthetic_execute({'synthetic_values': next_task['synthetic_values']},
                                   {'adapter': 'agent2_synthetic'})
        result['official_market_claim'] = False
        write_state(state_dir / 'next_result.json', result)
        state['steps'].append({'task_id': next_task['task_id'],
            'task_key': hashlib.sha256(canonical((identity, next_task['task_id']))).hexdigest(),
            'status': 'VERIFIED_FIXTURE', 'output_sha256': _sha(state_dir / 'next_result.json'),
            'autonomous': True, 'model_calls': 0, 'network_requests': 0,
            'selected_action': 'SYNTHETIC_SIGNAL_CHECK',
            'unselected_actions': ['RETRY_BLOCKED_PIT_WITHOUT_NEW_EVIDENCE'],
            'reason': 'Independent safe task selected after blocked PIT evidence'})
        state['phase'] = 'VERIFY_INDEPENDENTLY'
        state['transitions'].append({'from': 'NEXT_SAFE_TASK', 'to': 'VERIFY_INDEPENDENTLY',
            'reason': 'Check source hash and recompute fixture result'})
        state['status'] = 'EXPLORATORY_ONLY'
        write_state(workflow, state)
    verify(manifest, state_dir)
    if state['phase'] != 'TERMINAL':
        state['transitions'].append({'from': 'VERIFY_INDEPENDENTLY', 'to': 'TERMINAL',
            'reason': 'PIT evidence remains blocked; independent fixture verified'})
        state['phase'] = 'TERMINAL'
        write_state(workflow, state)
    return {'status': state['status'], 'workflow_path': str(workflow),
            'workflow_sha256': _sha(workflow), 'evidence_sha256': state['steps'][0]['output_sha256'],
            'next_sha256': state['steps'][1]['output_sha256'], 'transition_count': 1,
            'evidence_status': state['steps'][0]['status'], 'model_calls': 0,
            'network_requests': 0, 'official_market_claim': False}
