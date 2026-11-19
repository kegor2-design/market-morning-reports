"""Real OS process interruption of the research-only Supervisor and Worker."""
import json
import multiprocessing
from datetime import datetime, timedelta, timezone
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from universal_agent.research_job import PRIVATE_ROOT, _worker_identity, supervise


def _run_with_outer_deadline(manifest, job, deadline):
    supervise(manifest, job, outer_deadline_utc=deadline)


class ProcessRecoveryTests(unittest.TestCase):
    def setUp(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=PRIVATE_ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = self.root / 'manifest.json'
        self.job = self.root / 'job'
        self.manifest.write_text(json.dumps({
            'schema_version': 1, 'job_id': 'kill_recovery_test',
            'goal': 'Verify research process interruption and safe resume',
            'mode': 'synthetic_research',
            'hypothesis': {'direction': 'mean_above', 'threshold': 0},
            'synthetic_values': [-1, 2, 4], 'max_seconds': 20,
            'max_restarts': 1, 'max_model_calls': 0,
            'fixture_delay_before_output_seconds': 3}))

    def start(self):
        return subprocess.Popen([sys.executable, '-m', 'universal_agent.research_job',
            'supervise', '--manifest', str(self.manifest), '--state-dir', str(self.job)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True)

    def active(self):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            path = self.job / 'job.json'
            if path.exists():
                try:
                    state = json.loads(path.read_text())
                    pid = state.get('worker_pid')
                    if state.get('task_status') == 'RUNNING' and \
                            _worker_identity(pid, self.job.resolve()) is not None:
                        return state
                except (ValueError, OSError):
                    pass
            time.sleep(.02)
        self.fail('Research-only worker did not start')

    def test_worker_sigkill_recovers_without_duplicate_completion(self):
        supervisor = self.start()
        try:
            state = self.active()
            os.kill(state['worker_pid'], signal.SIGKILL)
            supervisor.communicate(timeout=15)
            final = json.loads((self.job / 'job.json').read_text())
            self.assertEqual(final['status'], 'VERIFIED_RESEARCH_CONCLUSION')
            self.assertEqual(final['attempts'], 2)
            self.assertGreaterEqual(final['worker_crashes'], 1)
            self.assertEqual(final['duplicate_completion_count'], 0)
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait()
            supervisor.communicate()

    def test_outer_goal_deadline_stops_owned_child_and_persists_failure(self):
        deadline = datetime.now(timezone.utc) + timedelta(seconds=1)
        result = supervise(self.manifest, self.job, outer_deadline_utc=deadline)
        self.assertEqual(result['status'], 'FAILED_TERMINAL')
        self.assertEqual(result['reason'], 'Wall-time budget exhausted')
        self.assertEqual(result['duplicate_completion_count'], 0)
        self.assertEqual(json.loads((self.job / 'job.json').read_text())['status'],
                         'FAILED_TERMINAL')
        self.assertIsNone(_worker_identity(result['worker_pid'], self.job.resolve()))

    def test_stopped_owned_worker_is_killed_after_shutdown_grace(self):
        deadline = datetime.now(timezone.utc) + timedelta(seconds=1)
        supervisor = multiprocessing.get_context('fork').Process(
            target=_run_with_outer_deadline,
            args=(self.manifest, self.job, deadline))
        started = time.monotonic()
        supervisor.start()
        worker_pid = None
        try:
            state = self.active()
            worker_pid = state['worker_pid']
            os.kill(worker_pid, signal.SIGSTOP)
            supervisor.join(timeout=7)
            self.assertFalse(supervisor.is_alive())
            final = json.loads((self.job / 'job.json').read_text())
            self.assertEqual(final['status'], 'FAILED_TERMINAL')
            self.assertEqual(final['reason'], 'Wall-time budget exhausted')
            self.assertIsNone(_worker_identity(worker_pid, self.job.resolve()))
            self.assertLess(time.monotonic() - started, 6)
            self.assertTrue(any(event.get('event') == 'WORKER_EXITED' and
                event.get('exit_code') == -signal.SIGKILL for event in final['events']))
        finally:
            if supervisor.is_alive():
                supervisor.kill()
                supervisor.join()
            if worker_pid and _worker_identity(worker_pid, self.job.resolve()) is not None:
                os.kill(worker_pid, signal.SIGKILL)

    def test_worker_killed_after_result_before_final_state(self):
        data = json.loads(self.manifest.read_text())
        data.pop('fixture_delay_before_output_seconds')
        data['fixture_delay_after_output_seconds'] = 3
        self.manifest.write_text(json.dumps(data))
        supervisor = self.start()
        try:
            state = self.active()
            end = time.monotonic() + 5
            while not (self.job / 'action_result.json').exists() and time.monotonic() < end:
                time.sleep(.02)
            self.assertTrue((self.job / 'action_result.json').exists())
            self.assertIsNotNone(_worker_identity(state['worker_pid'], self.job.resolve()))
            os.kill(state['worker_pid'], signal.SIGKILL)
            supervisor.communicate(timeout=10)
            final = json.loads((self.job / 'job.json').read_text())
            self.assertEqual(final['status'], 'VERIFIED_RESEARCH_CONCLUSION')
            self.assertEqual(final['attempts'], 1)
            self.assertEqual(final['duplicate_completion_count'], 0)
            self.assertGreaterEqual(final['worker_crashes'], 1)
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait()
            supervisor.communicate()

    def test_supervisor_sigkill_attaches_surviving_worker(self):
        supervisor = self.start()
        try:
            state = self.active()
            cmd = (Path('/proc') / str(supervisor.pid) / 'cmdline').read_bytes()
            self.assertIn(b'universal_agent.research_job', cmd)
            self.assertIn(os.fsencode(str(self.manifest)), cmd)
            os.kill(supervisor.pid, signal.SIGKILL)
            supervisor.wait(timeout=5)
            resumed = self.start()
            try:
                resumed.communicate(timeout=15)
            finally:
                if resumed.poll() is None:
                    resumed.kill()
                    resumed.wait()
                resumed.communicate()
            final = json.loads((self.job / 'job.json').read_text())
            self.assertEqual(final['status'], 'VERIFIED_RESEARCH_CONCLUSION')
            self.assertEqual(final['attempts'], 1)
            self.assertEqual(final['duplicate_completion_count'], 0)
            self.assertTrue(any(event['event'] == 'SURVIVING_WORKER_ATTACHED'
                                for event in final['events']))
            self.assertEqual(final['worker_pid'], state['worker_pid'])
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait()
            supervisor.communicate()


if __name__ == '__main__':
    unittest.main()
