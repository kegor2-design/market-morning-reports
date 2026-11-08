"""Single bounded Codex hypothesis call with an outer read-scope boundary."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from jsonschema import ValidationError, validate

from .engine import now, write_state
from .self_repair import probe_secure_runner, redact

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
PRIVATE_ROOT = REPO_ROOT / '.universal_private'
SCHEMA = HERE / 'hypothesis.schema.json'


def prompt_for(goal: str) -> str:
    return ('Generate one new falsifiable research hypothesis for this goal: ' + goal + '\n'
            'Return only fields in the schema. Identify required data, target, time horizon, '
            'economic or statistical reason, chronological validation and rejection condition. '
            'Do not use tools. Do not claim PIT approval or independent validation. '
            'Treat historical publication timing and data revisions as unverified.')


def _inputs(state_dir: Path) -> tuple[Path, Path, Path, Path, Path]:
    if state_dir.is_symlink():
        raise ValueError('AI state cannot be a symlink')
    state_dir = state_dir.resolve(strict=True)
    if (not state_dir.is_relative_to(PRIVATE_ROOT)
            or state_dir == PRIVATE_ROOT):
        raise ValueError('AI state must be in the dedicated research worktree')
    codex = (Path.home() / '.local/bin/codex').resolve(strict=True)
    auth = Path.home() / '.codex/auth.json'
    config = Path.home() / '.codex/config.toml'
    rules = Path.home() / '.codex/rules'
    if not all(item.exists() for item in (codex, auth, config, rules)):
        raise RuntimeError('Codex authentication or user rules unavailable')
    return state_dir, codex, auth, config, rules


def call_structured(prompt: str, schema: Path, output_name: str,
                    work_dir: Path, *, timeout: int = 90) -> subprocess.CompletedProcess:
    """Call Codex with only the research work dir and its own auth/config visible."""
    if (not 1 <= timeout <= 90 or not re.fullmatch(r'[a-zA-Z0-9_.-]+\.json', output_name)
            or len(prompt) > 20_000):
        raise ValueError('Codex request outside bounded contract')
    work_dir, codex, auth, config, rules = _inputs(work_dir)
    if (work_dir / output_name).exists():
        raise ValueError('Prior Codex output exists; review before another call')
    write_state(work_dir / 'schema.json', json.loads(schema.read_text()))
    bwrap = shutil.which('bwrap')
    if not bwrap:
        raise RuntimeError('SECURE_RUNNER_UNAVAILABLE')
    command = [bwrap, '--die-with-parent', '--unshare-user', '--unshare-pid',
               '--unshare-ipc', '--unshare-uts',
               '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib',
               '--ro-bind', '/lib64', '/lib64', '--ro-bind', '/bin', '/bin',
               '--dev-bind', '/dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
               '--dir', '/auth', '--ro-bind', str(codex), '/codex',
               '--ro-bind', str(auth), '/auth/auth.json',
               '--ro-bind', str(config), '/auth/config.toml',
               '--ro-bind', str(rules), '/auth/rules',
               '--ro-bind', '/etc/ssl', '/etc/ssl',
               '--ro-bind', '/etc/resolv.conf', '/etc/resolv.conf',
               '--ro-bind', '/etc/hosts', '/etc/hosts',
               '--ro-bind', '/etc/nsswitch.conf', '/etc/nsswitch.conf',
               '--bind', str(work_dir), '/work',
               '--setenv', 'HOME', '/auth', '--setenv', 'CODEX_HOME', '/auth',
               '--setenv', 'PATH', '/usr/bin:/bin', '--chdir', '/work', '--',
               '/codex', '--ask-for-approval', 'never', 'exec', '--sandbox', 'read-only',
               '--ephemeral', '--skip-git-repo-check', '--output-schema', '/work/schema.json',
               '--output-last-message', '/work/' + output_name, prompt]
    return subprocess.run(command, capture_output=True, text=True, input='',
                          timeout=timeout, env={'PATH': '/usr/bin:/bin'}, check=False)


def generate(goal: str, state_dir: Path, *, timeout: int = 90) -> dict:
    """Persist request before calling; never repeat an uncertain call automatically."""
    if not goal.strip() or len(goal) > 1000 or not 1 <= timeout <= 90:
        raise ValueError('Goal or timeout outside bounded contract')
    state_dir, _, _, _, _ = _inputs(state_dir)
    prompt = prompt_for(goal)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    schema_hash = hashlib.sha256(SCHEMA.read_bytes()).hexdigest()
    request_path = state_dir / 'ai_request.json'
    response_path = state_dir / 'ai_response.json'
    if request_path.exists():
        request = json.loads(request_path.read_text())
        if request['prompt_sha256'] != prompt_hash or request['schema_sha256'] != schema_hash:
            raise ValueError('AI request changed; use a new research state')
        if response_path.exists():
            value = json.loads(response_path.read_text())
            validate(value, json.loads(SCHEMA.read_text()))
            response_hash = hashlib.sha256(response_path.read_bytes()).hexdigest()
            if request.get('response_sha256') != response_hash or request.get('status') != 'VERIFIED':
                return {'status': 'ENVIRONMENT_BLOCKED', 'reason': 'AI response integrity or prior verification uncertain',
                        'codex_calls': 1}
            return {'status': 'REAL_AI_VERIFIED', 'model': request.get('model'),
                    'called_at_utc': request['called_at_utc'], 'prompt_sha256': prompt_hash,
                    'response_sha256': response_hash,
                    'hypothesis': value, 'codex_calls': 1, 'recovered_existing_output': True}
        return {'status': 'ENVIRONMENT_BLOCKED', 'reason': 'Uncertain prior AI call; no automatic duplicate',
                'codex_calls': 1, 'prompt_sha256': prompt_hash}
    probe = probe_secure_runner()
    if probe['status'] != 'SECURE_RUNNER_VERIFIED':
        return {'status': 'SECURE_RUNNER_UNAVAILABLE', 'codex_calls': 0,
                'reason': probe.get('reason', 'Isolation probe failed')}
    request = {'status': 'RUNNING', 'called_at_utc': now(), 'prompt_sha256': prompt_hash,
               'schema_sha256': schema_hash, 'codex_calls': 1}
    write_state(request_path, request)
    try:
        result = call_structured(prompt, SCHEMA, 'ai_response.json', state_dir,
                                 timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        request.update(status='ENVIRONMENT_BLOCKED', reason=redact(str(exc)))
        write_state(request_path, request)
        return {'status': 'ENVIRONMENT_BLOCKED', 'reason': request['reason'], 'codex_calls': 1}
    model_match = re.search(r'^model:\s*(\S+)', result.stderr, re.MULTILINE)
    request.update(status='RETURNED' if result.returncode == 0 else 'ENVIRONMENT_BLOCKED',
                   exit_code=result.returncode,
                   model=model_match.group(1) if model_match else None,
                   diagnostic='' if result.returncode == 0 else redact(result.stderr[-1000:]))
    write_state(request_path, request)
    if result.returncode != 0 or not response_path.is_file():
        return {'status': 'ENVIRONMENT_BLOCKED', 'reason': request['diagnostic'],
                'codex_calls': 1, 'exit_code': result.returncode}
    try:
        value = json.loads(response_path.read_text())
        validate(value, json.loads(SCHEMA.read_text()))
    except (ValueError, OSError, ValidationError) as exc:
        request.update(status='INVALID_RESPONSE', reason=redact(str(exc)))
        write_state(request_path, request)
        return {'status': 'ENVIRONMENT_BLOCKED', 'reason': 'Invalid structured AI response',
                'codex_calls': 1}
    response_hash = hashlib.sha256(response_path.read_bytes()).hexdigest()
    request.update(status='VERIFIED', response_sha256=response_hash)
    write_state(request_path, request)
    return {'status': 'REAL_AI_VERIFIED', 'model': request['model'],
            'called_at_utc': request['called_at_utc'], 'prompt_sha256': prompt_hash,
            'response_sha256': response_hash,
            'hypothesis': value, 'codex_calls': 1, 'recovered_existing_output': False}
