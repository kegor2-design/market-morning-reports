"""One bounded research job owned by an independent process supervisor.

The manifest chooses only reviewed actions. Generated code keeps using the
existing guided Agent 4.3 static gate and Bubblewrap path, not this registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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

SCHEMA = Path(__file__).with_name('research_job.schema.json')
ACTION_REGISTRY = {
    'synthetic_research': {'action': 'SYNTHETIC_SIGNAL_CHECK', 'risk': 'fixture_only',
                           'idempotent': True, 'rollback': 'discard_private_artifact'},
    'pit_problem': {'action': 'PIT_PROBLEM_SOLVE', 'risk': 'read_only_research',
                    'idempotent': False, 'rollback': 'preserve_uncertain_ai_call'},
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
    return data, sha(resolved)


def plan_for(manifest: dict, manifest_sha: str) -> dict:
    contract = ACTION_REGISTRY[manifest['mode']]
    input_sha = hashlib.sha256(canonical({
        'goal': manifest['goal'], 'hypothesis': manifest.get('hypothesis'),
        'values': manifest.get('synthetic_values'), 'mode': manifest['mode']})).hexdigest()
    task_id = manifest['job_id'] + '_execute'
    task_key = hashlib.sha256(canonical((manifest_sha, task_id, input_sha))).hexdigest()
    return {'goal': manifest['goal'], 'hypothesis': manifest.get('hypothesis'),
            'action': contract['action'], 'risk': contract['risk'],
            'idempotent': contract['idempotent'], 'rollback_rule': contract['rollback'],
            'task_id': task_id, 'task_key': task_key, 'input_sha256': input_sha,
            'max_attempts': manifest['max_restarts'] + 1,
            'max_seconds': manifest['max_seconds'],
            'max_model_calls': manifest['max_model_calls']}


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
    elif plan['action'] == 'PIT_PROBLEM_SOLVE':
        from .problem_solver import solve
        problem_state = private(state_dir / 'pit_solver')
        result = solve(manifest['goal'], problem_state, problem_id=manifest['job_id'])
        result = {'status': result['status'],
                  'problem_state': str(problem_state / 'problem_state.json'),
                  'problem_state_sha256': sha(problem_state / 'problem_state.json'),
                  'solution_request_sha256': sha(problem_state / 'solution_request.json')
                  if (problem_state / 'solution_request.json').exists() else None}
    else:
        raise ValueError('Unregistered action')
    write_state(artifact, {'task_key': task_key, 'action': plan['action'],
                           'input_sha256': plan['input_sha256'], 'result': result})
    delay = manifest.get('fixture_delay_after_output_seconds', 0)
    if delay and manifest['mode'] == 'synthetic_research':
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
                'observed_mean': observed, 'threshold': threshold,
                'sample_size': len(values), 'official_market_claim': False,
                'input_sha256': plan['input_sha256'], 'output_sha256': output_sha}
    result = artifact['result']
    return {'status': 'RESEARCH_BLOCKED_WITH_EVIDENCE',
            'reason': result['status'], 'official_market_claim': False,
            'input_sha256': plan['input_sha256'], 'output_sha256': output_sha,
            'problem_state_sha256': result['problem_state_sha256']}


def supervise(manifest_path: Path, state_dir: Path) -> dict:
    manifest, digest = manifest_load(manifest_path)
    state_dir = private(state_dir)
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
                        state['model_calls'] = int((state_dir / 'pit_solver/solution_request.json').exists())
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
                                          text=True, start_new_session=True)
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
