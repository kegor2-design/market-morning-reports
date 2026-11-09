"""Fault-inject a real model artifact into the guided path, then use its real repair artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from regime190.agent43_engine import _check_code
from universal_agent.engine import write_state
from universal_agent.guided_experiment import AI_ROOT, PRIVATE_ROOT, run
from universal_agent.isolated_codex import generate_agent43_code as real_generate


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exercise(ai_dir: Path, state_dir: Path, *, live_repair: bool = False) -> dict:
    ai_dir = ai_dir.resolve(strict=True)
    state_dir = state_dir.resolve()
    if (not ai_dir.is_relative_to(AI_ROOT) or
            not state_dir.is_relative_to(PRIVATE_ROOT) or state_dir.is_symlink()):
        raise ValueError('Fault trial outside private research state')
    verified = {}
    for kind in (('initial',) if live_repair else ('initial', 'repair')):
        request = json.loads((ai_dir / f'code_{kind}_request.json').read_text())
        response_path = ai_dir / f'code_{kind}.json'
        if request.get('status') != 'VERIFIED' or request.get('response_sha256') != _sha(response_path):
            raise ValueError('Model artifact is not verified')
        verified[kind] = json.loads(response_path.read_text())
    original = verified['initial']['code']
    faulty = original.replace('math.log(', 'math.no_such_log(', 1)
    if faulty == original:
        raise ValueError('Real model source changed; review fault injection')
    _check_code(faulty)
    def supply(brief: dict, work_dir: Path, *, repair_feedback: str = '', **_) -> dict:
        if repair_feedback and live_repair:
            return real_generate(brief, work_dir, repair_feedback=repair_feedback,
                                 failed_code=faulty)
        artifact = verified['repair'] if repair_feedback else (verified['initial'] | {'code': faulty})
        return {'status': 'REAL_CODE_GENERATION_VERIFIED', 'artifact': artifact,
                'codex_calls': 1, 'fault_injected_after_model_validation': not bool(repair_feedback)}
    with patch('universal_agent.guided_experiment.generate_agent43_code', side_effect=supply):
        outcome = run(ai_dir, state_dir)
    state = json.loads((state_dir / 'guided_state.json').read_text())
    repair_path = ai_dir / 'code_repair.json'
    repair_request_path = ai_dir / 'code_repair_request.json'
    repair_request = (json.loads(repair_request_path.read_text())
                      if live_repair and repair_request_path.exists() else None)
    repair_code = (json.loads(repair_path.read_text())['code']
                   if live_repair and repair_path.exists() else
                   verified['repair']['code'] if not live_repair else None)
    evidence = {'status': 'INTEGRATED_FAULT_INJECTION_VERIFIED' if
                outcome['status'] == 'EXPLORATORY_BACKTEST_VERIFIED' and
                state.get('repair', {}).get('status') == 'REPAIRED' else 'FAILED',
                'fault': 'allowed-library call error injected after genuine model generation',
                'original_model_code_sha256': hashlib.sha256(original.encode()).hexdigest(),
                'injected_code_sha256': hashlib.sha256(faulty.encode()).hexdigest(),
                'real_repair_code_sha256': hashlib.sha256(repair_code.encode()).hexdigest()
                    if repair_code else None,
                'diagnoses': state.get('failures', []), 'repair': state.get('repair'),
                'result_status': outcome['status'],
                'hypothesis_assessment': outcome.get('hypothesis_assessment'),
                'model_called_during_trial': bool(repair_request and
                    repair_request.get('called_at_utc', '') >= state['started_at_utc']),
                'repair_request': repair_request}
    write_state(state_dir / 'integrated_fault_evidence.json', evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ai-state-dir', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--live-repair', action='store_true')
    args = parser.parse_args()
    print(json.dumps(exercise(args.ai_state_dir, args.state_dir,
                              live_repair=args.live_repair), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
