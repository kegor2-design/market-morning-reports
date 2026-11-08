"""Isolated, bounded Codex code generation and exploratory Regime190 research."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import os
import resource
import signal
import shutil
import statistics
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from jsonschema import validate
from universal_agent.engine import locked_state, write_state
from .agent41_research import _observations
from .agent4_market import _score
from .eligibility_manifest import build_manifest
from .exploratory_backtest import HERE, load_indices

SCHEMA = HERE / 'agent43_hypothesis.schema.json'
QUEUE = 'agent43_queue.json'
MEMORY = 'agent43_memory.json'
TASKS = ('PIT-EMA20', 'FORECAST-CRASH20', 'FORECAST-RECOVERY10')
MAX_CODEX_CALLS = 3
MAX_CODEX_SECONDS = 90
MAX_EXEC_SECONDS = 15
MAX_CYCLES = 3
SOURCE_HASH_FILES = ('inventory_190.csv', 'indicator_spec.csv',
                     'pit_readiness_matrix_20261031.csv', 'data_coverage.csv')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _version() -> dict:
    return {name: _sha(HERE / name) for name in
            ('agent43_engine.py', 'agent43_hypothesis.schema.json',
             'agent41_research.py', 'agent42_orchestrator.py', 'agent4_market.py')}


def _data_version() -> dict:
    source = HERE.parent / 'daily-index-validation-20261021'
    return {name: _sha(path) for name, path in
            [(name, HERE / name) for name in SOURCE_HASH_FILES] +
            [(name, source / name) for name in
             ('naver_source_manifest.json', 'naver_kospi_daily.csv', 'naver_kosdaq_daily.csv')]}


def _rank_pit() -> list[dict]:
    manifest = build_manifest()
    if manifest['indicator_count'] != 190 or manifest['pit_eligible_count'] != 0:
        raise ValueError('PIT eligibility changed; review before research')
    ranking = []
    for row in manifest['records']:
        # ID 1 was investigated by Agent 4.2; ID 2 has a bounded EMA template.
        score = (40 if row['indicator_id'] == 2 else 0) + (
            12 if row['actual_indicator_series_rows'] else 0) + (
            5 if row['component_or_summary_rows'] else 0) - (
            20 if row['indicator_id'] == 1 else 0)
        ranking.append({'indicator_id': row['indicator_id'], 'score': score,
                        'pit_status': row['pit_status'],
                        'observed_rows': row['actual_indicator_series_rows'],
                        'source': row['source'], 'blocking_reason': row['blocking_reason']})
    ranking.sort(key=lambda x: (-x['score'], x['indicator_id']))
    if ranking[0]['indicator_id'] != 2:
        raise ValueError('No supported PIT candidate selected')
    return ranking


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _stage_pit(task_dir: Path) -> dict:
    rows, provenance = load_indices('1996-01-01', skip_invalid_pre2010=True)
    selected = [row for row in rows if '2019-10-01' <= row['date'] <= '2020-01-02'][-60:]
    if len(selected) != 60:
        raise ValueError('PIT calculation sample unavailable')
    _write_csv(task_dir / 'data.csv', ['date', 'close'],
               [{'date': row['date'], 'close': row['kospi']['close']} for row in selected])
    return {'kind': 'pit', 'indicator_id': 2, 'input_rows': 60,
            'first_date': selected[0]['date'], 'last_date': selected[-1]['date'],
            'source_provenance': provenance, 'pit_verified': False,
            'independent_source': 'NOT_AVAILABLE',
            'publication_vintage': 'NOT_AVAILABLE'}


def _stage_market(task_dir: Path, sealed_dir: Path, target: str, horizon: int,
                  observations: list[dict]) -> dict:
    fields = ['date', 'split', 'target', 'momentum5', 'momentum20',
              'volatility20', 'drawdown60', 'relative_kosdaq20']
    fold_specs = [('fold1', '2005-01-01', '2011-12-31', '2012-01-01', '2014-12-31'),
                  ('fold2', '2005-01-01', '2014-12-31', '2015-01-01', '2017-12-31')]
    summary = []
    for fold_id, train_start, train_end, valid_start, valid_end in fold_specs:
        train = [r for r in observations if train_start <= r['date'] <= train_end][:-20]
        valid = [r for r in observations if valid_start <= r['date'] <= valid_end][:-20]
        if len(train) < 500 or len(valid) < 200:
            raise ValueError('Insufficient chronological fold')
        fold_dir = task_dir / fold_id
        fold_dir.mkdir(mode=0o700)
        staged = []
        truth = {}
        for split, group in [('train', train), ('validation', valid)]:
            for row in group:
                feature = row['feature']
                label = int(row['labels'][str(horizon)][target])
                staged.append({'date': row['date'], 'split': split,
                    'target': label if split == 'train' else '',
                    **{name: feature[name] for name in fields[3:]}})
                if split == 'validation':
                    truth[row['date']] = label
        _write_csv(fold_dir / 'data.csv', fields, staged)
        positive_days = sum(truth.values())
        write_state(sealed_dir / f'{task_dir.name}_{fold_id}.json', truth)
        summary.append({'fold': fold_id, 'train': [train[0]['date'], train[-1]['date'], len(train)],
                        'validation': [valid[0]['date'], valid[-1]['date'], len(valid)],
                        'positive_days': positive_days,
                        'validation_labels_hidden_from_codex': True})
    return {'kind': 'market', 'target': target, 'horizon': horizon,
            'folds': summary, 'official_prediction_claim': False,
            'pit_verified': False, 'independent_holdout': 'NOT_AVAILABLE_PRIOR_PERIODS_INSPECTED',
            'validation_use': 'EXPLORATORY_ONLY'}


def _problem(task_id: str, ranking: list[dict], staged: dict) -> dict:
    if task_id == 'PIT-EMA20':
        return {'problem_id': 'PIT-002', 'problem_type': 'FORMULA_AND_VINTAGE_GAP',
                'evidence': [ranking[0]['blocking_reason'],
                             'Agent 4.2 SMA study did not resolve release/vintage evidence'],
                'root_cause': None, 'confidence': 'INSUFFICIENT', 'priority': 30,
                'expected_research_value': 'Test EMA seed convention with actual local closes',
                'required_data': ['KOSPI close snapshot', 'official release/vintage evidence'],
                'estimated_cost': 'one Codex call and one isolated calculation'}
    return {'problem_id': task_id, 'problem_type': 'UNVALIDATED_FORECAST_HYPOTHESIS',
            'evidence': [f"target={staged['target']} horizon={staged['horizon']}",
                         'Agent 4.1 crash Brier did not establish independent gain',
                         'Only pre-2018 exploratory folds are supplied'],
            'root_cause': None, 'confidence': 'INSUFFICIENT',
            'priority': 20 if task_id == 'FORECAST-CRASH20' else 18,
            'expected_research_value': 'Test a new causal feature hypothesis in two walk-forward folds',
            'required_data': ['hashed KOSPI/KOSDAQ close snapshots',
                              'unexamined PIT-verified holdout for adoption'],
            'estimated_cost': 'one Codex call and two isolated fold runs'}


def prepare(state_dir: Path) -> dict:
    state_dir = state_dir.resolve()
    if HERE in state_dir.parents or state_dir == HERE:
        raise ValueError('State must be outside tracked source')
    with locked_state(state_dir):
        path = state_dir / QUEUE
        if path.exists():
            queue = _load(path)
            _integrity(state_dir, queue)
            return {'status': 'ALREADY_PREPARED', 'order': queue['order']}
        ranking = _rank_pit()
        write_state(state_dir / 'pit_rank_190.json', {'ranking': ranking,
                    'pit_verified': 0, 'classification_counts':
                    {'PIT_BLOCKED': 71, 'CALCULATION_PENDING': 21, 'SOURCE_MISSING': 98}})
        sealed = state_dir / 'sealed'
        sealed.mkdir(mode=0o700)
        observations, _ = _observations()
        tasks = {}
        for task_id in TASKS:
            task_dir = state_dir / 'tasks' / task_id
            task_dir.mkdir(parents=True, mode=0o700)
            staged = (_stage_pit(task_dir) if task_id == 'PIT-EMA20' else
                      _stage_market(task_dir, sealed,
                          'crash' if task_id == 'FORECAST-CRASH20' else 'recovery',
                          20 if task_id == 'FORECAST-CRASH20' else 10, observations))
            problem = _problem(task_id, ranking, staged)
            write_state(task_dir / 'brief.json', {'task_id': task_id, 'problem': problem,
                'staged': staged, 'generation_method': 'PENDING_CODEX',
                'allowed_code_file': 'experiment.py',
                'forbidden_paths': ['/home/kegor2/MyDream2000',
                                    '/home/kegor2/MarketMorningPublisher', '/home/kegor2/.ssh']})
            files = {str(p.relative_to(task_dir)): _sha(p) for p in task_dir.rglob('*') if p.is_file()}
            tasks[task_id] = {'status': 'READY', 'attempts': 0,
                'problem_id': problem['problem_id'], 'priority': problem['priority'],
                'input_hashes': files, 'failure_reason': None}
        queue = {'schema_version': 1, 'created_at_utc': _now(),
                 'order': sorted(TASKS, key=lambda x: -tasks[x]['priority']),
                 'tasks': tasks, 'checkpoint_id': 0, 'codex_calls': 0,
                 'code_version': _version(), 'data_version': _data_version(),
                 'max_codex_calls': MAX_CODEX_CALLS, 'max_cycles': MAX_CYCLES}
        write_state(path, queue)
        return {'status': 'PREPARED', 'order': queue['order'],
                'pit_top_indicator': ranking[0]['indicator_id']}


def _integrity(state_dir: Path, queue: dict) -> None:
    if queue['code_version'] != _version() or queue['data_version'] != _data_version():
        raise ValueError('Research code/data changed; review required')
    for task_id, item in queue['tasks'].items():
        task_dir = state_dir / 'tasks' / task_id
        for name, digest in item['input_hashes'].items():
            if _sha(task_dir / name) != digest:
                raise ValueError('Staged input integrity mismatch')
        if item.get('output_hash') and _sha(task_dir / 'result.json') != item['output_hash']:
            raise ValueError('Research output integrity mismatch')


def adopt_code_revision(state_dir: Path) -> dict:
    """Record a reviewed engine-only revision before replaying generated artifacts."""
    state_dir = state_dir.resolve()
    with locked_state(state_dir):
        queue = _load(state_dir / QUEUE)
        current = _version()
        old = queue['code_version']
        changed = [name for name in current if current[name] != old.get(name)]
        if changed != ['agent43_engine.py'] or queue['data_version'] != _data_version():
            raise ValueError('Only an engine-only revision with identical data can be adopted')
        for task_id, item in queue['tasks'].items():
            task_dir = state_dir / 'tasks' / task_id
            for name, digest in item['input_hashes'].items():
                if _sha(task_dir / name) != digest:
                    raise ValueError('Staged input integrity mismatch')
            if item.get('output_hash') and _sha(task_dir / 'result.json') != item['output_hash']:
                raise ValueError('Research output integrity mismatch')
        audit = {'at_utc': _now(), 'old_code_version': old,
                 'new_code_version': current, 'changed_files': changed,
                 'reason': 'Resume Codex artifacts rejected by the previous code gate'}
        write_state(state_dir / f'code_revision_{queue["checkpoint_id"]}.json', audit)
        queue['code_version'] = current
        write_state(state_dir / QUEUE, queue)
        return audit


def _prompt(brief: dict) -> str:
    task = brief['task_id']
    common = ('You are a research engineer. Generate a genuinely new, falsifiable hypothesis '
              'from the evidence below and write a complete Python 3 standard-library script '
              'as the JSON field code. Return JSON matching the schema. '
              'Do not read files or use tools. Do not claim PIT approval or independent validation. '
              'Code may import only csv, json, math, statistics, collections; '
              'may read only data.csv and write only result.json or predictions.csv. '
              'Do not use OS, network, subprocess, eval, exec, or dynamic imports. '
              'Include basic assertions in code. Keep code below 100 lines. '
              'Propose one specific hypothesis distinct from prior volatility x drawdown bins. ')
    if brief.get('input_hypothesis'):
        common = ('You are a research engineer. Implement the supplied AI hypothesis in '
                  'a complete Python 3 standard-library script as the JSON field code. '
                  'Keep the hypothesis and rejection condition faithful to the supplied input. '
                  'Return JSON matching the schema. Do not read files or use tools. '
                  'Do not claim PIT approval or independent validation. '
                  'Code may import only csv, json, math, statistics, collections; '
                  'may read only data.csv and write only result.json or predictions.csv. '
                  'Do not use OS, network, subprocess, eval, exec, or dynamic imports. '
                  'Include basic assertions in code. Keep code below 100 lines. ')
    if task == 'PIT-EMA20':
        details = ('The staged data.csv has exactly 60 ordered date,close rows. '
                   'Write code computing EMA20 twice: seed from first close and seed from '
                   'the first 20 closes arithmetic mean. Alpha=2/21. Return result.json '
                   'with keys rows, last_date, ema_first_close, ema_sma_seed, seed_gap. '
                   'Hypothesis should address EMA warmup convention ambiguity, while stating '
                   'that official release/vintage evidence remains absent. ')
    else:
        details = ('Each fold directory has data.csv with date,split,target,momentum5,'
                   'momentum20,volatility20,drawdown60,relative_kosdaq20. '
                   'Training rows have numeric target 0/1. Validation targets are blank. '
                   'The same script will run separately inside each fold. '
                   'Fit a causal, simple bin or smoothed frequency model using only train rows. '
                   'Write predictions.csv with exactly date,probability columns for every '
                   'validation row, in date order. Probabilities must be finite in [0,1]. '
                   'Do not inspect validation labels, fit on validation rows, or use future data. '
                   f"Target is {brief['staged']['target']} within {brief['staged']['horizon']} sessions. ")
    return common + details + '\nBRIEF:\n' + json.dumps(brief, ensure_ascii=False)


def _codex(task_dir: Path) -> tuple[int | None, str | None]:
    codex = shutil.which('codex')
    if not codex:
        return None, 'MANUAL_DISPATCH_REQUIRED'
    command = [codex, '--ask-for-approval', 'never', 'exec', '--sandbox', 'read-only',
               '--skip-git-repo-check', '--ephemeral', '--output-schema', str(SCHEMA),
               '--output-last-message', str(task_dir / 'hypothesis.json'), '-']
    env = {key: os.environ[key] for key in ('HOME', 'PATH', 'USER', 'LANG', 'CODEX_HOME')
           if key in os.environ}
    try:
        result = subprocess.run(command, cwd=task_dir, input=_prompt(_load(task_dir / 'brief.json')),
                                text=True, capture_output=True, timeout=MAX_CODEX_SECONDS,
                                env=env, check=False)
    except subprocess.TimeoutExpired:
        return None, 'CODEX_TIMEOUT'
    (task_dir / 'codex_stdout.log').write_text(result.stdout[:100_000])
    (task_dir / 'codex_stderr.log').write_text(result.stderr[:100_000])
    return result.returncode, None if result.returncode == 0 else f'CODEX_EXIT_{result.returncode}'


def _check_code(source: str) -> None:
    if not 100 <= len(source) <= 20_000:
        raise ValueError('Generated code size invalid')
    tree = ast.parse(source)
    allowed = {'csv', 'json', 'math', 'statistics', 'collections'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise ValueError('Disallowed Python syntax')
        if isinstance(node, ast.ImportFrom) and (
                node.module not in allowed or node.level != 0 or
                any(alias.name == '*' or alias.name.startswith('__') for alias in node.names)):
            raise ValueError('Disallowed import from module')
        if isinstance(node, ast.Import) and any(alias.name not in allowed for alias in node.names):
            raise ValueError('Disallowed import')
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {
                'eval', 'exec', 'compile', '__import__', 'input'}:
            raise ValueError('Disallowed dynamic execution')
        if isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            raise ValueError('Disallowed dunder access')


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (MAX_EXEC_SECONDS, MAX_EXEC_SECONDS + 1))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _isolated_python(work_dir: Path) -> dict:
    work_dir = work_dir.resolve(strict=True)
    if not work_dir.is_dir():
        raise ValueError('Isolated work directory must exist')
    script = work_dir / 'experiment.py'
    data = work_dir / 'data.csv'
    if script.is_symlink() or data.is_symlink() or not script.is_file():
        raise ValueError('Unsafe isolated source or input path')
    # Apply the process limit after Bubblewrap creates its namespaces. Applying
    # RLIMIT_NPROC to bwrap itself can prevent namespace creation on this host.
    launcher = ('import resource,runpy; '
                'resource.setrlimit(resource.RLIMIT_NPROC,(32,32)); '
                'runpy.run_path("experiment.py",run_name="__main__")')
    command = ['bwrap', '--die-with-parent', '--unshare-all',
               '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib',
               '--ro-bind', '/lib64', '/lib64', '--ro-bind', '/bin', '/bin',
               '--dev-bind', '/dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
               '--bind', str(work_dir), '/work',
               '--ro-bind', str(script), '/work/experiment.py',
               *(['--ro-bind', str(data), '/work/data.csv'] if data.is_file() else []),
               '--chdir', '/work',
               '--setenv', 'HOME', '/work', '--setenv', 'PATH', '/usr/bin:/bin',
               '--', '/usr/bin/python3', '-I', '-B', '-c', launcher]
    try:
        result = subprocess.run(command, cwd=work_dir, capture_output=True, text=True,
                                timeout=MAX_EXEC_SECONDS + 5, check=False,
                                env={'PATH': '/usr/bin:/bin'}, preexec_fn=_limits)
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'error': 'EXEC_TIMEOUT'}
    if result.returncode in {-signal.SIGXCPU, 128 + signal.SIGXCPU}:
        return {'exit_code': None, 'error': 'EXEC_TIMEOUT',
                'signal': signal.SIGXCPU,
                'sandbox': 'BWRAP_UNSHARE_ALL_NO_HOME_NO_NETWORK',
                'cpu_limit_seconds': MAX_EXEC_SECONDS, 'memory_limit_mb': 256,
                'process_limit': 32}
    if result.returncode in {-signal.SIGKILL, 128 + signal.SIGKILL}:
        return {'exit_code': None, 'error': 'EXEC_TERMINATED',
                'signal': signal.SIGKILL,
                'sandbox': 'BWRAP_UNSHARE_ALL_NO_HOME_NO_NETWORK',
                'cpu_limit_seconds': MAX_EXEC_SECONDS, 'memory_limit_mb': 256,
                'process_limit': 32}
    return {'exit_code': result.returncode,
            'stdout': result.stdout[:10_000], 'stderr': result.stderr[:10_000],
            'sandbox': 'BWRAP_UNSHARE_ALL_NO_HOME_NO_NETWORK',
            'cpu_limit_seconds': MAX_EXEC_SECONDS, 'memory_limit_mb': 256,
            'process_limit': 32}


def _verify_pit(task_dir: Path) -> dict:
    data = _load(task_dir / 'result.json')
    with (task_dir / 'data.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    values = [Decimal(row['close']) for row in rows]
    alpha = Decimal(2) / Decimal(21)
    first = values[0]
    for value in values[1:]:
        first = alpha * value + (1 - alpha) * first
    seeded = sum(values[:20]) / Decimal(20)
    for value in values[20:]:
        seeded = alpha * value + (1 - alpha) * seeded
    if (data['rows'] != 60 or data['last_date'] != rows[-1]['date']
            or abs(float(first) - float(data['ema_first_close'])) > 1e-6
            or abs(float(seeded) - float(data['ema_sma_seed'])) > 1e-6
            or abs(abs(float(first - seeded)) - abs(float(data['seed_gap']))) > 1e-6):
        raise ValueError('PIT arithmetic verification failed')
    return {'status': 'BLOCKED_EVIDENCE', 'experiment': data,
            'independent_formula_check': 'PASSED_SAME_SOURCE',
            'pit_verified': False, 'independent_source': 'NOT_AVAILABLE',
            'release_vintage': 'NOT_AVAILABLE'}


def _baseline(train: list[dict], valid: list[dict]) -> list[float]:
    prior = sum(int(row['target']) for row in train) / len(train)
    groups = {}
    for row in train:
        key = float(row['drawdown60']) <= -.10
        hits, count = groups.get(key, (0, 0))
        groups[key] = hits + int(row['target']), count + 1
    return [(groups.get(float(row['drawdown60']) <= -.10, (0, 0))[0] + 20 * prior) /
            (groups.get(float(row['drawdown60']) <= -.10, (0, 0))[1] + 20)
            for row in valid]


def _verify_market(task_dir: Path, sealed_dir: Path, target: str) -> dict:
    folds = []
    threshold = .1 if target == 'crash' else .05
    for fold_id in ('fold1', 'fold2'):
        fold_dir = task_dir / fold_id
        with (fold_dir / 'data.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        train = [row for row in rows if row['split'] == 'train']
        valid = [row for row in rows if row['split'] == 'validation']
        with (fold_dir / 'predictions.csv').open(newline='') as stream:
            predictions = list(csv.DictReader(stream))
        truth = _load(sealed_dir / f'{task_dir.name}_{fold_id}.json')
        dates = [row['date'] for row in valid]
        if (len(predictions) != len(valid) or len(dates) != len(set(dates))
                or [row['date'] for row in predictions] != dates
                or any(row['target'] for row in valid)):
            raise ValueError('Prediction alignment or label sealing failed')
        labels = [bool(truth[date]) for date in dates]
        candidate = [float(row['probability']) for row in predictions]
        baseline = _baseline(train, valid)
        candidate_metrics = _score(labels, candidate, threshold)
        baseline_metrics = _score(labels, baseline, threshold)
        false_alarm = (candidate_metrics['fp'] /
                       (candidate_metrics['fp'] + candidate_metrics['tn'])
                       if candidate_metrics['fp'] + candidate_metrics['tn'] else None)
        folds.append({'fold': fold_id, 'first': dates[0], 'last': dates[-1],
                      'candidate': {key: candidate_metrics[key] for key in
                                    ('n', 'positive_days', 'precision', 'recall',
                                     'pr_auc_average_precision', 'brier',
                                     'calibration_ece_five_bins')},
                      'baseline_brier': baseline_metrics['brier'],
                      'brier_delta': candidate_metrics['brier'] - baseline_metrics['brier'],
                      'false_alarm_rate': false_alarm})
    rejected = all(fold['brier_delta'] >= 0 for fold in folds)
    return {'status': 'EXPLORATORY_ONLY', 'folds': folds,
            'hypothesis_test': 'REJECTED_BRIER_WORSE_IN_BOTH_FOLDS' if rejected
                               else 'MIXED_OR_UNCONFIRMED',
            'walk_forward': True, 'embargo_sessions': 20,
            'validation_periods_previously_inspected': True,
            'pit_verified': False, 'independent_holdout': 'NOT_AVAILABLE',
            'transition_detection_delay': 'NOT_VERIFIED_NO_INDEPENDENT_TRUTH'}


def _next(queue: dict) -> dict:
    for task_id in queue['order']:
        item = queue['tasks'][task_id]
        if item['status'] in {'READY', 'RUNNING'} or (
                item['status'] == 'FAILED' and item['attempts'] < 2 and
                (queue['codex_calls'] < MAX_CODEX_CALLS or item.get('codex_exit_code') == 0)):
            return {'task_id': task_id, 'status': 'READY_OR_RETRY'}
    return {'task_id': 'ACQUIRE_PIT_AND_UNEXAMINED_HOLDOUT', 'status': 'BLOCKED',
            'reason': 'No independent release/vintage evidence or unexamined PIT-valid test set'}


def _memory(queue: dict, state_dir: Path) -> dict:
    records = []
    for task_id in queue['order']:
        item = queue['tasks'][task_id]
        task_dir = state_dir / 'tasks' / task_id
        hypothesis = _load(task_dir / 'hypothesis.json') if item.get('hypothesis_hash') else None
        result = _load(task_dir / 'result.json') if item.get('output_hash') else None
        records.append({'research_id': f'agent43-{task_id}',
            'problem_id': item['problem_id'],
            'hypothesis_id': hypothesis['hypothesis_id'] if hypothesis else None,
            'generation_method': 'CODEX_CLI_LLM' if hypothesis else 'NOT_GENERATED',
            'model_identifier': 'CODEX_CLI_DEFAULT_MODEL_UNVERIFIED',
            'code_version': item.get('code_hash'), 'data_version': queue['data_version'],
            'input_hash': item['input_hashes'], 'output_hash': item.get('output_hash'),
            'test_result': item.get('test_result'),
            'backtest_result': item.get('backtest_result'),
            'validation_result': item.get('validation_result'),
            'failure_reason': item.get('failure_reason'),
            'next_action': item.get('next_action'),
            'execution_cost': {'codex_calls': item['attempts'],
                               'code_execution_seconds_limit': MAX_EXEC_SECONDS},
            'checkpoint_id': item.get('checkpoint_id'), 'status': item['status']})
    return {'schema_version': 1, 'checkpoint_id': queue['checkpoint_id'],
            'records': records, 'next_research': _next(queue),
            'official_prediction_claim': False, 'pit_approved': 0}


def reassess_completed(state_dir: Path) -> dict:
    """Recompute exploratory outcomes from sealed labels after an engine revision."""
    state_dir = state_dir.resolve()
    with locked_state(state_dir):
        queue = _load(state_dir / QUEUE)
        _integrity(state_dir, queue)
        revised = []
        for task_id in ('FORECAST-CRASH20', 'FORECAST-RECOVERY10'):
            item = queue['tasks'][task_id]
            if item['status'] != 'COMPLETED':
                continue
            task_dir = state_dir / 'tasks' / task_id
            result = _load(task_dir / 'result.json')
            old_hash = item['output_hash']
            verification = _verify_market(task_dir, state_dir / 'sealed',
                                          'crash' if task_id == 'FORECAST-CRASH20' else 'recovery')
            result['verification'] = verification
            result['reassessment'] = {'old_output_sha256': old_hash,
                                      'at_utc': _now(), 'reason': 'Apply recorded Brier failure criterion'}
            write_state(task_dir / 'result.json', result)
            item['output_hash'] = _sha(task_dir / 'result.json')
            item['backtest_result'] = verification
            item['failure_reason'] = (verification['hypothesis_test'] if
                                      verification['hypothesis_test'].startswith('REJECTED') else None)
            item['next_action'] = ('Try a distinct causal feature only with fresh PIT-valid evidence '
                                   'and an unexamined holdout')
            revised.append(task_id)
        write_state(state_dir / QUEUE, queue)
        write_state(state_dir / MEMORY, _memory(queue, state_dir))
        return {'reassessed': revised, 'checkpoint_id': queue['checkpoint_id']}


def run(state_dir: Path, max_cycles: int = MAX_CYCLES) -> dict:
    if not 1 <= max_cycles <= MAX_CYCLES:
        raise ValueError('Cycle limit exceeded')
    prepare(state_dir)
    state_dir = state_dir.resolve()
    processed = 0
    for task_id in _load(state_dir / QUEUE)['order']:
        with locked_state(state_dir):
            queue = _load(state_dir / QUEUE)
            _integrity(state_dir, queue)
            if (state_dir / 'STOP').exists():
                return {'status': 'STOPPED', 'checkpoint_id': queue['checkpoint_id']}
            item = queue['tasks'][task_id]
            if item['status'] in {'COMPLETED', 'BLOCKED', 'REVIEW_REQUIRED'}:
                continue
            if item['status'] == 'RUNNING':
                started = datetime.fromisoformat(item['started_at_utc'])
                if (datetime.now(timezone.utc) - started).total_seconds() < 2 * MAX_CODEX_SECONDS:
                    return {'status': 'RUNNING', 'task_id': task_id}
                item['status'] = 'FAILED'
                item['failure_reason'] = 'INTERRUPTED'
            replay = (item['status'] == 'FAILED' and item.get('codex_exit_code') == 0
                      and (state_dir / 'tasks' / task_id / 'hypothesis.json').is_file()
                      and (state_dir / 'tasks' / task_id / 'codex_stdout.log').is_file())
            if item['attempts'] >= 2 or (queue['codex_calls'] >= MAX_CODEX_CALLS and not replay):
                item['status'] = 'BLOCKED'
                item['failure_reason'] = 'RETRY_OR_LLM_BUDGET_EXHAUSTED'
                write_state(state_dir / QUEUE, queue)
                continue
            if not replay:
                item['attempts'] += 1
                queue['codex_calls'] += 1
            item['status'] = 'RUNNING'
            item['replayed_generated_artifact'] = replay
            item['started_at_utc'] = _now()
            write_state(state_dir / QUEUE, queue)
        task_dir = state_dir / 'tasks' / task_id
        exit_code, error = (0, None) if replay else _codex(task_dir)
        with locked_state(state_dir):
            queue = _load(state_dir / QUEUE)
            item = queue['tasks'][task_id]
            item['codex_exit_code'] = exit_code
            try:
                if error:
                    raise ValueError(error)
                hypothesis = _load(task_dir / 'hypothesis.json')
                validate(hypothesis, _load(SCHEMA))
                _check_code(hypothesis['code'])
                if replay and not (task_dir / 'codex_stdout.log').read_text().strip():
                    raise ValueError('Generated artifact lacks Codex execution evidence')
                if queue['code_version'] != _version():
                    raise ValueError('Research source changed during generation')
                code_path = task_dir / 'experiment.py'
                code_path.write_text(hypothesis['code'], encoding='utf-8')
                item['hypothesis_hash'] = _sha(task_dir / 'hypothesis.json')
                item['code_hash'] = _sha(code_path)
                runs = []
                if task_id == 'PIT-EMA20':
                    run_info = _isolated_python(task_dir)
                    runs.append(run_info)
                    if run_info['exit_code'] != 0:
                        raise ValueError('PIT_CODE_EXECUTION_FAILED: ' + run_info.get('stderr', ''))
                    verification = _verify_pit(task_dir)
                    item['status'] = 'BLOCKED'
                    item['next_action'] = 'Acquire licensed official EMA closes, release clock and vintages'
                else:
                    for fold_id in ('fold1', 'fold2'):
                        fold_dir = task_dir / fold_id
                        shutil.copyfile(code_path, fold_dir / 'experiment.py')
                        run_info = _isolated_python(fold_dir)
                        runs.append(run_info)
                        if run_info['exit_code'] != 0:
                            raise ValueError(f'{fold_id}_CODE_EXECUTION_FAILED: ' + run_info.get('stderr', ''))
                    verification = _verify_market(task_dir, state_dir / 'sealed',
                        'crash' if task_id == 'FORECAST-CRASH20' else 'recovery')
                    item['status'] = 'COMPLETED'
                    item['next_action'] = ('Try a distinct causal feature only with fresh PIT-valid '
                                           'evidence and an unexamined holdout')
                item['test_result'] = 'PASSED_ISOLATED_EXECUTION_AND_HOST_VERIFICATION'
                item['backtest_result'] = verification
                item['validation_result'] = verification['status']
                item['failure_reason'] = (verification.get('hypothesis_test') if
                                          verification.get('hypothesis_test', '').startswith('REJECTED')
                                          else None)
                write_state(task_dir / 'result.json', {'hypothesis': {k: v for k, v in hypothesis.items() if k != 'code'},
                            'verification': verification, 'executions': runs,
                            'code_sha256': item['code_hash'], 'codex_exit_code': exit_code})
                item['output_hash'] = _sha(task_dir / 'result.json')
                queue['checkpoint_id'] += 1
                item['checkpoint_id'] = queue['checkpoint_id']
            except Exception as exc:
                item['status'] = 'REVIEW_REQUIRED' if 'changed' in str(exc) else 'FAILED'
                item['failure_reason'] = str(exc)[:600]
                item['test_result'] = 'FAILED'
                item['next_action'] = 'Review failed isolated code; select next bounded research task'
            write_state(state_dir / QUEUE, queue)
            write_state(state_dir / MEMORY, _memory(queue, state_dir))
        processed += 1
        if processed >= max_cycles:
            break
    queue = _load(state_dir / QUEUE)
    return {'status': 'CYCLE_CHECKPOINTED', 'checkpoint_id': queue['checkpoint_id'],
            'codex_calls': queue['codex_calls'],
            'tasks': {key: value['status'] for key, value in queue['tasks'].items()},
            'next_research': _next(queue)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--adopt-engine-revision', action='store_true')
    parser.add_argument('--reassess-completed', action='store_true')
    parser.add_argument('--max-cycles', type=int, default=MAX_CYCLES)
    args = parser.parse_args()
    result = (adopt_code_revision(args.state_dir) if args.adopt_engine_revision else
              reassess_completed(args.state_dir) if args.reassess_completed else
              prepare(args.state_dir) if args.prepare_only else run(args.state_dir, args.max_cycles))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
