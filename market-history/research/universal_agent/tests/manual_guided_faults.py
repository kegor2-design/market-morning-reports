"""Run bounded faults against a copy of real AI-generated research code."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

from regime190.agent43_engine import _check_code, _isolated_python
from universal_agent.engine import write_state
from universal_agent.guided_experiment import PRIVATE_ROOT
from universal_agent.self_repair import Failure, diagnose, probe_secure_runner


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(state_dir: Path) -> dict:
    if state_dir.is_symlink():
        raise ValueError('State cannot be symlinked')
    state_dir = state_dir.resolve(strict=True)
    if not state_dir.is_relative_to(PRIVATE_ROOT):
        raise ValueError('Fault test must remain in private research tree')
    if probe_secure_runner()['status'] != 'SECURE_RUNNER_VERIFIED':
        return {'status': 'SECURE_RUNNER_UNAVAILABLE'}
    state = json.loads((state_dir / 'guided_state.json').read_text())
    if state['status'] != 'EXPLORATORY_BACKTEST_VERIFIED':
        raise ValueError('Real generated code has not completed its first backtest')
    source_dir = Path(state['data']['task_dir']) / 'fold1'
    source = source_dir / 'experiment.py'
    if _sha(source) != state['code_sha256']:
        raise ValueError('AI generated source hash mismatch')
    root = state_dir / 'faults'
    root.mkdir(mode=0o700, exist_ok=True)
    outcomes = {}
    for fault, code in (('COLUMN_MISMATCH', 'SCHEMA_MISMATCH'),
                        ('VALIDATION_TARGET_LEAK', 'DATA_CONTRACT_ERROR'),
                        ('ALLOWED_LIBRARY_CALL_ERROR', 'CODE_ERROR')):
        work = root / fault
        work.mkdir(mode=0o700, exist_ok=True)
        data = work / 'data.csv'
        shutil.copyfile(source_dir / 'data.csv', data)
        script = work / 'experiment.py'
        script.write_bytes(source.read_bytes())
        if fault == 'COLUMN_MISMATCH':
            data.write_text(data.read_text().replace('momentum5', 'missing_momentum5', 1))
        elif fault == 'VALIDATION_TARGET_LEAK':
            with data.open(newline='') as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames
                rows = list(reader)
            next(row for row in rows if row['split'] == 'validation')['target'] = '1'
            with data.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        else:
            script.write_text(script.read_text().replace('math.log(', 'math.no_such_log(', 1))
            _check_code(script.read_text())
        execution = _isolated_python(work)
        failure = diagnose(Failure(state['run_id'], 'BACKTEST_CODE', code,
                                   execution.get('stderr', ''), fault))
        outcomes[fault] = {'exit_code': execution['exit_code'],
                           'error_type': failure['error_type'],
                           'next_action': failure['next_action'],
                           'script_sha256': _sha(script), 'input_sha256': _sha(data),
                           'failed_as_expected': execution['exit_code'] != 0}
    repeated = Failure(state['run_id'], 'BACKTEST_CODE', 'CODE_ERROR',
                       'AttributeError: same method', 'repeat-context')
    first = diagnose(repeated)
    second = diagnose(repeated, [first])
    evidence = {'status': 'FAULT_INJECTION_VERIFIED' if all(
        item['failed_as_expected'] for item in outcomes.values()) else 'FAULT_INJECTION_FAILED',
        'source_ai_code_sha256': state['code_sha256'], 'faults': outcomes,
        'repeat_actions': [first['next_action'], second['next_action']]}
    write_state(root / 'fault_evidence.json', evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.state_dir), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
