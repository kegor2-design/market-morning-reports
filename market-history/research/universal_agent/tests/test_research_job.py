import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Timer
from unittest.mock import patch

from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.agent2_synthetic import execute as synthetic_execute
from universal_agent.engine import write_state
from universal_agent.research_job import (PRIVATE_ROOT, manifest_load, plan_for,
                                          verify_artifact, supervise)


class ResearchJobBoundaryTests(unittest.TestCase):
    def setUp(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=PRIVATE_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'manifest.json'
        self.state = self.root / 'state'
        self.state.mkdir()
        self.data = {'schema_version': 1, 'job_id': 'test_job',
                     'goal': 'Evaluate this bounded synthetic signal',
                     'mode': 'synthetic_research',
                     'hypothesis': {'direction': 'mean_above', 'threshold': 0},
                     'synthetic_values': [-1, 2, 4], 'max_seconds': 30,
                     'max_restarts': 1, 'max_model_calls': 0}

    def save(self):
        self.manifest.write_text(json.dumps(self.data))

    def test_manifest_rejects_unreviewed_actions_and_model_budget(self):
        for added in ({'action': 'WRITE_PRODUCTION_DB'},
                      {'action': 'FETCH_UNAPPROVED_NETWORK'},
                      {'action': 'DISABLE_SANDBOX'},
                      {'action': 'REVEAL_CREDENTIALS'},
                      {'max_model_calls': 3}):
            with self.subTest(added=added):
                self.data.update(added)
                self.save()
                with self.assertRaises(ValidationError):
                    manifest_load(self.manifest)
                self.data.pop('action', None)
                self.data['max_model_calls'] = 0

    def test_result_tampering_fails_independent_verification(self):
        self.save()
        manifest, digest = manifest_load(self.manifest)
        plan = plan_for(manifest, digest)
        result = synthetic_execute({'synthetic_values': self.data['synthetic_values']}, {})
        write_state(self.state / 'action_result.json',
                    {'task_key': plan['task_key'], 'action': plan['action'],
                     'input_sha256': plan['input_sha256'], 'result': result})
        verify_artifact(manifest, plan, self.state)
        artifact = json.loads((self.state / 'action_result.json').read_text())
        artifact['result']['mean'] = 99
        write_state(self.state / 'action_result.json', artifact)
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            verify_artifact(manifest, plan, self.state)

    def test_model_declared_pit_completion_is_rejected(self):
        self.data = {'schema_version': 1, 'job_id': 'pit_test',
                     'goal': 'Validate point in time availability before market research',
                     'mode': 'pit_problem', 'max_seconds': 30,
                     'max_restarts': 1, 'max_model_calls': 1}
        self.save()
        manifest, digest = manifest_load(self.manifest)
        plan = plan_for(manifest, digest)
        solver = self.state / 'pit_solver'
        solver.mkdir()
        state_path = solver / 'problem_state.json'
        write_state(state_path, {'problem_id': 'pit_test', 'status': 'VERIFIED_RESOLUTION',
                                 'execution_result': {'status': 'PIT_VERIFIED',
                                                      'goal_sources_ready': False}})
        from universal_agent.research_job import sha
        write_state(self.state / 'action_result.json',
                    {'task_key': plan['task_key'], 'action': plan['action'],
                     'input_sha256': plan['input_sha256'], 'result': {
                         'status': 'VERIFIED_RESOLUTION', 'problem_state': str(state_path),
                         'problem_state_sha256': sha(state_path),
                         'solution_request_sha256': None}})
        with self.assertRaisesRegex(ValueError, 'Model-declared PIT completion'):
            verify_artifact(manifest, plan, self.state)

    def test_rejected_hypothesis_runs_bounded_follow_on_and_reuses_checkpoint(self):
        self.data['synthetic_values'] = [-4, -2, -1]
        self.save()
        first = supervise(self.manifest, self.state)
        self.assertEqual(first['status'], 'VERIFIED_RESEARCH_CONCLUSION')
        self.assertFalse(first['conclusion']['hypothesis_supported'])
        transition = first['conclusion']['hypothesis_transition']
        self.assertEqual(transition['transition_count'], 1)
        self.assertEqual(transition['hypothesis']['direction'], 'mean_below')
        self.assertEqual(transition['result']['mean'], -7 / 3)
        resumed = supervise(self.manifest, self.state)
        self.assertTrue(resumed['reused_checkpoint'])
        self.assertEqual(resumed['attempts'], 1)
        self.assertEqual(resumed['duplicate_completion_count'], 0)

    def test_market_e2e_manifest_limits_fault_and_hypothesis_budget(self):
        from universal_agent.guided_experiment import PRIVATE_ROOT as data_root
        self.data = {'schema_version': 1, 'job_id': 'bounded_market_test',
                     'goal': 'Evaluate crash-risk hypotheses on sealed historical folds',
                     'mode': 'guided_e2e', 'ai_state_dir': str(self.root / 'ai'),
                     'guided_state_dir': str(data_root / 'bounded_market_test'),
                     'fault_kind': 'library_call', 'max_follow_on_hypotheses': 2,
                     'max_seconds': 600, 'max_restarts': 1, 'max_model_calls': 10}
        self.save()
        manifest_load(self.manifest)
        for key, bad in (('fault_kind', 'disable_sandbox'),
                         ('max_follow_on_hypotheses', 3),
                         ('max_model_calls', 11), ('max_seconds', 601)):
            with self.subTest(key=key):
                original = self.data[key]
                self.data[key] = bad
                self.save()
                with self.assertRaises(ValidationError):
                    manifest_load(self.manifest)
                self.data[key] = original

    def test_actual_worker_sigkill_then_resume_without_duplicate(self):
        """Kill a real child process before it can write an artifact."""
        self.save()
        actual_popen = subprocess.Popen
        launches = []

        def injected_popen(command, **kwargs):
            if not launches:
                process = actual_popen(['/bin/sleep', '5'], **kwargs)
                launches.append(process.pid)
                Timer(0.15, lambda: os.kill(process.pid, signal.SIGKILL)).start()
                return process
            return actual_popen(command, **kwargs)

        with patch('universal_agent.research_job.subprocess.Popen', side_effect=injected_popen):
            result = supervise(self.manifest, self.state)
        self.assertEqual(result['status'], 'VERIFIED_RESEARCH_CONCLUSION')
        self.assertEqual(result['worker_crashes'], 1)
        self.assertEqual(result['worker_restarts'], 1)
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(result['duplicate_completion_count'], 0)
        self.assertEqual(supervise(self.manifest, self.state)['attempts'], 2)

    def test_actual_supervisor_sigkill_then_checkpoint_resume(self):
        """Kill the supervisor and its test worker; resume the sealed job."""
        self.save()
        code = (
            'import subprocess; from pathlib import Path; '
            'from universal_agent.research_job import supervise; '
            'real=subprocess.Popen; '
            'subprocess.Popen=lambda command, **kwargs: real(["/bin/sleep", "30"], **kwargs); '
            f'supervise(Path({str(self.manifest)!r}), Path({str(self.state)!r}))'
        )
        process = subprocess.Popen([sys.executable, '-c', code],
                                   env={'PATH': '/usr/bin:/bin',
                                        'PYTHONPATH': str(Path(__file__).resolve().parents[2])},
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, text=True)
        worker_pid = None
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if (self.state / 'job.json').exists():
                    saved = json.loads((self.state / 'job.json').read_text())
                    if saved.get('worker_pid') and saved['status'] == 'RUNNING':
                        worker_pid = saved['worker_pid']
                        break
                time.sleep(.02)
            self.assertIsNotNone(worker_pid, 'Test supervisor did not start a worker')
            os.kill(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
            deferred = supervise(self.manifest, self.state)
            self.assertEqual(deferred['status'], 'RUNNING')
            self.assertEqual(deferred['attempts'], 1)
            self.assertIn('Prior worker is still active', deferred['reason'])
            os.kill(worker_pid, signal.SIGKILL)
            recovered = supervise(self.manifest, self.state)
            self.assertEqual(recovered['status'], 'VERIFIED_RESEARCH_CONCLUSION')
            self.assertEqual(recovered['attempts'], 2)
            self.assertEqual(recovered['duplicate_completion_count'], 0)
            self.assertEqual(supervise(self.manifest, self.state)['attempts'], 2)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            if process.stderr is not None:
                process.stderr.close()
            if worker_pid is not None:
                try:
                    os.kill(worker_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    unittest.main()
