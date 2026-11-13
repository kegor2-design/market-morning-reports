"""One bounded research job owned by an independent process supervisor."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

from jsonschema import validate

from .agent2_synthetic import execute as synthetic_execute, verify as synthetic_verify
from .engine import canonical, locked_state, now, write_state
from .isolated_codex import PRIVATE_ROOT
from .self_repair import redact
from .guided_experiment import AI_ROOT, PRIVATE_ROOT as GUIDED_ROOT

SCHEMA = Path(__file__).with_name('research_job.schema.json')
ACTION_REGISTRY = {
    'synthetic_research': {'action': 'SYNTHETIC_SIGNAL_CHECK', 'risk': 'fixture_only',
                           'idempotent': True, 'rollback': 'discard_private_artifact'},
    'pit_problem': {'action': 'PIT_PROBLEM_SOLVE', 'risk': 'read_only_research',
                    'idempotent': False, 'rollback': 'preserve_uncertain_ai_call'},
    'guided_experiment': {'action': 'GUIDED_EXPERIMENT', 'risk': 'sandboxed_research',
                          'idempotent': True, 'rollback': 'preserve_guided_checkpoint'},
    'guided_e2e': {'action': 'GUIDED_E2E', 'risk': 'sandboxed_research',
                   'idempotent': False, 'rollback': 'preserve_uncertain_ai_call'},
    'evidence_workflow': {'action': 'EVIDENCE_WORKFLOW', 'risk': 'read_only_research',
                          'idempotent': True, 'rollback': 'preserve_hashed_task_checkpoints'},
    'data_recovery': {'action': 'DATA_RECOVERY', 'risk': 'read_only_research',
                      'idempotent': False, 'rollback': 'preserve_uncertain_api_call'},
}
FINAL = {'VERIFIED_RESEARCH_CONCLUSION', 'RESEARCH_BLOCKED_WITH_EVIDENCE',
         'FAILED_TERMINAL'}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError('Symlinked job path')
    resolved = path.resolve()
    if resolved == PRIVATE_ROOT or not resolved.is_relative_to(PRIVATE_ROOT):
        raise ValueError('Job path outside dedicated private root')
    resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    return resolved


def manifest_load(path: Path) -> tuple[dict, str]:
    if path.is_symlink():
        raise ValueError('Symlinked manifest')
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(PRIVATE_ROOT) or not resolved.is_file():
        raise ValueError('Manifest outside private root')
    data = json.loads(resolved.read_text())
    validate(data, json.loads(SCHEMA.read_text()))
    if data['mode'] == 'synthetic_research':
        values = data['synthetic_values']
        if any(isinstance(value, bool) for value in values):
            raise ValueError('Boolean is not a research observation')
    if data['mode'] in {'guided_experiment', 'guided_e2e'}:
        for key, root in (('ai_state_dir', AI_ROOT), ('guided_state_dir', GUIDED_ROOT)):
            candidate = Path(data[key])
            if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()):
                raise ValueError(f'{key} outside private research root')
    if data['mode'] == 'evidence_workflow':
        request, next_task = data['evidence_request'], data['next_task']
        if (request['goal_id'] != data['job_id'] or
                request['task_id'] == next_task['task_id'] or
                next_task['independent_of'] != request['indicator'] or
                request['budget']['max_seconds'] > data['max_seconds'] or
                request['budget']['max_model_calls'] != 0 or
                request['budget']['max_network_requests'] != 0):
            raise ValueError('Evidence task identity, dependency or budget invalid')
    if data['mode'] == 'data_recovery':
        request = data['data_request']
        if (request['job_id'] != data['job_id'] or request['goal_id'] != data['job_id'] or
                request['budget']['max_seconds'] > data['max_seconds'] or
                request['budget']['max_model_calls'] != 0 or data['max_restarts'] > 1):
            raise ValueError('Recovery task identity or budget invalid')
    return data, sha(resolved)


def plan_for(manifest: dict, manifest_sha: str) -> dict:
    contract = ACTION_REGISTRY[manifest['mode']]
    input_sha = hashlib.sha256(canonical({
        'goal': manifest['goal'], 'hypothesis': manifest.get('hypothesis'),
        'values': manifest.get('synthetic_values'), 'mode': manifest['mode'],
        'ai_state_dir': manifest.get('ai_state_dir'),
        'guided_state_dir': manifest.get('guided_state_dir'),
        'fault_kind': manifest.get('fault_kind'),
        'evidence_request': manifest.get('evidence_request'),
        'data_request': manifest.get('data_request'),
        'next_task': manifest.get('next_task'),
        'max_follow_on_hypotheses': manifest.get('max_follow_on_hypotheses')})).hexdigest()
    task_id = manifest['job_id'] + '_execute'
    task_key = hashlib.sha256(canonical((manifest_sha, task_id, input_sha))).hexdigest()
    plan = {'goal': manifest['goal'], 'hypothesis': manifest.get('hypothesis'),
            'action': contract['action'], 'risk': contract['risk'],
            'idempotent': contract['idempotent'], 'rollback_rule': contract['rollback'],
            'task_id': task_id, 'task_key': task_key, 'input_sha256': input_sha,
            'max_attempts': manifest['max_restarts'] + 1,
            'max_seconds': manifest['max_seconds'],
            'max_model_calls': manifest['max_model_calls']}
    if manifest['mode'] in {'evidence_workflow', 'data_recovery'}:
        plan['resource_limits'] = {'cpu_seconds': min(manifest['max_seconds'], 60),
                                   'memory_mb': 512, 'file_mb': 20, 'open_files': 64,
                                   'network_requests': manifest.get('data_request', {}).get(
                                       'budget', {}).get('max_network_requests', 0)}
    return plan


def _limit_evidence_worker(limits: dict) -> None:
    """Apply OS limits before the offline evidence worker imports source data."""
    cpu = limits['cpu_seconds']
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    memory = limits['memory_mb'] * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    file_size = limits['file_mb'] * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits['open_files'], limits['open_files']))


def _artifact(state_dir: Path) -> Path:
    return state_dir / 'action_result.json'


def _worker(manifest_path: Path, state_dir: Path, task_key: str) -> int:
    manifest, digest = manifest_load(manifest_path)
    state_dir = private(state_dir)
    plan = plan_for(manifest, digest)
    if task_key != plan['task_key']:
        raise ValueError('Task key changed')
    artifact = _artifact(state_dir)
    if artifact.exists():
        raise ValueError('Worker cannot overwrite an existing action artifact')
    before_delay = manifest.get('fixture_delay_before_output_seconds', 0)
    if before_delay and manifest['mode'] == 'synthetic_research':
        time.sleep(before_delay)
    if plan['action'] == 'SYNTHETIC_SIGNAL_CHECK':
        task = {'synthetic_values': manifest['synthetic_values']}
        result = synthetic_execute(task, {'adapter': 'agent2_synthetic'})
        hypothesis = manifest['hypothesis']
        mean = result['mean']
        rejected = not (mean > hypothesis['threshold'] if hypothesis['direction'] == 'mean_above'
                        else mean < hypothesis['threshold'])
        if rejected:
            alternative = {'direction': 'mean_below' if hypothesis['direction'] == 'mean_above'
                           else 'mean_above', 'threshold': hypothesis['threshold']}
            follow_on = synthetic_execute(task, {'adapter': 'agent2_synthetic'})
            result['hypothesis_transition'] = {'reason': 'Observed mean rejected initial direction',
                'hypothesis': alternative, 'result': follow_on, 'transition_count': 1}
    elif plan['action'] == 'PIT_PROBLEM_SOLVE':
        from .problem_solver import solve
        problem_state = private(state_dir / 'pit_solver')
        result = solve(manifest['goal'], problem_state, problem_id=manifest['job_id'])
        result = {'status': result['status'],
                  'problem_state': str(problem_state / 'problem_state.json'),
                  'problem_state_sha256': sha(problem_state / 'problem_state.json'),
                  'solution_request_sha256': sha(problem_state / 'solution_request.json')
                  if (problem_state / 'solution_request.json').exists() else None}
    elif plan['action'] == 'GUIDED_EXPERIMENT':
        from .guided_experiment import run
        guided = run(Path(manifest['ai_state_dir']), Path(manifest['guided_state_dir']))
        checkpoint = Path(manifest['guided_state_dir']) / 'guided_state.json'
        result = {'status': guided['status'], 'guided_checkpoint': str(checkpoint),
                  'guided_checkpoint_sha256': sha(checkpoint),
                  'code_calls': json.loads(checkpoint.read_text()).get('code_calls', 0)}
    elif plan['action'] == 'GUIDED_E2E':
        from .guided_e2e import run_job
        result = run_job(manifest, state_dir)
    elif plan['action'] == 'EVIDENCE_WORKFLOW':
        from .evidence_workflow import run
        result = run(manifest, state_dir)
    elif plan['action'] == 'DATA_RECOVERY':
        from .problem_solver import recover_data_gap
        recovery_dir = private(state_dir / 'data_recovery')
        recovery = recover_data_gap(manifest['data_request'], recovery_dir)
        result = {'status': recovery['status'], 'recovery_checkpoint': str(
            recovery_dir / 'data_recovery.json'),
            'recovery_checkpoint_sha256': sha(recovery_dir / 'data_recovery.json'),
            'content_sha256': recovery.get('content_sha256'),
            'network_requests': recovery['network_requests'], 'official_market_claim': False}
    else:
        raise ValueError('Unregistered action')
    write_state(artifact, {'task_key': task_key, 'action': plan['action'],
                           'input_sha256': plan['input_sha256'], 'result': result})
    delay = manifest.get('fixture_delay_after_output_seconds', 0)
    if delay and manifest['mode'] in {'synthetic_research', 'data_recovery'}:
        time.sleep(delay)
    return 0


def verify_artifact(manifest: dict, plan: dict, state_dir: Path) -> dict:
    path = _artifact(state_dir)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing action artifact')
    item = json.loads(path.read_text())
    if (item.get('task_key') != plan['task_key'] or
            item.get('action') != plan['action'] or
            item.get('input_sha256') != plan['input_sha256']):
        raise ValueError('Action artifact identity mismatch')
    result = item['result']
    if plan['action'] == 'SYNTHETIC_SIGNAL_CHECK':
        synthetic_verify({'synthetic_values': manifest['synthetic_values']}, result)
        if 'hypothesis_transition' in result:
            transition = result['hypothesis_transition']
            if transition['transition_count'] != 1 or transition['hypothesis'] != {
                'direction': 'mean_below' if manifest['hypothesis']['direction'] == 'mean_above'
                else 'mean_above', 'threshold': manifest['hypothesis']['threshold']}:
                raise ValueError('Invalid follow-on hypothesis')
            synthetic_verify({'synthetic_values': manifest['synthetic_values']}, transition['result'])
    elif plan['action'] == 'PIT_PROBLEM_SOLVE':
        state_path = Path(result['problem_state'])
        if (state_path.is_symlink() or state_path.parent.is_symlink() or
                not state_path.resolve().is_relative_to(state_dir.resolve()) or
                sha(state_path) != result['problem_state_sha256']):
            raise ValueError('Problem checkpoint integrity mismatch')
        saved = json.loads(state_path.read_text())
        if (saved.get('problem_id') != manifest['job_id'] or
                saved.get('status') != result['status'] or
                result['status'] not in {'BLOCKED_WITH_EVIDENCE',
                                         'BLOCKED_WITH_ALTERNATIVE_RESEARCH',
                                         'VERIFIED_RESOLUTION', 'BLOCKED_EVIDENCE',
                                         'BLOCKED_AI_CALL', 'BLOCKED_SECURE_RUNNER',
                                         'BLOCKED_UNCERTAIN_AI_CALL',
                                         'BLOCKED_INVALID_AI_RESPONSE'}):
            raise ValueError('Problem solution status unverified')
        if (result['status'] == 'VERIFIED_RESOLUTION' and
                (saved.get('execution_result', {}).get('status') != 'PIT_VERIFIED' or
                 not saved.get('execution_result', {}).get('goal_sources_ready'))):
            raise ValueError('Model-declared PIT completion rejected')
        if result['status'] == 'VERIFIED_RESOLUTION':
            from .problem_solver import collect_pit_evidence
            from regime190.exploratory_backtest import pit_eligibility
            current = collect_pit_evidence()
            sources_ready = (all(current['index_snapshot_provenance'].get(name, {}).get(
                'pit_status') == 'PIT_VERIFIED' for name in ('KOSPI', 'KOSDAQ')) and
                current['independent_holdout'] == 'AVAILABLE')
            if not sources_ready or not pit_eligibility()['eligible_indicator_ids']:
                raise ValueError('Current PIT evidence does not independently verify completion')
        request = state_path.parent / 'solution_request.json'
        if result['solution_request_sha256'] and sha(request) != result['solution_request_sha256']:
            raise ValueError('AI request artifact changed')
        if request.exists():
            request_data = json.loads(request.read_text())
            response = state_path.parent / 'solution_response.json'
            if request_data.get('status') == 'VERIFIED' and (
                    not response.is_file() or
                    request_data.get('response_sha256') != sha(response)):
                raise ValueError('AI solution response changed')
        if result['status'] == 'BLOCKED_WITH_ALTERNATIVE_RESEARCH':
            alternative = state_path.parent / 'alternative_research/autonomous_state.json'
            if alternative.is_symlink() or not alternative.resolve().is_relative_to(state_dir.resolve()):
                raise ValueError('Alternative checkpoint outside job state')
            research = json.loads(alternative.read_text())
            if research.get('official_claim') is not False or not any(
                    cycle['status'] == 'COMPLETED' for cycle in research['cycles'].values()):
                raise ValueError('Alternative research checkpoint unverified')
            snapshot = Path(research['snapshot'])
            if (snapshot.is_symlink() or sha(snapshot) != research['snapshot_sha256'] or
                    research['snapshot_sha256'] != saved['evidence'][
                        'index_snapshot_provenance']['KOSPI']['sha256']):
                raise ValueError('Alternative research source integrity mismatch')
            for cycle in research['cycles'].values():
                if cycle['status'] == 'COMPLETED' and hashlib.sha256(json.dumps(
                        cycle['result'], sort_keys=True).encode()).hexdigest() != cycle['result_sha256']:
                    raise ValueError('Alternative research result integrity mismatch')
    elif plan['action'] == 'GUIDED_EXPERIMENT':
        from .guided_experiment import _load_ai, _sha, assess_hypothesis, validate_fold_output
        from regime190.agent43_engine import _verify_market
        checkpoint = Path(result['guided_checkpoint'])
        if (checkpoint.is_symlink() or checkpoint.resolve() !=
                (Path(manifest['guided_state_dir']) / 'guided_state.json').resolve() or
                sha(checkpoint) != result['guided_checkpoint_sha256']):
            raise ValueError('Guided checkpoint integrity mismatch')
        saved = json.loads(checkpoint.read_text())
        if saved.get('status') != result['status'] or saved.get('code_calls', 0) > plan['max_model_calls']:
            raise ValueError('Guided model budget or status mismatch')
        if result['status'] == 'EXPLORATORY_BACKTEST_VERIFIED':
            _, ai_hash = _load_ai(Path(manifest['ai_state_dir']))
            if saved['ai_response_sha256'] != ai_hash:
                raise ValueError('Guided AI hypothesis changed')
            task_dir = Path(saved['data']['task_dir'])
            sealed_dir = Path(saved['data']['sealed_dir'])
            root = Path(manifest['guided_state_dir']).resolve()
            if (not task_dir.resolve().is_relative_to(root) or
                    not sealed_dir.resolve().is_relative_to(root)):
                raise ValueError('Guided execution paths outside checkpoint')
            code_hash = saved.get('active_code_sha256', saved['code_sha256'])
            for fold, input_hash in saved['data']['input_sha256'].items():
                fold_dir = task_dir / fold
                checked = validate_fold_output(fold_dir, input_hash)
                if (checked['output_sha256'] != saved['output_sha256'][fold] or
                        _sha(fold_dir / 'experiment.py') != code_hash):
                    raise ValueError('Guided source or output integrity mismatch')
            if _verify_market(task_dir, sealed_dir, 'crash') != saved['result']:
                raise ValueError('Guided sealed-fold verification failed')
            if saved.get('hypothesis_assessment') and assess_hypothesis(
                    task_dir, sealed_dir, saved['data']['input_sha256']) != saved['hypothesis_assessment']:
                raise ValueError('Guided hypothesis assessment changed')
    elif plan['action'] == 'GUIDED_E2E':
        from .guided_e2e import _used_calls, verify_cycle
        if result.get('official_market_claim') is not False or result.get('status') not in {
                'EXPLORATORY_ONLY', 'BLOCKED_FAULT_REPAIR', 'BLOCKED_ALTERNATE_MODEL',
                'BLOCKED_DUPLICATE_HYPOTHESIS', 'BLOCKED_ALTERNATE_EXECUTION'}:
            raise ValueError('Invalid exploratory E2E status')
        cycles = result['cycles']
        if len(cycles) > manifest['max_follow_on_hypotheses'] + 1 or result.get(
                'transition_count', 0) != max(0, len(cycles) - 1):
            raise ValueError('Hypothesis transition bound exceeded')
        seen = set()
        for index, cycle in enumerate(cycles):
            ai_dir = Path(cycle['ai_dir'])
            data_dir = Path(cycle['data_dir'])
            alternate_index = cycle.get('alternative_index', 0)
            if (alternate_index == 0) != (index == 0) or not 0 <= alternate_index <= manifest[
                    'max_follow_on_hypotheses']:
                raise ValueError('Cycle index mismatch')
            expected_ai = (Path(manifest['ai_state_dir']) if index == 0 else
                           AI_ROOT / f"{manifest['job_id']}_alt{alternate_index}")
            expected_data = (Path(manifest['guided_state_dir']) if index == 0 else
                             GUIDED_ROOT / f"{manifest['job_id']}_alt{alternate_index}")
            if ai_dir.resolve() != expected_ai.resolve() or data_dir.resolve() != expected_data.resolve():
                raise ValueError('Cycle identity mismatch')
            hypothesis = verify_cycle(ai_dir, data_dir, cycle)
            identity = hashlib.sha256(canonical((hypothesis['hypothesis'].lower().strip(),
                hypothesis['economic_reason'].lower().strip()))).hexdigest()
            if identity in seen:
                raise ValueError('Duplicate market hypothesis')
            seen.add(identity)
            if index == 0:
                evidence = data_dir / 'integrated_fault_evidence.json'
                if (not evidence.is_file() or sha(evidence) != cycle['fault_evidence_sha256'] or
                        cycle['fault_status'] != 'INTEGRATED_FAULT_INJECTION_VERIFIED'):
                    raise ValueError('Fault repair evidence missing')
                proof = json.loads(evidence.read_text())
                if (proof['status'] != cycle['fault_status'] or
                        proof['repair']['status'] != 'REPAIRED' or
                        not proof['model_called_during_trial']):
                    raise ValueError('Actual model repair not proven')
        if result['status'] == 'EXPLORATORY_ONLY' and not cycles:
            raise ValueError('No verified market cycle')
        for attempt in result.get('rejected_attempts', []):
            attempt_index = attempt['index']
            if not 1 <= attempt_index <= manifest['max_follow_on_hypotheses']:
                raise ValueError('Rejected attempt index outside bound')
            ai_response = AI_ROOT / f"{manifest['job_id']}_alt{attempt_index}" / 'ai_response.json'
            checkpoint = state_dir / f'alternate_attempt_{attempt_index}.json'
            if (not ai_response.is_file() or sha(ai_response) != attempt['hypothesis_sha256'] or
                    json.loads(checkpoint.read_text()) != attempt):
                raise ValueError('Rejected alternative evidence changed')
        if result['status'] == 'BLOCKED_FAULT_REPAIR':
            evidence = Path(manifest['guided_state_dir']) / 'integrated_fault_evidence.json'
            if (cycles or not evidence.is_file() or
                    sha(evidence) != result['fault_evidence_sha256'] or
                    json.loads(evidence.read_text())['status'] != result['fault_status']):
                raise ValueError('Blocked fault evidence mismatch')
        if (result.get('model_calls', 0) != _used_calls(manifest) or
                result['model_calls'] > plan['max_model_calls']):
            raise ValueError('E2E model budget exceeded')
    elif plan['action'] == 'EVIDENCE_WORKFLOW':
        from .evidence_workflow import verify
        workflow = Path(result['workflow_path'])
        if (workflow.is_symlink() or workflow.resolve() !=
                (state_dir / 'workflow.json').resolve() or
                sha(workflow) != result['workflow_sha256']):
            raise ValueError('Evidence workflow checkpoint integrity mismatch')
        saved = verify(manifest, state_dir)
        if (len(saved['steps']) != 2 or result['evidence_sha256'] != saved['steps'][0][
                'output_sha256'] or result['next_sha256'] != saved['steps'][1]['output_sha256'] or
                result['transition_count'] != 1 or result['evidence_status'] != saved['steps'][0][
                    'status'] or result['model_calls'] != 0 or
                result['network_requests'] != 0 or result['official_market_claim'] is not False):
            raise ValueError('Evidence workflow transition unverified')
    elif plan['action'] == 'DATA_RECOVERY':
        path = Path(result['recovery_checkpoint'])
        if (path.is_symlink() or path.resolve() !=
                (state_dir / 'data_recovery/data_recovery.json').resolve() or
                sha(path) != result['recovery_checkpoint_sha256']):
            raise ValueError('Recovery checkpoint integrity mismatch')
        saved = json.loads(path.read_text())
        if (saved['request_sha256'] != hashlib.sha256(canonical(
                manifest['data_request'])).hexdigest() or
                saved['status'] != result['status'] or
                saved.get('content_sha256') != result['content_sha256'] or
                saved['network_requests'] > plan['resource_limits']['network_requests'] or
                result['official_market_claim'] is not False):
            raise ValueError('Recovery identity, budget or status mismatch')
        if result['status'] in {'DATA_RECOVERED_PIT_UNVERIFIED', 'DATA_MISMATCH'}:
            from .data_recovery import verify_recovery
            verify_recovery(manifest['data_request'], path.parent)
        elif result['status'] not in {'BLOCKED_ENV', 'BLOCKED_EVIDENCE',
                                      'BLOCKED_UNCERTAIN_API_CALL',
                                      'EXISTING_DATA_UNVERIFIED'}:
            raise ValueError('Unsupported recovery status')
    else:
        raise ValueError('Unregistered action')
    return item


def _conclude(manifest: dict, plan: dict, artifact: dict, output_sha: str) -> dict:
    if plan['action'] == 'SYNTHETIC_SIGNAL_CHECK':
        values = manifest['synthetic_values']
        observed = sum(values) / len(values)
        reported = artifact['result']['mean']
        if abs(observed - reported) > 1e-9:
            raise ValueError('Independent result recomputation failed')
        threshold = manifest['hypothesis']['threshold']
        direction = manifest['hypothesis']['direction']
        supports = observed > threshold if direction == 'mean_above' else observed < threshold
        return {'status': 'VERIFIED_RESEARCH_CONCLUSION',
                'scope': 'SYNTHETIC_FIXTURE_ONLY', 'hypothesis_supported': supports,
                'hypothesis_transition': artifact['result'].get('hypothesis_transition'),
                'observed_mean': observed, 'threshold': threshold,
                'sample_size': len(values), 'official_market_claim': False,
                'input_sha256': plan['input_sha256'], 'output_sha256': output_sha}
    result = artifact['result']
    if plan['action'] == 'EVIDENCE_WORKFLOW':
        return {'status': 'RESEARCH_BLOCKED_WITH_EVIDENCE',
                'reason': result['evidence_status'],
                'next_task_status': 'VERIFIED_FIXTURE', 'scope': 'EXPLORATORY_ONLY',
                'official_market_claim': False, 'input_sha256': plan['input_sha256'],
                'output_sha256': output_sha}
    if plan['action'] == 'DATA_RECOVERY':
        return {'status': 'RESEARCH_BLOCKED_WITH_EVIDENCE',
                'reason': result['status'], 'official_market_claim': False,
                'recovery_checkpoint_sha256': result['recovery_checkpoint_sha256'],
                'input_sha256': plan['input_sha256'], 'output_sha256': output_sha}
    if plan['action'] == 'GUIDED_E2E':
        return {'status': 'RESEARCH_BLOCKED_WITH_EVIDENCE',
                'reason': 'PIT_UNVERIFIED' if result['status'] == 'EXPLORATORY_ONLY'
                else result['status'], 'official_market_claim': False,
                'transition_count': result.get('transition_count', 0),
                'input_sha256': plan['input_sha256'], 'output_sha256': output_sha}
    if plan['action'] == 'GUIDED_EXPERIMENT':
        return {'status': 'RESEARCH_BLOCKED_WITH_EVIDENCE',
                'reason': 'PIT_UNVERIFIED' if result['status'] == 'EXPLORATORY_BACKTEST_VERIFIED'
                else result['status'], 'official_market_claim': False,
                'guided_checkpoint_sha256': result['guided_checkpoint_sha256'],
                'input_sha256': plan['input_sha256'], 'output_sha256': output_sha}
    return {'status': 'RESEARCH_BLOCKED_WITH_EVIDENCE',
            'reason': result['status'], 'official_market_claim': False,
            'input_sha256': plan['input_sha256'], 'output_sha256': output_sha,
            'problem_state_sha256': result['problem_state_sha256']}


def supervise(manifest_path: Path, state_dir: Path) -> dict:
    manifest, digest = manifest_load(manifest_path)
    state_dir = private(state_dir)
    if manifest['mode'] in {'guided_experiment', 'guided_e2e'}:
        guided_dir = Path(manifest['guided_state_dir']).resolve()
        if (guided_dir == state_dir or guided_dir.is_relative_to(state_dir)
                or state_dir.is_relative_to(guided_dir)):
            raise ValueError('Guided state and supervisor checkpoint must be separate')
    plan = plan_for(manifest, digest)
    path = state_dir / 'job.json'
    with locked_state(state_dir):
        state = json.loads(path.read_text()) if path.exists() else {
            'schema_version': 1, 'job_id': manifest['job_id'], 'manifest_sha256': digest,
            'plan': plan, 'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(),
            'status': 'PENDING', 'task_status': 'PENDING', 'attempts': 0,
            'worker_restarts': 0, 'worker_crashes': 0,
            'duplicate_completion_count': 0, 'model_calls': 0,
            'events': [], 'started_at_utc': now()}
        if (state['job_id'] != manifest['job_id'] or state['manifest_sha256'] != digest or
                state['plan_sha256'] != hashlib.sha256(canonical(plan)).hexdigest()):
            raise ValueError('Job manifest or plan changed')
        if state['status'] in FINAL:
            if state.get('output_sha256'):
                verify_artifact(manifest, plan, state_dir)
                if sha(_artifact(state_dir)) != state['output_sha256']:
                    raise ValueError('Final output integrity mismatch')
            return {**state, 'reused_checkpoint': True}
        state['supervisor_pid'] = os.getpid()
        deadline = time.monotonic() + manifest['max_seconds']
        stopping = False
        def stop(_signal, _frame):
            nonlocal stopping
            stopping = True
        old_handler = signal.signal(signal.SIGTERM, stop)
        try:
            state['status'] = 'RUNNING'
            state['events'].append({'at_utc': now(), 'event': 'PLAN_VERIFIED',
                                    'task_id': plan['task_id'], 'input_sha256': plan['input_sha256'],
                                    'plan_sha256': state['plan_sha256']})
            write_state(path, state)
            while not stopping and time.monotonic() < deadline:
                if (state_dir / 'STOP').exists():
                    stopping = True
                    break
                artifact = _artifact(state_dir)
                if artifact.exists():
                    try:
                        item = verify_artifact(manifest, plan, state_dir)
                        state['model_calls'] = (item['result'].get('model_calls', 0)
                            if plan['action'] == 'GUIDED_E2E' else
                            item['result'].get('code_calls', 0)
                            if plan['action'] == 'GUIDED_EXPERIMENT' else
                            int((state_dir / 'pit_solver/solution_request.json').exists()))
                        if state['model_calls'] > plan['max_model_calls']:
                            raise ValueError('Model-call budget exceeded')
                        state['output_sha256'] = sha(artifact)
                        state['task_status'] = 'COMPLETED'
                        state['events'].append({'at_utc': now(), 'event': 'ACTION_VERIFIED',
                                                'output_sha256': state['output_sha256']})
                        state['conclusion'] = _conclude(manifest, plan, item,
                                                       state['output_sha256'])
                        state['status'] = state['conclusion']['status']
                        state['completed_at_utc'] = now()
                        write_state(path, state)
                        break
                    except Exception as exc:
                        state['status'] = 'FAILED_TERMINAL'
                        state['reason'] = redact(str(exc))
                        write_state(path, state)
                        break
                if state['attempts'] >= plan['max_attempts']:
                    state['status'] = 'FAILED_TERMINAL'
                    state['reason'] = 'Worker attempt budget exhausted without verified artifact'
                    write_state(path, state)
                    break
                if plan['action'] == 'PIT_PROBLEM_SOLVE':
                    request = state_dir / 'pit_solver/solution_request.json'
                    response = state_dir / 'pit_solver/solution_response.json'
                    if request.exists() and not response.exists():
                        state['model_calls'] = 1
                        state['status'] = 'RESEARCH_BLOCKED_WITH_EVIDENCE'
                        state['reason'] = 'Uncertain prior AI call; no duplicate model request'
                        write_state(path, state)
                        break
                command = [sys.executable, '-m', 'universal_agent.research_job', 'worker',
                           '--manifest', str(manifest_path.resolve()),
                           '--state-dir', str(state_dir), '--task-key', plan['task_key']]
                env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
                worker = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[3],
                                          env=env, stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                          text=True, start_new_session=True,
                                          preexec_fn=(lambda: _limit_evidence_worker(
                                              plan['resource_limits'])) if plan['action'] in
                                              {'EVIDENCE_WORKFLOW', 'DATA_RECOVERY'} else None)
                if state['attempts']:
                    state['worker_restarts'] += 1
                state['attempts'] += 1
                state['worker_pid'] = worker.pid
                state['task_status'] = 'RUNNING'
                state['events'].append({'at_utc': now(), 'event': 'WORKER_STARTED',
                                        'worker_pid': worker.pid, 'task_key': plan['task_key']})
                write_state(path, state)
                while worker.poll() is None and not stopping and time.monotonic() < deadline:
                    if (state_dir / 'STOP').exists():
                        stopping = True
                        break
                    time.sleep(.05)
                if worker.poll() is None:
                    os.killpg(worker.pid, signal.SIGTERM)
                    try:
                        worker.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(worker.pid, signal.SIGKILL)
                _, stderr = worker.communicate(timeout=3)
                state['events'].append({'at_utc': now(), 'event': 'WORKER_EXITED',
                                        'worker_pid': worker.pid, 'exit_code': worker.returncode,
                                        'stderr_tail': redact(stderr[-500:])})
                if worker.returncode != 0:
                    state['worker_crashes'] += 1
                    state['events'].append({'at_utc': now(), 'event': 'CRASH_OR_FAILURE_DETECTED',
                                            'recovery_artifact_present': artifact.exists()})
                write_state(path, state)
            if stopping:
                state['status'] = 'RESEARCH_BLOCKED_WITH_EVIDENCE'
                state['reason'] = 'STOP requested'
            elif time.monotonic() >= deadline and state['status'] == 'RUNNING':
                state['status'] = 'FAILED_TERMINAL'
                state['reason'] = 'Wall-time budget exhausted'
            write_state(path, state)
            return state
        finally:
            signal.signal(signal.SIGTERM, old_handler)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('supervise', 'worker'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--task-key')
    args = parser.parse_args()
    if args.mode == 'worker':
        if not args.task_key:
            raise ValueError('Worker needs a task key')
        return _worker(args.manifest, args.state_dir, args.task_key)
    result = supervise(args.manifest, args.state_dir)
    print(json.dumps({'job_id': result['job_id'], 'status': result['status'],
                      'attempts': result['attempts'],
                      'worker_restarts': result['worker_restarts']}))
    return 0 if result['status'] in {'VERIFIED_RESEARCH_CONCLUSION',
                                     'RESEARCH_BLOCKED_WITH_EVIDENCE'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
