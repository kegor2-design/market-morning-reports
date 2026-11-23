"""Isolated execution and restoration of the reviewed Korean crash analysis."""
import ast
import hashlib
import inspect
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from regime190.agent43_engine import _check_code, _isolated_python
from regime190.exploratory_backtest import load_indices

from .engine import canonical, write_state
from .kr_crash_analysis import crash_windows
from .self_repair import repair_research_source


def reviewed_script():
    return ('import statistics\nimport json\n' + inspect.getsource(crash_windows) +
            '\nwith open("data.csv") as stream:\n    rows, provenance = json.load(stream)\n'
            'with open("result.json", "w") as stream:\n'
            '    json.dump(crash_windows(rows, provenance), stream)\n')


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _check_analysis(source):
    _check_code(source)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'open':
            if ([arg.value if isinstance(arg, ast.Constant) else None for arg in node.args]
                    not in (['data.csv'], ['result.json', 'w']) or node.keywords):
                raise RuntimeError('Unapproved analysis file access')


def _candidate(directory, failed, fault):
    review = directory / 'kr_patch_approval.json'
    if review.is_symlink():
        raise ValueError('Unsafe patch review')
    if review.exists():
        permit = json.loads(review.read_bytes())
        if (permit.get('status') != 'APPROVED' or permit.get('goal_id') != directory.name
                or permit.get('failed_source_sha256') != fault['source_sha256']):
            raise ValueError('Patch approval differs from failed goal')
        origin = permit.get('origin')
        if origin == 'AI_GENERATED_PATCH':
            req = directory / 'ai_repair_request.json'
            response = directory / 'ai_repair_response.json'
            if req.is_symlink() or response.is_symlink() or response.stat().st_size > 64000:
                raise ValueError('Unsafe repair proposal')
            ledger = json.loads(req.read_bytes())
            proposal = json.loads(response.read_bytes())
            if (ledger.get('status') != 'VERIFIED' or ledger.get('provider') != 'OPENAI_RESPONSES'
                    or ledger['goal_id'] != directory.name or proposal['goal_id'] != directory.name
                    or proposal['target'] != 'kr_analysis_copy.py'
                    or proposal['failed_source_sha256'] != fault['source_sha256']
                    or ledger['response_sha256'] != _hash(response.read_bytes())):
                raise ValueError('Missing verified live repair ledger')
            replacement = proposal['replacement']
        elif origin == 'MANUAL_PATCH':
            path = directory / 'manual_kr_candidate.py'
            if path.is_symlink() or path.stat().st_size > 20000:
                raise ValueError('Unsafe manual candidate')
            replacement = path.read_text()
        else:
            raise ValueError('Unknown reviewed patch origin')
        if _hash(replacement.encode()) != permit.get('replacement_sha256'):
            raise ValueError('Patch review digest changed')
        return replacement, origin

    # Correct a one-session look-ahead in the prior-volatility slice without
    # replacing unrelated researcher edits. Output still needs both oracles.
    leaked = 'returns[day_index-20:day_index]'
    if fault.get('failure_class') == 'RESULT_MISMATCH' and failed.count(leaked) == 1:
        return failed.replace(leaked, 'returns[day_index-21:day_index-1]'), 'RULE_BASED_PATCH'
    return reviewed_script(), 'HOST_SUPPLIED_PATCH'


def _matches(path, expected):
    return (not path.is_symlink() and path.is_file() and path.stat().st_size < 100000
            and canonical(json.loads(path.read_bytes())) == canonical(expected))


