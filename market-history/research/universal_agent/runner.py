"""Bounded autonomous runner layered on the Phase 2 evidence engine.

Task manifests are data, never shell commands. The only model capability is a
read-only, noninteractive Codex invocation in a declared Git worktree.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol

from .engine import SAFE_KINDS, check_evidence, locked_state, now, write_state

CLASSIFICATIONS = {'NETWORK', 'PROVIDER', 'QUOTA', 'AUTH', 'CODE', 'DATA_QUALITY',
                   'VERIFICATION', 'PERMISSION', 'RESOURCE', 'EXECUTION'}
RETRYABLE = {'NETWORK', 'PROVIDER'}
APPROVAL_RISKS = {'research_write', 'operating_code', 'operating_db',
                  'service_restart', 'live_order', 'credential_change',
                  'delete_data', 'bulk_recollect', 'force_push'}
DEFAULT_LIMITS = {'max_runtime_seconds': 120, 'max_iterations': 3,
                  'max_retries': 3, 'max_concurrency': 1,
                  'max_processes': 1,
                  'min_free_bytes': 5 * 1024**3,
                  'max_state_bytes': 10 * 1024**2,
                  'max_log_bytes': 128 * 1024,
                  'max_external_calls': 1}
FINAL_SCHEMA = {
    'type': 'object',
    'properties': {
        'task_id': {'type': 'string'},
        'outcome': {'type': 'string'},
        'evidence': {'type': 'array', 'items': {'type': 'string'}},
        'next_action': {'type': 'string'},
    },
    'required': ['task_id', 'outcome', 'evidence', 'next_action'],
    'additionalProperties': False,
}


def _inside(root: Path, relative: str) -> Path:
    part = Path(relative)
    if part.is_absolute() or '..' in part.parts or not relative:
        raise ValueError('Path must stay inside project root')
    path = (root / part).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError('Path escapes project root')
    return path


def load_runner_project(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    item = json.loads(raw)
    if item.get('schema_version') != 2:
        raise ValueError('Runner requires a version 2 manifest; Phase 2 manifests remain supported by the Phase 2 CLI')
    project_id = item.get('project_id')
    if not isinstance(project_id, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{1,63}', project_id):
        raise ValueError('Invalid project ID')
    if not isinstance(item.get('goal'), str) or not item['goal'].strip():
        raise ValueError('Research goal required')
    if not isinstance(item.get('success_criteria'), list) or not item['success_criteria']:
        raise ValueError('Success criteria required')
    if type(item.get('codex_execution_enabled', False)) is not bool:
        raise ValueError('codex_execution_enabled must be boolean')
    root = Path(item['workspace_root']).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Project root must be a directory')
    access = item.get('data_access')
    if not isinstance(access, list) or not access:
        raise ValueError('Project requires explicit data_access paths')
    allowed = [_inside(root, relative) for relative in access]
    for key in ('research_questions', 'data_sources', 'allowed_operations', 'constraints'):
        value = item.get(key, [])
        if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValueError(key + ' must be a list of nonempty strings')
    if item.get('success_checks') is not None:
        checks = item['success_checks']
        if (not isinstance(checks, list) or len(checks) != len(item['success_criteria'])
                or any(not isinstance(c, dict) or c.get('kind') not in SAFE_KINDS for c in checks)):
            raise ValueError('Each success criterion needs one registered evidence check')
        for check in checks:
            if check['kind'] != 'review_required':
                evidence = _inside(root, check['path'])
                if not any(evidence == scope or evidence.is_relative_to(scope) for scope in allowed):
                    raise ValueError('Success check is outside project data_access')
    limits = DEFAULT_LIMITS | item.get('limits', {})
    if set(limits) != set(DEFAULT_LIMITS) or any(type(v) is not int or v < 1 for v in limits.values()):
        raise ValueError('Limits must be positive integers with known names')
    if limits['max_concurrency'] != 1:
        raise ValueError('Only one task at a time is supported')
    if limits['max_processes'] != 1:
        raise ValueError('Only one child process at a time is supported')
    tasks = item.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('Project requires tasks')
    ids = [task.get('id') for task in tasks]
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', i) for i in ids):
        raise ValueError('Task IDs must be unique and simple')
    for task in tasks:
        if type(task.get('priority')) is not int or task['priority'] < 0:
            raise ValueError('Invalid priority')
        if task.get('method') not in {'probe', 'codex'} or task.get('risk') not in ({'read_only'} | APPROVAL_RISKS):
            raise ValueError('Invalid method or risk')
        for key in ('goal_relation', 'selection_reason', 'success_condition', 'verification_method'):
            if not isinstance(task.get(key), str) or not task[key].strip():
                raise ValueError('Task metadata missing: ' + key)
        deps = task.get('depends_on', [])
        if not isinstance(deps, list) or any(dep not in ids or dep == task['id'] for dep in deps):
            raise ValueError('Invalid dependency')
        if task['method'] == 'codex':
            if not isinstance(task.get('prompt'), str) or not task['prompt'].strip():
                raise ValueError('Codex task needs a prompt')
        checks = task.get('checks')
        if (not isinstance(checks, list) or not checks or
                any(not isinstance(c, dict) or c.get('kind') not in SAFE_KINDS for c in checks)):
            raise ValueError('Task requires registered evidence checks')
        for check in checks:
            if check['kind'] != 'review_required':
                evidence = _inside(root, check['path'])
                if not any(evidence == scope or evidence.is_relative_to(scope) for scope in allowed):
                    raise ValueError('Evidence path is outside project data_access')
    graph = {task['id']: task.get('depends_on', []) for task in tasks}
    visiting, visited = set(), set()

    def visit(task_id):
        if task_id in visiting:
            raise ValueError('Dependency cycle')
        if task_id in visited:
            return
        visiting.add(task_id)
        for dep in graph[task_id]:
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in ids:
        visit(task_id)
    item['_root'] = root
    item['_allowed'] = allowed
    item['_limits'] = limits
    return item, hashlib.sha256(raw).hexdigest()


def new_state(project: dict, digest: str) -> dict:
    return {'schema_version': 2, 'project_id': project['project_id'],
            'manifest_sha256': digest, 'goal': project['goal'],
            'success_criteria': project['success_criteria'], 'updated_at_utc': now(),
            'tasks': {task['id']: {'status': 'PENDING', 'attempts': 0, 'evidence': [],
                                   'classification': None, 'reason': ''}
                      for task in project['tasks']}, 'events': [], 'plan_changes': [],
            'external_calls': 0}


def state_for(project: dict, digest: str, path: Path) -> dict:
    if path.exists():
        state = json.loads(path.read_text(encoding='utf-8'))
        if state.get('project_id') != project['project_id'] or state.get('manifest_sha256') != digest:
            raise ValueError('Project manifest changed; review and use a new state directory')
    else:
        state = new_state(project, digest)
    return state


def ranked_tasks(project: dict, state: dict) -> list[dict]:
    return sorted(project['tasks'], key=lambda t: (t['priority'], t['id']))


def next_task(project: dict, state: dict, excluded: set[str] | None = None) -> dict | None:
    excluded = excluded or set()
    for task in ranked_tasks(project, state):
        if task['id'] in excluded:
            continue
        record = state['tasks'][task['id']]
        eligible = record['status'] == 'PENDING' or (
            record['status'] == 'FAILED' and
            (record['classification'] in RETRYABLE or record.get('retryable', False))
            and record['attempts'] < project['_limits']['max_retries'])
        if eligible and all(state['tasks'][d]['status'] == 'COMPLETED' for d in task.get('depends_on', [])):
            return task
    return None


def plan_snapshot(project: dict, state: dict, include_evidence: bool = False) -> dict:
    selected = next_task(project, state)
    snapshot = {'goal': project['goal'], 'success_criteria': project['success_criteria'],
            'selected_task': selected['id'] if selected else None,
            'tasks': [{key: task.get(key) for key in ('id', 'goal_relation', 'selection_reason',
                       'priority', 'depends_on', 'method', 'risk', 'success_condition',
                       'verification_method')}
                      | {'status': state['tasks'][task['id']]['status']}
                      for task in ranked_tasks(project, state)]}
    if include_evidence and selected:
        try:
            snapshot['evidence_preview'] = [_authorized_check(project, check)
                                            for check in selected['checks']]
        except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
            snapshot['evidence_error'] = type(exc).__name__ + ': ' + str(exc)[:180]
    return snapshot


def record_plan(project: dict, state: dict) -> None:
    snapshot = plan_snapshot(project, state, include_evidence=True)
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if state.get('plan_sha256') != digest:
        old = state.get('plan')
        if old is None:
            reason = 'Initial plan generated from project goal, success criteria and registered tasks'
        else:
            previous = {task['id']: task['status'] for task in old['tasks']}
            changes = [task['id'] + ':' + previous.get(task['id'], 'NEW') + '->' + task['status']
                       for task in snapshot['tasks'] if previous.get(task['id']) != task['status']]
            reason = 'Task evidence/status changed: ' + ', '.join(changes)
            if old['selected_task'] != snapshot['selected_task']:
                reason += '; next task ' + str(old['selected_task']) + '->' + str(snapshot['selected_task'])
            if old.get('evidence_preview') != snapshot.get('evidence_preview'):
                reason += '; selected-task evidence preview changed'
        state['plan_changes'].append({'at_utc': now(), 'reason': reason,
                                      'previous_sha256': state.get('plan_sha256'), 'sha256': digest})
        state['plan_sha256'] = digest
    state['plan'] = snapshot


def classify(message: str, returncode: int) -> str:
    lowered = message.lower()
    if any(word in lowered for word in ('usage limit', 'usage quota', 'quota exceeded',
                                         'insufficient quota', 'out of credits',
                                         'you have reached your limit', "you've hit your usage limit")):
        return 'QUOTA'
    if 'error loading rules' in lowered or 'starlark error' in lowered:
        return 'CODE'
    if any(word in lowered for word in ('not logged in', 'authentication', 'unauthorized')):
        return 'AUTH'
    if any(word in lowered for word in ('permission denied', 'sandbox denied', 'approval required')):
        return 'PERMISSION'
    if any(word in lowered for word in ('rate limit', 'provider unavailable', 'server error')):
        return 'PROVIDER'
    if any(word in lowered for word in ('connection', 'dns', 'timeout', 'network')):
        return 'NETWORK'
    if any(word in lowered for word in ('disk full', 'no space', 'resource limit')):
        return 'RESOURCE'
    if returncode:
        return 'EXECUTION'
    return 'VERIFICATION'


class Executor(Protocol):
    def execute(self, project: dict, task: dict, state_dir: Path) -> dict: ...


class CodexExecutor:
    """Only the installed CLI's verified read-only options are used."""

    REQUIRED_FLAGS = ('--sandbox', '--json', '--ephemeral', '--output-schema',
                      '--output-last-message', '--cd')

    def __init__(self, binary: str = 'codex'):
        self.binary = binary

    def preflight(self, max_seconds: int = 30) -> dict:
        binary = shutil.which(self.binary)
        if not binary:
            raise RuntimeError('CODEX_NOT_INSTALLED')
        deadline = time.monotonic() + max_seconds

        def probe(args):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('CODEX_PREFLIGHT_TIMEOUT')
            return subprocess.run(args, capture_output=True, text=True,
                                  timeout=min(10, remaining))

        version = probe([binary, '--version'])
        help_result = probe([binary, 'exec', '--help'])
        auth = probe([binary, 'login', 'status'])
        if version.returncode or help_result.returncode or any(flag not in help_result.stdout for flag in self.REQUIRED_FLAGS):
            raise RuntimeError('CODEX_UNSUPPORTED_CLI')
        if auth.returncode or 'logged in' not in (auth.stdout + auth.stderr).lower():
            raise RuntimeError('CODEX_NOT_AUTHENTICATED')
        return {'binary': binary, 'version': version.stdout.strip()}

    def execute(self, project: dict, task: dict, state_dir: Path) -> dict:
        started = time.monotonic()
        meta = self.preflight(project['_limits']['max_runtime_seconds'])
        schema_path = state_dir / 'codex_response.schema.json'
        output_path = state_dir / (task['id'] + '-' + str(time.time_ns()) + '.last.json')
        schema_path.write_text(json.dumps(FINAL_SCHEMA), encoding='utf-8')
        prompt = ('Read-only research task. Do not edit files, run services, access credentials, '
                  'or claim verification from your own answer. Return only the required JSON.\n'
                  f"Project goal: {project['goal']}\nTask ID: {task['id']}\n"
                  f"Task: {task['prompt']}\nSuccess condition: {task['success_condition']}")
        with tempfile.TemporaryDirectory(prefix='codex-readonly-', dir=state_dir) as scratch:
            workdir = Path(scratch)
            subprocess.run(['git', 'init', '-q', str(workdir)], check=True, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            command = [meta['binary'], 'exec', '--sandbox', 'read-only', '--json', '--ephemeral',
                       '-C', str(workdir), '--output-schema', str(schema_path),
                       '-o', str(output_path), prompt]
            allowed_env = {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TERM',
                           'CODEX_HOME', 'XDG_RUNTIME_DIR', 'HTTPS_PROXY', 'HTTP_PROXY',
                           'ALL_PROXY', 'NO_PROXY', 'SSL_CERT_FILE'}
            child_env = {key: value for key, value in os.environ.items() if key in allowed_env}
            process = subprocess.Popen(command, cwd=workdir, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True,
                                       env=child_env)
            try:
                remaining = max(1, project['_limits']['max_runtime_seconds'] -
                                (time.monotonic() - started))
                stdout, stderr = process.communicate(timeout=remaining)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                return {'ok': False, 'classification': 'RESOURCE', 'reason': 'Codex timeout',
                        'returncode': None, 'version': meta['version']}
        cap = project['_limits']['max_log_bytes']
        if len(stdout) > cap or len(stderr) > cap or (output_path.exists() and output_path.stat().st_size > cap):
            return {'ok': False, 'classification': 'RESOURCE', 'reason': 'Codex log limit exceeded',
                    'returncode': process.returncode, 'version': meta['version']}
        # Do not persist raw event streams: they may contain excerpts of private context.
        if process.returncode:
            diagnostic = stderr.decode(errors='replace')
            for line in stdout.decode(errors='replace').splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('type') in {'error', 'turn.failed'}:
                    diagnostic += '\n' + str(event.get('message', event.get('error', '')))
            category = classify(diagnostic, process.returncode)
            location = re.search(r'([A-Za-z0-9_.-]+\.rules:\d+)', diagnostic)
            reason = ('Codex usage quota exhausted' if category == 'QUOTA' else
                      'Codex execpolicy parse error at ' + location.group(1)
                      if category == 'CODE' and location else
                      'Codex exited with status ' + str(process.returncode))
            retry_match = re.search(r'(?:retry|try again|resets?|reset)\s+(?:at|after|in)\s+([A-Za-z0-9:,+. /-]{1,64})',
                                    diagnostic, re.IGNORECASE) if category == 'QUOTA' else None
            return {'ok': False, 'classification': category,
                    'reason': reason,
                    'reported_retry_time': retry_match.group(1).strip() if retry_match else None,
                    'partial_output_path': str(output_path) if output_path.exists() else None,
                    'returncode': process.returncode, 'version': meta['version']}
        try:
            payload = json.loads(output_path.read_text(encoding='utf-8'))
            if (set(payload) != set(FINAL_SCHEMA['required']) or payload['task_id'] != task['id']
                    or not isinstance(payload['outcome'], str)
                    or not isinstance(payload['next_action'], str)
                    or not isinstance(payload['evidence'], list)
                    or any(not isinstance(item, str) for item in payload['evidence'])):
                raise ValueError('Invalid structured response')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {'ok': False, 'classification': 'CODE', 'reason': type(exc).__name__,
                    'returncode': process.returncode, 'version': meta['version']}
        return {'ok': True, 'classification': None, 'reason': '', 'returncode': 0,
                'version': meta['version'], 'response': payload}


def _resource_check(project: dict, state_dir: Path, calls_this_run: int) -> str | None:
    limits = project['_limits']
    if shutil.disk_usage(project['_root']).free < limits['min_free_bytes']:
        return 'Disk free space below project floor'
    state_bytes = sum(path.stat().st_size for path in state_dir.rglob('*') if path.is_file())
    if state_bytes >= limits['max_state_bytes']:
        return 'Runner state artifact limit reached'
    if calls_this_run >= limits['max_external_calls']:
        return 'External Codex invocation budget exhausted'
    return None


def _authorized_check(project: dict, check: dict) -> dict:
    if check['kind'] != 'review_required':
        evidence = _inside(project['_root'], check['path'])
        scopes = [_inside(project['_root'], path) for path in project['data_access']]
        if not any(evidence == scope or evidence.is_relative_to(scope) for scope in scopes):
            raise ValueError('Evidence path left project data_access')
    return check_evidence(project['_root'], check)


def _run_task(project: dict, state: dict, task: dict, state_dir: Path,
              state_path: Path, executor: Executor, calls_this_run: list[int],
              remaining_seconds: int) -> None:
    record = state['tasks'][task['id']]
    if task['risk'] in APPROVAL_RISKS:
        record.update(status='BLOCKED_APPROVAL', classification='PERMISSION',
                      reason='Task risk requires explicit approval outside autonomous runner')
        state['events'].append({'at_utc': now(), 'task': task['id'], 'status': 'BLOCKED_APPROVAL'})
        return
    if task['method'] == 'codex' and not project.get('codex_execution_enabled', False):
        record.update(status='BLOCKED_APPROVAL', classification='PERMISSION',
                      reason='Codex execution is disabled for this project')
        state['events'].append({'at_utc': now(), 'task': task['id'], 'status': 'BLOCKED_APPROVAL'})
        return
    if task['method'] == 'codex':
        resource_reason = _resource_check(project, state_dir, calls_this_run[0])
        if resource_reason:
            record.update(status='BLOCKED', classification='RESOURCE', reason=resource_reason)
            state['events'].append({'at_utc': now(), 'task': task['id'], 'status': 'BLOCKED'})
            return
    record['status'] = 'IN_PROGRESS'
    record['attempts'] += 1
    state['events'].append({'at_utc': now(), 'task': task['id'], 'status': 'IN_PROGRESS'})
    if task['method'] == 'codex':
        calls_this_run[0] += 1
        state['external_calls'] += 1
    write_state(state_path, state)
    if task['method'] == 'codex':
        try:
            bounded = dict(project)
            bounded['_limits'] = dict(project['_limits'], max_runtime_seconds=remaining_seconds)
            result = executor.execute(bounded, task, state_dir)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            message = str(exc)
            result = {'ok': False, 'classification': classify(message, 1),
                      'reason': message[:180]}
            if message == 'CODEX_NOT_AUTHENTICATED':
                result['classification'] = 'AUTH'
            elif message == 'CODEX_NOT_INSTALLED':
                result['classification'] = 'RESOURCE'
            elif message == 'CODEX_PREFLIGHT_TIMEOUT' or isinstance(exc, subprocess.TimeoutExpired):
                result['classification'] = 'RESOURCE'
        record['execution'] = result
        if not result['ok']:
            if result['classification'] == 'QUOTA':
                record.update(status='BLOCKED', classification='QUOTA',
                              reason='Provider usage quota exhausted; review before new invocation',
                              retryable=False)
                state['quota_blocked'] = True
                state['events'].append({'at_utc': now(), 'task': task['id'],
                                        'status': 'BLOCKED', 'classification': 'QUOTA'})
                return
            record.update(status='FAILED', classification=result['classification'], reason=result['reason'],
                          retryable=result['classification'] in RETRYABLE)
            state['events'].append({'at_utc': now(), 'task': task['id'], 'status': 'FAILED',
                                    'classification': result['classification']})
            return
    try:
        evidence = [_authorized_check(project, check) for check in task['checks']]
        record['evidence'] = evidence
        if not all(item['ok'] for item in evidence):
            record.update(status='BLOCKED', classification='VERIFICATION',
                          reason='Evidence gate did not pass', retryable=False)
        else:
            record.update(status='VERIFIED', classification=None, reason='', retryable=False)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        record.update(status='FAILED', classification='DATA_QUALITY',
                      reason=(type(exc).__name__ + ': ' + str(exc))[:180], retryable=False)
    state['events'].append({'at_utc': now(), 'task': task['id'], 'status': record['status']})
    if record['status'] == 'VERIFIED':
        record['status'] = 'COMPLETED'
        state['events'].append({'at_utc': now(), 'task': task['id'], 'status': 'COMPLETED'})


def summary(state: dict) -> dict:
    statuses = {key: value['status'] for key, value in state['tasks'].items()}
    total = len(statuses)
    attention = next((key for key, value in statuses.items()
                      if value in {'BLOCKED', 'BLOCKED_APPROVAL', 'FAILED'}), None)
    return {'total': total, 'completed': sum(value == 'COMPLETED' for value in statuses.values()),
            'failed': [key for key, value in statuses.items() if value == 'FAILED'],
            'blocked': [key for key, value in statuses.items()
                        if value in {'BLOCKED', 'BLOCKED_APPROVAL'}],
            'progress_pct': round(100 * sum(value == 'COMPLETED' for value in statuses.values()) / total, 2),
            'next_task': state.get('next_task'), 'attention_task': attention,
            'attention_reason': state['tasks'][attention]['reason'] if attention else None}


def operate(mode: str, config_path: Path, state_dir: Path, executor: Executor | None = None) -> dict:
    """Run one bounded action or inspect/plan without invoking Codex."""
    if mode not in {'inspect', 'plan', 'dry-run', 'run-once', 'resume', 'status'}:
        raise ValueError('Unknown mode')
    project, digest = load_runner_project(config_path)
    state_path = state_dir / 'state.json'
    if mode in {'inspect', 'dry-run', 'status'}:
        state = state_for(project, digest, state_path)
        snapshot = plan_snapshot(project, state, include_evidence=mode == 'inspect')
        selected = next_task(project, state)
        state['next_task'] = selected['id'] if selected else None
        result = {'mode': mode, 'project_id': project['project_id'],
                  'plan': snapshot, 'next_task': selected['id'] if selected else None,
                  'statuses': {key: value['status'] for key, value in state['tasks'].items()},
                  'summary': summary(state)}
        if mode == 'dry-run' and selected:
            result['would_execute'] = {'task_id': selected['id'], 'method': selected['method'],
                                       'risk': selected['risk'], 'checks': selected['checks']}
            try:
                result['dry_run_evidence'] = [_authorized_check(project, c)
                                              for c in selected['checks']]
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                result['dry_run_error'] = type(exc).__name__ + ': ' + str(exc)[:180]
        return result
    if mode == 'plan':
        with locked_state(state_dir) as locked_path:
            state = state_for(project, digest, locked_path)
            record_plan(project, state)
            state['next_task'] = (next_task(project, state) or {}).get('id')
            write_state(locked_path, state)
            return {'mode': mode, 'project_id': project['project_id'],
                    'plan': state['plan'], 'state_path': str(locked_path),
                    'summary': summary(state)}
    executor = executor or CodexExecutor()
    started = time.monotonic()
    with locked_state(state_dir) as state_path:
        state = state_for(project, digest, state_path)
        if state.get('quota_blocked'):
            return {'mode': mode, 'project_id': project['project_id'],
                    'next_task': None,
                    'statuses': {key: value['status'] for key, value in state['tasks'].items()},
                    'state_path': str(state_path), 'summary': summary(state)}
        for task_id, record in state['tasks'].items():
            if record['status'] == 'IN_PROGRESS':
                record.update(status='FAILED', classification='EXECUTION',
                              reason='Previous process interrupted before verification',
                              retryable=True)
                state['events'].append({'at_utc': now(), 'task': task_id, 'status': 'FAILED'})
        record_plan(project, state)
        write_state(state_path, state)
        attempted = set()
        calls_this_run = [0]
        iterations = 1 if mode == 'run-once' else project['_limits']['max_iterations']
        for _ in range(iterations):
            if time.monotonic() - started >= project['_limits']['max_runtime_seconds']:
                break
            task = next_task(project, state, attempted)
            if not task:
                break
            attempted.add(task['id'])
            remaining = max(1, int(project['_limits']['max_runtime_seconds'] -
                                   (time.monotonic() - started)))
            _run_task(project, state, task, state_dir, state_path, executor,
                      calls_this_run, remaining)
            record_plan(project, state)
            write_state(state_path, state)
            if state['tasks'][task['id']]['status'] in {'FAILED', 'BLOCKED', 'BLOCKED_APPROVAL'}:
                break
        state['next_task'] = (next_task(project, state) or {}).get('id')
        write_state(state_path, state)
        return {'mode': mode, 'project_id': project['project_id'], 'next_task': state['next_task'],
                'statuses': {key: value['status'] for key, value in state['tasks'].items()},
                'state_path': str(state_path), 'summary': summary(state)}
