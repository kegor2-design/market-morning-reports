"""Bounded model proposal boundary for reviewed Research Program DAGs.

The model explains a goal and proposes tasks. Only the host's existing source,
action, budget and DAG contract can become executable. No model output grants
new capability or changes a sealed Goal Contract.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import json
import math
import subprocess
from copy import deepcopy
from pathlib import Path

from jsonschema import ValidationError, validate

from .engine import canonical, now, write_state
from .isolated_codex import (PRIVATE_ROOT, _try_reserve_request,
                             call_structured, classify_model_failure)
from .research_planner import ACTIONS, SERIES, _task, plan_goal, validate_plan
from .rate_analysis import SIGNALS
from .source_adapters import REGISTRY

SCHEMA = Path(__file__).with_name('ai_program_candidate.schema.json')


def capability_registry() -> dict:
    """Expose only implemented, reviewed source and analysis capabilities."""
    capabilities = {}
    for task_type, action in ACTIONS.items():
        input_schema = ({'type': 'object', 'required': ['series'],
                         'properties': {'series': {'enum': list(SERIES)}}}
                        if task_type.startswith('DATA_') else
                        {'type': 'object',
                         'required': ['series', 'api_recovery_revision_sha256',
                                      'original_task_id', 'original_request_sha256',
                                      'new_request_id'],
                         'properties': {'series': {'enum': list(SERIES)}}}
                        if task_type == 'API_RECOVERY_RETRY' else
                        {'oneOf': [{'type': 'object', 'maxProperties': 0},
                                   {'type': 'object',
                                    'required': ['signal', 'hypothesis', 'train_rows'],
                                    'properties': {'signal': {'enum': list(SIGNALS)},
                                                   'train_rows': {'const': 12}}}]}
                        if task_type == 'EXPERIMENT_EXECUTION' else
                        {'type': 'object', 'required': ['indicator'],
                         'properties': {'indicator': {'const': '116'}}}
                        if task_type == 'PIT_VALIDATION' else
                        {'type': 'object', 'required': ['revision_sha256', 'failed_task_id'],
                         'properties': {'revision_sha256': {'type': 'string', 'minLength': 64,
                                                            'maxLength': 64},
                                        'failed_task_id': {'const': 'analyze_fixture'}}}
                        if task_type == 'CODE_REPAIR_TASK' else
                        {'type': 'object', 'maxProperties': 0})
        sources = (['US_TREASURY', 'NYFED_REFERENCE_RATES']
                   if task_type in {'DATA_DISCOVERY', 'DATA_ACQUISITION',
                                    'DATA_CALENDAR_REVALIDATION',
                                    'DATA_SCHEMA_REVALIDATION', 'EXPERIMENT_EXECUTION',
                                    'API_RECOVERY_RETRY'}
                   else ['FRED_ALFRED'] if task_type == 'PIT_VALIDATION'
                   else ['LOCAL_CODE_FIXTURE'] if task_type in {
                       'FIXTURE_ANALYSIS', 'CODE_REPAIR_TASK'}
                   else ['NAVER_HASHED_LOCAL'])
        capabilities[task_type] = {
            'capability_id': task_type, 'capability_type': 'RESEARCH_TASK',
            'input_schema': input_schema, 'output_schema': {'type': 'object'},
            'allowed_data_types': list(SERIES) if 'DATA_' in task_type or
                                  task_type in {'EXPERIMENT_EXECUTION',
                                                'API_RECOVERY_RETRY'} else [],
            'supported_research_types': (['US_RATES'] if sources[0] == 'US_TREASURY'
                                         else ['KR_EQUITY_CONTEXT'] if sources[0] == 'FRED_ALFRED'
                                         else ['ISOLATED_CODE_FIXTURE'] if
                                         sources[0] == 'LOCAL_CODE_FIXTURE'
                                         else ['KR_EQUITY_EXPLORATORY']),
            'required_sources': sources, 'action_id': action,
            'execution_permission': ('EXPLICIT_LOCAL_FIXTURE_APPROVAL'
                                     if task_type == 'API_RECOVERY_RETRY'
                                     else 'EXPLICIT_FIXTURE_CANDIDATE_APPROVAL' if
                                     task_type == 'CODE_REPAIR_TASK'
                                     else 'HOST_REVIEWED'),
            'resource_requirements': {'max_network_requests':
                                      1 if task_type in {'DATA_ACQUISITION',
                                                         'API_RECOVERY_RETRY'} else 0,
                                      'max_model_calls': 0},
            'pit_limit': 'EXPLORATORY_ONLY', 'validation_status': 'IMPLEMENTED'}
    return {'version': 3, 'sources': sorted(REGISTRY),
            'actions': sorted(set(ACTIONS.values())),
            'capabilities': capabilities,
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
    if len(proposed) != len(candidate['task_dag']) or not set(expected) <= set(proposed):
        raise ValueError('AI proposal DAG omits or duplicates reviewed capabilities')
    for task_id, task in proposed.items():
        if task_id in expected:
            if task['task_type'] != expected[task_id]['task_type'] or \
                    task['allowed_actions'] != expected[task_id]['allowed_actions']:
                raise ValueError('AI proposal DAG changes implemented action')
        else:
            series = task_id.removeprefix('collect_').upper()
            if (baseline['market'] != 'US_RATES' or series not in SERIES or
                    task_id != 'collect_' + series.lower() or
                    task['task_type'] != 'DATA_ACQUISITION' or
                    task['allowed_actions'] != ['DATA_RECOVERY'] or
                    task['dependencies'] != ['discover_' + series.lower()]):
                raise ValueError('AI proposal DAG adds unimplemented capability or action')
    plan = deepcopy(baseline)
    for task_id in set(proposed) - set(expected):
        series = task_id.removeprefix('collect_').upper()
        plan['tasks'].append(_task(task_id, 'DATA_ACQUISITION', 20,
                                   dependencies=proposed[task_id]['dependencies'],
                                   inputs={'series': series}))
    for task in plan['tasks']:
        task['dependencies'] = list(proposed[task['task_id']]['dependencies'])
    collection_ids = set(proposed) - set(expected)
    if collection_ids and not collection_ids <= set(proposed['analyze_rates']['dependencies']):
        raise ValueError('AI proposal DAG analysis omits acquisition dependency')
    if baseline['market'] == 'US_RATES':
        signal = next((key for key, description in SIGNALS.items()
                       if description == candidate['hypothesis']), None)
        if signal is None:
            raise ValueError('AI hypothesis requires an unimplemented analysis capability')
        analysis = next(task for task in plan['tasks']
                        if task['task_type'] == 'EXPERIMENT_EXECUTION')
        if collection_ids or signal != 'positive_spread' or any(task['dependencies'] !=
                expected[task['task_id']]['dependencies'] for task in plan['tasks']
                if task['task_id'] in expected):
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
    return _proposal(plan['goal_id'], prompt, state_dir, SCHEMA, 'ai_program',
                     lambda candidate: validate_candidate(goal, candidate), approval, timeout, caller)


def request_repair(goal, program_dir, *, approval=None, timeout=30, caller=call_structured):
    from regime190.agent43_engine import _check_code
    plan = plan_goal(goal)
    if ('RESTORE_REVIEWED_KR_ANALYSIS' not in plan['goal_contract']['allowed_actions'] or
            program_dir.is_symlink() or not program_dir.resolve().is_relative_to(PRIVATE_ROOT) or
            type(timeout) is not int or not 1 <= timeout <= 90):
        raise ValueError('Outside reviewed repair scope')
    source = program_dir / 'kr_analysis_copy.py'
    evidence = program_dir / 'kr_analysis_error.json'
    if source.is_symlink() or evidence.is_symlink() or source.stat().st_size > 20000:
        raise ValueError('Unsafe repair input')
    failed_source = source.read_bytes()
    digest = hashlib.sha256(failed_source).hexdigest()
    fault = json.loads(evidence.read_bytes())
    if fault['source_sha256'] != digest or fault['problem_type'] != 'CODE_ERROR':
        raise ValueError('Failure identity changed')
    schema = Path(__file__).with_name('repair_proposal.schema.json')
    def check(candidate):
        validate(candidate, json.loads(schema.read_bytes()))
        if candidate['goal_id'] != plan['goal_id'] or candidate['failed_source_sha256'] != digest:
            raise ValueError('Repair proposal is for a different failure')
        _check_code(candidate['replacement'])
    if (not approval or (approval.get('status') != 'PREFLIGHT' and
            (approval.get('purpose') != 'PROPOSE_REPAIR' or approval.get('failed_source_sha256') != digest))):
        return {'status': 'APPROVAL_REQUIRED', 'model_calls': 0}
    prompt = canonical({'goal_id': plan['goal_id'], 'goal': goal, 'failed_source_sha256': digest,
                        'source': failed_source.decode(), 'diagnosis': fault['reason'],
                        'target': source.name, 'task': 'Propose a replacement for isolated review'}).decode()
    return _proposal(plan['goal_id'], prompt, program_dir, schema, 'ai_repair', check,
                     approval, timeout, caller)


def _proposal(goal_id, prompt, state_dir, schema, name, check, approval, timeout, caller):
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
    schema_sha = hashlib.sha256(schema.read_bytes()).hexdigest()
    request_path = state_dir / (name + '_request.json')
    response_path = state_dir / (name + '_response.json')
    if request_path.is_symlink() or response_path.is_symlink():
        raise ValueError('Symlinked model artifact')
    def read_candidate():
        if response_path.is_symlink() or response_path.stat().st_size > 64_000:
            raise ValueError('Unsafe or oversized model output')
        return json.loads(response_path.read_bytes())
    if request_path.exists():
        request = json.loads(request_path.read_text())
        if request['prompt_sha256'] != prompt_sha or request['schema_sha256'] != schema_sha:
            raise ValueError('Model request identity changed')
        if request.get('status') == 'VERIFIED' and response_path.is_file() and response_path.stat().st_size <= 64_000 and \
                hashlib.sha256(response_path.read_bytes()).hexdigest() == request.get('response_sha256'):
            candidate = read_candidate()
            check(candidate)
            return {'status': 'VERIFIED', 'candidate': candidate,
                    'response_sha256': request['response_sha256'], 'reused': True}
        return {'status': 'BLOCKED_UNCERTAIN_MODEL_CALL', 'request_id': request['request_id']}
    if approval and approval.get('status') == 'PREFLIGHT':
        from .model_transport import prepare
        purpose = 'PROPOSE_REPAIR' if name == 'ai_repair' else 'PROPOSE_PLAN'
        _, scope = prepare(prompt, schema, state_dir, purpose, goal_id, timeout)
        return {'status': 'APPROVAL_REQUIRED', 'model_calls': 0, 'required_scope': scope}
    if (approval is None or approval.get('status') != 'APPROVED' or
            approval.get('goal_id') != goal_id or
            type(approval.get('max_calls')) is not int or
            approval['max_calls'] != 1 or
            type(approval.get('max_cost_usd')) not in (int, float) or
            not math.isfinite(approval['max_cost_usd']) or
            approval['max_cost_usd'] <= 0 or
            type(approval.get('max_seconds')) is not int or
            approval['max_seconds'] < timeout):
        return {'status': 'APPROVAL_REQUIRED', 'model_calls': 0}
    from . import model_transport
    live = approval.get('provider') == 'OPENAI_RESPONSES' and caller is call_structured
    if live:
        purpose = 'PROPOSE_REPAIR' if name == 'ai_repair' else 'PROPOSE_PLAN'
        body, scope = model_transport.prepare(prompt, schema, state_dir, purpose, goal_id, timeout)
        if not model_transport.authorized(scope, approval):
            return {'status': 'APPROVAL_REQUIRED', 'model_calls': 0, 'required_scope': scope}
    elif caller is call_structured or approval.get('provider') != 'INJECTED_TEST':
        return {'status': 'BLOCKED_COST_ENFORCEMENT', 'model_calls': 0}
    request_id = hashlib.sha256(canonical({'goal_id': goal_id,
        'prompt_sha256': prompt_sha, 'schema_sha256': schema_sha})).hexdigest()[:24]
    request = {'request_id': request_id, 'goal_id': goal_id,
        'prompt_sha256': prompt_sha, 'schema_sha256': schema_sha,
        'max_calls': 1, 'max_seconds': timeout,
        'max_cost_usd': approval['max_cost_usd'], 'status': 'RESERVED',
        'created_at_utc': now()}
    request['provider'] = approval['provider']
    if live:
        request.update(scope=scope, approval_sha256=hashlib.sha256(canonical(approval)).hexdigest(),
                       project=approval['project'], billing_overrun_accepted=True)
    # The project lock serializes live proposals from this worktree. The
    # durable goal/purpose reservation survives a client or supervisor crash.
    lock_fd = None
    reserved = False
    try:
        if live:
            lock_fd = os.open(PRIVATE_ROOT / '.model.lock', os.O_CREAT | os.O_NOFOLLOW | os.O_RDWR, 0o600)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'status': 'MODEL_BUSY', 'model_calls': 0}
        if not _try_reserve_request(request_path, request):
            return {'status': 'BLOCKED_UNCERTAIN_MODEL_CALL', 'request_id': request_id}
        reserved = True
        if live:
            output, request['usage'] = model_transport.exchange(body, state_dir, timeout)
            with response_path.open('xb') as stream:
                stream.write(output)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            completed = caller(prompt, schema, response_path.name, state_dir, timeout=timeout)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr or 'Model call failed')
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError, KeyError, TypeError) as exc:
        if not reserved:
            raise
        request.update(status='BLOCKED', error_type=classify_model_failure(
            str(exc), timed_out=isinstance(exc, subprocess.TimeoutExpired)))
        write_state(request_path, request)
        return {'status': 'BLOCKED_MODEL', 'error_type': request['error_type']}
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
    try:
        candidate = read_candidate()
        check(candidate)
    except (OSError, ValueError, KeyError, SyntaxError, ValidationError) as exc:
        request.update(status='BLOCKED', error_type='MODEL_OUTPUT_VALIDATION_FAILED')
        write_state(request_path, request)
        return {'status': 'BLOCKED_MODEL_OUTPUT', 'error_type': type(exc).__name__}
    request.update(status='VERIFIED', response_sha256=hashlib.sha256(
        response_path.read_bytes()).hexdigest())
    write_state(request_path, request)
    return {'status': 'VERIFIED', 'candidate': candidate,
            'response_sha256': request['response_sha256'], 'reused': False}


def propose_design(goal, state_dir, *, approval=None, timeout=60, caller=call_structured):
    """Design unsupported research too. Only a reviewed projection may enter the queue."""
    from .research_planner import UnsupportedGoal
    if (state_dir.is_symlink() or not state_dir.resolve().is_relative_to(PRIVATE_ROOT)
            or type(timeout) is not int or not 1 <= timeout <= 90):
        raise ValueError('Design outside reviewed scope')
    try:
        baseline = plan_goal(goal)
    except UnsupportedGoal:
        baseline = None
    goal_id = 'research_' + hashlib.sha256(goal.encode()).hexdigest()[:12]
    schema = Path(__file__).with_name('research_design.schema.json')
    projection = None if baseline is None else {
        k: baseline[k] for k in ('goal_contract', 'tasks', 'evaluation_methods')}
    prompt = canonical({'goal': goal, 'goal_id': goal_id, 'host_plan': projection,
        'reviewed_signals': SIGNALS, 'candidate_schema': json.loads(SCHEMA.read_bytes()),
        'instruction': 'Design a falsifiable study for the full goal. Specify missing capabilities '
        'and return a null executable_candidate if any required data, action or validation is '
        'unavailable. Otherwise propose the executable DAG using only reviewed capabilities. '
        'Keep independent verification, PIT and stopping criteria explicit.'}).decode()
    def check(design):
        validate(design, json.loads(schema.read_bytes()))
        if design['goal_id'] != goal_id:
            raise ValueError('Design goal changed')
        candidate = design['executable_candidate']
        if candidate is None:
            if not design['missing_capabilities']:
                raise ValueError('Missing capability diagnosis required')
            return
        compiled = validate_candidate(goal, candidate)
        if (baseline is None or design['missing_capabilities']
                or set(design['required_data']) != set(compiled['data_requirements'])
                or set(design['source_candidates']) != set(compiled['allowed_sources'])
                or design['hypotheses'] != compiled['research_hypotheses']
                or design['target_variables'] != [compiled['goal_contract']['target']]
                or design['methods'] != compiled['evaluation_methods']):
            raise ValueError('Design exceeds executable host projection')
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return _proposal(goal_id, prompt, state_dir, schema, 'ai_design', check, approval, timeout, caller)
