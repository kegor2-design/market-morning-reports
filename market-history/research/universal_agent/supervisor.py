"""Durable, bounded supervisor over the Phase 3 runner and evidence engine.

The Phase 2/3 state formats and CLIs remain supported. Supervisor checkpoints
live in a separate directory and never migrate an older checkpoint implicitly.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from .engine import locked_state, now, write_state
from .runner import (APPROVAL_RISKS, CodexExecutor, _authorized_check, classify,
                     load_runner_project)

STATES = {'PENDING', 'READY', 'RUNNING', 'VERIFYING', 'COMPLETED',
          'FAILED_RETRYABLE', 'FAILED_TERMINAL', 'BLOCKED_APPROVAL',
          'BLOCKED_DEPENDENCY', 'BLOCKED_DATA', 'BLOCKED_QUOTA', 'PAUSED', 'CANCELLED'}
TRANSITIONS = {
    'PENDING': {'READY', 'BLOCKED_DEPENDENCY', 'BLOCKED_APPROVAL', 'CANCELLED'},
    'READY': {'RUNNING', 'BLOCKED_APPROVAL', 'PAUSED', 'CANCELLED'},
    'RUNNING': {'VERIFYING', 'FAILED_RETRYABLE', 'FAILED_TERMINAL', 'BLOCKED_QUOTA', 'PAUSED'},
    'VERIFYING': {'COMPLETED', 'BLOCKED_DATA', 'FAILED_TERMINAL', 'PAUSED'},
    'FAILED_RETRYABLE': {'READY', 'FAILED_TERMINAL', 'PAUSED'},
    'BLOCKED_DEPENDENCY': {'READY', 'CANCELLED'},
    'PAUSED': {'READY', 'VERIFYING', 'CANCELLED'},
    'BLOCKED_DATA': {'CANCELLED'},
    'BLOCKED_APPROVAL': {'CANCELLED'},
    'BLOCKED_QUOTA': {'READY', 'CANCELLED'},
    'FAILED_TERMINAL': {'CANCELLED'},
    'COMPLETED': set(), 'CANCELLED': set(),
}


def code_version() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def transition(state: dict, task_id: str, target: str, reason: str = '') -> None:
    record = state['tasks'][task_id]
    old = record['status']
    if target not in TRANSITIONS[old]:
        raise ValueError(f'Invalid transition {old}->{target}')
    record.update(status=target, updated_at_utc=now(), reason=reason[:240])
    state['events'].append({'at_utc': now(), 'task_id': task_id, 'from': old,
                            'to': target, 'reason': reason[:240]})
    state['events'] = state['events'][-200:]


def register(registry: Path, manifest: Path) -> dict:
    project, digest = load_runner_project(manifest)
    with locked_state(registry.parent / (registry.name + '.lockdir')):
        data = json.loads(registry.read_text()) if registry.exists() else {'schema_version': 1, 'projects': {}}
        if data.get('schema_version') != 1 or not isinstance(data.get('projects'), dict):
            raise ValueError('Invalid registry')
        prior = data['projects'].get(project['project_id'])
        entry = {'manifest': str(manifest.resolve()), 'sha256': digest, 'registered_at_utc': now()}
        if prior and (prior['manifest'], prior['sha256']) != (entry['manifest'], digest):
            raise ValueError('Project already registered with another manifest; review before replacement')
        if prior:
            return prior
        data['projects'][project['project_id']] = entry
        write_state(registry, data)
        return entry


def resolve_project(manifest: Path | None, registry: Path | None, project_id: str | None) -> Path:
    if manifest:
        return manifest
    if not registry or not project_id:
        raise ValueError('Provide --project or --registry and --project-id')
    data = json.loads(registry.read_text())
    entry = data['projects'][project_id]
    path = Path(entry['manifest'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Registered manifest changed; explicit review required')
    return path


def _initial(project: dict, digest: str) -> dict:
    return {'schema_version': 3, 'project_id': project['project_id'],
            'project_goal': project['goal'], 'success_criteria': project['success_criteria'],
            'manifest_sha256': digest, 'created_at_utc': now(), 'run_ids': [],
            'tasks': {task['id']: {'status': 'PENDING', 'attempts': 0,
                                   'rationale': task['selection_reason'],
                                   'dependencies': task.get('depends_on', []),
                                   'evidence': [], 'updated_at_utc': now()}
                      for task in project['tasks']}, 'events': [], 'selection_log': [],
            'budgets': {'codex_calls': 0, 'tasks_started': 0}, 'next_task': None}


def _load(path: Path, project: dict, digest: str) -> dict:
    state = json.loads(path.read_text()) if path.exists() else _initial(project, digest)
    if (state.get('schema_version') != 3 or state.get('project_id') != project['project_id']
            or state.get('manifest_sha256') != digest
            or set(state.get('tasks', {})) != {t['id'] for t in project['tasks']}
            or any(r.get('status') not in STATES for r in state['tasks'].values())):
        raise ValueError('Checkpoint incompatible or corrupt; inspect and recover manually')
    return state


def _persist(path: Path, state: dict, max_bytes: int) -> None:
    if len(json.dumps(state, ensure_ascii=False).encode('utf-8')) > max_bytes:
        raise RuntimeError('Checkpoint exceeds project state byte budget')
    write_state(path, state)


def _rank(task: dict) -> tuple:
    # Optional evidence-value, cost and risk inputs never override dependencies.
    value = task.get('information_value', 0)
    cost = task.get('estimated_cost', 0)
    if not all(type(x) in (int, float) and 0 <= x <= 100 for x in (value, cost)):
        raise ValueError('Invalid planning value or cost')
    return (task['priority'] - value / 100 + cost / 100,
            task['risk'] != 'read_only', task['id'])


def _select(project: dict, state: dict, excluded: set[str] | None = None) -> dict | None:
    excluded = excluded or set()
    for task in sorted(project['tasks'], key=_rank):
        if task['id'] in excluded:
            continue
        record = state['tasks'][task['id']]
        if record['status'] not in {'PENDING', 'READY', 'FAILED_RETRYABLE', 'BLOCKED_DEPENDENCY'}:
            continue
        if record['status'] == 'FAILED_RETRYABLE' and record['attempts'] >= min(3, project['_limits']['max_retries']):
            continue
        if all(state['tasks'][dep]['status'] == 'COMPLETED' for dep in task.get('depends_on', [])):
            return task
    return None


def _refresh(project: dict, state: dict) -> None:
    for task in project['tasks']:
        record = state['tasks'][task['id']]
        if record['status'] not in {'PENDING', 'BLOCKED_DEPENDENCY'}:
            continue
        dependencies_ok = all(state['tasks'][dep]['status'] == 'COMPLETED' for dep in task.get('depends_on', []))
        if task['risk'] in APPROVAL_RISKS or (task['method'] == 'codex' and not project.get('codex_execution_enabled', False)):
            transition(state, task['id'], 'BLOCKED_APPROVAL', 'Separate approval required')
        elif dependencies_ok:
            transition(state, task['id'], 'READY', 'Dependencies verified')
        elif record['status'] == 'PENDING':
            transition(state, task['id'], 'BLOCKED_DEPENDENCY', 'Waiting for verified dependency')


def _verify(project: dict, task: dict, record: dict) -> tuple[bool, list[dict]]:
    evidence = [_authorized_check(project, check) for check in task['checks']]
    provenance = []
    for check, result in zip(task['checks'], evidence):
        source = {'source_identity': check.get('path'), 'source_timestamp': None,
                  'collection_time': now(), 'point_in_time_available_at': check.get('pit_available_at'),
                  'dataset_version': None, 'code_version': code_version(),
                  'verification_method': check['kind'], 'verification_result': result['ok'],
                  'epistemic_status': 'OBSERVED' if result['ok'] else 'BLOCKED'}
        if check.get('path'):
            path = project['_root'] / check['path']
            stats = path.stat()
            source['source_timestamp'] = stats.st_mtime_ns
            source['dataset_version'] = f'{stats.st_size}:{stats.st_mtime_ns}'
        provenance.append(source)
    record['provenance'] = provenance
    # The model response is recorded, but only independent checks establish completion.
    return all(item['ok'] for item in evidence), evidence


def _outcome(project: dict, state: dict) -> str:
    records = list(state['tasks'].values())
    if any(r['status'] == 'FAILED_TERMINAL' for r in records):
        return 'RESEARCH_FAILED'
    if any(r['status'] in {'BLOCKED_APPROVAL', 'BLOCKED_DATA', 'BLOCKED_QUOTA', 'PAUSED'} for r in records):
        return 'RESEARCH_BLOCKED'
    if all(r['status'] == 'COMPLETED' for r in records):
        checks = project.get('success_checks')
        if checks:
            try:
                if all(_authorized_check(project, check)['ok'] for check in checks):
                    return 'RESEARCH_COMPLETED'
            except (OSError, ValueError, KeyError):
                return 'RESEARCH_BLOCKED'
        return 'RESEARCH_PARTIAL'  # Free-text criteria are not proof.
    if state.get('last_stop_reason') == 'BUDGET':
        return 'RESEARCH_BUDGET_EXHAUSTED'
    return 'RESEARCH_PARTIAL'


def operate(mode: str, config_path: Path, state_dir: Path, executor=None,
            max_tasks: int = 3, max_seconds: int = 1800,
            task_id: str | None = None, resolution: str | None = None) -> dict:
    if mode not in {'inspect', 'plan', 'dry-run', 'run-once', 'run-bounded', 'resume', 'status', 'report', 'stop', 'recover'}:
        raise ValueError('Unknown supervisor mode')
    if not 1 <= max_tasks <= 3 or not 1 <= max_seconds <= 1800:
        raise ValueError('Bounded run caps are 3 tasks and 1800 seconds')
    project, digest = load_runner_project(config_path)
    max_tasks = min(max_tasks, project['_limits']['max_iterations'])
    max_seconds = min(max_seconds, project['_limits']['max_runtime_seconds'])
    state_path = state_dir / 'state.json'
    if mode in {'inspect', 'dry-run', 'status', 'report'}:
        state = _load(state_path, project, digest)
        selected = _select(project, state)
        return _report(mode, project, state, selected)
    with locked_state(state_dir) as locked_path:
        state = _load(locked_path, project, digest)
        state['runner_code_version'] = code_version()
        if mode == 'recover':
            if resolution == 'clear-stop' and task_id is None:
                (state_dir / 'STOP').unlink(missing_ok=True)
                state['events'].append({'at_utc': now(), 'action': 'stop_cleared_by_operator'})
                _persist(locked_path, state, project['_limits']['max_state_bytes'])
                return _report(mode, project, state, _select(project, state))
            if not task_id or task_id not in state['tasks'] or resolution not in {'retry', 'cancel'}:
                raise ValueError('recover requires a known task and retry or cancel resolution')
            record = state['tasks'][task_id]
            if record['status'] not in {'PAUSED', 'BLOCKED_QUOTA'}:
                raise ValueError('Only an explicitly reviewed PAUSED or BLOCKED_QUOTA task can be recovered')
            task = next(t for t in project['tasks'] if t['id'] == task_id)
            if resolution == 'retry' and (task['risk'] != 'read_only' or
                    record['attempts'] >= min(3, project['_limits']['max_retries'])):
                raise ValueError('Read-only retry budget exceeded or task requires approval')
            if record['status'] == 'BLOCKED_QUOTA':
                # Operator recovery confirms provider access and review of partial output.
                state['quota_blocked'] = False
            transition(state, task_id, 'READY' if resolution == 'retry' else 'CANCELLED',
                       'Explicit operator recovery: ' + resolution)
            _persist(locked_path, state, project['_limits']['max_state_bytes'])
            return _report(mode, project, state, _select(project, state))
        if mode == 'stop':
            (state_dir / 'STOP').write_text(now() + '\n')
            state['events'].append({'at_utc': now(), 'action': 'stop_requested'})
            _persist(locked_path, state, project['_limits']['max_state_bytes'])
            return _report(mode, project, state, None)
        if mode == 'plan':
            _refresh(project, state)
            selected = _select(project, state)
            state['next_task'] = selected['id'] if selected else None
            _persist(locked_path, state, project['_limits']['max_state_bytes'])
            return _report(mode, project, state, selected)
        if (state_dir / 'STOP').exists():
            return _report(mode, project, state, None)
        if state.get('quota_blocked') or any(r['status'] == 'BLOCKED_QUOTA' for r in state['tasks'].values()):
            return _report(mode, project, state, None)
        for task in project['tasks']:
            record = state['tasks'][task['id']]
            if record['status'] == 'RUNNING':
                transition(state, task['id'], 'PAUSED', 'Interrupted; outcome uncertain, no automatic rerun')
            elif record['status'] == 'VERIFYING':
                try:
                    ok, evidence = _verify(project, task, record)
                    record['evidence'] = evidence
                    transition(state, task['id'], 'COMPLETED' if ok else 'BLOCKED_DATA',
                               'Recovered independent verification')
                except (OSError, ValueError, KeyError) as exc:
                    transition(state, task['id'], 'PAUSED', 'Recovery verification failed: ' + str(exc))
        _refresh(project, state)
        run_id = str(uuid.uuid4())
        state['last_stop_reason'] = None
        state['run_ids'] = (state['run_ids'] + [run_id])[-30:]
        _persist(locked_path, state, project['_limits']['max_state_bytes'])
        started = time.monotonic()
        completed_or_started = 0
        attempted = set()
        executor = executor or CodexExecutor()
        while completed_or_started < (1 if mode == 'run-once' else max_tasks):
            if (state_dir / 'STOP').exists() or time.monotonic() - started >= max_seconds:
                state['last_stop_reason'] = 'STOP' if (state_dir / 'STOP').exists() else 'BUDGET'
                break
            task = _select(project, state, attempted)
            if task is None:
                break
            attempted.add(task['id'])
            record = state['tasks'][task['id']]
            if record['status'] == 'FAILED_RETRYABLE':
                if time.monotonic() - started + 1 >= max_seconds:
                    break
                time.sleep(min(2 ** max(0, record['attempts'] - 1), 4))
                transition(state, task['id'], 'READY', 'Bounded transient retry')
            if task['method'] == 'codex':
                if (state['budgets']['codex_calls'] >= project['_limits']['max_external_calls']
                        or shutil.disk_usage(project['_root']).free < project['_limits']['min_free_bytes']):
                    transition(state, task['id'], 'PAUSED', 'Codex or disk budget exhausted')
                    state['last_stop_reason'] = 'BUDGET'
                    break
            rationale = {'at_utc': now(), 'task_id': task['id'], 'chosen_because': task['selection_reason'],
                         'alternatives': [t['id'] for t in project['tasks'] if t['id'] != task['id']
                                          and state['tasks'][t['id']]['status'] == 'READY'],
                         'success_condition': task['success_condition']}
            state['selection_log'] = (state['selection_log'] + [rationale])[-100:]
            record['attempts'] += 1
            record['execution_id'] = str(uuid.uuid4())
            record['code_version'] = code_version()
            record['manifest_sha256'] = digest
            record['idempotency_key'] = hashlib.sha256(
                f"{digest}:{task['id']}:{record['attempts']}".encode()).hexdigest()
            transition(state, task['id'], 'RUNNING', 'Execution started')
            state['budgets']['tasks_started'] += 1
            _persist(locked_path, state, project['_limits']['max_state_bytes'])
            completed_or_started += 1
            if task['method'] == 'codex':
                state['budgets']['codex_calls'] += 1
                bounded = dict(project)
                bounded['_limits'] = dict(project['_limits'], max_runtime_seconds=max(1, min(
                    project['_limits']['max_runtime_seconds'], int(max_seconds - (time.monotonic() - started)))))
                try:
                    result = executor.execute(bounded, task, state_dir)
                except Exception as exc:
                    result = {'ok': False, 'classification': classify(str(exc), 1),
                              'reason': (type(exc).__name__ + ': ' + str(exc))[:180]}
            else:
                result = {'ok': True, 'classification': None, 'reason': '', 'response': None}
            record['execution'] = result
            if task['method'] == 'codex':
                record['model_claim_status'] = 'UNVERIFIED'
            if not result.get('ok'):
                category = result.get('classification', 'EXECUTION')
                if category == 'QUOTA':
                    record['reported_retry_time'] = result.get('reported_retry_time')
                    state['quota_blocked'] = True
                    state['last_stop_reason'] = 'QUOTA'
                    transition(state, task['id'], 'BLOCKED_QUOTA',
                               'Provider usage quota exhausted; review partial output before manual recovery')
                    _persist(locked_path, state, project['_limits']['max_state_bytes'])
                    break
                retryable = category in {'NETWORK', 'PROVIDER'} and record['attempts'] < min(3, project['_limits']['max_retries'])
                transition(state, task['id'], 'FAILED_RETRYABLE' if retryable else 'FAILED_TERMINAL',
                           result.get('reason', 'Execution failed'))
                _persist(locked_path, state, project['_limits']['max_state_bytes'])
                break
            transition(state, task['id'], 'VERIFYING', 'Execution returned; checking independent evidence')
            _persist(locked_path, state, project['_limits']['max_state_bytes'])
            try:
                verified, evidence = _verify(project, task, record)
                record['evidence'] = evidence
                transition(state, task['id'], 'COMPLETED' if verified else 'BLOCKED_DATA',
                           'Independent evidence passed' if verified else 'Independent evidence failed')
            except (OSError, ValueError, KeyError) as exc:
                transition(state, task['id'], 'BLOCKED_DATA', 'Evidence error: ' + str(exc)[:180])
            _refresh(project, state)
            selected = _select(project, state)
            state['next_task'] = selected['id'] if selected else None
            _persist(locked_path, state, project['_limits']['max_state_bytes'])
            # An independently eligible safe task can still make progress
            # after this task is blocked; the failed task is excluded here.
        selected = _select(project, state)
        state['next_task'] = selected['id'] if selected else None
        if selected and completed_or_started >= (1 if mode == 'run-once' else max_tasks):
            state['last_stop_reason'] = 'BUDGET'
        _persist(locked_path, state, project['_limits']['max_state_bytes'])
        return _report(mode, project, state, selected)


def _report(mode: str, project: dict, state: dict, selected: dict | None) -> dict:
    ranked = sorted(project['tasks'], key=_rank)
    plan = [{'task_id': task['id'], 'status': state['tasks'][task['id']]['status'],
             'priority': task['priority'], 'information_value': task.get('information_value', 0),
             'estimated_cost': task.get('estimated_cost', 0), 'risk': task['risk'],
             'dependencies': task.get('depends_on', []),
             'selection_reason': task['selection_reason'],
             'success_condition': task['success_condition']}
            for task in ranked]
    preview = None
    if mode in {'inspect', 'dry-run', 'plan'} and selected:
        try:
            preview = [_authorized_check(project, check) for check in selected['checks']]
        except (OSError, ValueError, KeyError) as exc:
            preview = {'error': (type(exc).__name__ + ': ' + str(exc))[:180]}
    return {'mode': mode, 'project_id': project['project_id'],
            'next_task': selected['id'] if selected else None,
            'outcome': _outcome(project, state),
            'statuses': {task_id: record['status'] for task_id, record in state['tasks'].items()},
            'budgets': state['budgets'], 'plan': plan, 'evidence_preview': preview,
            'selection_log': state['selection_log'][-3:],
            'tasks': state['tasks'] if mode == 'report' else None}
