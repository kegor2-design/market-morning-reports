"""Bounded market hypothesis continuation within an existing research job.

Only the reviewed Guided/Agent 4.3 path can execute generated code. Every
result remains exploratory until the independent PIT and holdout gates pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .engine import canonical, write_state
from .fault_trial import exercise
from .guided_experiment import (AI_ROOT, PRIVATE_ROOT as DATA_ROOT,
                                _load_ai, assess_hypothesis, run,
                                validate_fold_output)
from .isolated_codex import generate
from regime190.agent43_engine import _verify_market


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_cycle(ai_dir: Path, data_dir: Path, cycle: dict) -> dict:
    """Read-only verification of the original AI response and both sealed folds."""
    if (ai_dir.is_symlink() or data_dir.is_symlink() or
            not ai_dir.resolve().is_relative_to(AI_ROOT.resolve()) or
            not data_dir.resolve().is_relative_to(DATA_ROOT.resolve())):
        raise ValueError('Cycle state outside private roots')
    checkpoint = data_dir / 'guided_state.json'
    if checkpoint.is_symlink() or sha(checkpoint) != cycle['checkpoint_sha256']:
        raise ValueError('Guided checkpoint changed')
    saved = json.loads(checkpoint.read_text())
    hypothesis, ai_hash = _load_ai(ai_dir)
    if (ai_hash != cycle['hypothesis_sha256'] or
            saved['ai_response_sha256'] != ai_hash or
            saved['status'] != 'EXPLORATORY_BACKTEST_VERIFIED'):
        raise ValueError('Guided hypothesis or status mismatch')
    task_dir = Path(saved['data']['task_dir'])
    sealed_dir = Path(saved['data']['sealed_dir'])
    if (not task_dir.resolve().is_relative_to(data_dir.resolve()) or
            not sealed_dir.resolve().is_relative_to(data_dir.resolve())):
        raise ValueError('Staged data outside cycle state')
    code_hash = saved.get('active_code_sha256', saved['code_sha256'])
    if (cycle['code_sha256'] != code_hash or
            cycle['input_sha256'] != saved['data']['input_sha256'] or
            cycle['output_sha256'] != saved['output_sha256'] or
            cycle['code_calls'] != saved['code_calls']):
        raise ValueError('Cycle input, code, or output hashes changed')
    for fold in ('fold1', 'fold2'):
        fold_dir = task_dir / fold
        checked = validate_fold_output(fold_dir, saved['data']['input_sha256'][fold])
        if (checked['output_sha256'] != saved['output_sha256'][fold] or
                sha(fold_dir / 'experiment.py') != code_hash):
            raise ValueError('Generated source or prediction integrity mismatch')
    if _verify_market(task_dir, sealed_dir, 'crash') != saved['result']:
        raise ValueError('Sealed-fold result changed')
    assessment = assess_hypothesis(task_dir, sealed_dir, saved['data']['input_sha256'])
    if assessment != cycle['assessment']:
        raise ValueError('Independent hypothesis assessment changed')
    if assessment['pit_verified'] or assessment['official_claim']:
        raise ValueError('Unverified PIT result promoted')
    return hypothesis


def _record(ai_dir: Path, data_dir: Path, assessment: dict, *, fault: dict | None = None,
            alternative_index: int = 0) -> dict:
    checkpoint = data_dir / 'guided_state.json'
    saved = json.loads(checkpoint.read_text())
    cycle = {'ai_dir': str(ai_dir), 'data_dir': str(data_dir),
             'alternative_index': alternative_index,
             'hypothesis_sha256': saved['ai_response_sha256'],
             'checkpoint_sha256': sha(checkpoint), 'assessment': assessment,
             'code_sha256': saved.get('active_code_sha256', saved['code_sha256']),
             'input_sha256': saved['data']['input_sha256'],
             'output_sha256': saved['output_sha256'],
             'code_calls': saved['code_calls']}
    if fault is not None:
        cycle['fault_evidence_sha256'] = sha(data_dir / 'integrated_fault_evidence.json')
        cycle['fault_status'] = fault['status']
    verify_cycle(ai_dir, data_dir, cycle)
    return cycle


def _goal(manifest: dict, prior: list[dict], index: int) -> str:
    prior_text = [item['hypothesis'][:200] for item in prior]
    return (manifest['goal'][:200] + ' Generate a distinct alternative to rejected '
            '20-session KOSPI crash hypotheses: ' + ' | '.join(prior_text)[:350] +
            '. The required_data array MUST explicitly name all five available '
            'staged columns: momentum5, momentum20, volatility20, drawdown60, '
            'relative_kosdaq20. Do not require any other data. Use 20 sessions, '
            'a standard-library binned frequency model, two chronological folds, '
            'and a falsifiable comparison against the volatility-only baseline. '
            'Propose a different economic mechanism or feature interaction. '
            f'Alternative number {index}; exploratory PIT-unverified only.')[:1000]


def _used_calls(manifest: dict) -> int:
    dirs = [Path(manifest['ai_state_dir'])] + [
        AI_ROOT / f"{manifest['job_id']}_alt{index}"
        for index in range(1, manifest['max_follow_on_hypotheses'] + 1)]
    return sum(len(list(directory.glob('*_request.json'))) for directory in dirs
               if directory.is_dir())


def run_job(manifest: dict, state_dir: Path) -> dict:
    def finish(value: dict) -> dict:
        value['model_calls'] = _used_calls(manifest)
        value['task_id'] = manifest['job_id'] + '_execute'
        return value

    ai_dir = Path(manifest['ai_state_dir']).resolve()
    data_dir = Path(manifest['guided_state_dir']).resolve()
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fault = exercise(ai_dir, data_dir, live_repair=True,
                     fault_kind=manifest['fault_kind'])
    if fault['status'] != 'INTEGRATED_FAULT_INJECTION_VERIFIED':
        return finish({'status': 'BLOCKED_FAULT_REPAIR', 'fault_status': fault['status'],
                'fault_evidence_sha256': sha(data_dir / 'integrated_fault_evidence.json'),
                'cycles': [], 'official_market_claim': False})
    initial = json.loads((data_dir / 'guided_state.json').read_text())
    assessment = initial.get('hypothesis_assessment') or assess_hypothesis(
        Path(initial['data']['task_dir']), Path(initial['data']['sealed_dir']),
        initial['data']['input_sha256'])
    cycles = [_record(ai_dir, data_dir, assessment, fault=fault)]
    prior = [_load_ai(ai_dir)[0]]
    rejected_attempts = []
    if assessment['status'] != 'REJECTED_EXPLORATORY':
        return finish({'status': 'EXPLORATORY_ONLY', 'cycles': cycles,
                'transition_count': 0, 'official_market_claim': False})
    for index in range(1, manifest['max_follow_on_hypotheses'] + 1):
        if _used_calls(manifest) >= manifest['max_model_calls']:
            return finish({'status': 'BLOCKED_ALTERNATE_MODEL', 'reason': 'Model budget exhausted',
                    'cycles': cycles, 'transition_count': len(cycles) - 1,
                    'official_market_claim': False})
        alternate_ai = AI_ROOT / f"{manifest['job_id']}_alt{index}"
        alternate_data = DATA_ROOT / f"{manifest['job_id']}_alt{index}"
        alternate_ai.mkdir(mode=0o700, parents=True, exist_ok=True)
        alternate_data.mkdir(mode=0o700, parents=True, exist_ok=True)
        generated = generate(_goal(manifest, prior, index), alternate_ai)
        if generated['status'] != 'REAL_AI_VERIFIED':
            return finish({'status': 'BLOCKED_ALTERNATE_MODEL', 'reason': generated['status'],
                    'cycles': cycles, 'transition_count': len(cycles) - 1,
                    'official_market_claim': False})
        hypothesis = generated['hypothesis']
        fingerprints = {hashlib.sha256(canonical((item['hypothesis'].lower().strip(),
                          item['economic_reason'].lower().strip()))).hexdigest()
                        for item in prior}
        fingerprint = hashlib.sha256(canonical((hypothesis['hypothesis'].lower().strip(),
                          hypothesis['economic_reason'].lower().strip()))).hexdigest()
        if fingerprint in fingerprints:
            return finish({'status': 'BLOCKED_DUPLICATE_HYPOTHESIS', 'cycles': cycles,
                    'transition_count': len(cycles) - 1, 'official_market_claim': False})
        prior.append(hypothesis)
        # Guided may make an initial code call and one repair call.
        if _used_calls(manifest) + 2 > manifest['max_model_calls']:
            return finish({'status': 'BLOCKED_ALTERNATE_MODEL', 'reason': 'Code-call budget exhausted',
                    'cycles': cycles, 'transition_count': len(cycles) - 1,
                    'official_market_claim': False})
        outcome = run(alternate_ai, alternate_data)
        if outcome['status'] != 'EXPLORATORY_BACKTEST_VERIFIED':
            rejected_attempts.append({'index': index, 'status': outcome['status'],
                'reason': outcome.get('reason'),
                'hypothesis_sha256': sha(alternate_ai / 'ai_response.json')})
            write_state(state_dir / f'alternate_attempt_{index}.json', rejected_attempts[-1])
            continue
        saved = json.loads((alternate_data / 'guided_state.json').read_text())
        assessment = assess_hypothesis(Path(saved['data']['task_dir']),
            Path(saved['data']['sealed_dir']), saved['data']['input_sha256'])
        cycle = _record(alternate_ai, alternate_data, assessment,
                        alternative_index=index)
        cycles.append(cycle)
        write_state(state_dir / f'cycle_{index}.json', cycle)
        if assessment['status'] != 'REJECTED_EXPLORATORY':
            break
    return finish({'status': 'EXPLORATORY_ONLY' if len(cycles) > 1 else
            'BLOCKED_ALTERNATE_EXECUTION', 'cycles': cycles,
            'rejected_attempts': rejected_attempts,
            'transition_count': len(cycles) - 1, 'official_market_claim': False})
