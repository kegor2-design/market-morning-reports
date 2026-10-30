"""CLI for a bounded research-agent pass."""
import argparse
import json
from pathlib import Path

from .engine import load_project, reopen, run, select_task


def main() -> int:
    parser = argparse.ArgumentParser(description='Evidence-gated research coordinator')
    parser.add_argument('command', choices=('plan', 'run', 'reopen'))
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--max-steps', type=int, default=1)
    parser.add_argument('--task')
    args = parser.parse_args()
    if args.command == 'run':
        state = run(args.project, args.state_dir, args.max_steps)
    elif args.command == 'reopen':
        if not args.task:
            parser.error('reopen requires --task')
        state = reopen(args.project, args.state_dir, args.task)
    else:
        config, digest = load_project(args.project)
        state_path = args.state_dir / 'state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if state.get('config_sha256') != digest:
                parser.error('Project manifest changed; review state before resuming')
        else:
            state = {'project_id': config['project_id'],
                     'tasks': {task['id']: {'status': 'PENDING'} for task in config['tasks']}}
        state['next_task'] = (select_task(config, state) or {}).get('id')
    print(json.dumps({'project_id': state['project_id'], 'next_task': state['next_task'],
                      'tasks': {key: value['status'] for key, value in state['tasks'].items()}},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
