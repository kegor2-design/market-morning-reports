"""Bounded independent supervisor for one approved guided research job."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .engine import canonical, locked_state, now, write_state
from .guided_experiment import AI_ROOT, PRIVATE_ROOT
from .self_repair import redact


def _wall_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _boot_id() -> str:
    """Bind persisted monotonic deadlines to the current Linux boot."""
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def _program_task_key(goal_id: str, task: dict) -> str:
    return hashlib.sha256(canonical((goal_id, task))).hexdigest()


def _program_manifest(path: Path, data: dict) -> Path:
    """Seal a child Research Job manifest before any external side effect."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Symlinked child manifest')
    if path.exists():
        if json.loads(path.read_text()) != data:
            raise ValueError('Child manifest changed after reservation')
    else:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
    return path


def _child_for(plan: dict, task: dict, program_dir: Path,
               test_analysis_delay: int = 0) -> dict:
    """Translate one allowlisted DAG task into the existing Research Job contract."""
    from .research_planner import dates_for, SERIES
    from .source_adapters import select
    task_id = task['task_id']
    job_id = plan['goal_id'] + '_' + task_id
    base = {'schema_version': 1, 'job_id': job_id,
            'goal': plan['research_goal'], 'max_seconds': 60,
            'max_restarts': 1, 'max_model_calls': 0}
    if task['task_type'] in {'DATA_ACQUISITION', 'DATA_CALENDAR_REVALIDATION',
                             'DATA_SCHEMA_REVALIDATION', 'API_RECOVERY_RETRY'}:
        series = task['inputs']['series']
        source = 'NYFED_REFERENCE_RATES' if series == 'NYFED_SOFR' else 'US_TREASURY'
        calendar_revalidation = task['task_type'] == 'DATA_CALENDAR_REVALIDATION'
        revalidation = task['task_type'] in {'DATA_CALENDAR_REVALIDATION',
                                              'DATA_SCHEMA_REVALIDATION'}
        if task['task_type'] == 'API_RECOVERY_RETRY':
            from .api_recovery import verify_task
            revision = verify_task(plan, task, program_dir)
            fixture_path = program_dir / 'local_http_fixture.json'
            if fixture_path.is_symlink():
                raise ValueError('Symlinked local source fixture')
            fixture_uri = (json.loads(fixture_path.read_text())['uris'][series]
                           if fixture_path.is_file() else None)
            if (revision['series'] != series or revision['source_id'] != source or
                    revision['source_uri'] != (fixture_uri or select(series, [source]).uri(
                        series, plan['research_period']['start'],
                        plan['research_period']['end']))):
                raise ValueError('Recovery source adapter changed')
        if calendar_revalidation:
            from .us_rates_calendar import expected_observations
            expected, _ = expected_observations(plan['research_period']['start'],
                                                plan['research_period']['end'], series)
        else:
            expected = dates_for(plan)
        base.update(mode='data_recovery', data_request={
            'goal_id': job_id, 'job_id': job_id, 'task_id': task_id,
            'series': series, 'market': 'US', 'unit': 'percent',
            'start': plan['research_period']['start'],
            'end': plan['research_period']['end'],
            'expected_dates': expected, 'existing': {},
            'allowed_sources': [source],
            'budget': {'max_network_requests': 0 if revalidation else 1,
                       'max_seconds': 25,
                       'max_retries': 0, 'max_model_calls': 0}})
        fixture_path = program_dir / 'local_http_fixture.json'
        if fixture_path.is_symlink():
            raise ValueError('Symlinked local source fixture')
        if fixture_path.is_file():
            fixture = json.loads(fixture_path.read_text())
            if (fixture.get('scope') != 'LOCAL_LOOPBACK_TEST' or
                    fixture.get('goal_id') != plan['goal_id'] or
                    set(fixture.get('uris', {})) != set(SERIES)):
                raise ValueError('Local fixture contract changed')
            base['data_request']['fixture_source_uri'] = fixture['uris'][series]
            if fixture.get('request_timeout_seconds') == 1:
                base['data_request']['budget']['max_seconds'] = 1
    elif task['task_type'] == 'EXPERIMENT_EXECUTION':
        calendar_revalidation = 'calendar_revision_sha256' in task['inputs']
        schema_revalidation = 'schema_revision_sha256' in task['inputs']
        api_recovery = 'api_recovery_revision_sha256' in task['inputs']
        recovered_series = None
        if api_recovery:
            revision_path = program_dir / 'api_recovery_revision_v1.json'
            if hashlib.sha256(revision_path.read_bytes()).hexdigest() != \
                    task['inputs']['api_recovery_revision_sha256']:
                raise ValueError('Analysis API revision changed')
            recovered_series = json.loads(revision_path.read_text())['series']
        sources = {}
        for series in SERIES:
            child_id = (('api_recover_' if series == recovered_series else 'collect_')
                        if api_recovery else
                        ('schema_revalidate_' if series in ('UST_2Y', 'UST_10Y')
                         else 'collect_') if schema_revalidation else
                        ('revalidate_' if calendar_revalidation else 'collect_')) + series.lower()
            sources[series] = {
                'manifest': str((program_dir / 'manifests' / (child_id + '.json')).resolve()),
                'job_dir': str((program_dir / 'jobs' / child_id).resolve())}
        if calendar_revalidation:
            from .us_rates_calendar import expected_observations
            analysis_dates, _ = expected_observations(plan['research_period']['start'],
                plan['research_period']['end'], SERIES[0])
            if any(expected_observations(plan['research_period']['start'],
                    plan['research_period']['end'], series)[0] != analysis_dates
                   for series in SERIES[1:]):
                raise ValueError('Source calendars do not align for analysis')
        else:
            analysis_dates = dates_for(plan)
        base.update(mode='rate_analysis', analysis_sources=sources,
                    analysis_dates=analysis_dates, train_rows=12)
        if plan['goal_contract']['version'] == 2:
            base['analysis_signal'] = task['inputs']['signal']
        if test_analysis_delay:
            base['fixture_delay_before_output_seconds'] = test_analysis_delay
    else:
        raise ValueError('Task has no registered child Research Job')
    return base


