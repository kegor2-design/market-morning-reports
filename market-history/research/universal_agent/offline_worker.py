"""Bounded, persistent server research worker with no Codex execution path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .engine import locked_state, now, write_state

ALLOWED_ADAPTERS = {'regime190': 'regime190.offline_tasks'}
STATES = {'PENDING', 'RUNNING', 'VERIFYING', 'COMPLETED', 'BLOCKED_EVIDENCE',
          'BLOCKED_LICENSE', 'BLOCKED_QUOTA', 'CODEX_REQUIRED', 'RETRYABLE', 'FAILED'}
RETRY_LIMIT = 2


class QuotaBlocked(Exception):
    """An approved offline data provider denied requests because of quota."""


def _adapter(name: str):
    if name not in ALLOWED_ADAPTERS:
        raise ValueError('Offline adapter is not allowlisted')
    from importlib import import_module
    return import_module(ALLOWED_ADAPTERS[name])


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp needs timezone')
    return parsed.astimezone(timezone.utc)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _memory_available() -> int:
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('Memory availability unknown')


def load_plan(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    plan = json.loads(raw)
    if (plan.get('schema_version') != 1 or plan.get('adapter') not in ALLOWED_ADAPTERS
            or plan.get('research_project') != 'regime190'):
        raise ValueError('Unsupported offline plan')
    _adapter(plan['adapter'])
    ids = [task['task_id'] for task in plan['tasks']]
    if len(ids) != len(set(ids)) or any(not isinstance(key, str) or
                                         not re.fullmatch(r'[a-z][a-z0-9_]*', key) for key in ids):
        raise ValueError('Duplicate or unsafe task ID')
    for task in plan['tasks']:
        if task['execution_class'] not in {'SERVER_EXECUTABLE', 'CODEX_REQUIRED'}:
            raise ValueError('Invalid execution class')
        if task['execution_class'] == 'SERVER_EXECUTABLE' and task['task_type'] not in {
                'source_snapshot', 'pit_recheck', 'backtest_gate'}:
            raise ValueError('Unregistered server task')
        if any(dep not in ids or dep == task['task_id'] for dep in task['dependencies']):
            raise ValueError('Invalid dependency')
        if not 0 <= task['delay_hours'] <= 72 or not 0 <= task['priority'] <= 100:
            raise ValueError('Invalid schedule or priority')
        budget = task['resource_budget']
        if not 1 <= budget['max_seconds'] <= 60 or not 1 <= budget['max_attempts'] <= RETRY_LIMIT:
            raise ValueError('Invalid task resource budget')
    graph = {task['task_id']: task['dependencies'] for task in plan['tasks']}
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError('Offline task dependency cycle')
        if key in visited:
            return
        visiting.add(key)
        for dependency in graph[key]:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)
    for key in graph:
        visit(key)
    return plan, hashlib.sha256(raw).hexdigest()


def _project(queue: dict, state_dir: Path) -> dict:
    tasks = queue['tasks']
    completed = [key for key, value in tasks.items() if value['status'] == 'COMPLETED']
    blocked = [key for key, value in tasks.items() if value['status'].startswith('BLOCKED')]
    failed = [key for key, value in tasks.items() if value['status'] == 'FAILED']
    codex = [key for key, value in tasks.items() if value['status'] == 'CODEX_REQUIRED']
    pit = next((json.loads(Path(tasks[key]['output_artifacts'][0]).read_text())['result']
                for key in reversed(completed) if tasks[key]['task_type'] == 'pit_recheck'), None)
    gate = next((json.loads(Path(tasks[key]['output_artifacts'][0]).read_text())['result']
                 for key in reversed(completed) if tasks[key]['task_type'] == 'backtest_gate'), None)
    return {'checkpoint_id': queue['checkpoint_id'], 'completed_tasks': completed,
            'blocked_tasks': blocked, 'failed_tasks': failed, 'codex_required_tasks': codex,
            'pit_validation_results': pit, 'backtest_results': gate,
            'newly_collected_data': [],
            'research_status': 'BACKTEST_BLOCKED' if not gate or gate['status'] == 'BACKTEST_BLOCKED'
                               else 'REVIEW_REQUIRED'}


def publish(queue: dict, state_dir: Path, repo: Path) -> None:
    """Regenerate views from the canonical queue; no second mutable task store."""
    queue_path = state_dir / 'task_queue.json'
    checkpoint = {'schema_version': 1, 'checkpoint_id': queue['checkpoint_id'],
                  'generation': queue.get('generation', 0),
                  'queue_sha256': _sha(queue_path), 'queue_path': str(queue_path)}
    write_state(state_dir / 'checkpoint.json', checkpoint)
    projection = _project(queue, state_dir)
    write_state(state_dir / 'research_status.json', projection.copy())
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True,
                            text=True, timeout=3, check=True).stdout.strip()
    branch = subprocess.run(['git', 'branch', '--show-current'], cwd=repo, capture_output=True,
                            text=True, timeout=3, check=True).stdout.strip()
    tracked = subprocess.run(['git', 'rev-parse', '--verify', '@{u}'], cwd=repo,
                             capture_output=True, text=True, timeout=3)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True,
                           text=True, timeout=3, check=True).stdout.strip()
    handoff = {'schema_version': 1, 'last_verified_checkpoint': checkpoint,
               'current_research_status': projection['research_status'],
               'completed_tasks': projection['completed_tasks'],
               'failed_tasks': projection['failed_tasks'],
               'blocked_tasks': projection['blocked_tasks'],
               'newly_collected_data': projection['newly_collected_data'],
               'pit_validation_results': projection['pit_validation_results'],
               'backtest_results': projection['backtest_results'],
               'unresolved_problems': ['Original cutoff request/response absent',
                                       'Historical market membership and PIT release times unverified'],
               'codex_required_tasks': projection['codex_required_tasks'],
               'recommended_next_actions': ['Inspect newly completed offline evidence',
                                            'Resolve cutoff provenance and historical universe'],
               'git_commit_reference': commit, 'git_branch': branch,
               'remote_tracking_head': tracked.stdout.strip() if tracked.returncode == 0 else None,
               'working_tree_clean': not bool(dirty),
               'remote_live_head_verified': False}
    write_state(state_dir / 'codex_handoff.json', handoff)
    summary = (f"# Offline research status\n\nCheckpoint {queue['checkpoint_id']}\n\n"
               f"Completed: {len(projection['completed_tasks'])}; blocked: {len(projection['blocked_tasks'])}; "
               f"Codex required: {len(projection['codex_required_tasks'])}.\n\n"
               f"Research status: {projection['research_status']}.\n")
    temporary = state_dir / '.research_summary.tmp'
    temporary.write_text(summary, encoding='utf-8')
    temporary.chmod(0o600)
    os.replace(temporary, state_dir / 'research_summary.md')


def prepare(plan_path: Path, state_dir: Path, repo: Path, horizon_hours: int = 48) -> dict:
    if not 24 <= horizon_hours <= 72:
        raise ValueError('Horizon must be 24 to 72 hours')
    plan, digest = load_plan(plan_path)
    with locked_state(state_dir):
        path = state_dir / 'task_queue.json'
        if path.exists():
            queue = _load_queue(state_dir)
            if queue.get('plan_sha256') != digest:
                raise ValueError('Queue plan changed; preserve and review existing checkpoint')
            publish(queue, state_dir, repo)
            return queue
        created = _utc(now())
        tasks = {}
        for spec in plan['tasks']:
            if spec['delay_hours'] > horizon_hours:
                continue
            key = spec['task_id']
            tasks[key] = dict(spec, research_project=plan['research_project'],
                              status='CODEX_REQUIRED' if spec['execution_class'] == 'CODEX_REQUIRED' else 'PENDING',
                              attempt_count=0, created_at=created.isoformat(), updated_at=created.isoformat(),
                              last_started_at=None, last_completed_at=None, checkpoint_id=None,
                              input_artifacts=spec.get('input_artifacts', []), output_artifacts=[],
                              evidence_refs=[], error_reason=None, retry_after=None,
                              not_before=(created + timedelta(hours=spec['delay_hours'])).isoformat())
        queue = {'schema_version': 1, 'research_project': plan['research_project'],
                 'adapter': plan['adapter'], 'plan_sha256': digest, 'checkpoint_id': 0,
                 'generation': 0,
                 'created_at': created.isoformat(), 'tasks': tasks, 'events': []}
        write_state(path, queue)
        publish(queue, state_dir, repo)
        return queue


def _load_queue(state_dir: Path) -> dict:
    path = state_dir / 'task_queue.json'
    queue = json.loads(path.read_text())
    checkpoint_path = state_dir / 'checkpoint.json'
    if queue.get('schema_version') != 1 or not isinstance(queue.get('tasks'), dict):
        raise ValueError('Invalid offline queue')
    if any(record.get('status') not in STATES for record in queue['tasks'].values()):
        raise ValueError('Invalid offline task status')
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text())
        if (checkpoint['checkpoint_id'] > queue['checkpoint_id']
                or checkpoint.get('generation', 0) > queue.get('generation', 0)
                or (checkpoint.get('generation', 0) == queue.get('generation', 0)
                    and checkpoint['queue_sha256'] != _sha(path))):
            raise ValueError('Checkpoint integrity mismatch')
    return queue


def _eligible(queue: dict) -> dict | None:
    current = _utc(now())
    for task in sorted(queue['tasks'].values(), key=lambda row: (row['priority'], row['not_before'], row['task_id'])):
        if task['execution_class'] != 'SERVER_EXECUTABLE' or task['status'] not in {'PENDING', 'RETRYABLE'}:
            continue
        if _utc(task['not_before']) > current or (task['retry_after'] and _utc(task['retry_after']) > current):
            continue
        if all(queue['tasks'][dep]['status'] == 'COMPLETED' for dep in task['dependencies']):
            return task
    return None


def _save(queue: dict, state_dir: Path, repo: Path) -> None:
    queue['generation'] = queue.get('generation', 0) + 1
    write_state(state_dir / 'task_queue.json', queue)
    publish(queue, state_dir, repo)


def _verify_output(adapter, task: dict) -> dict:
    path = Path(task['output_artifacts'][0])
    payload = json.loads(path.read_text())
    if payload['task_id'] != task['task_id'] or payload['plan_task_type'] != task['task_type']:
        raise ValueError('Output identity mismatch')
    adapter.verify(task, payload['result'])
    return payload


def run(state_dir: Path, repo: Path, max_tasks: int = 3, max_seconds: int = 120) -> dict:
    if not 1 <= max_tasks <= 5 or not 1 <= max_seconds <= 1800:
        raise ValueError('Offline run exceeds hard limits')
    with locked_state(state_dir):
        queue = _load_queue(state_dir)
        adapter = _adapter(queue['adapter'])
        if (state_dir / 'STOP').exists():
            return {'processed': 0, 'checkpoint_id': queue['checkpoint_id'],
                    'next_task': None, 'stop_reason': 'STOP'}
        # Recovery only validates an existing output; uncertain work is not duplicated.
        for task in queue['tasks'].values():
            if task['status'] in {'RUNNING', 'VERIFYING'}:
                try:
                    _verify_output(adapter, task)
                    task['status'] = 'COMPLETED'
                    task['last_completed_at'] = now()
                    queue['checkpoint_id'] += 1
                    task['checkpoint_id'] = queue['checkpoint_id']
                except (IndexError, OSError, ValueError, KeyError):
                    task['status'] = 'BLOCKED_EVIDENCE'
                    task['error_reason'] = 'Interrupted with uncertain output; review before retry'
                task['updated_at'] = now()
                queue['events'].append({'at': now(), 'task_id': task['task_id'], 'status': task['status'],
                                        'reason': 'interruption recovery'})
        _save(queue, state_dir, repo)
        started = time.monotonic()
        processed = 0
        while processed < max_tasks and time.monotonic() - started < max_seconds:
            if (state_dir / 'STOP').exists():
                break
            task = _eligible(queue)
            if task is None:
                break
            if shutil.disk_usage(state_dir).free < 1_000_000_000 or _memory_available() < 256_000_000:
                break
            task['status'] = 'RUNNING'
            task['attempt_count'] += 1
            task['output_artifacts'] = []
            task['retry_after'] = None
            task['last_started_at'] = task['updated_at'] = now()
            queue['events'].append({'at': now(), 'task_id': task['task_id'], 'status': 'RUNNING'})
            _save(queue, state_dir, repo)
            processed += 1
            try:
                remaining = max_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('Offline run time budget exhausted')
                previous = signal.getsignal(signal.SIGALRM)
                def _timeout(_signum, _frame):
                    raise TimeoutError('Offline task time budget exhausted')
                signal.signal(signal.SIGALRM, _timeout)
                signal.setitimer(signal.ITIMER_REAL, min(task['resource_budget']['max_seconds'], remaining))
                try:
                    result = adapter.execute(task, queue)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    signal.signal(signal.SIGALRM, previous)
                adapter.verify(task, result)
                artifacts = state_dir / 'artifacts'
                artifacts.mkdir(mode=0o700, exist_ok=True)
                output = artifacts / (task['task_id'] + '.json')
                write_state(output, {'task_id': task['task_id'], 'plan_task_type': task['task_type'],
                                     'executed_at_utc': now(), 'result': result})
                task['output_artifacts'] = [str(output)]
                task['status'] = 'VERIFYING'
                task['updated_at'] = now()
                _save(queue, state_dir, repo)
                _verify_output(adapter, task)
                task['status'] = 'COMPLETED'
                task['last_completed_at'] = task['updated_at'] = now()
                task['evidence_refs'] = [str(output), _sha(output)]
                queue['checkpoint_id'] += 1
                task['checkpoint_id'] = queue['checkpoint_id']
            except Exception as exc:
                task['error_reason'] = (type(exc).__name__ + ': ' + str(exc))[:240]
                if isinstance(exc, QuotaBlocked):
                    task['status'] = 'BLOCKED_QUOTA'
                elif isinstance(exc, PermissionError):
                    task['status'] = 'BLOCKED_LICENSE'
                elif isinstance(exc, (ValueError, KeyError, FileNotFoundError)):
                    task['status'] = 'BLOCKED_EVIDENCE'
                elif task['attempt_count'] < task['resource_budget']['max_attempts']:
                    task['status'] = 'RETRYABLE'
                    task['retry_after'] = (_utc(now()) + timedelta(seconds=2 ** task['attempt_count'] * 60)).isoformat()
                else:
                    task['status'] = 'FAILED'
                task['updated_at'] = now()
            queue['events'].append({'at': now(), 'task_id': task['task_id'], 'status': task['status']})
            _save(queue, state_dir, repo)
        return {'processed': processed, 'checkpoint_id': queue['checkpoint_id'],
                'next_task': (_eligible(queue) or {}).get('task_id'),
                'statuses': {key: value['status'] for key, value in queue['tasks'].items()}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'run', 'status', 'handoff', 'stop', 'clear-stop'))
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--horizon-hours', type=int, default=48)
    parser.add_argument('--max-tasks', type=int, default=3)
    parser.add_argument('--max-seconds', type=int, default=120)
    args = parser.parse_args()
    if args.mode == 'stop':
        args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_state(args.state_dir / 'STOP', {'stop_requested': True})
        result = {'stop_requested': True}
    elif args.mode == 'clear-stop':
        with locked_state(args.state_dir):
            (args.state_dir / 'STOP').unlink(missing_ok=True)
        result = {'stop_cleared': True}
    elif args.mode == 'prepare':
        if not args.plan:
            raise ValueError('prepare requires --plan')
        result = prepare(args.plan, args.state_dir, args.repo, args.horizon_hours)
        result = {'task_count': len(result['tasks']), 'checkpoint_id': result['checkpoint_id']}
    elif args.mode == 'run':
        result = run(args.state_dir, args.repo, args.max_tasks, args.max_seconds)
    elif args.mode == 'handoff':
        with locked_state(args.state_dir):
            result = _load_queue(args.state_dir)
            publish(result, args.state_dir, args.repo)
            result = json.loads((args.state_dir / 'codex_handoff.json').read_text())
    else:
        result = _load_queue(args.state_dir)
        result = {'checkpoint_id': result['checkpoint_id'],
                  'next_task': (_eligible(result) or {}).get('task_id'),
                  'statuses': {key: value['status'] for key, value in result['tasks'].items()}}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
