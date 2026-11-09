"""Bounded independent supervisor for one approved guided research job."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .engine import locked_state, now, write_state
from .guided_experiment import AI_ROOT, PRIVATE_ROOT
from .self_repair import redact


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
    parser.add_argument('--ai-state-dir', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--job-dir', type=Path, required=True)
    parser.add_argument('--max-restarts', type=int, default=2)
    parser.add_argument('--max-seconds', type=int, default=300)
    args = parser.parse_args()
    result = supervise(args.ai_state_dir, args.state_dir, args.job_dir,
                       max_restarts=args.max_restarts, max_seconds=args.max_seconds)
    print(json.dumps({'job_id': result['job_id'], 'status': result['status'],
                      'launch_count': result['launch_count'], 'restarts': result['restarts']}))
    return 0 if result['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
