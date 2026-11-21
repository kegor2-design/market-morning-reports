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

from .engine import write_state
from .kr_crash_analysis import crash_windows
from .self_repair import repair_research_source


def reviewed_script():
    return ('import statistics\nimport json\n' + inspect.getsource(crash_windows) +
            '\nwith open("data.csv") as stream:\n    rows, provenance = json.load(stream)\n'
            'with open("result.json", "w") as stream:\n'
            '    json.dump(crash_windows(rows, provenance), stream)\n')


def _hash(data):
    return hashlib.sha256(data).hexdigest()


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
            return (not result.is_symlink() and result.is_file() and
                    result.stat().st_size < 100000 and json.loads(result.read_bytes()) == expected)
        if repair:
            fault = json.loads((directory / 'kr_analysis_error.json').read_bytes())
            if fault['source_sha256'] != _hash(original) and original != trusted.encode():
                raise ValueError('Failed analysis copy changed before repair')
            item = repair_research_source(script, [trusted], root, verified,
                                         max_candidates=1, deadline_utc=deadline)
            if item['status'] == 'REPAIRED':
                if source.read_bytes() != original or script.read_text() != trusted:
                    raise ValueError('Analysis copy changed before promotion')
                os.replace(script, source)
            return {**item, 'candidate_origin': 'HOST_SUPPLIED_PATCH'}
        try:
            _check_code(original.decode())
            for node in ast.walk(ast.parse(original)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'open':
                    if ([arg.value if isinstance(arg, ast.Constant) else None for arg in node.args]
                            not in (['data.csv'], ['result.json', 'w']) or node.keywords):
                        raise RuntimeError('Unapproved analysis file access')
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
            'problem_type': 'CODE_ERROR', 'reason': reason, 'source_sha256': _hash(original),
            'reviewed_source_sha256': _hash(trusted.encode()), 'data_hashes': expected['source_sha256']})
        raise ValueError('Isolated analysis failed verification')
