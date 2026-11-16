"""Bounded independent supervisor for one approved guided research job."""
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

from .engine import canonical, locked_state, now, write_state
from .guided_experiment import AI_ROOT, PRIVATE_ROOT
from .self_repair import redact


def _program_task_key(goal_id: str, task: dict) -> str:
    return hashlib.sha256(canonical((goal_id, task))).hexdigest()


def _program_manifest(path: Path, data: dict) -> Path:
    """Seal a child Research Job manifest before any external side effect."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Symlinked child manifest')
    if path.exists():
        if json.loads(path.read_text()) != data:
            raise ValueError('Child manifest changed after reservation')
    else:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
    return path


def _child_for(plan: dict, task: dict, program_dir: Path) -> dict:
    """Translate one allowlisted DAG task into the existing Research Job contract."""
    from .research_planner import dates_for, SERIES
    task_id = task['task_id']
    job_id = plan['goal_id'] + '_' + task_id
    base = {'schema_version': 1, 'job_id': job_id,
            'goal': plan['research_goal'], 'max_seconds': 60,
            'max_restarts': 1, 'max_model_calls': 0}
    if task['task_type'] == 'DATA_ACQUISITION':
        series = task['inputs']['series']
        source = 'NYFED_REFERENCE_RATES' if series == 'NYFED_SOFR' else 'US_TREASURY'
        base.update(mode='data_recovery', data_request={
            'goal_id': job_id, 'job_id': job_id, 'task_id': task_id,
            'series': series, 'market': 'US', 'unit': 'percent',
            'start': plan['research_period']['start'],
            'end': plan['research_period']['end'],
            'expected_dates': dates_for(plan), 'existing': {},
            'allowed_sources': [source],
            'budget': {'max_network_requests': 1, 'max_seconds': 25,
                       'max_retries': 0, 'max_model_calls': 0}})
    elif task['task_type'] == 'EXPERIMENT_EXECUTION':
        sources = {}
        for series in SERIES:
            child_id = 'collect_' + series.lower()
            sources[series] = {
                'manifest': str((program_dir / 'manifests' / (child_id + '.json')).resolve()),
                'job_dir': str((program_dir / 'jobs' / child_id).resolve())}
        base.update(mode='rate_analysis', analysis_sources=sources,
                    analysis_dates=dates_for(plan), train_rows=12)
    else:
        raise ValueError('Task has no registered child Research Job')
    return base


def _program_result(state: dict, program_dir: Path) -> dict:
    from .research_planner import validate_plan
    plan = dict(state['plan'], tasks=state['tasks'])
    validate_plan(plan)
    analysis = None
    if state['records'].get('analyze_rates', {}).get('status') == 'COMPLETED_EXPLORATORY':
        artifact = program_dir / 'jobs/analyze_rates/action_result.json'
        analysis = json.loads(artifact.read_text())['result']
    result = {'goal_id': state['goal_id'], 'research_goal': state['plan']['research_goal'],
              'status': 'EXPLORATORY_ONLY' if analysis else 'RESEARCH_INCOMPLETE',
              'task_statuses': {key: value['status'] for key, value in state['records'].items()},
              'executed_tasks': [key for key, value in state['records'].items()
                                 if value['status'] in {'VERIFIED', 'COMPLETED_EXPLORATORY'}],
              'blocked_tasks': [key for key, value in state['records'].items()
                                if value['status'].startswith('BLOCKED')],
              'selection_history': state['selection_history'],
              'replanning_history': state['replanning_history'],
              'analysis': analysis, 'pit_status': 'PIT_UNVERIFIED',
              'official_market_claim': False, 'independent_holdout': 'NOT_AVAILABLE',
              'next_action': 'ACQUIRE_PIT_AND_INDEPENDENT_HOLDOUT' if analysis else
                             'RESUME_BOUNDED_TASKS'}
    write_state(program_dir / 'research_report.json', result)
    return result


def run_research_program(goal: str, program_dir: Path | None = None,
                         *, max_tasks: int = 12, max_seconds: int = 300) -> dict:
    """Sequentially run reviewed DAG tasks through existing Research Job Supervisor."""
    from .isolated_codex import PRIVATE_ROOT as JOB_ROOT
    from .research_planner import plan_goal, validate_plan, dates_for
    from .research_job import supervise as supervise_research
    if not 1 <= max_tasks <= 12 or not 10 <= max_seconds <= 300:
        raise ValueError('Program budget exceeded')
    plan = plan_goal(goal)
    program_dir = program_dir or JOB_ROOT / 'programs' / plan['goal_id']
    if program_dir.is_symlink() or not program_dir.resolve().is_relative_to(JOB_ROOT):
        raise ValueError('Program path outside private research root')
    with locked_state(program_dir) as checkpoint:
        plan_path = program_dir / 'plan.json'
        plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
        if plan_path.exists():
            saved_plan = json.loads(plan_path.read_text())
            saved_plan.pop('updated_at_utc', None)
            if plan_path.is_symlink() or hashlib.sha256(canonical(saved_plan)).hexdigest() != plan_hash:
                raise ValueError('Program plan changed')
        else:
            write_state(plan_path, dict(plan))
            # write_state adds a timestamp; compare the reviewed fields only.
        state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {
            'schema_version': 1, 'goal_id': plan['goal_id'], 'plan_sha256': plan_hash,
            'plan': plan, 'tasks': list(plan['tasks']),
            'records': {task['task_id']: {'status': 'PENDING', 'attempts': 0}
                        for task in plan['tasks']},
            'selection_history': [], 'replanning_history': [],
            'network_requests_reserved': 0, 'model_calls': 0,
            'started_at_utc': now()}
        if state['goal_id'] != plan['goal_id'] or state['plan_sha256'] != plan_hash:
            raise ValueError('Program checkpoint identity changed')
        for saved_task in state['tasks']:
            saved_record = state['records'][saved_task['task_id']]
            if saved_record.get('task_key') and saved_record['task_key'] != \
                    _program_task_key(plan['goal_id'], saved_task):
                raise ValueError('Program task changed after execution')
            if saved_record.get('checkpoint_sha256'):
                saved_checkpoint = Path(saved_record['checkpoint'])
                if saved_checkpoint.is_symlink() or not saved_checkpoint.resolve().is_relative_to(program_dir):
                    raise ValueError('Child checkpoint outside program')
                if not saved_checkpoint.is_file() or hashlib.sha256(
                        saved_checkpoint.read_bytes()).hexdigest() != \
                        saved_record['checkpoint_sha256']:
                    raise ValueError('Child Research Job checkpoint changed')
        if (program_dir / 'STOP').exists():
            state['status'] = 'CANCELLED'
            write_state(checkpoint, state)
            return _program_result(state, program_dir)
        validate_plan(dict(plan, tasks=state['tasks']))
        started = time.monotonic()
        executed = 0
        while executed < max_tasks and time.monotonic() - started < max_seconds:
            tasks = sorted(state['tasks'], key=lambda item: (item['priority'], item['task_id']))
            ready = [task for task in tasks if state['records'][task['task_id']]['status'] in
                     {'PENDING', 'READY', 'RUNNING'} and all(
                         state['records'][dep]['status'] in {'VERIFIED', 'COMPLETED_EXPLORATORY'}
                         for dep in task['dependencies'])]
            if not ready:
                break
            task = ready[0]
            task_id = task['task_id']
            record = state['records'][task_id]
            if task['task_type'] == 'DATA_ACQUISITION' and record['status'] != 'RUNNING' and \
                    state['network_requests_reserved'] >= plan['resource_budget']['max_network_requests']:
                record.update(status='BLOCKED_ENV', reason='Program network budget exhausted')
                write_state(checkpoint, state)
                continue
            state['selection_history'].append({'selected': task_id,
                'candidates': [item['task_id'] for item in ready[1:]],
                'reason': 'Highest-priority independent ready task'})
            if record['status'] != 'RUNNING':
                record.update(status='RUNNING', attempts=record['attempts'] + 1,
                              task_key=_program_task_key(plan['goal_id'], task))
                if task['task_type'] == 'DATA_ACQUISITION':
                    state['network_requests_reserved'] += 1
                write_state(checkpoint, state)
            if task['task_type'] == 'DATA_DISCOVERY':
                gaps = dates_for(plan)
                record.update(status='VERIFIED', gaps=gaps,
                              next_action='ADD_APPROVED_DATA_ACQUISITION')
                new_id = 'collect_' + task['inputs']['series'].lower()
                if new_id not in state['records']:
                    from .research_planner import _task
                    added = _task(new_id, 'DATA_ACQUISITION', task['priority'] + 10,
                                  dependencies=[task_id], inputs=task['inputs'])
                    state['tasks'].append(added)
                    state['records'][new_id] = {'status': 'PENDING', 'attempts': 0}
                    analysis_task = next(t for t in state['tasks'] if t['task_id'] == 'analyze_rates')
                    analysis_task['dependencies'].append(new_id)
                    validate_plan(dict(plan, tasks=state['tasks']))
                    state['replanning_history'].append({'cause': 'DATA_MISSING',
                        'from_task': task_id, 'new_task': new_id,
                        'new_dependency': 'analyze_rates', 'gap_count': len(gaps)})
            elif task['task_type'] == 'PIT_VALIDATION':
                from .problem_solver import collect_indicator_evidence
                request = {'goal_id': plan['goal_id'], 'task_id': task_id,
                    'indicator': '116', 'source': 'FRED_ALFRED',
                    'data_requirement': 'first_vintage_pit',
                    'as_of': '2026-11-13T09:00:00+09:00',
                    'allowed_sources': ['FRED_ALFRED'],
                    'budget': {'max_seconds': 30, 'max_network_requests': 0,
                               'max_model_calls': 0},
                    'policy': {'read_only': True, 'official_claim_allowed': False}}
                evidence = collect_indicator_evidence(request)
                evidence_path = program_dir / 'pit_evidence.json'
                write_state(evidence_path, evidence)
                record.update(status='BLOCKED_EVIDENCE' if evidence['status'] == 'PIT_BLOCKED'
                              else evidence['status'], reason=evidence['status'],
                              checkpoint=str(evidence_path),
                              checkpoint_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                              next_action='SELECT_INDEPENDENT_REAL_RESEARCH')
            else:
                child_manifest = _child_for(plan, task, program_dir)
                manifest_path = _program_manifest(program_dir / 'manifests' /
                                                  (task_id + '.json'), child_manifest)
                job_dir = program_dir / 'jobs' / task_id
                child = supervise_research(manifest_path, job_dir)
                record['checkpoint'] = str(job_dir / 'job.json')
                record['checkpoint_sha256'] = hashlib.sha256(
                    (job_dir / 'job.json').read_bytes()).hexdigest()
                reason = child.get('conclusion', {}).get('reason')
                record['reason'] = reason
                if child['status'] == 'RESEARCH_BLOCKED_WITH_EVIDENCE' and \
                        reason in {'DATA_RECOVERED_PIT_UNVERIFIED',
                                   'DATA_MISMATCH_RESOLVED_PIT_UNVERIFIED'}:
                    record['status'] = 'VERIFIED'
                elif child['status'] == 'RESEARCH_BLOCKED_WITH_EVIDENCE' and \
                        reason == 'EXPLORATORY_ONLY':
                    record['status'] = 'COMPLETED_EXPLORATORY'
                elif reason == 'BLOCKED_ENV':
                    record.update(status='BLOCKED_ENV',
                                  next_action='RESOLVE_SOURCE_ACCESS_OR_USE_VERIFIED_DATA')
                else:
                    record.update(status='BLOCKED_EVIDENCE' if child['status'] ==
                                  'RESEARCH_BLOCKED_WITH_EVIDENCE' else 'FAILED',
                                  next_action='RUN_INDEPENDENT_ALLOWED_TASK')
            executed += 1
            write_state(checkpoint, state)
            _program_result(state, program_dir)
            if (program_dir / 'STOP').exists():
                break
        for task in state['tasks']:
            record = state['records'][task['task_id']]
            if record['status'] == 'PENDING' and any(state['records'][dep]['status'].startswith(
                    'BLOCKED') for dep in task['dependencies']):
                record['status'] = 'WAITING_DEPENDENCY'
        state['status'] = 'EXPLORATORY_ONLY' if state['records']['analyze_rates']['status'] == \
            'COMPLETED_EXPLORATORY' else 'RESEARCH_INCOMPLETE'
        state['next_action'] = 'VERIFY_OR_RESUME'
        write_state(checkpoint, state)
        return _program_result(state, program_dir)


def _scoped(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise ValueError('Symlinked research state')
    path = path.resolve(strict=True)
    if path == root or not path.is_relative_to(root):
        raise ValueError('Research state outside private tree')
    return path


def supervise(ai_dir: Path, data_dir: Path, job_dir: Path,
              *, max_restarts: int = 2, max_seconds: int = 300) -> dict:
    if not 0 <= max_restarts <= 2 or not 10 <= max_seconds <= 600:
        raise ValueError('Supervisor budget exceeded')
    ai_dir = _scoped(ai_dir, AI_ROOT)
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    data_dir = _scoped(data_dir, PRIVATE_ROOT)
    job_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    job_dir = _scoped(job_dir, PRIVATE_ROOT)
    if data_dir == job_dir or data_dir.is_relative_to(job_dir) or job_dir.is_relative_to(data_dir):
        raise ValueError('Job and execution states must be separate')
    state_path = job_dir / 'job.json'
    with locked_state(job_dir):
        state = json.loads(state_path.read_text()) if state_path.exists() else {
            'job_id': job_dir.name, 'ai_dir': str(ai_dir), 'data_dir': str(data_dir),
            'status': 'PENDING', 'launch_count': 0, 'restarts': 0, 'events': []}
        if state['ai_dir'] != str(ai_dir) or state['data_dir'] != str(data_dir):
            raise ValueError('Job identity changed')
        if state['status'] == 'COMPLETED':
            return state
        if state['status'] not in {'PENDING', 'RUNNING'}:
            return state
        state['supervisor_pid'] = os.getpid()
        deadline = time.monotonic() + max_seconds
        stopping = False
        def stop(_signum, _frame):
            nonlocal stopping
            stopping = True
        prior = signal.signal(signal.SIGTERM, stop)
        try:
            while not stopping and time.monotonic() < deadline:
                checkpoint = data_dir / 'guided_state.json'
                if checkpoint.exists():
                    saved = json.loads(checkpoint.read_text())
                    state['checkpoint_status'] = saved.get('status')
                    state['checkpoint_id'] = saved.get('updated_at_utc')
                if (job_dir / 'STOP').exists():
                    stopping = True
                    break
                if state['launch_count'] > max_restarts:
                    state['status'] = 'FAILED_RETRY_LIMIT'
                    break
                cmd = [sys.executable, '-m', 'universal_agent.guided_experiment',
                       '--ai-state-dir', str(ai_dir), '--state-dir', str(data_dir)]
                env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
                worker = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parents[3],
                                          env=env, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, start_new_session=True)
                state['status'] = 'RUNNING'
                state['worker_pid'] = worker.pid
                state['launch_count'] += 1
                state['events'].append({'at_utc': now(), 'event': 'WORKER_STARTED',
                                        'worker_pid': worker.pid,
                                        'checkpoint_id': state.get('checkpoint_id')})
                write_state(state_path, state)
                while worker.poll() is None and not stopping and time.monotonic() < deadline:
                    if (job_dir / 'STOP').exists():
                        stopping = True
                        break
                    time.sleep(.2)
                if worker.poll() is None:
                    os.killpg(worker.pid, signal.SIGTERM)
                    try:
                        worker.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(worker.pid, signal.SIGKILL)
                stdout, stderr = worker.communicate(timeout=3)
                state['events'].append({'at_utc': now(), 'event': 'WORKER_EXITED',
                                        'worker_pid': worker.pid, 'exit_code': worker.returncode,
                                        'stderr_tail': redact(stderr[-500:])})
                checkpoint = data_dir / 'guided_state.json'
                saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
                state['checkpoint_status'] = saved.get('status')
                state['checkpoint_id'] = saved.get('updated_at_utc')
                if worker.returncode == 0:
                    try:
                        result = json.loads(stdout.strip().splitlines()[-1])
                    except (IndexError, ValueError):
                        result = {}
                    if (result.get('status') == 'EXPLORATORY_BACKTEST_VERIFIED'
                            and saved.get('status') == result['status']):
                        state['status'] = 'COMPLETED'
                        state['result_status'] = result['status']
                        state['resumed_without_duplicate'] = result.get('resumed_without_duplicate', False)
                        state['completed_job_executions'] = 1
                        state['duplicate_completed_job_executions'] = 0
                    else:
                        state['status'] = 'BLOCKED_RESEARCH'
                    write_state(state_path, state)
                    break
                state['restarts'] += 1
                state['events'].append({'at_utc': now(), 'event': 'CRASH_DETECTED',
                                        'recovery_checkpoint': state.get('checkpoint_id')})
                write_state(state_path, state)
            if stopping:
                state['status'] = 'STOPPED'
            elif state['status'] == 'RUNNING' and time.monotonic() >= deadline:
                state['status'] = 'FAILED_TIME_BUDGET'
            write_state(state_path, state)
            return state
        finally:
            signal.signal(signal.SIGTERM, prior)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--research-goal', type=str)
    parser.add_argument('--program-dir', type=Path)
    parser.add_argument('--research-manifest', type=Path)
    parser.add_argument('--ai-state-dir', type=Path)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--job-dir', type=Path)
    parser.add_argument('--max-restarts', type=int, default=2)
    parser.add_argument('--max-seconds', type=int, default=300)
    args = parser.parse_args()
    if args.research_goal:
        if args.research_manifest or args.ai_state_dir or args.state_dir or args.job_dir:
            parser.error('Research goal mode cannot share a single-job state')
        result = run_research_program(args.research_goal, args.program_dir,
                                      max_seconds=args.max_seconds)
        print(json.dumps({'goal_id': result['goal_id'], 'status': result['status'],
                          'task_statuses': result['task_statuses'],
                          'official_market_claim': False}))
        return 0 if result['status'] == 'EXPLORATORY_ONLY' else 1
    if args.research_manifest:
        if args.ai_state_dir or args.state_dir or not args.job_dir:
            parser.error('Research manifest mode requires only --job-dir')
        from .research_job import supervise as supervise_research
        result = supervise_research(args.research_manifest, args.job_dir)
        print(json.dumps({'job_id': result['job_id'], 'status': result['status'],
                          'attempts': result['attempts'],
                          'worker_restarts': result['worker_restarts']}))
        return 0 if result['status'] in {'VERIFIED_RESEARCH_CONCLUSION',
                                         'RESEARCH_BLOCKED_WITH_EVIDENCE'} else 1
    if not args.ai_state_dir or not args.state_dir or not args.job_dir:
        parser.error('Guided mode requires --ai-state-dir, --state-dir and --job-dir')
    result = supervise(args.ai_state_dir, args.state_dir, args.job_dir,
                       max_restarts=args.max_restarts, max_seconds=args.max_seconds)
    print(json.dumps({'job_id': result['job_id'], 'status': result['status'],
                      'launch_count': result['launch_count'], 'restarts': result['restarts']}))
    return 0 if result['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
