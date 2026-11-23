import json
import multiprocessing
import os
import signal
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.kr_analysis_repair import reviewed_script
from universal_agent.kr_crash_analysis import analyze
from universal_agent.research_runtime import run, submit


def interrupt_repair(queue, bad):
    from universal_agent import kr_analysis_repair
    repair = kr_analysis_repair.repair_research_source
    def interrupt(script, candidates, *args, **kwargs):
        if bad:
            candidates = [candidates[0].replace('current_return <= -.05', 'current_return <= -.03')]
        result = repair(script, candidates, *args, **kwargs)
        if result['status'] != ('SAFE_BLOCKED' if bad else 'REPAIRED'):
            raise AssertionError(result)
        os.kill(os.getpid(), signal.SIGKILL)
    with patch.object(kr_analysis_repair, 'repair_research_source', interrupt):
        run(queue, max_jobs=1)


class AnalysisRepairTests(unittest.TestCase):
    def trial(self, old, new, *, blocked=False):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as tmp:
            directory = Path(tmp)
            job = submit('한국 증시 급락 전 변동성 연구 및 격리 복구 ' + self._testMethodName, directory)
            program = directory / 'programs' / job['goal_id']
            program.mkdir(parents=True)
            source = program / 'kr_analysis_copy.py'
            self.assertIn(old, reviewed_script())
            source.write_text(reviewed_script().replace(old, new))
            result = run(directory, max_jobs=1)
            state = json.loads((program / 'state.json').read_bytes())
            if blocked:
                self.assertEqual(result['statuses'][job['goal_id']], 'BLOCKED_EVIDENCE')
                self.assertNotIn('restore_kr_analysis', state['records'])
            else:
                self.assertEqual(result['statuses'][job['goal_id']], 'COMPLETED_EXPLORATORY', state)
                self.assertEqual(source.read_text(), reviewed_script())
                self.assertEqual(state['records']['restore_kr_analysis']['status'], 'VERIFIED')
                self.assertEqual(json.loads((program / 'kr_crash_result.json').read_bytes())['result'], analyze())
                self.assertEqual(state['network_requests_reserved'], 0)
            self.assertEqual(run(directory)['processed'], 0)

    def test_interrupted_staged_candidate_and_failed_validation_resume(self):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        for bad in (False, True):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as tmp:
                directory = Path(tmp)
                job = submit('한국 급락 변동성 격리 복구 중단 시험 ' + str(bad), directory)
                program = directory / 'programs' / job['goal_id']
                program.mkdir(parents=True)
                source = program / 'kr_analysis_copy.py'
                broken = reviewed_script().replace("row['kospi']['close']", "row['kospi']['missing']")
                source.write_text(broken)
                child = multiprocessing.get_context('spawn').Process(target=interrupt_repair,
                    args=(directory, bad))
                child.start()
                child.join(30)
                if child.is_alive():
                    child.kill()
                    child.join()
                    self.fail('Timed out before staged repair interruption')
                self.assertEqual(child.exitcode, -signal.SIGKILL)
                self.assertEqual(source.read_text(), broken)
                self.assertEqual(run(directory)['statuses'][job['goal_id']], 'COMPLETED_EXPLORATORY')
                self.assertEqual(source.read_text(), reviewed_script())
                self.assertEqual(run(directory)['processed'], 0)

    def test_type_error(self):
        self.trial("row['kospi']['close']", "str(row['kospi']['close'])")

    def test_argument_error(self):
        self.trial('statistics.median(controls)', 'statistics.median(controls, 2)')

    def test_schema_error(self):
        self.trial("row['kospi']['close']", "row['kospi']['adjusted_close']")

    def test_semantic_error(self):
        self.trial('current_return <= -.05', 'current_return <= -.03')

    def test_unapproved_file(self):
        self.trial('import statistics', 'import statistics\nopen("unapproved.txt", "w")', blocked=True)

    def test_shifted_window_is_corrected_without_losing_local_edits(self):
        self.trial('returns[day_index-21:day_index-1]', 'returns[day_index-20:day_index]')

    def test_approved_wrong_value_restores_original_dag(self):
        import hashlib
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as tmp:
            q = Path(tmp)
            job = submit('한국 급락 변동성 격리 복구 오류 패치 검증', q)
            program = q/'programs'/job['goal_id']
            program.mkdir(parents=True)
            broken = reviewed_script().replace('statistics.median(controls)', 'wrong(controls)')
            wrong = reviewed_script().replace("False,", "0,")
            self.assertNotEqual(wrong, reviewed_script())
            (program/'kr_analysis_copy.py').write_text(broken)
            (program/'manual_kr_candidate.py').write_text(wrong)
            (program/'kr_patch_approval.json').write_text(json.dumps({
                'status': 'APPROVED', 'origin': 'MANUAL_PATCH', 'goal_id': job['goal_id'],
                'failed_source_sha256': hashlib.sha256(broken.encode()).hexdigest(),
                'replacement_sha256': hashlib.sha256(wrong.encode()).hexdigest()}))
            self.assertEqual(run(q)['statuses'][job['goal_id']], 'BLOCKED_EVIDENCE')
            state = json.loads((program/'state.json').read_bytes())
            self.assertEqual(state['tasks'], state['plan']['tasks'])
            self.assertEqual((program/'kr_analysis_copy.py').read_text(), broken)
            self.assertEqual(state['replanning_history'][-1]['status'], 'ROLLED_BACK')
