"""Bounded Codex research dispatcher with persistent, fail-closed evidence gates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import validate
from universal_agent.engine import locked_state, write_state
from . import agent41_research
from .exploratory_backtest import HERE, load_indices

TASK_SCHEMA = HERE / 'agent42_task.schema.json'
RESULT_SCHEMA = HERE / 'agent42_codex_result.schema.json'
QUEUE = 'agent42_queue.json'
MEMORY = 'agent42_memory.json'
STATUSES = {'PENDING', 'READY', 'RUNNING', 'COMPLETED', 'FAILED', 'BLOCKED', 'REVIEW_REQUIRED'}
MAX_ATTEMPTS = 2
MAX_SECONDS = 90
MAX_LOG_BYTES = 100_000
KRX_DOC = 'https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES001_S2.cmd?BO_ID=EREKZauXnMmxyIlqzeDN'
KRX_RIGHTS = 'https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA003.jsp'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _code_hashes() -> dict:
    return {name: _sha(HERE / name) for name in
            ('agent42_orchestrator.py', 'agent42_task.schema.json',
             'agent42_codex_result.schema.json', 'agent41_research.py',
             'agent4_market.py', 'exploratory_backtest.py')}


def _source(agent41_dir: Path) -> tuple[dict, dict, dict]:
    original = agent41_research.cycle(agent41_dir)
    if original['status'] not in {'RESEARCH_CYCLE_RECORDED', 'ALREADY_EVALUATED'}:
        raise ValueError('Agent 4.1 evidence is unavailable')
    memory = _load(agent41_dir / agent41_research.STATE)
    pit = _load(agent41_dir / 'pit_research.json')
    forecast = _load(agent41_dir / 'forecast_research.json')
    if memory['artifacts_sha256'] != {
            name: _sha(agent41_dir / name) for name in
            ('pit_research.json', 'forecast_research.json')}:
        raise ValueError('Agent 4.1 artifact integrity mismatch')
    if pit['approved_after'] != 0 or forecast['official_prediction_claim']:
        raise ValueError('Research evidence has an unauthorized claim')
    return memory, pit, forecast


def _score_factors(impact: int, feasibility: int, availability: int,
                   cost: int, duplication: int, independent: int) -> dict:
    values = dict(market_impact=impact, feasibility=feasibility,
                  data_availability=availability, estimated_cost=cost,
                  duplication_penalty=duplication, independent_validation=independent)
    values['score'] = 4 * impact + 3 * feasibility + 2 * availability + 2 * independent - cost - duplication
    return values


def _problems(pit: dict, forecast: dict) -> list[dict]:
    candidate = next(row for row in pit['records']
                     if row['indicator_id'] == 1 and row['indicator_rows'] > 0)
    exp = forecast['experiments'][0]
    return [
        {'problem_id': 'PIT-001', 'problem_type': 'PIT_PUBLICATION_AND_VINTAGE_GAP',
         'evidence': [f"indicator={candidate['indicator_id']} {candidate['source_candidate']}",
                      f"observed_rows={candidate['indicator_rows']}",
                      *candidate['evidence_gap'], KRX_DOC, KRX_RIGHTS],
         'root_cause': None, 'confidence': 'INSUFFICIENT',
         'priority': _score_factors(3, 3, 2, 2, 1, 0),
         'expected_research_value': 'Determine whether SMA 20 has reproducible PIT inputs',
         'required_data': ['KRX dated close values', 'publication clock', 'historical vintages'],
         'estimated_cost': 'one bounded Codex review; no KRX API purchase',
         'research_status': 'READY'},
        {'problem_id': 'FORECAST-CRASH20', 'problem_type': 'BASELINE_UNDERPERFORMANCE_AND_HOLDOUT_GAP',
         'evidence': [f"baseline_brier={exp['baseline_brier']}",
                      f"candidate_brier={exp['validation_metrics']['brier']}",
                      f"validation={forecast['validation']}",
                      '2018-2021 was used in Agent 4.0/4.1; 2022+ was previously inspected'],
         'root_cause': None, 'confidence': 'INSUFFICIENT',
         'priority': _score_factors(3, 2, 2, 2, 2, 0),
         'expected_research_value': 'Identify falsifiable next crash-risk study without reusing holdout',
         'required_data': ['hashed index snapshots', 'unexamined PIT-verified holdout'],
         'estimated_cost': 'one bounded Codex review; no model retraining',
         'research_status': 'READY'}]


def _pit_formula_probe() -> dict:
    """Reproduce one SMA calculation on hashed local closes; never infer PIT from it."""
    rows, provenance = load_indices()
    index = next(i for i, row in enumerate(rows) if row['date'] == '2020-01-02')
    values = [rows[j]['kospi']['close'] for j in range(index - 19, index + 1)]
    if len(values) != 20:
        raise ValueError('SMA warmup invalid')
    ordinary = statistics.fmean(values)
    decimal = float(sum(Decimal(str(value)) for value in values) / Decimal(20))
    if abs(ordinary - decimal) > 1e-9:
        raise ValueError('SMA arithmetic mismatch')
    return {'indicator_id': 1, 'date': rows[index]['date'], 'window_sessions': 20,
            'first_component_date': rows[index - 19]['date'],
            'last_component_date': rows[index]['date'],
            'component_close_sha256': hashlib.sha256(
                json.dumps(values, separators=(',', ':')).encode()).hexdigest(),
            'sma20_float': ordinary, 'sma20_decimal': decimal,
            'formula_check': 'LOCAL_ARITHMETIC_REPRODUCED',
            'independent_source_comparison': 'NOT_VERIFIED',
            'publication_time': 'NOT_VERIFIED', 'historical_vintage': 'NOT_VERIFIED',
            'pit_approved': False, 'source_provenance': provenance}


def _task(problem: dict, state_dir: Path, forecast: dict) -> dict:
    pit = problem['problem_id'].startswith('PIT')
    task_id = 'A-PIT-001' if pit else 'B-CRASH20'
    task_dir = state_dir / 'tasks' / task_id
    return {'task_id': task_id, 'research_objective':
            ('Investigate PIT repair for SMA 20, verify source scope and identify absent row-level evidence'
             if pit else 'Evaluate the existing 20-session crash experiment and design the next falsifiable study'),
            'problem_id': problem['problem_id'], 'evidence': problem['evidence'],
            'hypothesis': ('Official KRX daily close can supply SMA components, but publication/vintage proof may still block PIT'
                           if pit else 'Volatility and drawdown interaction may improve Brier but may be validation-specific'),
            'required_inputs': ['evidence.json', 'task.json'],
            'allowed_paths': [str(task_dir)],
            'forbidden_paths': ['/home/kegor2/MyDream2000', '/home/kegor2/MarketMorningPublisher',
                                '/home/kegor2/market-morning-reports-main', '/home/kegor2/.ssh'],
            'allowed_operations': ['read staged evidence', 'reason over evidence',
                                   'return JSON result; no file edits or shell commands'],
            'validation_method': ('Compare KRX documentation to staged inventory; require dated release and revision evidence'
                                  if pit else 'Recompute Brier delta from staged numbers and check holdout/PIT gates'),
            'success_criteria': ('PIT can be promoted only with raw historical values, publication clock, revision history and independent formula check'
                                 if pit else 'Evidence supports a new hypothesis with an unexamined PIT-verified holdout'),
            'failure_criteria': ('Any absent historical publication/vintage or formula comparison blocks PIT'
                                 if pit else 'Reused validation, missing PIT evidence or no independent holdout blocks adoption'),
            'rollback_method': 'Read-only Codex task; discard task output on validation failure and preserve prior memory',
            'expected_outputs': ['answer.json', 'stdout.log', 'stderr.log'],
            'generation_method': 'DETERMINISTIC_RULE_TEMPLATE'}


def _markdown(task: dict) -> str:
    return '# ' + task['task_id'] + '\n\n' + '\n'.join(
        f"## {key}\n\n{json.dumps(value, ensure_ascii=False, indent=2)}\n"
        for key, value in task.items() if key != 'task_id')


def prepare(state_dir: Path, agent41_dir: Path) -> dict:
    state_dir = state_dir.resolve()
    agent41_dir = agent41_dir.resolve()
    if state_dir == HERE or HERE in state_dir.parents:
        raise ValueError('State must be outside tracked research source')
    source_memory, pit, forecast = _source(agent41_dir)
    with locked_state(state_dir):
        queue_path = state_dir / QUEUE
        if queue_path.exists():
            queue = _load(queue_path)
            _integrity(queue, state_dir, agent41_dir)
            return {'status': 'ALREADY_PREPARED', 'tasks': queue['order']}
        problems = _problems(pit, forecast)
        tasks = {}
        for problem in sorted(problems, key=lambda p: (-p['priority']['score'], p['problem_id'])):
            task = _task(problem, state_dir, forecast)
            validate(task, _load(TASK_SCHEMA))
            task_dir = state_dir / 'tasks' / task['task_id']
            task_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            if task['problem_id'] == 'PIT-001':
                evidence = {'problem': problem, 'indicator': pit['records'][0],
                    'local_formula_probe': _pit_formula_probe(),
                    'krx_documentation': {'url': KRX_DOC, 'scope': 'KOSPI index daily data since 2010-01-04',
                        'publication_clock': 'NOT_DOCUMENTED', 'revision_vintages': 'NOT_DOCUMENTED',
                        'raw_values_acquired': False},
                    'usage_rights': {'url': KRX_RIGHTS, 'review_required': True}}
            else:
                evidence = {'problem': problem, 'hypotheses': forecast['hypotheses'],
                    'experiment': forecast['experiments'][0],
                    'baseline_metrics': forecast['baseline_metrics'],
                    'train': forecast['train'], 'validation': forecast['validation'],
                    'final_holdout': forecast['final_holdout'],
                    'pit_verified': False}
            write_state(task_dir / 'evidence.json', evidence)
            write_state(task_dir / 'task.json', task)
            (task_dir / 'task.md').write_text(_markdown(task), encoding='utf-8')
            tasks[task['task_id']] = {'problem_id': task['problem_id'], 'status': 'READY',
                'attempts': 0, 'task_sha256': _sha(task_dir / 'task.json'),
                'evidence_sha256': _sha(task_dir / 'evidence.json'),
                'selected_priority': problem['priority'], 'last_error': None}
        queue = {'schema_version': 1, 'created_at_utc': _now(),
            'source_memory_sha256': _sha(agent41_dir / agent41_research.STATE),
            'source_artifacts_sha256': source_memory['artifacts_sha256'],
            'code_sha256': _code_hashes(), 'schema_sha256': _sha(TASK_SCHEMA),
            'order': list(tasks), 'tasks': tasks, 'checkpoint_id': 0,
            'dispatch_mode': 'CODEX_CLI_READ_ONLY', 'max_attempts': MAX_ATTEMPTS,
            'max_seconds_per_task': MAX_SECONDS}
        write_state(queue_path, queue)
        return {'status': 'PREPARED', 'tasks': queue['order'],
                'priorities': {key: value['selected_priority']['score'] for key, value in tasks.items()}}


def _integrity(queue: dict, state_dir: Path, agent41_dir: Path) -> None:
    if queue['code_sha256'] != _code_hashes() or queue['schema_sha256'] != _sha(TASK_SCHEMA):
        raise ValueError('Agent 4.2 code/schema integrity mismatch')
    if queue['source_memory_sha256'] != _sha(agent41_dir / agent41_research.STATE):
        raise ValueError('Agent 4.1 memory changed')
    for task_id, record in queue['tasks'].items():
        task_dir = state_dir / 'tasks' / task_id
        if (record['task_sha256'] != _sha(task_dir / 'task.json') or
                record['evidence_sha256'] != _sha(task_dir / 'evidence.json')):
            raise ValueError('Task input integrity mismatch')
        validate(_load(task_dir / 'task.json'), _load(TASK_SCHEMA))
        if record.get('result_sha256') and record['result_sha256'] != _sha(task_dir / 'answer.json'):
            raise ValueError('Task output integrity mismatch')


def _prompt(task: dict, evidence: dict) -> str:
    return ('You are conducting a bounded research review. Work only from the staged JSON below. '
            'Do not use shell tools, access other files, fetch websites, or modify files. '
            'Return a JSON object matching the output schema. '
            'Never claim PIT approval, independent validation, or production readiness from these inputs. '
            'A source URL in the input establishes documentation scope only; it does not prove historical publication time. '
            'If evidence is missing, set root_cause to null and confidence to INSUFFICIENT. '
            'For the forecast task, calculate candidate Brier minus baseline Brier and describe the exact limitation. '
            'Use decision EVIDENCE_BLOCKED for PIT and EXPLORATORY_ONLY or REJECTED for forecast. '
            'Make next_action concrete and bounded.\nTASK:\n' +
            json.dumps(task, ensure_ascii=False) + '\nEVIDENCE:\n' +
            json.dumps(evidence, ensure_ascii=False))


def _dispatch(task_dir: Path, timeout: int) -> tuple[int | None, str | None]:
    codex = shutil.which('codex')
    if not codex:
        return None, 'MANUAL_DISPATCH_REQUIRED: Codex CLI missing'
    command = [codex, '--ask-for-approval', 'never', 'exec', '--sandbox', 'read-only',
               '--skip-git-repo-check', '--ephemeral', '--output-schema', str(RESULT_SCHEMA),
               '--output-last-message', str(task_dir / 'answer.json'), '-']
    task = _load(task_dir / 'task.json')
    evidence = _load(task_dir / 'evidence.json')
    env = {key: os.environ[key] for key in ('HOME', 'PATH', 'USER', 'LANG', 'CODEX_HOME')
           if key in os.environ}
    try:
        result = subprocess.run(command, cwd=task_dir, input=_prompt(task, evidence),
                                text=True, capture_output=True, timeout=timeout,
                                check=False, env=env)
        (task_dir / 'stdout.log').write_text(result.stdout[:MAX_LOG_BYTES])
        (task_dir / 'stderr.log').write_text(result.stderr[:MAX_LOG_BYTES])
        return result.returncode, None
    except subprocess.TimeoutExpired as exc:
        (task_dir / 'stdout.log').write_bytes((exc.stdout or b'')[:MAX_LOG_BYTES])
        (task_dir / 'stderr.log').write_bytes((exc.stderr or b'')[:MAX_LOG_BYTES])
        return None, 'CODEX_TIMEOUT'
    except OSError as exc:
        return None, f'CODEX_LAUNCH_FAILED:{type(exc).__name__}'


def _validate_result(task_id: str, task_dir: Path, result: dict) -> dict:
    validate(result, _load(RESULT_SCHEMA))
    if result['task_id'] != task_id:
        raise ValueError('Codex task ID mismatch')
    if task_id == 'A-PIT-001':
        if result['decision'] != 'EVIDENCE_BLOCKED':
            raise ValueError('PIT promotion without row-level evidence')
        return {'status': 'BLOCKED', 'reason': 'PIT_RELEASE_VINTAGE_AND_VALUES_MISSING',
                'independent_validation': 'NOT_VERIFIED'}
    evidence = _load(task_dir / 'evidence.json')
    exp = evidence['experiment']
    delta = exp['validation_metrics']['brier'] - exp['baseline_brier']
    if not -1 < delta < 1 or result['decision'] not in {'EXPLORATORY_ONLY', 'REJECTED'}:
        raise ValueError('Forecast validation claim invalid')
    return {'status': 'COMPLETED', 'reason': 'EXPLORATORY_ONLY_NO_INDEPENDENT_HOLDOUT',
            'independent_validation': 'BLOCKED', 'verified_brier_delta': delta}


def _next(queue: dict) -> dict:
    statuses = {key: value['status'] for key, value in queue['tasks'].items()}
    if any(value in {'READY', 'PENDING', 'RUNNING', 'FAILED'} for value in statuses.values()):
        return {'task_id': next(key for key in queue['order']
                                if statuses[key] in {'READY', 'PENDING', 'RUNNING', 'FAILED'}),
                'status': 'READY_OR_RETRY'}
    if statuses.get('A-PIT-001') == 'BLOCKED':
        return {'task_id': 'PIT-001-OFFICIAL-RELEASE', 'status': 'BLOCKED',
                'required_evidence': 'official timestamp/vintage and licensed historical values'}
    return {'task_id': 'FORECAST-INDEPENDENT-HOLDOUT', 'status': 'BLOCKED',
            'required_evidence': 'new unexamined PIT-verified observations'}


def _memory(queue: dict, state_dir: Path, agent41_dir: Path) -> dict:
    items = []
    for task_id in queue['order']:
        record = queue['tasks'][task_id]
        task_dir = state_dir / 'tasks' / task_id
        result = _load(task_dir / 'answer.json') if record.get('result_sha256') else None
        items.append({'research_id': f'agent42-{task_id}', 'task_id': task_id,
            'hypothesis_id': 'H-PIT-SMA20' if task_id.startswith('A-') else 'H-CRASH-VOL-DD',
            'code_version': queue['code_sha256'],
            'data_version': queue['source_artifacts_sha256'],
            'input_hash': record['evidence_sha256'],
            'output_hash': record.get('result_sha256'),
            'experiment_result': result['experiment_result'] if result else None,
            'validation_result': record.get('validation'),
            'decision': record['status'], 'failure_reason': record['last_error'],
            'next_action': result['next_action'] if result else None,
            'attempts': record['attempts'], 'codex_exit_code': record.get('codex_exit_code')})
    return {'schema_version': 1, 'updated_at_utc': _now(),
            'checkpoint_id': queue['checkpoint_id'], 'dispatch_mode': queue['dispatch_mode'],
            'tasks': items, 'next_research': _next(queue),
            'llm_runtime': 'CODEX_CLI' if any(x['output_hash'] for x in items)
                           else 'NOT_VERIFIED',
            'official_prediction_claim': False, 'pit_approved': 0}


def run(state_dir: Path, agent41_dir: Path, max_tasks: int = 2,
        timeout: int = MAX_SECONDS) -> dict:
    if not 1 <= max_tasks <= 2 or not 1 <= timeout <= MAX_SECONDS:
        raise ValueError('Resource budget exceeded')
    prepare(state_dir, agent41_dir)
    state_dir, agent41_dir = state_dir.resolve(), agent41_dir.resolve()
    attempted = 0
    for task_id in _load(state_dir / QUEUE)['order']:
        with locked_state(state_dir):
            queue = _load(state_dir / QUEUE)
            _integrity(queue, state_dir, agent41_dir)
            if (state_dir / 'STOP').exists():
                return {'status': 'STOPPED', 'checkpoint_id': queue['checkpoint_id']}
            record = queue['tasks'][task_id]
            if record['status'] in {'COMPLETED', 'BLOCKED', 'REVIEW_REQUIRED'}:
                continue
            if record['status'] == 'RUNNING':
                started = datetime.fromisoformat(record['started_at_utc'])
                if (datetime.now(timezone.utc) - started).total_seconds() <= 2 * MAX_SECONDS:
                    return {'status': 'RUNNING', 'task_id': task_id}
                record['status'] = 'FAILED'
                record['last_error'] = 'INTERRUPTED_RETRY'
            if record['attempts'] >= MAX_ATTEMPTS:
                record['status'] = 'BLOCKED'
                record['last_error'] = 'RETRY_BUDGET_EXHAUSTED'
                write_state(state_dir / QUEUE, queue)
                continue
            record['attempts'] += 1
            attempted += 1
            record['status'] = 'RUNNING'
            record['started_at_utc'] = _now()
            write_state(state_dir / QUEUE, queue)
        task_dir = state_dir / 'tasks' / task_id
        code_before = _code_hashes()
        exit_code, dispatch_error = _dispatch(task_dir, timeout)
        with locked_state(state_dir):
            queue = _load(state_dir / QUEUE)
            record = queue['tasks'][task_id]
            record['codex_exit_code'] = exit_code
            record['last_error'] = dispatch_error
            try:
                if code_before != _code_hashes() or queue['code_sha256'] != _code_hashes():
                    raise ValueError('Research code changed during Codex execution')
                if dispatch_error or exit_code != 0:
                    raise ValueError(dispatch_error or f'CODEX_EXIT_{exit_code}')
                result = _load(task_dir / 'answer.json')
                verdict = _validate_result(task_id, task_dir, result)
                record['status'] = verdict['status']
                record['validation'] = verdict
                record['result_sha256'] = _sha(task_dir / 'answer.json')
                record['stdout_sha256'] = _sha(task_dir / 'stdout.log')
                record['stderr_sha256'] = _sha(task_dir / 'stderr.log')
                record['last_error'] = None
                queue['checkpoint_id'] += 1
            except (ValueError, OSError, KeyError) as exc:
                record['status'] = ('REVIEW_REQUIRED' if 'Research code changed' in str(exc)
                                    else 'BLOCKED' if record['attempts'] >= MAX_ATTEMPTS
                                    else 'FAILED')
                record['last_error'] = str(exc)[:500]
            write_state(state_dir / QUEUE, queue)
            write_state(state_dir / MEMORY, _memory(queue, state_dir, agent41_dir))
        if attempted >= max_tasks:
            break
    queue = _load(state_dir / QUEUE)
    return {'status': 'CYCLE_CHECKPOINTED', 'checkpoint_id': queue['checkpoint_id'],
            'tasks': {key: value['status'] for key, value in queue['tasks'].items()},
            'next_research': _next(queue)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--agent41-state', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--max-tasks', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=MAX_SECONDS)
    args = parser.parse_args()
    result = (prepare(args.state_dir, args.agent41_state) if args.prepare_only else
              run(args.state_dir, args.agent41_state, args.max_tasks, args.timeout))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