def _program_result(state: dict, program_dir: Path) -> dict:
    from .research_planner import validate_plan
    plan = dict(state['plan'], tasks=state['tasks'])
    validate_plan(plan)
    analysis = None
    if state['records'].get('analyze_rates', {}).get('status') == 'COMPLETED_EXPLORATORY':
        artifact = program_dir / 'jobs/analyze_rates/action_result.json'
        analysis = json.loads(artifact.read_text())['result']
    if state['records'].get('analyze_kr_crashes', {}).get('status') == 'COMPLETED_EXPLORATORY':
        analysis = json.loads((program_dir / 'kr_crash_result.json').read_text())['result']
    if state['records'].get('analyze_kr_regime', {}).get('status') == 'COMPLETED_EXPLORATORY':
        analysis = json.loads((program_dir / 'kr_regime_result.json').read_bytes())['result']
    if state['records'].get('analyze_fixture', {}).get('status') == 'COMPLETED_EXPLORATORY':
        analysis = json.loads((program_dir / 'fixture_analysis_result.json').read_text())['result']
    result = {'goal_id': state['goal_id'], 'research_goal': state['plan']['research_goal'],
              'status': state['status'], 'goal_contract_sha256': state['goal_contract_sha256'],
              'task_statuses': {key: value['status'] for key, value in state['records'].items()},
              'executed_tasks': [key for key, value in state['records'].items()
                                 if value['status'] in {'VERIFIED', 'COMPLETED_EXPLORATORY'}],
              'blocked_tasks': [key for key, value in state['records'].items()
                                if value['status'].startswith('BLOCKED')],
              'selection_history': state['selection_history'],
              'replanning_history': state['replanning_history'],
              'calendar_revision': state.get('calendar_revision'),
              'independent_goal': state.get('independent_goal'),
              'analysis': analysis, 'pit_status': 'PIT_UNVERIFIED',
              'official_market_claim': False, 'independent_holdout': 'NOT_AVAILABLE',
              'next_action': state.get('next_action') or (analysis.get('next_action',
                             'ACQUIRE_PIT_AND_INDEPENDENT_HOLDOUT') if analysis else
                             'RESUME_BOUNDED_TASKS')}
    if state.get('schema_revision'):
        result['schema_revision'] = state['schema_revision']
    if state.get('api_recovery_revision'):
        result['api_recovery_revision'] = state['api_recovery_revision']
        result['recovery_network_requests_reserved'] = state.get(
            'recovery_network_requests_reserved', 0)
        result['retired_recovery_tasks'] = state.get('retired_recovery_tasks', [])
    if state.get('code_repair_revision'):
        result['code_repair_revision'] = state['code_repair_revision']
        result['retired_recovery_tasks'] = state.get('retired_recovery_tasks', [])
    write_state(program_dir / 'research_report.json', result)
    return result


