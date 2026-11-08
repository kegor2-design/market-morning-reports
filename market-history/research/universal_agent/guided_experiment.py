"""Connect a real AI hypothesis to Agent 4.3's bounded crash experiment.

The Regime190 adapter supplies only historical snapshot features. Its missing
publication clock and independent holdout keep every result exploratory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .engine import locked_state, now, write_state
from .isolated_codex import generate_agent43_code
from .self_repair import Failure, diagnose, probe_secure_runner, repair_research_source

HERE = Path(__file__).resolve().parent
RESEARCH_ROOT = HERE.parent
PRIVATE_ROOT = RESEARCH_ROOT / '.universal_private'
AI_ROOT = HERE.parents[2] / '.universal_private'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_ai(ai_dir: Path) -> tuple[dict, str]:
    from jsonschema import validate
    from .isolated_codex import SCHEMA
    ai_dir = ai_dir.resolve(strict=True)
    if not ai_dir.is_relative_to(AI_ROOT.resolve(strict=True)):
        raise ValueError('AI checkpoint outside private research state')
    request = json.loads((ai_dir / 'ai_request.json').read_text())
    response = ai_dir / 'ai_response.json'
    if request.get('status') != 'VERIFIED' or request.get('response_sha256') != _sha(response):
        raise ValueError('AI hypothesis evidence is not verified')
    hypothesis = json.loads(response.read_text())
    validate(hypothesis, json.loads(SCHEMA.read_text()))
    return hypothesis, request['response_sha256']


def _stage(data_dir: Path) -> dict:
    from regime190.agent41_research import _observations
    from regime190.agent43_engine import _stage_market
    task_dir = data_dir / 'FORECAST-CRASH20'
    sealed = data_dir / 'sealed'
    task_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    sealed.mkdir(mode=0o700, exist_ok=True)
    observations, provenance = _observations()
    staged = _stage_market(task_dir, sealed, 'crash', 20, observations)
    inputs = {fold: _sha(task_dir / fold / 'data.csv') for fold in ('fold1', 'fold2')}
    return {'task_dir': str(task_dir), 'sealed_dir': str(sealed),
            'staged': staged, 'input_sha256': inputs, 'provenance': provenance,
            'pit_status': 'PIT_UNVERIFIED', 'independent_holdout': 'NOT_AVAILABLE'}


def _brief(hypothesis: dict, staged: dict) -> dict:
    return {'task_id': 'FORECAST-CRASH20', 'staged': staged,
            'input_hypothesis': hypothesis,
            'data_contract': {'columns': ['date', 'split', 'target', 'momentum5',
                                          'momentum20', 'volatility20', 'drawdown60',
                                          'relative_kosdaq20'],
                              'validation_target': 'blank',
                              'output': 'predictions.csv: date,probability'},
            'research_status': 'EXPLORATORY_ONLY_PIT_UNVERIFIED'}


def run(ai_dir: Path, data_dir: Path) -> dict:
    """One hypothesis, at most two Codex code calls, and two sealed folds."""
    if data_dir.is_symlink():
        raise ValueError('Execution state cannot be a symlink')
    data_dir = data_dir.resolve()
    if not data_dir.is_relative_to(PRIVATE_ROOT):
        raise ValueError('Execution state must be in private research tree')
    hypothesis, ai_hash = _load_ai(ai_dir)
    if hypothesis['horizon_sessions'] != 20:
        return {'status': 'DATA_ACQUISITION_REQUIRED', 'reason': 'Regime190 adapter supports 20-session crash labels'}
    required = ' '.join(hypothesis['required_data']).lower()
    features = ('momentum5', 'momentum20', 'volatility20', 'drawdown60',
                'relative_kosdaq20')
    if any(feature not in required for feature in features):
        return {'status': 'DATA_ACQUISITION_REQUIRED',
                'reason': 'AI data requirements exceed the five staged Regime190 features'}
    with locked_state(data_dir):
        state_path = data_dir / 'guided_state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state['ai_response_sha256'] != ai_hash:
                raise ValueError('AI hypothesis changed; new run required')
        else:
            state = {'schema_version': 1, 'run_id': data_dir.name,
                     'ai_response_sha256': ai_hash, 'status': 'PREPARING',
                     'code_calls': 0, 'failures': [], 'started_at_utc': now()}
            write_state(state_path, state)
        if (data_dir / 'STOP').exists():
            state['status'] = 'STOPPED'
            write_state(state_path, state)
            return {'status': 'STOPPED'}
        if state.get('status') == 'EXPLORATORY_BACKTEST_VERIFIED':
            task_dir = Path(state['data']['task_dir'])
            if not state.get('output_sha256'):
                from regime190.agent43_engine import _verify_market
                if _verify_market(task_dir, Path(state['data']['sealed_dir']), 'crash') != state['result']:
                    raise ValueError('Previously completed result no longer matches outputs')
                state['output_sha256'] = {
                    fold: _sha(task_dir / fold / 'predictions.csv') for fold in ('fold1', 'fold2')}
                state['output_hash_backfilled_after_verification'] = True
                write_state(state_path, state)
            for fold, digest in state['data']['input_sha256'].items():
                if _sha(task_dir / fold / 'data.csv') != digest:
                    raise ValueError('Completed research input integrity mismatch')
                if _sha(task_dir / fold / 'predictions.csv') != state['output_sha256'][fold]:
                    raise ValueError('Completed research output integrity mismatch')
                expected_code = state.get('active_code_sha256', state['code_sha256'])
                if _sha(task_dir / fold / 'experiment.py') != expected_code:
                    raise ValueError('Completed generated code integrity mismatch')
            return {'status': state['status'], 'resumed_without_duplicate': True,
                    'result': state['result']}
        if 'data' not in state:
            state['data'] = _stage(data_dir)
            state['status'] = 'DATA_STAGED'
            write_state(state_path, state)
        task_dir = Path(state['data']['task_dir'])
        sealed_dir = Path(state['data']['sealed_dir'])
        for fold, digest in state['data']['input_sha256'].items():
            if _sha(task_dir / fold / 'data.csv') != digest:
                raise ValueError('Research input changed after staging')
        brief = _brief(hypothesis, state['data']['staged'])
        if state['code_calls'] >= 2 and not (ai_dir / 'code_initial.json').exists():
            return {'status': 'SAFE_BLOCKED', 'reason': 'Code call budget exhausted'}
        generated = generate_agent43_code(brief, ai_dir)
        state['code_calls'] = max(state['code_calls'], generated.get('codex_calls', 0))
        state['code_generation'] = {k: v for k, v in generated.items() if k != 'artifact'}
        write_state(state_path, state)
        if generated['status'] == 'CODE_VALIDATION_FAILED' and state['code_calls'] < 2:
            repaired = generate_agent43_code(brief, ai_dir,
                repair_feedback='Initial generated code failed Agent 4.3 static/schema gate: '
                                + generated['reason'][:1000])
            state['code_calls'] = 2
            state['repair_generation'] = {k: v for k, v in repaired.items() if k != 'artifact'}
            write_state(state_path, state)
            generated = repaired
        if generated['status'] != 'REAL_CODE_GENERATION_VERIFIED':
            state['status'] = generated['status']
            write_state(state_path, state)
            return {'status': state['status'], 'code_calls': state['code_calls']}
        code = generated['artifact']['code']
        state['code_sha256'] = hashlib.sha256(code.encode()).hexdigest()
        if state.get('active_code_sha256') and state['active_code_sha256'] != state['code_sha256']:
            repaired_path = task_dir / 'fold1' / 'experiment.py'
            if _sha(repaired_path) != state['active_code_sha256']:
                raise ValueError('Repaired source integrity mismatch')
            code = repaired_path.read_text()
        state['status'] = 'CODE_VALIDATED'
        write_state(state_path, state)
        probe = probe_secure_runner()
        if probe['status'] != 'SECURE_RUNNER_VERIFIED':
            state['status'] = 'SECURE_RUNNER_UNAVAILABLE'
            write_state(state_path, state)
            return {'status': state['status'], 'probe': probe}
        from regime190.agent43_engine import _isolated_python, _verify_market
        for fold in ('fold1', 'fold2'):
            fold_dir = task_dir / fold
            source = fold_dir / 'experiment.py'
            if fold in state.get('output_sha256', {}):
                if (_sha(source) != hashlib.sha256(code.encode()).hexdigest() or
                        _sha(fold_dir / 'predictions.csv') != state['output_sha256'][fold]):
                    raise ValueError('Verified fold integrity mismatch')
                continue
            source.write_text(code)
            output = fold_dir / 'predictions.csv'
            if output.exists():
                if output.is_symlink():
                    raise ValueError('Unsafe prediction output')
                output.unlink()
            execution = _isolated_python(fold_dir)
            if _sha(fold_dir / 'data.csv') != state['data']['input_sha256'][fold]:
                state['status'] = 'SAFE_BLOCKED'
                state['reason'] = 'Generated code modified staged input'
                write_state(state_path, state)
                return {'status': state['status'], 'reason': state['reason']}
            if execution['exit_code'] != 0:
                failure = diagnose(Failure(state['run_id'], 'BACKTEST_CODE',
                    'CODE_ERROR', execution.get('stderr', 'Execution failed'), fold), state['failures'])
                state['failures'].append(failure)
                write_state(state_path, state)
                if state['code_calls'] >= 2:
                    state['status'] = 'SAFE_BLOCKED'
                    write_state(state_path, state)
                    return {'status': state['status'], 'failure': failure}
                repaired = generate_agent43_code(brief, ai_dir,
                    repair_feedback=execution.get('stderr', 'Execution failed')[:1500])
                state['code_calls'] = 2
                state['repair_generation'] = {k: v for k, v in repaired.items() if k != 'artifact'}
                write_state(state_path, state)
                if repaired['status'] != 'REAL_CODE_GENERATION_VERIFIED':
                    state['status'] = 'SAFE_BLOCKED'
                    write_state(state_path, state)
                    return {'status': state['status'], 'repair': state['repair_generation']}
                def verify(path: Path, result: dict) -> bool:
                    if result['exit_code'] != 0 or _sha(path.parent / 'data.csv') != state['data']['input_sha256'][fold]:
                        return False
                    return output.is_file() and output.stat().st_size > 20
                repair = repair_research_source(source, [repaired['artifact']['code']],
                                                fold_dir, verify)
                state['repair'] = repair
                write_state(state_path, state)
                if repair['status'] != 'REPAIRED':
                    state['status'] = 'SAFE_BLOCKED'
                    write_state(state_path, state)
                    return {'status': state['status'], 'repair': repair}
                code = source.read_text()
                execution = {'exit_code': 0, 'sandbox': 'BWRAP_UNSHARE_ALL_NO_HOME_NO_NETWORK',
                             'repaired_code_sha256': _sha(source)}
                state['active_code_sha256'] = _sha(source)
            state.setdefault('executions', {})[fold] = execution
            if not output.is_file():
                state['status'] = 'SAFE_BLOCKED'
                state['reason'] = 'Generated code did not produce predictions.csv'
                write_state(state_path, state)
                return {'status': state['status'], 'reason': state['reason']}
            state.setdefault('output_sha256', {})[fold] = _sha(output)
            write_state(state_path, state)
        try:
            verification = _verify_market(task_dir, sealed_dir, 'crash')
        except Exception as exc:
            state['status'] = 'SAFE_BLOCKED'
            state['failure'] = diagnose(Failure(state['run_id'], 'BACKTEST_OUTPUT',
                type(exc).__name__, str(exc), 'Agent 4.3 output contract'), state['failures'])
            write_state(state_path, state)
            return {'status': state['status'], 'failure': state['failure']}
        state['status'] = 'EXPLORATORY_BACKTEST_VERIFIED'
        state['result'] = verification
        state['completed_at_utc'] = now()
        write_state(state_path, state)
        return {'status': state['status'], 'result': verification,
                'code_calls': state['code_calls'], 'ai_response_sha256': ai_hash,
                'code_sha256': state['code_sha256']}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ai-state-dir', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.ai_state_dir, args.state_dir), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
