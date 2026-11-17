"""Model boundary tests use deterministic candidates and make zero model calls."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from universal_agent.ai_research_planner import request_plan, validate_candidate
from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.research_planner import plan_goal
from universal_agent.research_runtime import run, submit

GOAL = 'Study Treasury yield spread and SOFR from 2018-06-01 to 2018-06-29.'


def candidate_for(goal):
    plan = plan_goal(goal)
    return {'goal_id': plan['goal_id'], 'original_research_goal': goal,
            'market': plan['market'], 'hypothesis': plan['research_hypotheses'][0],
            'data_requirements': plan['data_requirements'],
            'allowed_sources': plan['allowed_sources'],
            'evaluation_methods': plan['evaluation_methods'],
            'task_dag': [{key: task[key] for key in ('task_id', 'task_type',
                         'dependencies', 'allowed_actions')} for task in plan['tasks']],
            'pit_status': 'UNVERIFIED', 'holdout_status': 'NOT_AVAILABLE'}


class AIPlannerBoundaryTests(unittest.TestCase):
    def test_host_rejects_goal_source_action_and_dag_changes(self):
        good = candidate_for(GOAL)
        self.assertEqual(validate_candidate(GOAL, good)['goal_id'], good['goal_id'])
        for key, value in [('original_research_goal', 'Study another goal.'),
                           ('allowed_sources', ['UNREVIEWED_PROVIDER']),
                           ('pit_status', 'VERIFIED')]:
            bad = copy.deepcopy(good)
            bad[key] = value
            with self.assertRaises(Exception, msg=key):
                validate_candidate(GOAL, bad)
        for change in ('action', 'cycle'):
            bad = copy.deepcopy(good)
            if change == 'action':
                bad['task_dag'][0]['allowed_actions'] = ['RUN_SHELL']
            else:
                bad['task_dag'][0]['dependencies'] = ['analyze_rates']
            with self.assertRaisesRegex(ValueError, 'DAG'):
                validate_candidate(GOAL, bad)

    def test_distinct_reviewed_goals_have_distinct_plans(self):
        goals = [GOAL,
            '한국 증시 과거 급락 구간을 식별하고 급락 전 변동성 변화를 연구하라.',
            '지표 116의 한국 증시 선행 신호 PIT를 검증하라.']
        candidates = [candidate_for(goal) for goal in goals]
        for goal, candidate in zip(goals, candidates):
            validate_candidate(goal, candidate)
        self.assertEqual(len({tuple(task['task_type'] for task in item['task_dag'])
                              for item in candidates}), 3)

    def test_unapproved_model_call_never_reaches_provider(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            called = []
            result = request_plan(GOAL, Path(folder), caller=lambda *a, **k: called.append(a))
            self.assertEqual(result['status'], 'APPROVAL_REQUIRED')
            self.assertEqual(called, [])
            self.assertFalse((Path(folder) / 'ai_program_request.json').exists())

    def test_reserved_failure_is_not_replayed(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            approval = {'status': 'APPROVED', 'goal_id': plan_goal(GOAL)['goal_id'],
                        'max_calls': 1, 'max_cost_usd': 1, 'max_seconds': 30,
                        'provider': 'INJECTED_TEST'}
            calls = []
            def failed(*args, **kwargs):
                calls.append(1)
                raise subprocess.TimeoutExpired('isolated-model', 30)
            first = request_plan(GOAL, directory, approval=approval, timeout=30,
                                 caller=failed)
            second = request_plan(GOAL, directory, approval=approval, timeout=30,
                                  caller=failed)
            self.assertEqual(first['error_type'], 'TIMEOUT')
            self.assertEqual(second['status'], 'BLOCKED_UNCERTAIN_MODEL_CALL')
            self.assertEqual(len(calls), 1)
            self.assertEqual(json.loads((directory / 'ai_program_request.json').read_text())[
                'status'], 'BLOCKED')

    def test_invalid_provider_output_is_sealed_and_never_executed(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            approval = {'status': 'APPROVED', 'goal_id': plan_goal(GOAL)['goal_id'],
                        'max_calls': 1, 'max_cost_usd': 1, 'max_seconds': 30,
                        'provider': 'INJECTED_TEST'}
            calls = []
            def invalid(*args, **kwargs):
                calls.append(1)
                (directory / 'ai_program_response.json').write_text('{bad json')
                return subprocess.CompletedProcess([], 0, '', '')
            first = request_plan(GOAL, directory, approval=approval, timeout=30,
                                 caller=invalid)
            second = request_plan(GOAL, directory, approval=approval, timeout=30,
                                  caller=invalid)
            self.assertEqual(first['status'], 'BLOCKED_MODEL_OUTPUT')
            self.assertEqual(second['status'], 'BLOCKED_UNCERTAIN_MODEL_CALL')
            self.assertEqual(len(calls), 1)

    def test_real_cli_path_blocks_without_enforceable_cost_ceiling(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            approval = {'status': 'APPROVED', 'goal_id': plan_goal(GOAL)['goal_id'],
                        'max_calls': 1, 'max_cost_usd': 1, 'max_seconds': 30}
            result = request_plan(GOAL, Path(folder), approval=approval, timeout=30)
            self.assertEqual(result['status'], 'BLOCKED_COST_ENFORCEMENT')
            self.assertFalse((Path(folder) / 'ai_program_request.json').exists())

    def test_auth_failure_is_sealed_without_retry(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            approval = {'status': 'APPROVED', 'goal_id': plan_goal(GOAL)['goal_id'],
                        'max_calls': 1, 'max_cost_usd': 1, 'max_seconds': 30,
                        'provider': 'INJECTED_TEST'}
            calls = []
            def unauthorized(*args, **kwargs):
                calls.append(1)
                return subprocess.CompletedProcess([], 1, '', 'HTTP 401 unauthorized')
            first = request_plan(GOAL, directory, approval=approval, timeout=30,
                                 caller=unauthorized)
            second = request_plan(GOAL, directory, approval=approval, timeout=30,
                                  caller=unauthorized)
            self.assertEqual(first['error_type'], 'AUTH_ERROR')
            self.assertEqual(second['status'], 'BLOCKED_UNCERTAIN_MODEL_CALL')
            self.assertEqual(len(calls), 1)

    def test_candidate_enters_persistent_queue_and_executes_reviewed_task(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            candidate = candidate_for(GOAL)
            job = submit(GOAL, directory, ai_candidate=candidate)
            self.assertIsNotNone(job['ai_candidate_sha256'])
            with self.assertRaisesRegex(ValueError, 'candidate changed'):
                submit(GOAL, directory)
            result = run(directory, max_jobs=1, max_seconds=30)
            self.assertEqual(result['processed'], 1)
            program_dir = directory / 'programs' / job['goal_id']
            saved = json.loads((program_dir / 'ai_program_candidate.json').read_text())
            saved.pop('updated_at_utc', None)
            self.assertEqual(saved, candidate)
            state = json.loads((program_dir / 'state.json').read_text())
            self.assertEqual(state['records']['discover_ust_2y']['status'], 'VERIFIED')


if __name__ == '__main__':
    unittest.main()