def run(directory, deadline, *, repair=False):
    source = directory / 'kr_analysis_copy.py'
    trusted = reviewed_script()
    if source.is_symlink() or (source.exists() and source.stat().st_size > 20000):
        raise ValueError('Unsafe isolated research copy')
    if not source.exists():
        with source.open('x') as stream:
            stream.write(trusted)
    original = source.read_bytes()
    rows, provenance = load_indices('2010-01-01')
    expected = crash_windows(rows, provenance)
    with tempfile.TemporaryDirectory(dir=directory) as work:
        root = Path(work)
        script = root / 'experiment.py'
        script.write_bytes(original)
        (root / 'data.csv').write_text(json.dumps([rows, provenance]))
        result = root / 'result.json'
        def verified(*_):
            return _matches(result, expected)
        if repair:
            fault = json.loads((directory / 'kr_analysis_error.json').read_bytes())
            backup = directory / 'kr_failed_source.py'
            if backup.is_symlink():
                raise ValueError('Unsafe failed source')
            if not backup.exists():
                if fault['source_sha256'] != _hash(original):
                    raise ValueError('Failed analysis copy changed before repair')
                with backup.open('xb') as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
            failed = backup.read_bytes()
            if _hash(failed) != fault['source_sha256']:
                raise ValueError('Failed source checkpoint changed')
            candidate, origin = _candidate(directory, failed.decode(), fault)
            receipt = directory / 'kr_repair_validated.json'
            if receipt.is_symlink():
                raise ValueError('Unsafe repair receipt')
            if receipt.exists():
                item = json.loads(receipt.read_bytes())
                if (item['before_sha256'] != _hash(failed) or item['after_sha256'] != _hash(candidate.encode())
                        or item['candidate_origin'] != origin or item['data_hashes'] != expected['source_sha256']
                        or item['status'] != 'REPAIRED' or original not in (failed, candidate.encode())):
                    raise ValueError('Repair promotion receipt changed')
                script.write_text(candidate)
            else:
                if original != failed:
                    raise ValueError('Unverified change to analysis copy')
                def regress(*_):
                    if not verified():
                        return False
                    # Separate input with a known crash, controls and a different
                    # result. The original script and input are read-only in bwrap.
                    subset = [dict(row, kospi=dict(row['kospi'])) for row in rows[:120]]
                    subset[90]['kospi']['close'] = subset[89]['kospi']['close'] * 0.8
                    with tempfile.TemporaryDirectory(dir=directory) as regression_dir:
                        second = Path(regression_dir)
                        (second / 'experiment.py').write_text(candidate)
                        (second / 'data.csv').write_text(json.dumps([subset, provenance]))
                        run_result = _isolated_python(second, timeout_seconds=max(0, (
                            deadline - datetime.now(timezone.utc)).total_seconds()))
                        return run_result['exit_code'] == 0 and _matches(second / 'result.json',
                                                                         crash_windows(subset, provenance))
                item = repair_research_source(script, [candidate], root, regress,
                    static_check=_check_analysis, max_candidates=1, deadline_utc=deadline)
                item.update(candidate_origin=origin, data_hashes=expected['source_sha256'])
                if item['status'] != 'REPAIRED':
                    return item
                write_state(receipt, item)
            if source.read_bytes() != original or script.read_text() != candidate:
                raise ValueError('Analysis copy changed before promotion')
            if original != candidate.encode():
                os.replace(script, source)
            return item
        try:
            _check_analysis(original.decode())
            execution = _isolated_python(root, timeout_seconds=max(0.0, (
                deadline - datetime.now(timezone.utc)).total_seconds()))
            if execution['exit_code'] == 0 and verified():
                return expected
            if execution.get('error') or execution['exit_code'] in (None, -9):
                raise RuntimeError('Isolated analysis unavailable or timed out')
            error = (execution.get('stderr') or 'Analysis result differs from independent recomputation')
            reason = error.strip().splitlines()[-1][:180]
            if execution.get('exit_code') and not any(
                    kind in reason for kind in ('TypeError', 'KeyError', 'ValueError', 'NameError', 'AttributeError')):
                raise RuntimeError('Isolated analysis failed outside reviewed repair scope')
        except (SyntaxError, UnicodeError, ValueError) as exc:
            reason = type(exc).__name__
        write_state(directory / 'kr_analysis_error.json', {
            'problem_type': 'CODE_ERROR', 'reason': reason,
            'failure_class': ('RESULT_MISMATCH' if reason.startswith('Analysis result differs') else
                              reason.split(':', 1)[0]),
            'expected_result_sha256': _hash(canonical(expected)),
            'observed_output_sha256': _hash(result.read_bytes()) if result.is_file()
                and not result.is_symlink() and result.stat().st_size < 100000 else None, 'source_sha256': _hash(original),
            'reviewed_source_sha256': _hash(trusted.encode()), 'data_hashes': expected['source_sha256']})
        raise ValueError('Isolated analysis failed verification')
