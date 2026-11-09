"""Connect a real AI hypothesis to Agent 4.3's bounded crash experiment.

The Regime190 adapter supplies only historical snapshot features. Its missing
publication clock and independent holdout keep every result exploratory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
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


def _brief(hypothesis: dict, staged: dict, plan: dict | None = None) -> dict:
    brief = {'task_id': 'FORECAST-CRASH20', 'staged': staged,
            'input_hypothesis': hypothesis,
            'data_contract': {'columns': ['date', 'split', 'target', 'momentum5',
                                          'momentum20', 'volatility20', 'drawdown60',
                                          'relative_kosdaq20'],
                              'validation_target': 'blank',
                              'output': 'predictions.csv: date,probability'},
            'research_status': 'EXPLORATORY_ONLY_PIT_UNVERIFIED'}
    if plan:
        brief['research_plan'] = plan
    return brief


def validate_fold_output(fold_dir: Path, input_sha256: str) -> dict:
    """Check the staged input and generated prediction contract before acceptance."""
    data = fold_dir / 'data.csv'
    output = fold_dir / 'predictions.csv'
    if _sha(data) != input_sha256:
        raise ValueError('Staged input changed during generated-code execution')
    with data.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        required = {'date', 'split', 'target', 'momentum5', 'momentum20',
                    'volatility20', 'drawdown60', 'relative_kosdaq20'}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError('Input data column contract failed')
        rows = list(reader)
    train = [row for row in rows if row['split'] == 'train']
    valid = [row for row in rows if row['split'] == 'validation']
    if (not train or not valid or len(train) + len(valid) != len(rows)
            or train[-1]['date'] >= valid[0]['date']
            or any(row['target'] not in {'0', '1'} for row in train)
            or any(row['target'] != '' for row in valid)):
        raise ValueError('Input split or sealed-label contract failed')
    if output.is_symlink() or not output.is_file() or output.stat().st_size > 10_000_000:
        raise ValueError('Missing or unsafe prediction output')
    with output.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['date', 'probability']:
            raise ValueError('Prediction output column contract failed')
        predictions = list(reader)
    if [row['date'] for row in predictions] != [row['date'] for row in valid]:
        raise ValueError('Prediction dates do not match sealed validation rows')
    try:
        probabilities = [float(row['probability']) for row in predictions]
    except (TypeError, ValueError) as exc:
        raise ValueError('Prediction probability is not numeric') from exc
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities):
        raise ValueError('Prediction probability outside finite unit interval')
    return {'rows': len(predictions), 'output_sha256': _sha(output)}


def next_action(data: dict, result: dict | None = None) -> dict:
    """Keep a blocked data dependency separate from other exploratory work."""
    if data.get('pit_status') != 'PIT_VERIFIED':
        return {'action': 'PIT_VALIDATION_REQUIRED',
                'reason': 'Historical publication/vintage evidence is unavailable',
                'automatic': False, 'independent_research_can_continue': True,
                'official_performance_claim': False}
    if data.get('independent_holdout') != 'AVAILABLE':
        return {'action': 'INDEPENDENT_VALIDATION_REQUIRED',
                'reason': 'No unexamined independent evaluation period',
                'automatic': False, 'independent_research_can_continue': True,
                'official_performance_claim': False}
    return {'action': 'RESEARCH_COMPLETED' if result else 'BACKTEST_REQUIRED',
            'automatic': bool(result), 'independent_research_can_continue': True,
            'official_performance_claim': False}


def _verified_plan(ai_dir: Path, hypothesis_hash: str) -> tuple[dict | None, str | None]:
    from jsonschema import validate
    from .isolated_codex import PLAN_SCHEMA, validate_plan_for_agent43
    for prefix in ('plan_repair', 'plan'):
        request_path = ai_dir / f'{prefix}_request.json'
        response_path = ai_dir / f'{prefix}_response.json'
        if not request_path.exists():
            continue
        request = json.loads(request_path.read_text())
        if request.get('hypothesis_sha256') != hypothesis_hash:
            raise ValueError('AI plan is bound to another hypothesis')
        if request.get('status') != 'VERIFIED':
            return None, request.get('status', 'PLAN_UNVERIFIED')
        if request.get('response_sha256') != _sha(response_path):
            raise ValueError('AI plan artifact integrity mismatch')
        plan = json.loads(response_path.read_text())
        validate(plan, json.loads(PLAN_SCHEMA.read_text()))
        validate_plan_for_agent43(plan)
        return plan, request['response_sha256']
    return None, None


def assess_hypothesis(task_dir: Path, sealed_dir: Path, input_hashes: dict) -> dict:
    """Host-only volatility baseline and high-risk decile check for the AI claim."""
    from regime190.agent4_market import _score
    folds = []
    for fold in ('fold1', 'fold2'):
        work = task_dir / fold
        validate_fold_output(work, input_hashes[fold])
        with (work / 'data.csv').open(newline='', encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        train = [row for row in rows if row['split'] == 'train'][:-20]
        valid = [row for row in rows if row['split'] == 'validation']
        if not train:
            raise ValueError('No embargoed training rows')
        with (work / 'predictions.csv').open(newline='', encoding='utf-8') as stream:
            candidate = [float(row['probability']) for row in csv.DictReader(stream)]
        truth = json.loads((sealed_dir / f'{task_dir.name}_{fold}.json').read_text())
        labels = [bool(truth[row['date']]) for row in valid]
        values = sorted(float(row['volatility20']) for row in train)
        edges = (values[len(values) // 3], values[2 * len(values) // 3])
        def bucket(value: float) -> int:
            return 0 if value < edges[0] else 1 if value < edges[1] else 2
        label_count = Counter(int(row['target']) for row in train)
        grouped = {0: Counter(), 1: Counter()}
        for row in train:
            grouped[int(row['target'])][bucket(float(row['volatility20']))] += 1
        baseline = []
        for row in valid:
            group = bucket(float(row['volatility20']))
            positive = (grouped[1][group] + 1) / (label_count[1] + 4)
            negative = (grouped[0][group] + 1) / (label_count[0] + 4)
            score = math.log((label_count[1] + 1) / (label_count[0] + 1))
            score += 0.5 * math.log(positive / negative)
            baseline.append(1 / (1 + math.exp(-score)) if score >= 0
                            else math.exp(score) / (1 + math.exp(score)))
        candidate_ap = _score(labels, candidate, .1)['pr_auc_average_precision']
        baseline_ap = _score(labels, baseline, .1)['pr_auc_average_precision']
        top_count = max(1, math.ceil(len(valid) * .1))
        top_indices = sorted(range(len(valid)), key=lambda i: (-candidate[i], i))[:top_count]
        top_rate = sum(labels[i] for i in top_indices) / top_count
        base_rate = sum(labels) / len(labels)
        folds.append({'fold': fold, 'rows': len(valid), 'events': sum(labels),
                      'candidate_pr_auc': candidate_ap,
                      'volatility_only_pr_auc': baseline_ap,
                      'top_decile_event_rate': top_rate, 'overall_event_rate': base_rate,
                      'criterion_met': candidate_ap > baseline_ap and top_rate > base_rate})
    return {'status': 'SUPPORTED_EXPLORATORY' if all(f['criterion_met'] for f in folds)
            else 'REJECTED_EXPLORATORY', 'folds': folds, 'pit_verified': False,
            'independent_holdout': 'NOT_AVAILABLE', 'official_claim': False}


def _attach_ai_decision(state: dict, ai_dir: Path, state_path: Path) -> None:
    if 'ai_next_action' in state:
        saved = state['ai_next_action']
        if (saved.get('status') == 'REAL_AI_NEXT_ACTION_VERIFIED' and
                _sha(ai_dir / 'decision_response.json') != saved['response_sha256']):
            raise ValueError('AI next-action artifact integrity mismatch')
        return
    from .isolated_codex import generate_next_action
    summary = {'run_id': state['run_id'],
               'ai_response_sha256': state['ai_response_sha256'],
               'plan_sha256': state.get('plan_sha256'),
               'data_status': state['data_status'],
               'hypothesis_assessment': state.get('hypothesis_assessment'),
               'policy_next_action': state['next_action']}
    result = generate_next_action(summary, ai_dir)
    state['ai_next_action'] = result
    write_state(state_path, state)


def run(ai_dir: Path, data_dir: Path, *, ai_next_action: bool = False) -> dict:
    """One hypothesis, at most two Codex code calls, and two sealed folds."""
    if data_dir.is_symlink():
        raise ValueError('Execution state cannot be a symlink')
    data_dir = data_dir.resolve()
    if not data_dir.is_relative_to(PRIVATE_ROOT):
        raise ValueError('Execution state must be in private research tree')
    hypothesis, ai_hash = _load_ai(ai_dir)
    plan, plan_status = _verified_plan(ai_dir, ai_hash)
    if plan_status == 'PLAN_ADAPTER_MISMATCH' and not (ai_dir / 'plan_repair_request.json').exists():
        from .isolated_codex import generate_research_plan
        initial = json.loads((ai_dir / 'plan_request.json').read_text())
        feedback = initial.get('reason', 'Plan adapter contract mismatch')[:1500]
        try:
            generate_research_plan(ai_dir, repair_feedback=feedback)
        except ValueError:
            pass  # The bounded state below records the unresolved plan dependency.
        plan, plan_status = _verified_plan(ai_dir, ai_hash)
    data_problem = None
    if hypothesis['horizon_sessions'] != 20:
        data_problem = 'Regime190 adapter supports 20-session crash labels'
    required = ' '.join(hypothesis['required_data']).lower()
    features = ('momentum5', 'momentum20', 'volatility20', 'drawdown60',
                'relative_kosdaq20')
    if any(feature not in required for feature in features):
        data_problem = 'AI data requirements exceed the five staged Regime190 features'
    if plan and any(feature not in ' '.join(plan['exploratory_data']).lower()
                    for feature in features):
        data_problem = 'AI plan requires data outside the staged Regime190 contract'
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
        if plan_status and not plan:
            state['status'] = 'PLAN_ADAPTER_MISMATCH'
            state['plan_status'] = plan_status
            state['next_action'] = {'action': 'REPAIR_RESEARCH_PLAN',
                                    'automatic': False,
                                    'independent_research_can_continue': True}
            write_state(state_path, state)
            return {'status': state['status'], 'next_action': state['next_action']}
        if plan:
            if state.get('plan_sha256') and state['plan_sha256'] != plan_status:
                raise ValueError('Verified AI plan changed during research')
            state['plan_sha256'] = plan_status
            state['plan_status'] = 'REAL_AI_PLAN_VERIFIED'
            write_state(state_path, state)
        if data_problem:
            state['status'] = 'DATA_ACQUISITION_REQUIRED'
            state['data_status'] = 'DATA_ACQUISITION_REQUIRED'
            state['reason'] = data_problem
            state['next_action'] = {'action': 'DATA_ACQUISITION_REQUIRED',
                                    'reason': data_problem, 'automatic': False,
                                    'independent_research_can_continue': True}
            write_state(state_path, state)
            return {'status': state['status'], 'reason': data_problem,
                    'next_action': state['next_action']}
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
            if 'next_action' not in state:
                state['data_status'] = 'AVAILABLE_PIT_UNVERIFIED'
                state['next_action'] = next_action(state['data'], state['result'])
                write_state(state_path, state)
            if plan and 'hypothesis_assessment' not in state:
                state['hypothesis_assessment'] = assess_hypothesis(
                    task_dir, Path(state['data']['sealed_dir']), state['data']['input_sha256'])
                write_state(state_path, state)
            if ai_next_action:
                _attach_ai_decision(state, ai_dir, state_path)
            return {'status': state['status'], 'resumed_without_duplicate': True,
                    'result': state['result'], 'next_action': state['next_action'],
                    'hypothesis_assessment': state.get('hypothesis_assessment'),
                    'ai_next_action': state.get('ai_next_action')}
        if 'data' not in state:
            state['data'] = _stage(data_dir)
            state['status'] = 'DATA_STAGED'
            write_state(state_path, state)
        task_dir = Path(state['data']['task_dir'])
        sealed_dir = Path(state['data']['sealed_dir'])
        for fold, digest in state['data']['input_sha256'].items():
            if _sha(task_dir / fold / 'data.csv') != digest:
                raise ValueError('Research input changed after staging')
        brief = _brief(hypothesis, state['data']['staged'], plan)
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
            input_hash = state['data']['input_sha256'][fold]
            if _sha(fold_dir / 'data.csv') != input_hash:
                state['status'] = 'SAFE_BLOCKED'
                state['reason'] = 'Generated code modified staged input'
                write_state(state_path, state)
                return {'status': state['status'], 'reason': state['reason']}
            contract_error = None
            if execution['exit_code'] == 0:
                try:
                    validate_fold_output(fold_dir, input_hash)
                except ValueError as exc:
                    contract_error = str(exc)
            if execution['exit_code'] != 0 or contract_error:
                error_code = ('OUTPUT_CONTRACT_ERROR' if contract_error and
                              ('Prediction' in contract_error or 'prediction' in contract_error)
                              else 'DATA_CONTRACT_ERROR' if contract_error
                              else 'TIMEOUT' if execution.get('error') == 'EXEC_TIMEOUT'
                              else 'CODE_ERROR')
                message = contract_error or ('Isolated execution exceeded time budget'
                    if error_code == 'TIMEOUT' else execution.get('stderr', 'Execution failed'))
                failure = diagnose(Failure(state['run_id'], 'BACKTEST_CODE',
                    error_code, message, fold), state['failures'])
                state['failures'].append(failure)
                write_state(state_path, state)
                if failure['next_action'] != 'REPAIR_RESEARCH_CODE':
                    state['status'] = 'SAFE_BLOCKED'
                    state['next_action'] = failure['next_action']
                    write_state(state_path, state)
                    return {'status': state['status'], 'failure': failure}
                if state['code_calls'] >= 2:
                    state['status'] = 'SAFE_BLOCKED'
                    write_state(state_path, state)
                    return {'status': state['status'], 'failure': failure}
                repaired = generate_agent43_code(brief, ai_dir,
                    repair_feedback=message[:1500], failed_code=code)
                state['code_calls'] = 2
                state['repair_generation'] = {k: v for k, v in repaired.items() if k != 'artifact'}
                write_state(state_path, state)
                if repaired['status'] != 'REAL_CODE_GENERATION_VERIFIED':
                    state['status'] = 'SAFE_BLOCKED'
                    write_state(state_path, state)
                    return {'status': state['status'], 'repair': state['repair_generation']}
                def verify(path: Path, result: dict) -> bool:
                    if result['exit_code'] != 0:
                        return False
                    try:
                        validate_fold_output(path.parent, input_hash)
                    except ValueError:
                        return False
                    return True
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
            contract = validate_fold_output(fold_dir, input_hash)
            state.setdefault('output_sha256', {})[fold] = contract['output_sha256']
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
        if plan:
            state['hypothesis_assessment'] = assess_hypothesis(
                task_dir, sealed_dir, state['data']['input_sha256'])
        state['data_status'] = 'AVAILABLE_PIT_UNVERIFIED'
        state['next_action'] = next_action(state['data'], verification)
        state['completed_at_utc'] = now()
        write_state(state_path, state)
        if ai_next_action:
            _attach_ai_decision(state, ai_dir, state_path)
        return {'status': state['status'], 'result': verification,
                'code_calls': state['code_calls'], 'ai_response_sha256': ai_hash,
                'code_sha256': state['code_sha256'],
                'next_action': state['next_action'],
                'hypothesis_assessment': state.get('hypothesis_assessment'),
                'ai_next_action': state.get('ai_next_action')}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ai-state-dir', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--ai-next-action', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.ai_state_dir, args.state_dir,
                         ai_next_action=args.ai_next_action), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
