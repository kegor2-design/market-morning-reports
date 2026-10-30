"""Small, deterministic research coordinator with read-only evidence probes.

No shell, network, service, or database mutation capability is registered here.
The executor boundary is intentionally an explicit list of probe kinds.
"""
from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {'PENDING', 'IN_PROGRESS', 'BLOCKED', 'FAILED', 'VERIFIED', 'COMPLETED'}
SAFE_KINDS = {'file_exists', 'json_equals', 'csv_unique_count', 'csv_financial_quality',
              'sqlite_integrity', 'sqlite_count', 'review_required'}
IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')


def load_project(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    config = json.loads(raw)
    if config.get('schema_version') != 1 or not isinstance(config.get('project_id'), str):
        raise ValueError('Unsupported project manifest')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,63}', config['project_id']):
        raise ValueError('Invalid project ID')
    root = Path(config['workspace_root']).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Workspace root is not a directory')
    tasks = config.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('At least one task is required')
    ids = [task['id'] for task in tasks]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r'[a-z][a-z0-9_]*', i) for i in ids):
        raise ValueError('Task IDs must be unique and simple')
    for task in tasks:
        if not isinstance(task.get('priority'), int) or task['priority'] < 0:
            raise ValueError('Task priority must be a nonnegative integer')
        if not isinstance(task.get('depends_on', []), list):
            raise ValueError('depends_on must be a list')
        if any(dep not in ids or dep == task['id'] for dep in task.get('depends_on', [])):
            raise ValueError('Unknown or self dependency')
        checks = task.get('checks')
        if not isinstance(checks, list) or not checks:
            raise ValueError('Each task requires evidence checks')
        if any(not isinstance(check, dict) or check.get('kind') not in SAFE_KINDS
               for check in checks):
            raise ValueError('Unsupported check kind')
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
    config['_root'] = root
    return config, hashlib.sha256(raw).hexdigest()


def evidence_path(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
            or '..' in Path(relative).parts):
        raise ValueError('Evidence path must be relative to workspace root')
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Evidence path escapes workspace or is not a file')
    return path


def check_evidence(root: Path, check: dict) -> dict:
    kind = check['kind']
    if kind == 'review_required':
        return {'kind': kind, 'ok': False,
                'reason': check.get('reason', 'Independent review is required')}
    path = evidence_path(root, check['path'])
    result = {'kind': kind, 'path': check['path'], 'ok': False}
    if kind == 'file_exists':
        result.update(ok=True, bytes=path.stat().st_size)
    elif kind == 'json_equals':
        value = json.loads(path.read_text(encoding='utf-8'))
        for part in check['pointer'].strip('/').split('/'):
            value = value[int(part)] if isinstance(value, list) else value[part]
        result.update(actual=value, expected=check['equals'], ok=value == check['equals'])
    elif kind == 'csv_unique_count':
        field = check['field']
        expected = check['equals']
        with path.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            if field not in (reader.fieldnames or []):
                raise ValueError('CSV field missing')
            values = [row[field] for row in reader]
        result.update(actual=len(values), unique=len(set(values)), expected=expected,
                      ok=len(values) == len(set(values)) == expected)
    elif kind == 'csv_financial_quality':
        # Optional fields support project-specific corporate-action, parity,
        # costs and walk-forward evidence without certifying absent fields.
        required = check.get('required_fields', [])
        if not isinstance(required, list) or any(not isinstance(v, str) for v in required):
            raise ValueError('Invalid required financial fields')
        key_fields = check.get('unique_key', ['symbol', 'date'])
        if not isinstance(key_fields, list) or not key_fields:
            raise ValueError('Financial unique_key required')
        duplicates = missing = lookahead = 0
        seen = set()
        count = 0
        with path.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            needed = set(key_fields) | set(required) | {'release_at', 'vintage_at',
                                                       'available_at', 'asof_at', 'source_id'}
            if not needed <= fields:
                raise ValueError('Missing financial fields: ' + ','.join(sorted(needed - fields)))
            for row in reader:
                count += 1
                key = tuple(row[field] for field in key_fields)
                if key in seen:
                    duplicates += 1
                seen.add(key)
                if any(not row.get(field) for field in needed):
                    missing += 1
                if row.get('available_at') and row.get('asof_at'):
                    try:
                        available = datetime.fromisoformat(row['available_at'].replace('Z', '+00:00'))
                        asof = datetime.fromisoformat(row['asof_at'].replace('Z', '+00:00'))
                        release = datetime.fromisoformat(row['release_at'].replace('Z', '+00:00'))
                        vintage = datetime.fromisoformat(row['vintage_at'].replace('Z', '+00:00'))
                        if any(value.tzinfo is None for value in (available, asof, release, vintage)):
                            missing += 1
                        elif max(available, release, vintage) > asof:
                            lookahead += 1
                    except ValueError:
                        missing += 1
        expected = check.get('min_rows', 1)
        result.update(rows=count, duplicates=duplicates, missing=missing,
                      future_available_rows=lookahead, min_rows=expected,
                      ok=count >= expected and not (duplicates or missing or lookahead))
    elif kind in {'sqlite_integrity', 'sqlite_count'}:
        uri = 'file:' + str(path) + '?mode=ro'
        with sqlite3.connect(uri, uri=True, timeout=2) as db:
            db.execute('PRAGMA query_only=ON')
            if kind == 'sqlite_integrity':
                value = db.execute('PRAGMA integrity_check').fetchone()[0]
                result.update(actual=value, expected='ok', ok=value == 'ok')
            else:
                table = check['table']
                if not IDENTIFIER.fullmatch(table):
                    raise ValueError('Unsafe SQLite table name')
                value = db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                result.update(actual=value, expected=check['equals'],
                              ok=value == check['equals'])
    return result


