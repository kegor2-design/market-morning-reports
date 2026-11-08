"""Verify a real AI repair candidate on both sealed Agent 4.3 folds."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from jsonschema import validate
from regime190.agent43_engine import SCHEMA, _check_code, _isolated_python, _verify_market
from universal_agent.engine import write_state
from universal_agent.guided_experiment import AI_ROOT, PRIVATE_ROOT
from universal_agent.self_repair import probe_secure_runner


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(ai_dir: Path, state_dir: Path) -> dict:
    if ai_dir.is_symlink() or state_dir.is_symlink():
        raise ValueError('Symlinked research state')
    ai_dir = ai_dir.resolve(strict=True)
    state_dir = state_dir.resolve(strict=True)
    if not ai_dir.is_relative_to(AI_ROOT) or not state_dir.is_relative_to(PRIVATE_ROOT):
        raise ValueError('Research state outside private scope')
    request = json.loads((ai_dir / 'code_repair_request.json').read_text())
    response_path = ai_dir / 'code_repair.json'
    if request['status'] != 'VERIFIED' or request['response_sha256'] != _sha(response_path):
        raise ValueError('AI repair candidate is unverified')
    artifact = json.loads(response_path.read_text())
    validate(artifact, json.loads(SCHEMA.read_text()))
    code = artifact['code']
    _check_code(code)
    if probe_secure_runner()['status'] != 'SECURE_RUNNER_VERIFIED':
        return {'status': 'SECURE_RUNNER_UNAVAILABLE'}
    prior = json.loads((state_dir / 'guided_state.json').read_text())
    source_task = Path(prior['data']['task_dir'])
    task = state_dir / 'repaired_backtest' / 'FORECAST-CRASH20'
    task.mkdir(mode=0o700, parents=True, exist_ok=True)
    executions = {}
    for fold in ('fold1', 'fold2'):
        work = task / fold
        work.mkdir(mode=0o700, exist_ok=True)
        data = work / 'data.csv'
        shutil.copyfile(source_task / fold / 'data.csv', data)
        if _sha(data) != prior['data']['input_sha256'][fold]:
            raise ValueError('Input integrity mismatch')
        (work / 'experiment.py').write_text(code)
        output = work / 'predictions.csv'
        if output.is_symlink():
            raise ValueError('Unsafe prior prediction output')
        output.unlink(missing_ok=True)
        result = _isolated_python(work)
        if (result['exit_code'] != 0 or _sha(data) != prior['data']['input_sha256'][fold]
                or not output.is_file()):
            raise ValueError('Repaired candidate failed isolated fold')
        executions[fold] = result
    verification = _verify_market(task, Path(prior['data']['sealed_dir']), 'crash')
    evidence = {'status': 'REPAIRED_CODE_EXPLORATORY_BACKTEST_VERIFIED',
                'repair_model': request.get('model'), 'repair_response_sha256': _sha(response_path),
                'repair_code_sha256': hashlib.sha256(code.encode()).hexdigest(),
                'executions': executions, 'verification': verification,
                'pit_verified': False, 'independent_holdout': 'NOT_AVAILABLE'}
    write_state(task.parent / 'evidence.json', evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ai-state-dir', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.ai_state_dir, args.state_dir), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
