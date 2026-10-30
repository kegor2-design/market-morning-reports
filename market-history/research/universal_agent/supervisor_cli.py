"""Bounded supervisor command line interface; no background service activation."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .supervisor import operate, register, resolve_project


def main() -> int:
    parser = argparse.ArgumentParser(description='Universal research supervisor')
    parser.add_argument('mode', choices=('inspect', 'register', 'plan', 'dry-run',
                         'run-once', 'run-bounded', 'resume', 'status', 'report', 'stop', 'recover'))
    parser.add_argument('--project', type=Path)
    parser.add_argument('--project-id')
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--max-tasks', type=int, default=3)
    parser.add_argument('--max-seconds', type=int, default=1800)
    parser.add_argument('--task-id')
    parser.add_argument('--resolution', choices=('retry', 'cancel', 'clear-stop'))
    args = parser.parse_args()
    try:
        if args.mode == 'register':
            if not args.project or not args.registry:
                raise ValueError('register requires --project and --registry')
            result = {'registered': register(args.registry, args.project)}
        elif args.mode == 'stop':
            if not args.state_dir:
                raise ValueError('stop requires --state-dir')
            args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.stop-', dir=args.state_dir)
            try:
                with os.fdopen(fd, 'w') as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write('Stop requested\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, args.state_dir / 'STOP')
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            result = {'mode': 'stop', 'stop_requested': True, 'state_dir': str(args.state_dir)}
        else:
            if not args.state_dir:
                raise ValueError('Mode requires --state-dir')
            project = resolve_project(args.project, args.registry, args.project_id)
            result = operate(args.mode, project, args.state_dir,
                             max_tasks=args.max_tasks, max_seconds=args.max_seconds,
                             task_id=args.task_id, resolution=args.resolution)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({'error': type(exc).__name__, 'reason': str(exc)[:240]}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
