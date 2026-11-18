"""Bounded, session-independent Goal queue around the existing Research Supervisor.

This stores registration and handoff state. The Task DAG and action checkpoint
remain owned by process_supervisor and Research Job; there is no second executor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .engine import canonical, locked_state, now, write_state
from .isolated_codex import PRIVATE_ROOT
from .research_planner import UnsupportedGoal, plan_goal
from .ai_research_planner import validate_candidate

FINAL = {'VERIFIED', 'COMPLETED_EXPLORATORY', 'BLOCKED_EVIDENCE', 'BLOCKED_ENV',
         'APPROVAL_REQUIRED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'}
ACTIVE = {'PENDING', 'READY', 'RUNNING', 'RETRY_WAIT'}


def _root(directory: Path) -> Path:
    if directory.is_symlink() or not directory.resolve().is_relative_to(PRIVATE_ROOT):
        raise ValueError('Runtime queue outside private research root')
    return directory.resolve()


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked runtime artifact')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _task(task: dict) -> dict:
    return {'task_id': task['task_id'], 'task_type': task['task_type'],
        'dependencies': task['dependencies'], 'priority': task['priority'],
        'status': 'PENDING', 'input_sha256': hashlib.sha256(canonical(task['inputs'])).hexdigest(),
        'output_sha256': None, 'worker_identity': None, 'attempt_count': 0,
        'retry_policy': task['retry_policy'], 'resource_budget': task['resource_budget'],
        'checkpoint': None, 'last_error': None, 'next_action': None,
        'approval_status': 'APPROVED'}


def _load(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError('Symlinked runtime queue')
    queue = json.loads(path.read_text()) if path.exists() else {
        'schema_version': 1, 'jobs': {}, 'events': [], 'generation': 0,
        'network_requests_reserved': 0, 'model_calls': 0}
    if queue.get('schema_version') != 1 or not isinstance(queue.get('jobs'), dict):
        raise ValueError('Invalid runtime queue')
    for goal_id, job in queue['jobs'].items():
        if isinstance(job.get('ai_candidate'), dict):
            # Earlier supervisor writes shared the candidate dict with the
            # mutable DAG. Restore only from the separately sealed proposal.
            original = dict(job['ai_candidate'])
            original.pop('updated_at_utc', None)
            if hashlib.sha256(canonical(original)).hexdigest() != job.get('ai_candidate_sha256'):
                sealed = path.parent / 'programs' / goal_id / 'ai_program_candidate.json'
                if sealed.is_symlink() or not sealed.is_file():
                    raise ValueError('Research AI candidate changed')
                original = json.loads(sealed.read_text())
                original.pop('updated_at_utc', None)
                if hashlib.sha256(canonical(original)).hexdigest() != job.get('ai_candidate_sha256'):
                    raise ValueError('Research AI candidate changed')
            job['ai_candidate'] = original
        if goal_id != job['goal_id'] or job['status'] not in FINAL | ACTIVE:
            raise ValueError('Runtime job identity or state changed')
        if job['approval_status'] != 'APPROVED' and job['status'] in ACTIVE:
            raise ValueError('Unapproved runtime job is executable')
        for task_id, task in job['tasks'].items():
            if task_id != task['task_id'] or task['status'] not in FINAL | ACTIVE | {
                    'WAITING_DEPENDENCY'}:
                raise ValueError('Runtime task identity or state changed')
            if task.get('output_sha256') and _sha(Path(task['checkpoint'])) != task['output_sha256']:
                raise ValueError('Research task output changed after verification')
        if job.get('checkpoint_sha256') and _sha(Path(job['checkpoint'])) != job['checkpoint_sha256']:
            raise ValueError('Research checkpoint changed after queue completion')
        if job.get('output_sha256') and _sha(Path(job['output'])) != job['output_sha256']:
            raise ValueError('Research report changed after queue completion')
    return queue


def _save(path: Path, queue: dict) -> None:
    queue['generation'] += 1
    write_state(path, queue)


def submit(goal: str, directory: Path, *, approval_required: bool = False,
           priority: int = 50, ai_candidate: dict | None = None) -> dict:
    if not 0 <= priority <= 100:
        raise ValueError('Invalid runtime priority')
    directory = _root(directory)
    with locked_state(directory) as path:
        queue = _load(path)
        try:
            plan = plan_goal(goal) if ai_candidate is None else validate_candidate(goal, ai_candidate)
        except UnsupportedGoal as exc:
            goal_id = 'research_' + hashlib.sha256(goal.encode()).hexdigest()[:12]
            plan = None
            reason = str(exc)
        else:
            goal_id = plan['goal_id']
            reason = None
        if ai_candidate is not None:
            reviewed = validate_candidate(goal, ai_candidate)
            if plan is None or canonical(reviewed) != canonical(plan):
                raise ValueError('AI candidate has no reviewed executable plan')
        if goal_id in queue['jobs']:
            if queue['jobs'][goal_id]['research_goal'] != goal:
                raise ValueError('Goal ID collision')
            if (queue['jobs'][goal_id].get('ai_candidate') is None) != (ai_candidate is None) or (
                    ai_candidate is not None and canonical(queue['jobs'][goal_id]['ai_candidate']) !=
                    canonical(ai_candidate)):
                raise ValueError('Registered AI candidate changed')
            return queue['jobs'][goal_id]
        unsupported_dir = directory / 'programs' / goal_id
        if plan is None:
            from .process_supervisor import run_research_program
            run_research_program(goal, program_dir=unsupported_dir)
        status = 'UNSUPPORTED' if plan is None else 'APPROVAL_REQUIRED' if approval_required else 'PENDING'
        job = {'job_id': goal_id, 'goal_id': goal_id, 'research_goal': goal,
            'status': status, 'priority': priority, 'created_at_utc': now(),
            'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest() if plan else None,
            'goal_contract_sha256': hashlib.sha256(canonical(plan['goal_contract'])).hexdigest()
                if plan else None,
            'tasks': {task['task_id']: _task(task) for task in plan['tasks']} if plan else {},
            'attempt_count': 0, 'retry_policy': {'max_launches': 2},
            'resource_budget': plan['resource_budget'] if plan else {
                'max_seconds': 0, 'max_network_requests': 0, 'max_model_calls': 0},
            'worker_identity': None,
            'checkpoint': str(unsupported_dir / 'state.json') if plan is None else None,
            'checkpoint_sha256': _sha(unsupported_dir / 'state.json') if plan is None else None,
            'output': str(unsupported_dir / 'research_report.json') if plan is None else None,
            'output_sha256': _sha(unsupported_dir / 'research_report.json') if plan is None else None,
            'last_error': reason,
            'next_action': 'ADD_REVIEWED_SOURCE_AND_ACTION' if plan is None else
                'REQUEST_APPROVAL' if approval_required else 'RUN_APPROVED_GOAL',
            'approval_status': 'REQUIRED' if approval_required else 'APPROVED',
            'ai_candidate': ai_candidate,
            'ai_candidate_sha256': hashlib.sha256(canonical(ai_candidate)).hexdigest()
                if ai_candidate is not None else None,
            'model_calls': 0, 'network_requests_reserved': 0}
        queue['jobs'][goal_id] = job
        queue['events'].append({'at_utc': now(), 'goal_id': goal_id, 'event': status})
        _save(path, queue)
        return job


def _sync_tasks(job: dict, program: dict) -> None:
    for task in program['tasks']:
        task_id = task['task_id']
        if task_id not in job['tasks']:
            job['tasks'][task_id] = _task(task)
        row = job['tasks'][task_id]
        record = program['records'][task_id]
        current_input_sha = hashlib.sha256(canonical(task['inputs'])).hexdigest()
        if row['input_sha256'] != current_input_sha:
            revision = (program.get('calendar_revision') or program.get('schema_revision') or
                        program.get('api_recovery_revision') or {})
            revision_path = Path(revision['path']) if revision.get('path') else None
            program_dir = Path(job['checkpoint']).parent if job.get('checkpoint') else None
            revision_kind = ('calendar' if program.get('calendar_revision') else
                             'schema' if program.get('schema_revision') else 'api_recovery')
            revision_key = revision_kind + '_revision_sha256'
            if (task_id != 'analyze_rates' or row['attempt_count'] != 0 or
                    row['status'] not in {'PENDING', 'WAITING_DEPENDENCY'} or
                    task['inputs'].get(revision_key) != revision.get('sha256') or
                    revision_path is None or program_dir is None or
                    revision_path.parent != program_dir or
                    revision_path.name != revision_kind + '_revision_v1.json' or
                    _sha(revision_path) != revision['sha256']):
                raise ValueError('Runtime task input changed')
            row['original_input_sha256'] = row['input_sha256']
            row[revision_key] = revision['sha256']
            row['input_sha256'] = current_input_sha
        row['dependencies'] = task['dependencies']
        row.update(status=record['status'], attempt_count=record['attempts'],
            output_sha256=record.get('checkpoint_sha256'),
            checkpoint=record.get('checkpoint'), last_error=record.get('reason'),
            next_action=record.get('next_action'),
            worker_identity={'pid': program.get('supervisor_pid')}
                if record['status'] == 'RUNNING' else None)


def run(directory: Path, *, max_jobs: int = 3, max_seconds: int = 300,
        startup_delay: int = 0) -> dict:
    if not 1 <= max_jobs <= 3 or not 10 <= max_seconds <= 300 or not 0 <= startup_delay <= 3:
        raise ValueError('Runtime budget exceeded')
    directory = _root(directory)
    if startup_delay:
        time.sleep(startup_delay)
    with locked_state(directory) as path:
        queue = _load(path)
        from .problem_solver import solve_calendar_gap, solve_schema_gap, solve_api_failure
        for candidate in queue['jobs'].values():
            if (candidate['status'] not in {'BLOCKED_EVIDENCE', 'BLOCKED_ENV'} or
                    candidate['approval_status'] != 'APPROVED' or
                    candidate['attempt_count'] >= candidate['retry_policy']['max_launches']):
                continue
            program_dir = directory / 'programs' / candidate['goal_id']
            try:
                saved = json.loads((program_dir / 'state.json').read_text())
                proposed = candidate.get('ai_candidate')
                plan = (plan_goal(candidate['research_goal']) if proposed is None else
                        validate_candidate(candidate['research_goal'], proposed))
                evidence = (solve_calendar_gap(plan, saved, program_dir) or
                            solve_schema_gap(plan, saved, program_dir))
                if evidence is None and (program_dir / 'api_recovery_approval.json').is_file():
                    evidence = solve_api_failure(plan, saved, program_dir)
            except (OSError, ValueError, KeyError) as exc:
                candidate['last_error'] = 'RECOVERY_DIAGNOSIS_' + type(exc).__name__
                candidate['next_action'] = 'REVIEW_RECOVERY_EVIDENCE'
                queue['events'].append({'at_utc': now(), 'goal_id': candidate['goal_id'],
                                        'event': 'RECOVERY_DIAGNOSIS_BLOCKED'})
                _save(path, queue)
                continue
            if evidence is not None:
                candidate['status'] = 'READY'
                candidate['next_action'] = evidence['solution_action']
                recovery_event = ('SCHEMA_RECOVERY_READY' if evidence['problem_type'] ==
                                  'SCHEMA_MISMATCH' else 'API_RECOVERY_READY' if
                                  evidence['problem_type'] == 'API_ERROR' else
                                  'CALENDAR_RECOVERY_READY')
                queue['events'].append({'at_utc': now(), 'goal_id': candidate['goal_id'],
                                        'event': recovery_event,
                                        'evidence_sha256': hashlib.sha256(canonical(evidence)).hexdigest()})
                _save(path, queue)
        started = time.monotonic()
        processed = 0
        processed_ids: set[str] = set()
        while processed < max_jobs and time.monotonic() - started < max_seconds:
            if (directory / 'STOP').exists():
                break
            candidates = sorted((job for job in queue['jobs'].values()
                if job['status'] in {'PENDING', 'READY', 'RUNNING', 'RETRY_WAIT'} and
                   job['goal_id'] not in processed_ids and
                   job['approval_status'] == 'APPROVED'),
                key=lambda job: (job['priority'], job['created_at_utc'], job['job_id']))
            if not candidates:
                break
            job = candidates[0]
            if max_seconds - (time.monotonic() - started) < 10:
                break
            if job['attempt_count'] >= job['retry_policy']['max_launches']:
                job.update(status='FAILED', last_error='Runtime launch budget exhausted',
                           next_action='REVIEW_FAILED_GOAL')
                _save(path, queue)
                continue
            job['attempt_count'] += 1
            job['status'] = 'RUNNING'
            job['worker_identity'] = {'pid': os.getpid(), 'started_at_utc': now()}
            queue['events'].append({'at_utc': now(), 'goal_id': job['goal_id'],
                                    'event': 'RUNNING', 'pid': os.getpid()})
            _save(path, queue)
            from .process_supervisor import run_research_program
            try:
                current_plan = (plan_goal(job['research_goal']) if job.get('ai_candidate') is None
                                else validate_candidate(job['research_goal'], job['ai_candidate']))
                if hashlib.sha256(canonical(current_plan)).hexdigest() != job['plan_sha256']:
                    raise ValueError('Reviewed research plan changed after queue submission')
                if job.get('ai_candidate') is not None:
                    if (hashlib.sha256(canonical(job['ai_candidate'])).hexdigest() !=
                            job.get('ai_candidate_sha256') or
                            canonical(validate_candidate(job['research_goal'], job['ai_candidate'])) !=
                            canonical(current_plan)):
                        raise ValueError('AI candidate changed after queue submission')
                program_dir = directory / 'programs' / job['goal_id']
                result = run_research_program(job['research_goal'], program_dir=program_dir,
                    max_seconds=min(job['resource_budget']['max_seconds'],
                                    max(10, int(max_seconds - (time.monotonic() - started)))),
                    ai_candidate=job.get('ai_candidate'))
                program = json.loads((program_dir / 'state.json').read_text())
                _sync_tasks(job, program)
                job['network_requests_reserved'] = program['network_requests_reserved']
                job['recovery_network_requests_reserved'] = program.get(
                    'recovery_network_requests_reserved', 0)
                queue['network_requests_reserved'] = sum(j['network_requests_reserved']
                    for j in queue['jobs'].values())
                status = result['status']
                job['status'] = ('COMPLETED_EXPLORATORY' if status ==
                    'RESEARCH_COMPLETED_EXPLORATORY' else 'VERIFIED' if status ==
                    'RESEARCH_COMPLETED' else 'CANCELLED' if status ==
                    'RESEARCH_CANCELLED' else 'BLOCKED_ENV' if any(
                        task['status'] == 'BLOCKED_ENV' for task in job['tasks'].values()) else
                    'BLOCKED_EVIDENCE' if status == 'RESEARCH_BLOCKED' else
                    'RETRY_WAIT' if status == 'RESEARCH_INCOMPLETE' else 'FAILED')
                job['checkpoint'] = str(program_dir / 'state.json')
                job['checkpoint_sha256'] = _sha(Path(job['checkpoint']))
                job['output'] = str(program_dir / 'research_report.json')
                job['output_sha256'] = _sha(Path(job['output']))
                job['next_action'] = result.get('next_action')
                job['last_error'] = None if job['status'] in {'VERIFIED',
                    'COMPLETED_EXPLORATORY'} else status
            except Exception as exc:
                job['status'] = 'BLOCKED_ENV' if isinstance(exc, OSError) else 'FAILED'
                job['last_error'] = type(exc).__name__
                job['next_action'] = 'INSPECT_RESEARCH_CHECKPOINT_BEFORE_RETRY'
            job['worker_identity'] = None
            queue['events'].append({'at_utc': now(), 'goal_id': job['goal_id'],
                                    'event': job['status']})
            _save(path, queue)
            processed += 1
            processed_ids.add(job['goal_id'])
        return {'processed': processed, 'statuses': {key: value['status']
                for key, value in queue['jobs'].items()},
                'network_requests_reserved': queue['network_requests_reserved'],
                'model_calls': queue['model_calls']}


def reconcile_calendar(directory: Path) -> dict:
    """Verify a completed calendar DAG after a failed queue projection; run no task."""
    directory = _root(directory)
    with locked_state(directory) as path:
        if path.is_symlink():
            raise ValueError('Symlinked runtime queue')
        queue = json.loads(path.read_text())
        if queue.get('schema_version') != 1 or len(queue.get('jobs', {})) != 1:
            raise ValueError('Calendar reconciliation needs one sealed Goal')
        job = next(iter(queue['jobs'].values()))
        program_dir = directory / 'programs' / job['goal_id']
        if (job['status'] != 'FAILED' or job['last_error'] != 'ValueError' or
                job['next_action'] != 'INSPECT_RESEARCH_CHECKPOINT_BEFORE_RETRY' or
                job['checkpoint'] != str(program_dir / 'state.json') or
                job['output'] != str(program_dir / 'research_report.json')):
            raise ValueError('Queue failure is not eligible for calendar reconciliation')
        program = json.loads((program_dir / 'state.json').read_text())
        revision = program.get('calendar_revision') or {}
        revision_path = Path(revision['path']) if revision.get('path') else None
        if (program['status'] != 'RESEARCH_COMPLETED_EXPLORATORY' or
                program['goal_id'] != job['goal_id'] or
                program['plan_sha256'] != job['plan_sha256'] or
                program['goal_contract_sha256'] != job['goal_contract_sha256'] or
                revision_path != program_dir / 'calendar_revision_v1.json' or
                _sha(revision_path) != revision.get('sha256') or
                any(record['status'] in ACTIVE for record in program['records'].values())):
            raise ValueError('Calendar program is not sealed and terminal')
        from .process_supervisor import run_research_program
        verified = run_research_program(job['research_goal'], program_dir=program_dir,
                                        max_seconds=10)
        if verified['status'] != 'RESEARCH_COMPLETED_EXPLORATORY':
            raise ValueError('Calendar result failed independent program verification')
        program = json.loads((program_dir / 'state.json').read_text())
        _sync_tasks(job, program)
        job.update(status='COMPLETED_EXPLORATORY', last_error=None,
                   next_action=verified['next_action'],
                   checkpoint_sha256=_sha(program_dir / 'state.json'),
                   output_sha256=_sha(program_dir / 'research_report.json'),
                   network_requests_reserved=program['network_requests_reserved'])
        queue['network_requests_reserved'] = sum(item['network_requests_reserved']
            for item in queue['jobs'].values())
        queue['events'].append({'at_utc': now(), 'goal_id': job['goal_id'],
                                'event': 'CALENDAR_RESULT_RECONCILED',
                                'reexecuted_tasks': 0})
        _save(path, queue)
        return {'goal_id': job['goal_id'], 'status': job['status'],
                'reexecuted_tasks': 0,
                'network_requests_reserved': job['network_requests_reserved']}


def launch(directory: Path, *, max_jobs: int = 3, max_seconds: int = 300,
           startup_delay: int = 0) -> int:
    directory = _root(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    log = directory / 'runtime.log'
    if log.is_symlink():
        raise ValueError('Symlinked runtime log')
    fd = os.open(log, os.O_CREAT | os.O_APPEND | os.O_WRONLY |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        command = [sys.executable, '-m', 'universal_agent.research_runtime', 'run',
                   '--queue-dir', str(directory), '--max-jobs', str(max_jobs),
                   '--max-seconds', str(max_seconds), '--startup-delay', str(startup_delay)]
        child = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[3],
            env={'PATH': '/usr/bin:/bin',
                 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
            stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, start_new_session=True,
            close_fds=True)
        return child.pid
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('submit', 'run', 'launch', 'status', 'stop',
                                           'reconcile-calendar'))
    parser.add_argument('--queue-dir', type=Path, required=True)
    parser.add_argument('--goal')
    parser.add_argument('--approval-required', action='store_true')
    parser.add_argument('--priority', type=int, default=50)
    parser.add_argument('--max-jobs', type=int, default=3)
    parser.add_argument('--max-seconds', type=int, default=300)
    parser.add_argument('--startup-delay', type=int, default=0)
    args = parser.parse_args()
    if args.action == 'submit':
        if not args.goal:
            parser.error('submit requires --goal')
        item = submit(args.goal, args.queue_dir,
                      approval_required=args.approval_required, priority=args.priority)
        print(json.dumps({'goal_id': item['goal_id'], 'status': item['status']}))
    elif args.action == 'run':
        print(json.dumps(run(args.queue_dir, max_jobs=args.max_jobs,
            max_seconds=args.max_seconds, startup_delay=args.startup_delay)))
    elif args.action == 'launch':
        print(json.dumps({'runtime_pid': launch(args.queue_dir,
            max_jobs=args.max_jobs, max_seconds=args.max_seconds,
            startup_delay=args.startup_delay)}))
    elif args.action == 'status':
        directory = _root(args.queue_dir)
        # write_state replaces the complete JSON atomically. A read-only status
        # query must remain available while the worker owns the execution lock.
        path = directory / 'state.json'
        if path.is_symlink():
            raise ValueError('Symlinked runtime queue')
        queue = json.loads(path.read_text()) if path.exists() else _load(path)
        if queue.get('schema_version') != 1 or not isinstance(queue.get('jobs'), dict):
            raise ValueError('Invalid runtime status snapshot')
        print(json.dumps({'generation': queue['generation'],
            'statuses': {key: value['status'] for key, value in queue['jobs'].items()},
            'events': queue['events'][-10:]}))
    elif args.action == 'reconcile-calendar':
        print(json.dumps(reconcile_calendar(args.queue_dir)))
    else:
        directory = _root(args.queue_dir)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        (directory / 'STOP').touch(mode=0o600, exist_ok=True)
        print(json.dumps({'status': 'STOP_REQUESTED'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
