"""Bounded recovery decisions for research tasks; no production mutation capability."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .engine import now

ERROR_TYPES = frozenset({
    'CODE_ERROR', 'DEPENDENCY_ERROR', 'CONFIG_ERROR', 'PERMISSION_ERROR',
    'SANDBOX_ERROR', 'NETWORK_ERROR', 'DNS_ERROR', 'AUTH_ERROR',
    'API_RATE_LIMIT', 'DATA_GAP', 'SCHEMA_MISMATCH', 'PIT_FAILURE',
    'BACKTEST_FAILURE', 'GIT_SYNC_ERROR', 'API_REQUEST_ERROR',
    'API_NOT_FOUND', 'DATA_CONTRACT_ERROR', 'OUTPUT_CONTRACT_ERROR',
    'TIMEOUT', 'UNKNOWN_ERROR',
})
RESEARCH_ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r'(?i)\b(authorization|api[_-]?key|token|password|secret)\s*[:=]\s*(?:Bearer\s+)?[^\s,;]+')


def redact(value: str) -> str:
    return SECRET.sub(lambda match: match.group(1) + '=[REDACTED]', value)[:500]


def redact_record(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_record(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_record(item) for item in value]
    return value


def classify(stage: str, message: str, error_code: str = '') -> str:
    """Use both the failing stage and structured code before message hints."""
    m = message.lower()
    code = error_code.upper()
    stage = stage.upper()
    if code == 'NETWORK_ERROR' and any(x in m for x in ('name resolution', 'dns', 'could not resolve')):
        return 'DNS_ERROR'
    if code in ERROR_TYPES:
        return code
    if code in {'429', 'HTTP_429'} or 'http 429' in m or 'rate limit' in m:
        return 'API_RATE_LIMIT'
    if code in {'400', 'HTTP_400'} or 'http 400' in m:
        return 'API_REQUEST_ERROR'
    if code in {'404', 'HTTP_404'} or 'http 404' in m:
        return 'API_NOT_FOUND'
    if code in {'403', 'HTTP_403', '401', 'HTTP_401'}:
        return 'AUTH_ERROR'
    if 'PIT' in stage and any(x in m for x in ('vintage', 'release', 'publication')):
        return 'PIT_FAILURE'
    if 'SCHEMA' in stage or any(x in m for x in ('missing column', 'undefined column', 'no such column')):
        return 'SCHEMA_MISMATCH'
    if 'SANDBOX' in stage or 'SECURE_RUNNER' in stage or 'bwrap' in m or 'namespace mapping' in m:
        return 'SANDBOX_ERROR'
    if any(x in m for x in ('name resolution', 'dns', 'could not resolve')):
        return 'DNS_ERROR'
    if 'GIT' in stage and any(x in m for x in ('push', 'merge', 'conflict', '403')):
        return 'GIT_SYNC_ERROR'
    if any(x in m for x in ('unauthorized', 'authentication', 'permission denied')):
        return 'AUTH_ERROR' if 'auth' in m or 'unauthorized' in m else 'PERMISSION_ERROR'
    if any(x in m for x in ('timeout', 'connection refused', 'network unreachable')):
        return 'NETWORK_ERROR'
    if isinstance(message, str) and any(x in m for x in ('syntaxerror', 'nameerror', 'typeerror')):
        return 'CODE_ERROR'
    if any(x in m for x in ('modulenotfounderror', 'no module named', 'importerror')):
        return 'DEPENDENCY_ERROR'
    if 'BACKTEST' in stage:
        return 'BACKTEST_FAILURE'
    if 'CONFIG' in stage:
        return 'CONFIG_ERROR'
    if any(x in m for x in ('missing data', 'insufficient data', 'no data')):
        return 'DATA_GAP'
    return 'UNKNOWN_ERROR'


@dataclass(frozen=True)
class Failure:
    run_id: str
    stage: str
    error_code: str
    message: str
    context: str

    def record(self) -> dict:
        category = classify(self.stage, self.message, self.error_code)
        public = {'run_id': self.run_id, 'stage': self.stage, 'error_code': self.error_code,
                  'error_type': category, 'message': redact(self.message),
                  'context': redact(self.context)}
        public['fingerprint'] = hashlib.sha256(json.dumps(
            (self.stage, category, self.error_code, self.context), sort_keys=True
        ).encode()).hexdigest()
        public['at_utc'] = now()
        return public


def plans(error_type: str) -> list[dict]:
    """Rank only actions the agent can safely take without privilege changes."""
    options = {
        'API_RATE_LIMIT': [('RETRY_WITH_BACKOFF', 1), ('SAFE_BLOCKED', 9)],
        'API_REQUEST_ERROR': [('FIX_REQUEST_PARAMETERS', 2), ('SAFE_BLOCKED', 9)],
        'API_NOT_FOUND': [('ALTERNATIVE_DATA_SOURCE', 3), ('DATA_ACQUISITION_REQUIRED', 4)],
        'DNS_ERROR': [('RETRY_WITH_BACKOFF', 2), ('PRESERVE_LOCAL_COMMIT', 3)],
        'NETWORK_ERROR': [('RETRY_WITH_BACKOFF', 2), ('SAFE_BLOCKED', 9)],
        'SCHEMA_MISMATCH': [('INSPECT_READ_ONLY_SCHEMA', 2), ('REPAIR_RESEARCH_ADAPTER', 4)],
        'DATA_CONTRACT_ERROR': [('INSPECT_INPUT_CONTRACT', 2), ('REPAIR_RESEARCH_ADAPTER', 4)],
        'OUTPUT_CONTRACT_ERROR': [('REPAIR_RESEARCH_CODE', 2), ('SAFE_BLOCKED', 9)],
        'TIMEOUT': [('SAFE_BLOCKED', 2)],
        'CODE_ERROR': [('REPAIR_RESEARCH_CODE', 3), ('SAFE_BLOCKED', 9)],
        'SANDBOX_ERROR': [('PROBE_APPROVED_ISOLATION', 2), ('SECURE_RUNNER_UNAVAILABLE', 3)],
        'PIT_FAILURE': [('PIT_VALIDATION_REQUIRED', 2)],
        'DATA_GAP': [('DATA_ACQUISITION_REQUIRED', 2)],
        'AUTH_ERROR': [('HUMAN_APPROVAL_REQUIRED', 2)],
        'PERMISSION_ERROR': [('HUMAN_APPROVAL_REQUIRED', 2)],
        'GIT_SYNC_ERROR': [('PRESERVE_LOCAL_COMMIT', 2), ('HUMAN_APPROVAL_REQUIRED', 4)],
    }
    return [{'action': action, 'rank': rank, 'security_risk': 'LOW' if rank < 4 else 'REVIEW',
             'requires_approval': action == 'HUMAN_APPROVAL_REQUIRED'}
            for action, rank in options.get(error_type, [('SAFE_BLOCKED', 9)])]


def diagnose(failure: Failure, history: list[dict] | None = None) -> dict:
    record = failure.record()
    previous = [item for item in history or [] if item.get('fingerprint') == record['fingerprint']]
    record['repeat_count'] = len(previous)
    record['root_cause_candidates'] = {
        'SANDBOX_ERROR': ['namespace, seccomp, AppArmor or capability restriction'],
        'SCHEMA_MISMATCH': ['adapter expects a column absent from the observed schema'],
        'API_RATE_LIMIT': ['provider request quota or rate window'],
        'CODE_ERROR': ['research source or input contract defect'],
    }.get(record['error_type'], ['inspect the bounded diagnostic evidence'])
    attempted = {item.get('action') for item in previous}
    record['plans'] = [plan for plan in plans(record['error_type'])
                       if plan['action'] not in attempted]
    record['next_action'] = record['plans'][0]['action'] if record['plans'] else 'SAFE_BLOCKED'
    record['action'] = record['next_action']
    return record


def run_stage(run_id: str, stage: str, context: str, execute,
              history: list[dict], *, max_retries: int = 2, sleep=time.sleep) -> dict:
    """Run a trusted stage with bounded transient retries and recorded decisions."""
    if not 0 <= max_retries <= 2:
        raise ValueError('Retry budget exceeds two')
    for attempt in range(max_retries + 1):
        try:
            return {'status': 'COMPLETED', 'result': execute(), 'attempts': attempt + 1}
        except Exception as exc:
            diagnosis = diagnose(Failure(run_id, stage, type(exc).__name__, str(exc), context),
                                 history)
            diagnosis['attempt'] = attempt + 1
            history.append(diagnosis)
            if (diagnosis['next_action'] != 'RETRY_WITH_BACKOFF' or attempt >= max_retries):
                return {'status': 'SAFE_BLOCKED', 'diagnosis': diagnosis,
                        'attempts': attempt + 1}
            sleep(min(2 ** attempt, 4))
    raise AssertionError('unreachable')


def probe_secure_runner() -> dict:
    """Probe Bubblewrap with a harmless trusted command; never weaken policy."""
    binary = shutil.which('bwrap')
    evidence = {'platform': os.uname().sysname, 'runner': binary,
                'user_namespace_setting': None, 'seccomp': None,
                'apparmor': None, 'capabilities_effective': None}
    for name, path in [('user_namespace_setting', '/proc/sys/kernel/unprivileged_userns_clone'),
                       ('apparmor', '/proc/self/attr/current')]:
        try:
            evidence[name] = Path(path).read_text().strip()[:160]
        except OSError:
            pass
    try:
        status = Path('/proc/self/status').read_text()
        for key, field in [('Seccomp', 'seccomp'), ('CapEff', 'capabilities_effective')]:
            match = re.search(r'^' + key + r':\s*(\S+)', status, re.MULTILINE)
            evidence[field] = match.group(1) if match else None
    except OSError:
        pass
    if binary is None:
        evidence.update(status='SECURE_RUNNER_UNAVAILABLE', reason='Bubblewrap executable absent')
        return evidence
    host_net = os.readlink('/proc/self/ns/net')
    probe = ('import json,os; print(json.dumps({'
             '"marker":"isolation-probe",'
             '"home_visible":os.path.exists("/home/kegor2"),'
             '"net_namespace":os.readlink("/proc/self/ns/net")}))')
    command = [binary, '--die-with-parent', '--unshare-all', '--ro-bind', '/usr', '/usr',
               '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64',
               '--ro-bind', '/bin', '/bin', '--dev-bind', '/dev', '/dev',
               '--proc', '/proc', '--tmpfs', '/tmp', '--',
               '/usr/bin/python3', '-I', '-c', probe]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5,
                                env={'PATH': '/usr/bin:/bin'}, check=False)
        evidence['exit_code'] = result.returncode
        child = json.loads(result.stdout) if result.returncode == 0 else {}
        evidence['home_hidden'] = child.get('home_visible') is False
        evidence['network_namespace_separate'] = child.get('net_namespace') != host_net
        evidence['status'] = ('SECURE_RUNNER_VERIFIED' if result.returncode == 0 and
                              child.get('marker') == 'isolation-probe' and
                              evidence['home_hidden'] and evidence['network_namespace_separate']
                              else 'SECURE_RUNNER_UNAVAILABLE')
        evidence['reason'] = redact(result.stderr.strip()) if result.returncode else ''
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        evidence.update(status='SECURE_RUNNER_UNAVAILABLE', reason=redact(str(exc)))
    return evidence


def repair_research_source(path: Path, candidates: list[str], root: Path,
                           verify_result, *, max_candidates: int = 2,
                           static_check=None) -> dict:
    """Apply a candidate only inside a research tree and roll back failed verification.

    The generated script is always executed by Agent 4.3's Bubblewrap runner;
    the caller's verifier only inspects its result. Static checks alone never
    authorize execution.
    """
    if path.is_symlink():
        return {'status': 'SAFE_BLOCKED', 'reason': 'Research scope or secure runner unavailable'}
    root = root.resolve(strict=True)
    path = path.resolve(strict=True)
    if (not path.is_relative_to(root) or not root.is_relative_to(RESEARCH_ROOT)
            or path.name != 'experiment.py'
            or not path.is_file()
            or probe_secure_runner()['status'] != 'SECURE_RUNNER_VERIFIED'):
        return {'status': 'SAFE_BLOCKED', 'reason': 'Research scope or secure runner unavailable'}
    from regime190.agent43_engine import _check_code, _isolated_python
    if static_check is None:
        static_check = _check_code
    backup = path.with_name('.experiment.py.repair-backup')
    recovered_interruption = False
    if backup.exists():
        if backup.is_symlink():
            return {'status': 'SAFE_BLOCKED', 'reason': 'Unsafe repair backup'}
        path.write_bytes(backup.read_bytes())
        backup.unlink()
        recovered_interruption = True
    original = path.read_bytes()
    output_paths = [path.parent / name for name in ('result.json', 'predictions.csv')]
    if any(output.is_symlink() for output in output_paths):
        return {'status': 'SAFE_BLOCKED', 'reason': 'Unsafe prior generated output'}
    prior_outputs = {output: output.read_bytes() for output in output_paths if output.exists()}
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        backup.unlink(missing_ok=True)
        raise
    attempts = []
    finished = False
    try:
        for candidate in candidates[:max_candidates]:
            try:
                ast.parse(candidate)
                static_check(candidate)
            except (SyntaxError, ValueError) as exc:
                attempts.append({'status': 'REJECTED_STATIC', 'reason': redact(str(exc))})
                continue
            data = candidate.encode('utf-8')
            for output in output_paths:
                output.unlink(missing_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix='.repair-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, path)
                execution = _isolated_python(path.parent)
                ok = execution['exit_code'] == 0 and bool(verify_result(path, execution))
                attempts.append({'status': 'VERIFIED' if ok else 'ROLLED_BACK',
                                 'candidate_sha256': hashlib.sha256(data).hexdigest()})
                if ok:
                    finished = True
                    return {'status': 'REPAIRED', 'attempts': attempts,
                            'recovered_interruption': recovered_interruption,
                            'before_sha256': hashlib.sha256(original).hexdigest(),
                            'after_sha256': hashlib.sha256(data).hexdigest()}
            except Exception as exc:
                attempts.append({'status': 'ROLLED_BACK', 'reason': redact(str(exc))})
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
                if attempts and attempts[-1]['status'] == 'ROLLED_BACK':
                    path.write_bytes(original)
                    for output in output_paths:
                        output.unlink(missing_ok=True)
                    for output, content in prior_outputs.items():
                        output.write_bytes(content)
        finished = True
        return {'status': 'SAFE_BLOCKED', 'attempts': attempts,
                'recovered_interruption': recovered_interruption,
                'before_sha256': hashlib.sha256(original).hexdigest()}
    finally:
        if finished:
            backup.unlink(missing_ok=True)