def run_research_program(goal: str, program_dir: Path | None = None,
                         *, max_tasks: int = 12, max_seconds: int = 300,
                         test_analysis_delay: int = 0, rollback_only: bool = False,
                         ai_candidate: dict | None = None) -> dict:
    """Sequentially run reviewed DAG tasks through existing Research Job Supervisor."""
    from .isolated_codex import PRIVATE_ROOT as JOB_ROOT
    from .research_planner import plan_goal, validate_plan, dates_for, UnsupportedGoal
    from .research_job import supervise as supervise_research
    from .ai_research_planner import validate_candidate
    if (not 1 <= max_tasks <= 12 or not 10 <= max_seconds <= 300 or
            not 0 <= test_analysis_delay <= 3):
        raise ValueError('Program budget exceeded')
    try:
        plan = plan_goal(goal) if ai_candidate is None else validate_candidate(goal, ai_candidate)
    except UnsupportedGoal as exc:
        goal_id = 'research_' + hashlib.sha256(goal.encode()).hexdigest()[:12]
        unsupported_dir = program_dir or JOB_ROOT / 'programs' / goal_id
        if unsupported_dir.is_symlink() or not unsupported_dir.resolve().is_relative_to(JOB_ROOT):
            raise ValueError('Program path outside private research root')
        with locked_state(unsupported_dir) as checkpoint:
            contract = {'version': 1, 'goal_id': goal_id,
                'original_research_goal': goal, 'market': None, 'research_period': None,
                'target': None, 'hypotheses': [], 'data_requirements': [],
                'allowed_sources': [], 'allowed_actions': [], 'evaluation_methods': [],
                'pit_policy': 'No official claim', 'holdout_policy': 'Not applicable',
                'resource_budget': {'max_network_requests': 0, 'max_model_calls': 0},
                'terminal_conditions': ['RESEARCH_UNSUPPORTED'],
                'approved_independent_goal_ids': []}
            contract_hash = hashlib.sha256(canonical(contract)).hexdigest()
            path = unsupported_dir / 'goal_contract.json'
            if path.exists():
                previous = json.loads(path.read_text())
                previous.pop('updated_at_utc', None)
                if previous != contract:
                    raise ValueError('Unsupported goal contract changed')
            else:
                write_state(path, contract)
            state = {'schema_version': 1, 'goal_id': goal_id,
                     'goal_contract_sha256': contract_hash,
                     'status': 'RESEARCH_UNSUPPORTED', 'reason': str(exc),
                     'missing_capabilities': ['REVIEWED_SOURCE_ADAPTER',
                                              'REVIEWED_ANALYSIS_ACTION'],
                     'task_statuses': {}, 'model_calls': 0,
                     'network_requests_reserved': 0, 'official_market_claim': False}
            if '한국' in goal and ('급락' in goal or '국면' in goal):
                from .source_discovery import korean_requirements
                state['source_candidates'] = korean_requirements()
            write_state(checkpoint, state)
            write_state(unsupported_dir / 'research_report.json', state)
            return state
    if ai_candidate is not None:
        reviewed = validate_candidate(goal, ai_candidate)
        if canonical(reviewed) != canonical(plan):
            raise ValueError('AI candidate plan changed before execution')
    program_dir = program_dir or JOB_ROOT / 'programs' / plan['goal_id']
    if program_dir.is_symlink() or not program_dir.resolve().is_relative_to(JOB_ROOT):
        raise ValueError('Program path outside private research root')
    program_dir = program_dir.resolve()
    with locked_state(program_dir) as checkpoint:
        if ai_candidate is not None:
            candidate_path = program_dir / 'ai_program_candidate.json'
            if candidate_path.is_symlink():
                raise ValueError('Symlinked AI candidate')
            if candidate_path.exists():
                prior = json.loads(candidate_path.read_text())
                prior.pop('updated_at_utc', None)
                if canonical(prior) != canonical(ai_candidate):
                    raise ValueError('AI candidate changed after registration')
            else:
                write_state(candidate_path, dict(ai_candidate))
        plan_path = program_dir / 'plan.json'
        contract_path = program_dir / 'goal_contract.json'
        plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
        contract_hash = hashlib.sha256(canonical(plan['goal_contract'])).hexdigest()
        if contract_path.exists():
            saved_contract = json.loads(contract_path.read_text())
            saved_contract.pop('updated_at_utc', None)
            if (contract_path.is_symlink() or
                    hashlib.sha256(canonical(saved_contract)).hexdigest() != contract_hash):
                raise ValueError('Original research goal contract changed')
        else:
            write_state(contract_path, dict(plan['goal_contract']))
        if plan_path.exists():
            saved_plan = json.loads(plan_path.read_text())
            saved_plan.pop('updated_at_utc', None)
            if plan_path.is_symlink() or hashlib.sha256(canonical(saved_plan)).hexdigest() != plan_hash:
                raise ValueError('Program plan changed')
        else:
            write_state(plan_path, dict(plan))
            # write_state adds a timestamp; compare the reviewed fields only.
        state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {
            'schema_version': 1, 'goal_id': plan['goal_id'], 'plan_sha256': plan_hash,
            'goal_contract_sha256': contract_hash,
            'test_analysis_delay': test_analysis_delay,
            'plan': plan, 'tasks': deepcopy(plan['tasks']),
            'records': {task['task_id']: {'status': 'PENDING', 'attempts': 0}
                        for task in plan['tasks']},
            'status': 'RESEARCH_INCOMPLETE',
            'selection_history': [], 'replanning_history': [],
            'network_requests_reserved': 0, 'model_calls': 0,
            'started_at_utc': now(),
            'goal_budget_seconds': max_seconds,
            'goal_deadline_utc': (_wall_utc_now() +
                                  timedelta(seconds=max_seconds)).isoformat(),
            'goal_boot_id': _boot_id(),
            'goal_deadline_monotonic': time.monotonic() + max_seconds}
        if (state['goal_id'] != plan['goal_id'] or state['plan_sha256'] != plan_hash or
                state['goal_contract_sha256'] != contract_hash or
                state.get('test_analysis_delay', 0) != test_analysis_delay):
            raise ValueError('Program checkpoint identity changed')
        if 'goal_deadline_utc' not in state:
            # Upgrade old checkpoints once; later invocations cannot renew this budget.
            state['goal_budget_seconds'] = max_seconds
            state['goal_deadline_utc'] = (datetime.fromisoformat(state['started_at_utc']) +
                                           timedelta(seconds=max_seconds)).isoformat()
            write_state(checkpoint, state)
        goal_deadline = datetime.fromisoformat(state['goal_deadline_utc'])
        if (goal_deadline.tzinfo is None or
                type(state.get('goal_budget_seconds')) is not int or
                not 10 <= state['goal_budget_seconds'] <= 300):
            raise ValueError('Invalid persistent goal deadline')
        if 'goal_boot_id' not in state:
            # Legacy checkpoints retain their original UTC limit. Bind the
            # remaining interval once; a later restart cannot renew it.
            state['goal_boot_id'] = _boot_id()
            state['goal_deadline_monotonic'] = time.monotonic() + max(0.0,
                (goal_deadline - _wall_utc_now()).total_seconds())
            if state['status'] != 'RESEARCH_COMPLETED_EXPLORATORY':
                write_state(checkpoint, state)
        if (not isinstance(state.get('goal_boot_id'), str) or
                type(state.get('goal_deadline_monotonic')) not in (int, float) or
                state['goal_deadline_monotonic'] < 0):
            raise ValueError('Invalid persistent monotonic goal deadline')
        boot_changed = state['goal_boot_id'] != _boot_id()
        def remaining_goal_seconds() -> float:
            if boot_changed:
                return 0.0
            return min((goal_deadline - _wall_utc_now()).total_seconds(),
                       state['goal_deadline_monotonic'] - time.monotonic())
        for saved_task in state['tasks']:
            saved_record = state['records'][saved_task['task_id']]
            if saved_record.get('task_key') and saved_record['task_key'] != \
                    _program_task_key(plan['goal_id'], saved_task):
                raise ValueError('Program task changed after execution')
            if saved_record.get('checkpoint_sha256'):
                saved_checkpoint = Path(saved_record['checkpoint'])
                if saved_checkpoint.is_symlink() or not saved_checkpoint.resolve().is_relative_to(program_dir):
                    raise ValueError('Child checkpoint outside program')
                if not saved_checkpoint.is_file() or hashlib.sha256(
                        saved_checkpoint.read_bytes()).hexdigest() != \
                        saved_record['checkpoint_sha256']:
                    raise ValueError('Child Research Job checkpoint changed')
                if saved_task['task_type'] in {'DATA_ACQUISITION', 'API_RECOVERY_RETRY',
                                               'DATA_CALENDAR_REVALIDATION',
                                               'DATA_SCHEMA_REVALIDATION',
                                               'EXPERIMENT_EXECUTION'}:
                    from .research_job import manifest_load, plan_for, verify_artifact
                    manifest_path = program_dir / 'manifests' / (saved_task['task_id'] + '.json')
                    manifest, digest = manifest_load(manifest_path)
                    child_state = json.loads(saved_checkpoint.read_bytes())
                    if saved_record['status'] != 'FAILED' or child_state.get('output_sha256'):
                        verify_artifact(manifest, plan_for(manifest, digest),
                                        program_dir / 'jobs' / saved_task['task_id'])
                    elif child_state['status'] != 'FAILED_TERMINAL':
                        raise ValueError('Failed child checkpoint lacks terminal failure')
                elif saved_task['task_type'] == 'KR_INDEX_VALIDATION':
                    from regime190.exploratory_backtest import load_indices
                    rows, provenance = load_indices('2010-01-01')
                    item = json.loads(saved_checkpoint.read_text())
                    if item['common_rows'] != len(rows) or item['source_provenance'] != provenance:
                        raise ValueError('Korean index source changed after validation')
                elif saved_task['task_type'] == 'KR_REGIME_ANALYSIS' and saved_record['status'] == 'COMPLETED_EXPLORATORY':
                    from .kr_regime_analysis import bounded
                    if json.loads(saved_checkpoint.read_bytes())['result'] != bounded(60):
                        raise ValueError('Regime190 transition evidence changed')
                elif saved_task['task_type'] == 'KR_CRASH_ANALYSIS':
                    from .kr_crash_analysis import analyze
                    from .kr_crash_analysis import walk_forward
                    evaluate = walk_forward if saved_task['inputs'].get('evaluation') == 'expanding_annual' else analyze
                    if json.loads(saved_checkpoint.read_text())['result'] != evaluate():
                        raise ValueError('Korean crash analysis changed after checkpoint')
                elif saved_task['task_id'] == 'restore_kr_analysis' and saved_record['status'] == 'VERIFIED':
                    source = program_dir / 'kr_analysis_copy.py'
                    saved_result = json.loads(saved_checkpoint.read_bytes())
                    if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != saved_result['after_sha256']:
                        raise ValueError('Completed Korean repair source changed')
                elif saved_task['task_type'] in {'FIXTURE_ANALYSIS', 'CODE_REPAIR_TASK'} and \
                        saved_record['status'] in {'VERIFIED', 'COMPLETED_EXPLORATORY'}:
                    from .code_recovery import fixture_source
                    saved_result = json.loads(saved_checkpoint.read_text())
                    expected_source = (saved_result['result']['source_sha256'] if
                        saved_task['task_type'] == 'FIXTURE_ANALYSIS' else
                        saved_result['source_sha256'])
                    if hashlib.sha256(fixture_source(program_dir).read_bytes()).hexdigest() != \
                            expected_source:
                        raise ValueError('Completed code repair source changed')
        for retired in state.get('retired_recovery_tasks', []):
            saved_record = retired['record']
            if saved_record.get('checkpoint_sha256'):
                saved_checkpoint = Path(saved_record['checkpoint'])
                if (saved_checkpoint.is_symlink() or
                        not saved_checkpoint.resolve().is_relative_to(program_dir) or
                        hashlib.sha256(saved_checkpoint.read_bytes()).hexdigest() !=
                        saved_record['checkpoint_sha256']):
                    raise ValueError('Retired recovery checkpoint changed')
        if state['status'] == 'RESEARCH_COMPLETED_EXPLORATORY':
            report_path = program_dir / 'research_report.json'
            if report_path.is_symlink() or not report_path.is_file():
                raise ValueError('Completed research report missing')
            completed = json.loads(report_path.read_text())
            if (completed['goal_id'] != state['goal_id'] or
                    completed['goal_contract_sha256'] != state['goal_contract_sha256'] or
                    completed['status'] != state['status'] or
                    completed['task_statuses'] != {key: value['status']
                        for key, value in state['records'].items()}):
                raise ValueError('Completed research report changed')
            return completed
        if rollback_only:
            if (state['status'] != 'RESEARCH_BLOCKED' or
                    state.get('api_recovery_revision', {}).get('status') != 'REVISION_ROLLED_BACK'):
                raise ValueError('Interrupted recovery requires checkpoint review')
            from .api_recovery import finalize_transaction
            finalize_transaction(state, program_dir)
            write_state(checkpoint, state)
            return _program_result(state, program_dir)
        if state.get('api_recovery_revision'):
            from .api_recovery import finalize_transaction
            finalize_transaction(state, program_dir)
            write_state(checkpoint, state)
        if state.get('code_repair_revision'):
            from .code_recovery import finalize_transaction
            finalize_transaction(state, program_dir)
            write_state(checkpoint, state)
        if (program_dir / 'STOP').exists():
            state['status'] = 'RESEARCH_CANCELLED'
            write_state(checkpoint, state)
            return _program_result(state, program_dir)
        if not boot_changed and remaining_goal_seconds() <= 1:
            # An attached worker can outlive its supervisor. Reap only the already
            # identified child and give supervise no budget for another launch.
            for active_task in state['tasks']:
                task_id = active_task['task_id']
                record = state['records'][task_id]
                job_dir = program_dir / 'jobs' / task_id
                if record['status'] == 'RUNNING' and (job_dir / 'job.json').is_file():
                    manifest = program_dir / 'manifests' / (task_id + '.json')
                    child = supervise_research(manifest, job_dir, outer_deadline_utc=datetime.now(timezone.utc))
                    record.update(status='FAILED', reason=child.get('reason', 'Deadline at restart'),
                                  checkpoint=str(job_dir / 'job.json'), checkpoint_sha256=hashlib.sha256(
                                      (job_dir / 'job.json').read_bytes()).hexdigest())
                    if state['selection_history'] and state['selection_history'][-1]['selected'] == task_id:
                        state['selection_history'][-1].update(ended_at_utc=now(), ended_monotonic=time.monotonic())
        if remaining_goal_seconds() <= 0 and state['status'] != 'RESEARCH_COMPLETED_EXPLORATORY':
            state['status'] = 'RESEARCH_BLOCKED'
            state['next_action'] = ('GOAL_BOOT_CHANGED_REVIEW' if boot_changed
                                    else 'GOAL_DEADLINE_EXHAUSTED')
            write_state(checkpoint, state)
            return _program_result(state, program_dir)
        if state['status'] == 'RESEARCH_BLOCKED':
            from .problem_solver import solve_recovery
            proposal = solve_recovery(plan, state, program_dir, execute=True)
            if proposal:
                write_state(checkpoint, state)
                if proposal['problem_type'] == 'API_ERROR':
                    from .api_recovery import finalize_transaction
                    finalize_transaction(state, program_dir)
                    write_state(checkpoint, state)
                elif proposal['problem_type'] == 'CODE_ERROR':
                    from .code_recovery import finalize_transaction
                    finalize_transaction(state, program_dir)
                    write_state(checkpoint, state)
        validate_plan(dict(plan, tasks=state['tasks']))
        started = time.monotonic()
        executed = 0
        while (executed < max_tasks and time.monotonic() - started < max_seconds
               and remaining_goal_seconds() > 0):
            tasks = sorted(state['tasks'], key=lambda item: (item['priority'], item['task_id']))
            ready = [task for task in tasks if state['records'][task['task_id']]['status'] in
                     {'PENDING', 'READY', 'RUNNING'} and all(
                         state['records'][dep]['status'] in {'VERIFIED', 'COMPLETED_EXPLORATORY'}
                         for dep in task['dependencies'])]
            if not ready:
                break
            task = ready[0]
            task_id = task['task_id']
            record = state['records'][task_id]
            if remaining_goal_seconds() <= 1:
                state['status'] = 'RESEARCH_BLOCKED'
                state['next_action'] = 'GOAL_DEADLINE_INSUFFICIENT_FOR_TASK'
                write_state(checkpoint, state)
                break
            if task['task_type'] == 'DATA_ACQUISITION' and record['status'] != 'RUNNING' and \
                    state['network_requests_reserved'] >= plan['resource_budget']['max_network_requests']:
                record.update(status='BLOCKED_ENV', reason='Program network budget exhausted')
                write_state(checkpoint, state)
                continue
            task_deadline = min(goal_deadline, _wall_utc_now() + timedelta(
                seconds=max(0.0, min(task['resource_budget']['max_seconds'], remaining_goal_seconds()))))
            history = state['selection_history']
            continuing = (record['status'] == 'RUNNING' and history and
                          history[-1]['selected'] == task_id and 'started_at_utc' in history[-1]
                          and 'ended_at_utc' not in history[-1])
            if continuing:
                task_deadline = min(task_deadline, datetime.fromisoformat(history[-1]['task_deadline_utc']))
            else:
                history.append({'started_at_utc': now(), 'started_monotonic': time.monotonic(),
                    'task_deadline_utc': task_deadline.isoformat(), 'selected': task_id,
                    'candidates': [item['task_id'] for item in ready[1:]],
                    'reason': 'Highest-priority independent ready task'})
            if record['status'] != 'RUNNING':
                record.update(status='RUNNING', attempts=record['attempts'] + 1,
                              task_key=_program_task_key(plan['goal_id'], task))
                if task['task_type'] == 'DATA_ACQUISITION':
                    state['network_requests_reserved'] += 1
                elif task['task_type'] == 'API_RECOVERY_RETRY':
                    if state.get('recovery_network_requests_reserved', 0) >= 1:
                        raise ValueError('Separate API recovery budget exhausted')
                    state['recovery_network_requests_reserved'] = 1
                write_state(checkpoint, state)
            if task['task_type'] == 'DATA_DISCOVERY':
                from .source_discovery import discover
                record['source_search'] = discover(task['inputs']['series'])
                gaps = dates_for(plan)
                record.update(status='VERIFIED', gaps=gaps,
                              next_action='ADD_APPROVED_DATA_ACQUISITION')
                new_id = 'collect_' + task['inputs']['series'].lower()
                if new_id not in state['records']:
                    from .research_planner import _task
                    added = _task(new_id, 'DATA_ACQUISITION', task['priority'] + 10,
                                  dependencies=[task_id], inputs=task['inputs'])
                    state['tasks'].append(added)
                    state['records'][new_id] = {'status': 'PENDING', 'attempts': 0}
                    analysis_task = next(t for t in state['tasks'] if t['task_id'] == 'analyze_rates')
                    analysis_task['dependencies'].append(new_id)
                    validate_plan(dict(plan, tasks=state['tasks']))
                    state['replanning_history'].append({'cause': 'DATA_MISSING',
                        'from_task': task_id, 'new_task': new_id,
                        'new_dependency': 'analyze_rates', 'gap_count': len(gaps)})
            elif task['task_type'] == 'PIT_VALIDATION':
                from .problem_solver import collect_indicator_evidence
                request = {'goal_id': plan['goal_id'], 'task_id': task_id,
                    'indicator': '116', 'source': 'FRED_ALFRED',
                    'data_requirement': 'first_vintage_pit',
                    'as_of': '2026-11-13T09:00:00+09:00',
                    'allowed_sources': ['FRED_ALFRED'],
                    'budget': {'max_seconds': 30, 'max_network_requests': 0,
                               'max_model_calls': 0},
                    'policy': {'read_only': True, 'official_claim_allowed': False}}
                evidence = collect_indicator_evidence(request)
                evidence_path = program_dir / 'pit_evidence.json'
                write_state(evidence_path, evidence)
                record.update(status='BLOCKED_EVIDENCE' if evidence['status'] == 'PIT_BLOCKED'
                              else evidence['status'], reason=evidence['status'],
                              checkpoint=str(evidence_path),
                              checkpoint_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                              next_action='SELECT_INDEPENDENT_REAL_RESEARCH')
            elif task['task_type'] == 'KR_INDEX_VALIDATION':
                from regime190.exploratory_backtest import load_indices
                try:
                    rows, provenance = load_indices('2010-01-01')
                except (OSError, ValueError) as exc:
                    record.update(status='BLOCKED_ENV' if isinstance(exc, OSError)
                                  else 'BLOCKED_EVIDENCE', reason=type(exc).__name__,
                                  next_action='RESTORE_HASHED_KR_INDEX_SNAPSHOT')
                else:
                    path = program_dir / 'kr_index_validation.json'
                    write_state(path, {'status': 'VERIFIED_EXPLORATORY_SOURCE',
                        'common_rows': len(rows), 'source_provenance': provenance,
                        'pit_status': 'PIT_UNVERIFIED'})
                    record.update(status='VERIFIED', checkpoint=str(path),
                        checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            elif task['task_type'] == 'KR_REGIME_ANALYSIS':
                from .kr_regime_analysis import bounded
                try:
                    result = bounded(min(60, remaining_goal_seconds()))
                except ValueError as exc:
                    record.update(status='BLOCKED_EVIDENCE', reason=str(exc))
                else:
                    path = program_dir / 'kr_regime_result.json'
                    write_state(path, {'result': result})
                    record.update(status='COMPLETED_EXPLORATORY', checkpoint=str(path),
                                  checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            elif task['task_type'] == 'KR_CRASH_ANALYSIS':
                from .kr_crash_analysis import analyze
                try:
                    isolated = 'RESTORE_REVIEWED_KR_ANALYSIS' in plan['goal_contract']['allowed_actions']
                    if isolated:
                        from .kr_analysis_repair import run
                        result = run(program_dir, task_deadline)
                    elif task['inputs'].get('evaluation') == 'expanding_annual':
                        from .kr_crash_analysis import walk_forward
                        result = walk_forward()
                    else:
                        result = analyze()
                except (OSError, RuntimeError, ValueError) as exc:
                    record.update(status='BLOCKED_ENV' if isinstance(exc, OSError)
                                  else 'BLOCKED_EVIDENCE', reason=type(exc).__name__,
                                  next_action='REVIEW_KR_SOURCE_AND_ANALYSIS')
                    evidence = program_dir / 'kr_analysis_error.json'
                    if (isolated and str(exc) == 'Isolated analysis failed verification' and
                            'restore_kr_analysis' not in state['records']):
                        from .research_planner import _task
                        repair = _task('restore_kr_analysis', 'CODE_REPAIR_TASK', 10,
                            dependencies=['validate_kr_index'], inputs={'failed_task_id': task_id})
                        repair['allowed_actions'] = ['RESTORE_REVIEWED_KR_ANALYSIS']
                        state['tasks'].append(repair)
                        state['records']['restore_kr_analysis'] = {'status': 'PENDING', 'attempts': 0}
                        state['replanning_history'].append({'cause': 'CODE_ERROR', 'failed_task': task_id,
                            'error_sha256': hashlib.sha256(evidence.read_bytes()).hexdigest(),
                            'original_record': dict(record), 'candidate_origin': 'HOST_SUPPLIED_PATCH'})
                        task['dependencies'] = ['restore_kr_analysis']
                        record.clear()
                        record.update(status='PENDING', attempts=0)
                        validate_plan(dict(plan, tasks=state['tasks']))
                else:
                    path = program_dir / 'kr_crash_result.json'
                    write_state(path, {'result': result,
                        'validation_checkpoint_sha256': state['records']['validate_kr_index'][
                            'checkpoint_sha256']})
                    record.update(status='COMPLETED_EXPLORATORY', checkpoint=str(path),
                        checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        reason='EXPLORATORY_ONLY')
            elif task['task_type'] == 'FIXTURE_ANALYSIS':
                from regime190.agent43_engine import _isolated_python
                from .code_recovery import fixture_source
                from .self_repair import classify
                source = fixture_source(program_dir)
                execution = _isolated_python(source.parent,
                    timeout_seconds=max(0.0, remaining_goal_seconds()))
                output = source.parent / 'result.json'
                if execution['exit_code'] == 0 and output.is_file() and not output.is_symlink() \
                        and json.loads(output.read_text()) == {'answer': 42}:
                    path = program_dir / 'fixture_analysis_result.json'
                    write_state(path, {'result': {'answer': 42,
                        'fixture_only': True, 'source_sha256': hashlib.sha256(
                            source.read_bytes()).hexdigest()},
                        'verification': 'independent_exact_answer_42'})
                    record.update(status='COMPLETED_EXPLORATORY', checkpoint=str(path),
                        checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        reason='EXPLORATORY_FIXTURE_ONLY')
                else:
                    error = execution.get('stderr', '')
                    match = re.search(r'(?m)^(NameError|AttributeError|TypeError|'
                        r'SyntaxError|ZeroDivisionError|IndexError):', error)
                    exception_type = match.group(1) if match else None
                    kind = classify('RESEARCH_CODE', error, 'CODE_ERROR' if
                        exception_type else '')
                    path = program_dir / ('code_error_evidence.json' if
                        record['attempts'] == 1 else 'code_error_after_repair.json')
                    write_state(path, {'goal_id': plan['goal_id'],
                        'task_id': task_id, 'error_type': kind,
                        'python_exception_type': exception_type,
                        'traceback_sha256': hashlib.sha256(error.encode()).hexdigest(),
                        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest()
                            if output.is_file() and not output.is_symlink() else None,
                        'exit_code': execution['exit_code'],
                        'sandbox': execution.get('sandbox'),
                        'error_tail': redact(error[-500:])})
                    record.update(status='BLOCKED_EVIDENCE', problem_type=kind,
                        checkpoint=str(path), checkpoint_sha256=hashlib.sha256(
                            path.read_bytes()).hexdigest(),
                        reason='FIXTURE_CODE_ERROR', next_action='APPROVE_CODE_REPAIR_CANDIDATE')
            elif task_id == 'restore_kr_analysis':
                from .kr_analysis_repair import run
                evidence = program_dir / 'kr_analysis_error.json'
                if hashlib.sha256(evidence.read_bytes()).hexdigest() != state['replanning_history'][-1]['error_sha256']:
                    raise ValueError('Korean repair evidence changed')
                result = run(program_dir, task_deadline, repair=True)
                path = program_dir / 'kr_analysis_repair_result.json'
                write_state(path, result)
                record.update(status='VERIFIED' if result['status'] == 'REPAIRED' else 'BLOCKED_EVIDENCE',
                              checkpoint=str(path), checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            elif task['task_type'] == 'CODE_REPAIR_TASK':
                from .code_recovery import execute_task
                result = execute_task(plan, task, program_dir, task_deadline)
                path = program_dir / 'code_repair_result.json'
                write_state(path, result)
                record.update(status='VERIFIED' if result['status'] == 'REPAIRED'
                    else 'BLOCKED_EVIDENCE', checkpoint=str(path),
                    checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    reason=result['status'], next_action='RESUME_ORIGINAL_GOAL' if
                    result['status'] == 'REPAIRED' else 'REVIEW_FAILED_CODE_REPAIR')
            else:
                child_manifest = _child_for(plan, task, program_dir, test_analysis_delay)
                manifest_path = _program_manifest(program_dir / 'manifests' /
                                                  (task_id + '.json'), child_manifest)
                job_dir = program_dir / 'jobs' / task_id
                if task['task_type'] == 'DATA_CALENDAR_REVALIDATION':
                    from .calendar_recovery import seed_revalidation
                    seed_revalidation(plan, task, child_manifest, program_dir, job_dir)
                elif task['task_type'] == 'DATA_SCHEMA_REVALIDATION':
                    from .source_schema_recovery import seed_revalidation
                    seed_revalidation(plan, task, child_manifest, program_dir, job_dir)
                child = supervise_research(manifest_path, job_dir,
                    outer_deadline_utc=task_deadline)
                record['checkpoint'] = str(job_dir / 'job.json')
                record['checkpoint_sha256'] = hashlib.sha256(
                    (job_dir / 'job.json').read_bytes()).hexdigest()
                reason = child.get('conclusion', {}).get('reason')
                record['reason'] = reason
                if task['task_type'] in {'DATA_ACQUISITION', 'API_RECOVERY_RETRY'}:
                    conclusion = child.get('conclusion', {})
                    if conclusion.get('problem_type'):
                        record['problem_type'] = conclusion['problem_type']
                    if conclusion.get('network_call_outcome'):
                        record['network_call_outcome'] = conclusion['network_call_outcome']
                if child['status'] == 'RESEARCH_BLOCKED_WITH_EVIDENCE' and \
                        reason in {'DATA_RECOVERED_PIT_UNVERIFIED',
                                   'DATA_MISMATCH_RESOLVED_PIT_UNVERIFIED'}:
                    record['status'] = 'VERIFIED'
                elif child['status'] == 'RESEARCH_BLOCKED_WITH_EVIDENCE' and \
                        reason == 'EXPLORATORY_ONLY':
                    record['status'] = 'COMPLETED_EXPLORATORY'
                elif reason == 'BLOCKED_ENV':
                    record.update(status='BLOCKED_ENV',
                                  next_action='RESOLVE_SOURCE_ACCESS_OR_USE_VERIFIED_DATA')
                else:
                    record.update(status='BLOCKED_EVIDENCE' if child['status'] ==
                                  'RESEARCH_BLOCKED_WITH_EVIDENCE' else 'FAILED',
                                  next_action='RUN_INDEPENDENT_ALLOWED_TASK')
            state['selection_history'][-1].update(ended_at_utc=now(), ended_monotonic=time.monotonic())
            executed += 1
            write_state(checkpoint, state)
            _program_result(state, program_dir)
            if (program_dir / 'STOP').exists():
                break
        for task in state['tasks']:
            record = state['records'][task['task_id']]
            if record['status'] == 'PENDING' and any(state['records'][dep]['status'].startswith(
                    'BLOCKED') for dep in task['dependencies']):
                record['status'] = 'WAITING_DEPENDENCY'
        if state.get('api_recovery_revision'):
            from .api_recovery import rollback_failed_recovery, finalize_transaction
            if rollback_failed_recovery(plan, state, program_dir):
                write_state(checkpoint, state)
                finalize_transaction(state, program_dir)
                write_state(checkpoint, state)
        if state.get('code_repair_revision'):
            from .code_recovery import rollback_failed_repair, finalize_transaction
            if rollback_failed_repair(plan, state, program_dir):
                write_state(checkpoint, state)
                finalize_transaction(state, program_dir)
                write_state(checkpoint, state)
        if (program_dir / 'STOP').exists():
            state['status'] = 'RESEARCH_CANCELLED'
        elif any(state['records'].get(task_id, {}).get('status') == 'COMPLETED_EXPLORATORY'
                 for task_id in ('analyze_rates', 'analyze_kr_crashes', 'analyze_kr_regime', 'analyze_fixture')):
            state['status'] = 'RESEARCH_COMPLETED_EXPLORATORY'
        elif any(record['status'].startswith('BLOCKED') for record in state['records'].values()):
            state['status'] = 'RESEARCH_BLOCKED'
        elif any(record['status'] == 'FAILED' for record in state['records'].values()):
            state['status'] = 'RESEARCH_FAILED'
        else:
            state['status'] = 'RESEARCH_INCOMPLETE'
        if remaining_goal_seconds() <= 0 and state['status'] != 'RESEARCH_COMPLETED_EXPLORATORY':
            state['status'] = 'RESEARCH_BLOCKED'
            state['next_action'] = ('GOAL_BOOT_CHANGED_REVIEW' if boot_changed
                                    else 'GOAL_DEADLINE_EXHAUSTED')
        elif state.get('next_action') not in {
                'GOAL_DEADLINE_INSUFFICIENT_FOR_TASK',
                'REVIEW_FAILED_API_RECOVERY_EVIDENCE'}:
            state['next_action'] = 'VERIFY_OR_RESUME'
        write_state(checkpoint, state)
        if (state['status'] == 'RESEARCH_BLOCKED' and
                plan['goal_contract']['approved_independent_goal_ids'] and
                remaining_goal_seconds() >= 10 and
                not (program_dir / 'STOP').exists()):
            from .research_planner import APPROVED_INDEPENDENT_RATES_GOAL
            child = run_research_program(APPROVED_INDEPENDENT_RATES_GOAL,
                                         max_tasks=12, max_seconds=min(max_seconds, int(remaining_goal_seconds())))
            child_id = plan['goal_contract']['approved_independent_goal_ids'][0]
            if child['goal_id'] != child_id:
                raise ValueError('Independent goal identity changed')
            state['independent_goal'] = {'goal_id': child_id,
                'status': child['status'], 'separate_contract': True,
                'reason': 'Explicitly approved independent work after PIT block',
                'checkpoint': str(JOB_ROOT / 'programs' / child_id / 'state.json')}
            write_state(checkpoint, state)
        return _program_result(state, program_dir)


def _scoped(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise ValueError('Symlinked research state')
    path = path.resolve(strict=True)
    if path == root or not path.is_relative_to(root):
        raise ValueError('Research state outside private tree')
    return path


def supervise(ai_dir: Path, data_dir: Path, job_dir: Path,
              *, max_restarts: int = 2, max_seconds: int = 300) -> dict:
    if not 0 <= max_restarts <= 2 or not 10 <= max_seconds <= 600:
        raise ValueError('Supervisor budget exceeded')
    ai_dir = _scoped(ai_dir, AI_ROOT)
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    data_dir = _scoped(data_dir, PRIVATE_ROOT)
    job_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    job_dir = _scoped(job_dir, PRIVATE_ROOT)
    if data_dir == job_dir or data_dir.is_relative_to(job_dir) or job_dir.is_relative_to(data_dir):
        raise ValueError('Job and execution states must be separate')
    state_path = job_dir / 'job.json'
    with locked_state(job_dir):
        state = json.loads(state_path.read_text()) if state_path.exists() else {
            'job_id': job_dir.name, 'ai_dir': str(ai_dir), 'data_dir': str(data_dir),
            'status': 'PENDING', 'launch_count': 0, 'restarts': 0, 'events': []}
        if state['ai_dir'] != str(ai_dir) or state['data_dir'] != str(data_dir):
            raise ValueError('Job identity changed')
        if state['status'] == 'COMPLETED':
            return state
        if state['status'] not in {'PENDING', 'RUNNING'}:
            return state
        state['supervisor_pid'] = os.getpid()
        deadline = time.monotonic() + max_seconds
        stopping = False
        def stop(_signum, _frame):
            nonlocal stopping
            stopping = True
        prior = signal.signal(signal.SIGTERM, stop)
        try:
            while not stopping and time.monotonic() < deadline:
                checkpoint = data_dir / 'guided_state.json'
                if checkpoint.exists():
                    saved = json.loads(checkpoint.read_text())
                    state['checkpoint_status'] = saved.get('status')
                    state['checkpoint_id'] = saved.get('updated_at_utc')
                if (job_dir / 'STOP').exists():
                    stopping = True
                    break
                if state['launch_count'] > max_restarts:
                    state['status'] = 'FAILED_RETRY_LIMIT'
                    break
                cmd = [sys.executable, '-m', 'universal_agent.guided_experiment',
                       '--ai-state-dir', str(ai_dir), '--state-dir', str(data_dir)]
                env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
                worker = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parents[3],
                                          env=env, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, start_new_session=True)
                state['status'] = 'RUNNING'
                state['worker_pid'] = worker.pid
                state['launch_count'] += 1
                state['events'].append({'at_utc': now(), 'event': 'WORKER_STARTED',
                                        'worker_pid': worker.pid,
                                        'checkpoint_id': state.get('checkpoint_id')})
                write_state(state_path, state)
                while worker.poll() is None and not stopping and time.monotonic() < deadline:
                    if (job_dir / 'STOP').exists():
                        stopping = True
                        break
                    time.sleep(.2)
                if worker.poll() is None:
                    os.killpg(worker.pid, signal.SIGTERM)
                    try:
                        worker.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(worker.pid, signal.SIGKILL)
                stdout, stderr = worker.communicate(timeout=3)
                state['events'].append({'at_utc': now(), 'event': 'WORKER_EXITED',
                                        'worker_pid': worker.pid, 'exit_code': worker.returncode,
                                        'stderr_tail': redact(stderr[-500:])})
                checkpoint = data_dir / 'guided_state.json'
                saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
                state['checkpoint_status'] = saved.get('status')
                state['checkpoint_id'] = saved.get('updated_at_utc')
                if worker.returncode == 0:
                    try:
                        result = json.loads(stdout.strip().splitlines()[-1])
                    except (IndexError, ValueError):
                        result = {}
                    if (result.get('status') == 'EXPLORATORY_BACKTEST_VERIFIED'
                            and saved.get('status') == result['status']):
                        state['status'] = 'COMPLETED'
                        state['result_status'] = result['status']
                        state['resumed_without_duplicate'] = result.get('resumed_without_duplicate', False)
                        state['completed_job_executions'] = 1
                        state['duplicate_completed_job_executions'] = 0
                    else:
                        state['status'] = 'BLOCKED_RESEARCH'
                    write_state(state_path, state)
                    break
                state['restarts'] += 1
                state['events'].append({'at_utc': now(), 'event': 'CRASH_DETECTED',
                                        'recovery_checkpoint': state.get('checkpoint_id')})
                write_state(state_path, state)
            if stopping:
                state['status'] = 'STOPPED'
            elif state['status'] == 'RUNNING' and time.monotonic() >= deadline:
                state['status'] = 'FAILED_TIME_BUDGET'
            write_state(state_path, state)
            return state
        finally:
            signal.signal(signal.SIGTERM, prior)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--research-goal', type=str)
    parser.add_argument('--program-dir', type=Path)
    parser.add_argument('--research-manifest', type=Path)
    parser.add_argument('--ai-state-dir', type=Path)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--job-dir', type=Path)
    parser.add_argument('--max-restarts', type=int, default=2)
    parser.add_argument('--max-seconds', type=int, default=300)
    parser.add_argument('--test-analysis-delay', type=int, default=0)
    args = parser.parse_args()
    if args.research_goal:
        if args.research_manifest or args.ai_state_dir or args.state_dir or args.job_dir:
            parser.error('Research goal mode cannot share a single-job state')
        result = run_research_program(args.research_goal, args.program_dir,
                                      max_seconds=args.max_seconds,
                                      test_analysis_delay=args.test_analysis_delay)
        print(json.dumps({'goal_id': result['goal_id'], 'status': result['status'],
                          'task_statuses': result['task_statuses'],
                          'official_market_claim': False}))
        return 0 if result['status'] == 'RESEARCH_COMPLETED_EXPLORATORY' else 1
    if args.research_manifest:
        if args.ai_state_dir or args.state_dir or not args.job_dir:
            parser.error('Research manifest mode requires only --job-dir')
        from .research_job import supervise as supervise_research
        result = supervise_research(args.research_manifest, args.job_dir)
        print(json.dumps({'job_id': result['job_id'], 'status': result['status'],
                          'attempts': result['attempts'],
                          'worker_restarts': result['worker_restarts']}))
        return 0 if result['status'] in {'VERIFIED_RESEARCH_CONCLUSION',
                                         'RESEARCH_BLOCKED_WITH_EVIDENCE'} else 1
    if not args.ai_state_dir or not args.state_dir or not args.job_dir:
        parser.error('Guided mode requires --ai-state-dir, --state-dir and --job-dir')
    result = supervise(args.ai_state_dir, args.state_dir, args.job_dir,
                       max_restarts=args.max_restarts, max_seconds=args.max_seconds)
    print(json.dumps({'job_id': result['job_id'], 'status': result['status'],
                      'launch_count': result['launch_count'], 'restarts': result['restarts']}))
    return 0 if result['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