def initial_state(config: dict, digest: str) -> dict:
    return {'schema_version': 1, 'project_id': config['project_id'],
            'config_sha256': digest, 'updated_at_utc': now(),
            'tasks': {task['id']: {'status': 'PENDING', 'attempts': 0, 'evidence': []}
                      for task in config['tasks']}, 'events': []}


def write_state(path: Path, state: dict) -> None:
    state['updated_at_utc'] = now()
    data = json.dumps(state, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    fd, name = tempfile.mkstemp(prefix='.state-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def locked_state(state_dir: Path):
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state_dir.is_symlink():
        raise ValueError('State directory cannot be a symlink')
    lock = state_dir / '.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'a+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another agent run holds the project lock') from exc
        state_path = state_dir / 'state.json'
        if state_path.is_symlink():
            raise ValueError('State file cannot be a symlink')
        yield state_path


def reopen(config_path: Path, state_dir: Path, task_id: str) -> dict:
    """Explicitly retry a blocked task after evidence changes; keep its history."""
    config, digest = load_project(config_path)
    with locked_state(state_dir) as state_path:
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('config_sha256') != digest or task_id not in state['tasks']:
            raise ValueError('Manifest changed or task is unknown')
        record = state['tasks'][task_id]
        if record['status'] not in {'BLOCKED', 'FAILED'}:
            raise ValueError('Only blocked or failed tasks can be reopened')
        record.update(status='PENDING', attempts=0, reason='Reopened for new evidence')
        state['events'].append({'at_utc': now(), 'task': task_id, 'status': 'PENDING'})
        state['next_task'] = (select_task(config, state) or {}).get('id')
        write_state(state_path, state)
        return state


def select_task(config: dict, state: dict, exclude: set[str] | None = None) -> dict | None:
    exclude = exclude or set()
    ranked = sorted(config['tasks'], key=lambda task: (task['priority'], task['id']))
    for task in ranked:
        record = state['tasks'][task['id']]
        if task['id'] in exclude or record['status'] not in {'PENDING', 'BLOCKED', 'FAILED'}:
            continue
        if record['status'] != 'PENDING' and record.get('attempts', 0) >= 3:
            continue
        if all(state['tasks'][dep]['status'] == 'COMPLETED'
               for dep in task.get('depends_on', [])):
            return task
    return None


def run(config_path: Path, state_dir: Path, max_steps: int = 1) -> dict:
    if max_steps < 1:
        raise ValueError('max_steps must be positive')
    config, digest = load_project(config_path)
    with locked_state(state_dir) as state_path:
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if state.get('config_sha256') != digest or state.get('project_id') != config['project_id']:
                raise ValueError('Project manifest changed; review state before resuming')
        else:
            state = initial_state(config, digest)
            write_state(state_path, state)
        for task_id, record in state['tasks'].items():
            if record['status'] == 'IN_PROGRESS':
                record['status'] = 'FAILED'
                record['reason'] = 'Previous run interrupted before verification'
                state['events'].append({'at_utc': now(), 'task': task_id, 'status': 'FAILED'})
        write_state(state_path, state)
        attempted_this_run = set()
        for _ in range(max_steps):
            task = select_task(config, state, attempted_this_run)
            if task is None:
                break
            attempted_this_run.add(task['id'])
            record = state['tasks'][task['id']]
            record['status'] = 'IN_PROGRESS'
            record['attempts'] += 1
            state['events'].append({'at_utc': now(), 'task': task['id'], 'status': 'IN_PROGRESS'})
            write_state(state_path, state)
            try:
                evidence = [check_evidence(config['_root'], c) for c in task['checks']]
                record['evidence'] = evidence
                record['status'] = 'VERIFIED' if all(x['ok'] for x in evidence) else 'BLOCKED'
                record['reason'] = '' if record['status'] == 'VERIFIED' else 'Evidence did not meet expected values'
            except (OSError, ValueError, KeyError, sqlite3.Error, json.JSONDecodeError) as exc:
                record['status'] = 'FAILED'
                record['reason'] = type(exc).__name__ + ': ' + str(exc)[:160]
            state['events'].append({'at_utc': now(), 'task': task['id'], 'status': record['status']})
            write_state(state_path, state)
            if record['status'] == 'VERIFIED':
                record['status'] = 'COMPLETED'
                state['events'].append({'at_utc': now(), 'task': task['id'], 'status': 'COMPLETED'})
                write_state(state_path, state)
        state['next_task'] = (select_task(config, state) or {}).get('id')
        write_state(state_path, state)
        return state
