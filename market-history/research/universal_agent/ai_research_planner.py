"""Bounded model proposal boundary for reviewed Research Program DAGs.

The model explains a goal and proposes tasks. Only the host's existing source,
action, budget and DAG contract can become executable. No model output grants
new capability or changes a sealed Goal Contract.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from jsonschema import ValidationError, validate

from .engine import canonical, now, write_state
from .isolated_codex import (PRIVATE_ROOT, _try_reserve_request,
                             call_structured, classify_model_failure)
from .research_planner import plan_goal, validate_plan

SCHEMA = Path(__file__).with_name('ai_program_candidate.schema.json')


def validate_candidate(goal: str, candidate: dict) -> dict:
    """Return the only executable plan allowed by the host for this goal."""
    validate(candidate, json.loads(SCHEMA.read_text()))
    plan = plan_goal(goal)
    validate_plan(plan)
    if (candidate['goal_id'] != plan['goal_id'] or
            candidate['original_research_goal'] != goal or
            candidate['market'] != plan['market'] or
            candidate['data_requirements'] != plan['data_requirements'] or
            candidate['allowed_sources'] != plan['allowed_sources'] or
            candidate['hypothesis'] != plan['research_hypotheses'][0] or
            candidate['evaluation_methods'] != plan['evaluation_methods']):
        raise ValueError('AI proposal changes the sealed goal or reviewed research method')
    expected = [{key: task[key] for key in ('task_id', 'task_type', 'dependencies',
                                             'allowed_actions')} for task in plan['tasks']]
    if candidate['task_dag'] != expected:
        raise ValueError('AI proposal changes the reviewed executable DAG')
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
    prompt = ('Propose a research plan for this exact goal: ' + goal + '\n'
              'The host permits only this reviewed plan contract and task graph: ' +
              canonical(plan).decode() + '\nReturn the candidate schema only. '
              'Do not change sources, actions, hypothesis, budget, PIT or holdout status.')
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
