import json
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == '__main__':
    unittest.main()
