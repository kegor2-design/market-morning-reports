"""Bounded model proposal boundary for reviewed Research Program DAGs.

The model explains a goal and proposes tasks. Only the host's existing source,
action, budget and DAG contract can become executable. No model output grants
new capability or changes a sealed Goal Contract.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

from jsonschema import ValidationError, validate

from .engine import canonical, now, write_state
from .isolated_codex import (PRIVATE_ROOT, _try_reserve_request,
                             call_structured, classify_model_failure)
from .research_planner import plan_goal, validate_plan
from .rate_analysis import SIGNALS
from .source_adapters import REGISTRY

SCHEMA = Path(__file__).with_name('ai_program_candidate.schema.json')


def capability_registry() -> dict:
    """Expose only implemented, reviewed source and analysis capabilities."""
    from .research_planner import ACTIONS
    return {'version': 1, 'sources': sorted(REGISTRY),
            'actions': sorted(set(ACTIONS.values())),
            'rate_signals': dict(SIGNALS),
            'pit_status': 'UNVERIFIED', 'official_claim_allowed': False}


def validate_candidate(goal: str, candidate: dict) -> dict:
    """Compile a candidate against immutable host policy and implemented actions."""
    validate(candidate, json.loads(SCHEMA.read_text()))
    baseline = plan_goal(goal)
    if (candidate['goal_id'] != baseline['goal_id'] or
            candidate['original_research_goal'] != goal or
            candidate['market'] != baseline['market'] or
            candidate['data_requirements'] != baseline['data_requirements'] or
            candidate['allowed_sources'] != baseline['allowed_sources'] or
            candidate['evaluation_methods'] != baseline['evaluation_methods']):
        raise ValueError('AI proposal changes immutable Goal or reviewed source policy')
    expected = {task['task_id']: task for task in baseline['tasks']}
    proposed = {task['task_id']: task for task in candidate['task_dag']}
    if len(proposed) != len(candidate['task_dag']) or set(proposed) != set(expected):
        raise ValueError('AI proposal DAG omits or duplicates reviewed capabilities')
    for task_id, task in proposed.items():
        if task['task_type'] != expected[task_id]['task_type'] or \
                task['allowed_actions'] != expected[task_id]['allowed_actions']:
            raise ValueError('AI proposal DAG changes implemented action')
    plan = deepcopy(baseline)
    for task in plan['tasks']:
        task['dependencies'] = list(proposed[task['task_id']]['dependencies'])
    if baseline['market'] == 'US_RATES':
        signal = next((key for key, description in SIGNALS.items()
                       if description == candidate['hypothesis']), None)
        if signal is None:
            raise ValueError('AI hypothesis requires an unimplemented analysis capability')
        analysis = next(task for task in plan['tasks']
                        if task['task_type'] == 'EXPERIMENT_EXECUTION')
        if signal != 'positive_spread' or any(task['dependencies'] !=
                expected[task['task_id']]['dependencies'] for task in plan['tasks']):
            plan['goal_contract']['version'] = 2
            plan['research_hypotheses'] = [candidate['hypothesis']]
            plan['goal_contract']['hypotheses'] = [candidate['hypothesis']]
            analysis['inputs'] = {'hypothesis': candidate['hypothesis'],
                                  'signal': signal, 'train_rows': 12}
    elif candidate['hypothesis'] != baseline['research_hypotheses'][0] or any(
            task['dependencies'] != expected[task['task_id']]['dependencies']
            for task in plan['tasks']):
        raise ValueError('AI proposal requires an unimplemented market capability')
    validate_plan(plan)
    return plan


def request_plan(goal: str, state_dir: Path, *, approval: dict | None = None,
                 timeout: int = 90, caller=call_structured) -> dict:
    """Reserve one model side effect; uncertain calls are never retried.

    Approval must be an independently supplied, finite cost/call contract. It
    cannot be sourced from model output. The repository supplies no default.
    """
    plan = plan_goal(goal)
    if not 1 <= timeout <= 90:
        raise ValueError('Model time budget outside reviewed range')
    if state_dir.is_symlink() or not state_dir.resolve().is_relative_to(PRIVATE_ROOT):
        raise ValueError('Model state outside private research root')
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    immutable = {key: plan['goal_contract'][key] for key in (
        'goal_id', 'original_research_goal', 'market', 'research_period', 'target',
        'allowed_sources', 'allowed_actions', 'pit_policy', 'holdout_policy',
        'resource_budget', 'terminal_conditions')}
    prompt = ('Propose a research plan for this exact goal: ' + goal + '\n'
              'The host enforces this immutable goal/policy contract: ' +
              canonical(immutable).decode() + '\nImplemented capabilities: ' +
              canonical(capability_registry()).decode() + '\nReviewed task identities and actions: ' +
              canonical([{key: task[key] for key in ('task_id', 'task_type',
                  'dependencies', 'allowed_actions')} for task in plan['tasks']]).decode() +
              '\nFor US rates you may choose either reviewed rate signal and vary discovery '
              'dependencies without cycles; analysis must depend on all discovery tasks. '
              'Return only the candidate schema. Do not alter goal, source, action, '
              'budget, PIT or holdout policy.')
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
    schema_sha = hashlib.sha256(SCHEMA.read_bytes()).hexdigest()
    request_path = state_dir / 'ai_program_request.json'
    response_path = state_dir / 'ai_program_response.json'
    if request_path.exists():
        request = json.loads(request_path.read_text())
        if request['prompt_sha256'] != prompt_sha or request['schema_sha256'] != schema_sha:
            raise ValueError('Model request identity changed')
        if request.get('status') == 'VERIFIED' and response_path.is_file() and \
                hashlib.sha256(response_path.read_bytes()).hexdigest() == request.get('response_sha256'):
            candidate = json.loads(response_path.read_text())
            validate_candidate(goal, candidate)
            return {'status': 'VERIFIED', 'candidate': candidate,
                    'response_sha256': request['response_sha256'], 'reused': True}
        return {'status': 'BLOCKED_UNCERTAIN_MODEL_CALL', 'request_id': request['request_id']}
    if (approval is None or approval.get('status') != 'APPROVED' or
            approval.get('goal_id') != plan['goal_id'] or
            approval.get('max_calls') != 1 or
            not isinstance(approval.get('max_cost_usd'), (int, float)) or
            approval['max_cost_usd'] <= 0 or
            approval.get('max_seconds', 0) < timeout):
        return {'status': 'APPROVAL_REQUIRED', 'model_calls': 0}
    # The existing Codex CLI exposes a wall-time limit but no enforceable
    # per-call monetary ceiling. A declared dollar amount is not enforcement.
    # Only a caller injected by a test provider can exercise the reservation
    # protocol until a budget-enforcing production adapter is reviewed.
    if caller is call_structured or approval.get('provider') != 'INJECTED_TEST':
        return {'status': 'BLOCKED_COST_ENFORCEMENT', 'model_calls': 0}
    request_id = hashlib.sha256(canonical({'goal_id': plan['goal_id'],
        'prompt_sha256': prompt_sha, 'schema_sha256': schema_sha})).hexdigest()[:24]
    request = {'request_id': request_id, 'goal_id': plan['goal_id'],
        'prompt_sha256': prompt_sha, 'schema_sha256': schema_sha,
        'max_calls': 1, 'max_seconds': timeout,
        'max_cost_usd': approval['max_cost_usd'], 'status': 'RESERVED',
        'created_at_utc': now()}
    if not _try_reserve_request(request_path, request):
        return {'status': 'BLOCKED_UNCERTAIN_MODEL_CALL', 'request_id': request_id}
    try:
        completed = caller(prompt, SCHEMA, 'ai_program_response.json', state_dir,
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        request.update(status='BLOCKED', error_type=classify_model_failure(
            str(exc), timed_out=isinstance(exc, subprocess.TimeoutExpired)))
        write_state(request_path, request)
        return {'status': 'BLOCKED_MODEL', 'error_type': request['error_type']}
    if completed.returncode != 0:
        request.update(status='BLOCKED', error_type=classify_model_failure(completed.stderr))
        write_state(request_path, request)
        return {'status': 'BLOCKED_MODEL', 'error_type': request['error_type']}
    try:
        candidate = json.loads(response_path.read_text())
        validate_candidate(goal, candidate)
    except (OSError, ValueError, KeyError, ValidationError) as exc:
        request.update(status='BLOCKED', error_type='MODEL_OUTPUT_VALIDATION_FAILED')
        write_state(request_path, request)
        return {'status': 'BLOCKED_MODEL_OUTPUT', 'error_type': type(exc).__name__}
    request.update(status='VERIFIED', response_sha256=hashlib.sha256(
        response_path.read_bytes()).hexdigest())
    write_state(request_path, request)
    return {'status': 'VERIFIED', 'candidate': candidate,
            'response_sha256': request['response_sha256'], 'reused': False}
