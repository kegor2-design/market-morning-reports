"""Fixture CODE_ERROR recovery through the persistent Research Program DAG."""
import hashlib
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from universal_agent import code_recovery
from universal_agent.code_recovery import authorize_fixture, fixture_source, replan
from universal_agent.engine import write_state
from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.process_supervisor import run_research_program
from universal_agent.research_planner import plan_goal
from universal_agent.research_runtime import run, submit

GOAL = 'Fixture code repair research: verify exact answer 42 without market data.'
GOOD = ('import json\n'
    'value = 40 + 2\n'
    'result = {"answer": value}\n'
    'with open("result.json", "w", encoding="utf-8") as stream:\n'
    '    json.dump(result, stream)\n')
BAD = GOOD.replace('40 + 2', '40 + 1')
SLOW = GOOD.replace('value = 40 + 2',
    'value = 0\nfor _ in range(40000000):\n    value += 1\nvalue = 42')


def _kill_supervisor_after_rollback(directory):
    from universal_agent import process_supervisor
    original = process_supervisor.write_state
    def checkpoint_then_kill(path, value):
        original(path, value)
        if (path.name == 'state.json' and
                value.get('code_repair_revision', {}).get('status') ==
                'REVISION_ROLLED_BACK'):
            os.kill(os.getpid(), signal.SIGKILL)
    process_supervisor.write_state = checkpoint_then_kill
    process_supervisor.run_research_program(GOAL, directory)


