"""Phase 3 runner CLI; leaves the Phase 2 CLI unchanged."""
import argparse
import json
import sys
from pathlib import Path

from .runner import operate


def main() -> int:
    parser = argparse.ArgumentParser(description='Bounded autonomous research runner')
    parser.add_argument('mode', choices=('inspect', 'plan', 'dry-run', 'run-once', 'resume', 'status'))
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = operate(args.mode, args.project, args.state_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({'mode': args.mode, 'error_type': type(exc).__name__,
                          'reason': str(exc)[:240]}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
