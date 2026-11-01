import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.agent2 import (TOOL, DeterministicTestAdapter, cycle,
                                    ReplayAdapter, validate_objective, validate_plan,
                                    validate_tool_candidate)


class Agent2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'state'
        self.repo = Path(__file__).resolve().parents[4]
        self.objective = {'schema_version': 1, 'objective_id': 'fixture_crash_warning',
                          'domain': 'synthetic_fixture',
                          'question': 'Can a bounded synthetic signal be evaluated?'}

    def test_complete_cycle_memory_and_no_duplicate(self):
        first = cycle(self.objective, self.state, self.repo)
        self.assertEqual(first['stop_reason'], 'BUDGET_EXHAUSTED')
        self.assertEqual(first['model_status'], 'MOCKED_PLANNER_NOT_AI')
        memory = json.loads((self.state / 'research_memory.json').read_text())
        queue = json.loads((self.state / 'task_queue.json').read_text())
        self.assertEqual(memory['experiments'][0]['evaluation']['research_value'], 'FIXTURE_ONLY')
        self.assertEqual(queue['tasks']['synthetic_mean_positive']['status'], 'COMPLETED')
        self.assertEqual(queue['checkpoint_id'], 1)
        self.assertEqual(cycle(self.objective, self.state, self.repo)['stop_reason'], 'ALREADY_EVALUATED')
        self.assertEqual(json.loads((self.state / 'task_queue.json').read_text())['checkpoint_id'], 1)

    def test_stop_budget_and_approval_boundary(self):
        self.state.mkdir()
        (self.state / 'STOP').write_text('stop')
        self.assertEqual(cycle(self.objective, self.state, self.repo)['stop_reason'], 'STOP')
        plan = DeterministicTestAdapter().plan(self.objective)
        plan['execution_class'] = 'HUMAN_APPROVAL_REQUIRED'
        with self.assertRaises(ValueError):
            validate_plan(plan)
        plan['execution_class'] = 'SERVER_EXECUTABLE'
        plan['execution_budget']['max_tasks'] = 100
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_contract_and_sensitive_data_rejection(self):
        with self.assertRaises(ValueError):
            validate_objective(dict(self.objective, question='api_key=example'))
        plan = DeterministicTestAdapter().plan(self.objective)
        plan['tool_id'] = 'shell'
        with self.assertRaises(ValueError):
            validate_plan(plan)
        self.assertEqual(TOOL['side_effects'], [])

    def test_existing_worker_rejects_unregistered_fixture_task(self):
        from universal_agent.offline_worker import load_plan
        self.state.mkdir()
        path = self.state / 'plan.json'
        path.write_text(json.dumps({'schema_version': 1, 'research_project': 'agent2_synthetic',
          'adapter': 'agent2_synthetic', 'tasks': [{'task_id': 'unsafe', 'task_type': 'shell',
          'execution_class': 'SERVER_EXECUTABLE', 'priority': 0, 'dependencies': [],
          'delay_hours': 0, 'resource_budget': {'max_seconds': 10, 'max_attempts': 1}}]}))
        with self.assertRaises(ValueError):
            load_plan(path)

    def test_tool_candidate_cannot_be_active(self):
        candidate = {'schema_version': 1, 'tool_id': 'new_indicator',
                     'status': 'CODEX_REQUIRED', 'specification': 'Compute an offline feature',
                     'review_steps': ['isolated_implementation', 'static_validation',
                                      'unit_tests', 'security_review', 'regression_tests',
                                      'approval', 'activation']}
        self.assertEqual(validate_tool_candidate(candidate)['status'], 'CODEX_REQUIRED')
        candidate['status'] = 'ACTIVE'
        with self.assertRaises(ValueError):
            validate_tool_candidate(candidate)

    def test_offline_replay_requires_matching_result(self):
        adapter = DeterministicTestAdapter()
        result = {'synthetic': True, 'sample_size': 3, 'mean': 2.0,
                  'tool_version': '1.0', 'pit_status': 'NOT_APPLICABLE_SYNTHETIC',
                  'performance_claim': False}
        evaluation = adapter.evaluate(result)
        evaluation['model_status'] = 'OFFLINE_REPLAY_NOT_AI'
        decision = self.state.parent / 'decisions.json'
        decision.write_text(json.dumps({'plan': adapter.plan(self.objective),
            'expected_result_sha256': hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
            'evaluation': evaluation}))
        replay = ReplayAdapter(decision)
        self.assertEqual(cycle(self.objective, self.state, self.repo, replay)['stop_reason'],
                         'BUDGET_EXHAUSTED')
        self.assertEqual(cycle(self.objective, self.state, self.repo, replay)['stop_reason'],
                         'ALREADY_EVALUATED')


if __name__ == '__main__':
    unittest.main()