class CodeRecoveryTests(unittest.TestCase):
    def setUp(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=PRIVATE_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.plan = plan_goal(GOAL)

    def _initial_failure(self):
        first = run_research_program(GOAL, self.directory)
        state = json.loads((self.directory / 'state.json').read_text())
        self.assertEqual(first['status'], 'RESEARCH_BLOCKED')
        self.assertEqual(state['records']['analyze_fixture']['problem_type'], 'CODE_ERROR')
        return state

    def test_approved_patch_resumes_original_goal_without_duplicate(self):
        first = self._initial_failure()
        authorize_fixture(self.plan, first, self.directory,
            candidate=GOOD, approved_by='FIXTURE_TEST_OWNER')
        second = run_research_program(GOAL, self.directory)
        saved = json.loads((self.directory / 'state.json').read_text())
        self.assertEqual(second['status'], 'RESEARCH_COMPLETED_EXPLORATORY')
        self.assertEqual(second['goal_id'], first['goal_id'])
        self.assertEqual(saved['goal_contract_sha256'], first['goal_contract_sha256'])
        self.assertEqual(saved['plan_sha256'], first['plan_sha256'])
        self.assertEqual(saved['records']['code_repair_fixture']['status'], 'VERIFIED')
        self.assertEqual(saved['records']['analyze_fixture']['attempts'], 2)
        self.assertEqual(second['analysis']['answer'], 42)
        self.assertEqual(second['analysis']['fixture_only'], True)
        state_sha = hashlib.sha256((self.directory / 'state.json').read_bytes()).hexdigest()
        report_sha = hashlib.sha256((self.directory /
            'research_report.json').read_bytes()).hexdigest()
        self.assertEqual(run_research_program(GOAL, self.directory)['analysis'],
                         second['analysis'])
        self.assertEqual(hashlib.sha256((self.directory / 'state.json').read_bytes()).hexdigest(),
                         state_sha)
        self.assertEqual(hashlib.sha256((self.directory /
            'research_report.json').read_bytes()).hexdigest(), report_sha)
        self.assertEqual(json.loads((self.directory / 'state.json').read_text())[
            'records']['analyze_fixture']['attempts'], 2)
        source = fixture_source(self.directory)
        source.write_text(BAD)
        with self.assertRaisesRegex(ValueError, 'source changed'):
            run_research_program(GOAL, self.directory)

    def test_bad_patch_rolls_back_code_and_dag(self):
        first = self._initial_failure()
        source = fixture_source(self.directory)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        authorize_fixture(self.plan, first, self.directory,
            candidate=BAD, approved_by='FIXTURE_TEST_OWNER')
        second = run_research_program(GOAL, self.directory)
        saved = json.loads((self.directory / 'state.json').read_text())
        self.assertEqual(second['status'], 'RESEARCH_BLOCKED')
        self.assertEqual(saved['code_repair_revision']['status'], 'REVISION_ROLLED_BACK')
        self.assertEqual(json.loads((self.directory /
            'code_repair_transaction_v1.json').read_text())['transaction_state'],
            'REVISION_ROLLED_BACK')
        self.assertEqual([task['task_id'] for task in saved['tasks']],
                         [task['task_id'] for task in first['tasks']])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.assertEqual(saved['retired_recovery_tasks'][0]['record']['status'],
                         'BLOCKED_EVIDENCE')
        self.assertEqual(saved['records']['analyze_fixture']['attempts'], 1)
        self.assertEqual(run_research_program(GOAL, self.directory)['status'],
                         'RESEARCH_BLOCKED')

    def test_analysis_verification_failure_after_repair_rolls_back(self):
        from regime190.agent43_engine import _isolated_python
        state = self._initial_failure()
        source = fixture_source(self.directory)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        original_evidence = hashlib.sha256((self.directory /
            'code_error_evidence.json').read_bytes()).hexdigest()
        authorize_fixture(self.plan, state, self.directory,
            candidate=GOOD, approved_by='FIXTURE_TEST_OWNER')
        calls = []
        def corrupt_second_execution(work_dir, **kwargs):
            result = _isolated_python(work_dir, **kwargs)
            calls.append(1)
            if len(calls) == 2:
                (work_dir / 'result.json').write_text('{"answer":41}')
            return result
        with patch('regime190.agent43_engine._isolated_python',
                   side_effect=corrupt_second_execution):
            result = run_research_program(GOAL, self.directory)
        saved = json.loads((self.directory / 'state.json').read_text())
        self.assertEqual(result['status'], 'RESEARCH_BLOCKED')
        self.assertEqual(saved['code_repair_revision']['status'], 'REVISION_ROLLED_BACK')
        self.assertEqual(saved['tasks'], state['tasks'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.assertEqual(hashlib.sha256((self.directory /
            'code_error_evidence.json').read_bytes()).hexdigest(), original_evidence)
        self.assertEqual(saved['retired_recovery_tasks'][0]['analysis_record'][
            'status'], 'BLOCKED_EVIDENCE')
        self.assertEqual(saved['network_requests_reserved'], 0)

    def test_goal_deadline_during_repair_restores_code_and_blocks(self):
        state = self._initial_failure()
        source = fixture_source(self.directory)
        original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        authorize_fixture(self.plan, state, self.directory,
            candidate=SLOW, approved_by='FIXTURE_TEST_OWNER')
        state['goal_deadline_utc'] = (datetime.now(timezone.utc) +
            timedelta(seconds=2)).isoformat()
        write_state(self.directory / 'state.json', state)
        result = run_research_program(GOAL, self.directory)
        saved = json.loads((self.directory / 'state.json').read_text())
        self.assertEqual(result['status'], 'RESEARCH_BLOCKED')
        self.assertEqual(saved['code_repair_revision']['status'], 'REVISION_ROLLED_BACK')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_sha)
        self.assertEqual(saved['records']['analyze_fixture']['attempts'], 1)
        self.assertEqual(saved['network_requests_reserved'], 0)

    def test_no_approval_or_unapproved_goal_cannot_repair(self):
        self._initial_failure()
        self.assertEqual(run_research_program(GOAL, self.directory)['status'],
                         'RESEARCH_BLOCKED')
        self.assertFalse((self.directory / 'code_repair_revision_v1.json').exists())
        with self.assertRaisesRegex(ValueError, 'No eligible fixture'):
            authorize_fixture(plan_goal('Study Treasury yield spread and SOFR'),
                json.loads((self.directory / 'state.json').read_text()),
                self.directory, candidate=GOOD, approved_by='FIXTURE_TEST_OWNER')

    def test_persistent_queue_runs_repair_and_original_goal(self):
        queue_dir = self.directory / 'queue'
        job = submit(GOAL, queue_dir)
        first = run(queue_dir, max_jobs=1)
        self.assertEqual(first['statuses'][job['goal_id']], 'BLOCKED_EVIDENCE')
        program = queue_dir / 'programs' / job['goal_id']
        state = json.loads((program / 'state.json').read_text())
        authorize_fixture(self.plan, state, Path(os.path.relpath(program)),
            candidate=GOOD, approved_by='FIXTURE_TEST_OWNER')
        second = run(queue_dir, max_jobs=1)
        self.assertEqual(second['statuses'][job['goal_id']], 'COMPLETED_EXPLORATORY')
        self.assertEqual(second['processed'], 1)
        self.assertEqual(run(queue_dir, max_jobs=1)['processed'], 0)
        queue = json.loads((queue_dir / 'state.json').read_text())
        self.assertEqual(queue['jobs'][job['goal_id']]['network_requests_reserved'], 0)
        self.assertEqual(queue['jobs'][job['goal_id']]['attempt_count'], 2)

    def test_symlinked_fixture_directory_is_rejected(self):
        external = self.directory / 'outside'
        external.mkdir()
        program = self.directory / 'program'
        program.mkdir()
        (program / 'isolated_code_fixture').symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'outside program'):
            fixture_source(program)
        self.assertFalse((external / 'experiment.py').exists())

    def test_code_revision_journal_write_and_commit_faults_are_recoverable(self):
        state = self._initial_failure()
        authorize_fixture(self.plan, state, self.directory,
            candidate=GOOD, approved_by='FIXTURE_TEST_OWNER')
        original = deepcopy(state)
        real_artifact_write = code_recovery._write_or_verify
        def fail_journal(path, value):
            if path.name == 'code_repair_transaction_v1.json':
                raise OSError('injected code journal failure')
            return real_artifact_write(path, value)
        with patch.object(code_recovery, '_write_or_verify', side_effect=fail_journal):
            with self.assertRaisesRegex(OSError, 'injected code journal failure'):
                replan(self.plan, state, self.directory)
        self.assertEqual(state, original)
        self.assertTrue(replan(self.plan, state, self.directory))
        write_state(self.directory / 'state.json', state)
        real_state_write = code_recovery.write_state
        def fail_commit(path, value):
            if path.name == 'code_repair_transaction_v1.json':
                raise OSError('injected code commit failure')
            return real_state_write(path, value)
        with patch.object(code_recovery, 'write_state', side_effect=fail_commit):
            with self.assertRaisesRegex(OSError, 'injected code commit failure'):
                code_recovery.finalize_transaction(state, self.directory)
        self.assertEqual(state['code_repair_revision']['status'], 'REVISION_PREPARED')
        self.assertEqual(json.loads((self.directory /
            'code_repair_transaction_v1.json').read_text())['transaction_state'],
            'REVISION_PREPARED')
        code_recovery.finalize_transaction(state, self.directory)
        self.assertEqual(state['code_repair_revision']['status'], 'REVISION_ACTIVE')
        self.assertEqual(json.loads((self.directory /
            'code_repair_transaction_v1.json').read_text())['transaction_state'],
            'REVISION_COMMITTED')
        active = deepcopy(state)
        self.assertFalse(replan(self.plan, state, self.directory))
        self.assertEqual(state, active)

    def test_interrupted_patch_backup_restores_and_resumes(self):
        state = self._initial_failure()
        authorize_fixture(self.plan, state, self.directory,
            candidate=GOOD, approved_by='FIXTURE_TEST_OWNER')
        self.assertTrue(replan(self.plan, state, self.directory))
        write_state(self.directory / 'state.json', state)
        self.assertEqual(json.loads((self.directory /
            'code_repair_transaction_v1.json').read_text())['transaction_state'],
            'REVISION_PREPARED')
        source = fixture_source(self.directory)
        source.with_name('.experiment.py.repair-backup').write_bytes(source.read_bytes())
        source.write_text(BAD)
        result = run_research_program(GOAL, self.directory)
        self.assertEqual(result['status'], 'RESEARCH_COMPLETED_EXPLORATORY')
        repaired = json.loads((self.directory / 'code_repair_result.json').read_text())
        self.assertTrue(repaired['recovered_interruption'])
        self.assertEqual(json.loads((self.directory /
            'code_repair_transaction_v1.json').read_text())['transaction_state'],
            'REVISION_COMMITTED')

    def test_verified_patch_before_checkpoint_is_reused(self):
        state = self._initial_failure()
        authorize_fixture(self.plan, state, self.directory,
            candidate=GOOD, approved_by='FIXTURE_TEST_OWNER')
        self.assertTrue(replan(self.plan, state, self.directory))
        write_state(self.directory / 'state.json', state)
        source = fixture_source(self.directory)
        source.write_text(GOOD)
        (source.parent / 'result.json').write_text('{"answer":42}')
        result = run_research_program(GOAL, self.directory)
        self.assertEqual(result['status'], 'RESEARCH_COMPLETED_EXPLORATORY')
        repaired = json.loads((self.directory / 'code_repair_result.json').read_text())
        self.assertTrue(repaired['recovered_existing_output'])

    def test_supervisor_sigkill_during_patch_recovers_backup(self):
        state = self._initial_failure()
        authorize_fixture(self.plan, state, self.directory,
            candidate=SLOW, approved_by='FIXTURE_TEST_OWNER')
        env = {'PATH': '/usr/bin:/bin',
            'PYTHONPATH': str(Path(__file__).resolve().parents[2])}
        command = [sys.executable, '-m', 'universal_agent.process_supervisor',
            '--research-goal', GOAL, '--program-dir', str(self.directory)]
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True)
        source = fixture_source(self.directory)
        backup = source.with_name('.experiment.py.repair-backup')
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if backup.exists() and hashlib.sha256(source.read_bytes()).hexdigest() == \
                        hashlib.sha256(SLOW.encode()).hexdigest():
                    break
                time.sleep(.01)
            else:
                self.fail('Patch application point was not observed')
            os.kill(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            self.assertEqual(process.returncode, -signal.SIGKILL)
            self.assertTrue(backup.exists())
            result = run_research_program(GOAL, self.directory)
            self.assertEqual(result['status'], 'RESEARCH_COMPLETED_EXPLORATORY')
            self.assertFalse(backup.exists())
            repaired = json.loads((self.directory / 'code_repair_result.json').read_text())
            self.assertTrue(repaired['recovered_interruption'])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.communicate()

    def test_supervisor_sigkill_during_rollback_preserves_original_dag(self):
        first = self._initial_failure()
        source = fixture_source(self.directory)
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        authorize_fixture(self.plan, first, self.directory,
            candidate=BAD, approved_by='FIXTURE_TEST_OWNER')
        child = multiprocessing.get_context('fork').Process(
            target=_kill_supervisor_after_rollback, args=(self.directory,))
        child.start()
        child.join(timeout=20)
        if child.is_alive():
            child.kill()
            child.join()
            self.fail('Rollback Supervisor did not stop')
        self.assertEqual(child.exitcode, -signal.SIGKILL)
        interrupted = json.loads((self.directory / 'state.json').read_text())
        self.assertEqual(interrupted['code_repair_revision']['status'],
                         'REVISION_ROLLED_BACK')
        self.assertEqual(interrupted['goal_id'], first['goal_id'])
        self.assertEqual(interrupted['tasks'], first['tasks'])
        self.assertEqual(json.loads((self.directory /
            'code_repair_transaction_v1.json').read_text())['transaction_state'],
            'REVISION_COMMITTED')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_sha)
        resumed = run_research_program(GOAL, self.directory)
        self.assertEqual(resumed['status'], 'RESEARCH_BLOCKED')
        self.assertEqual(json.loads((self.directory /
            'code_repair_transaction_v1.json').read_text())['transaction_state'],
            'REVISION_ROLLED_BACK')
        self.assertEqual(json.loads((self.directory / 'state.json').read_text())[
            'records']['analyze_fixture']['attempts'], 1)


if __name__ == '__main__':
    unittest.main()
