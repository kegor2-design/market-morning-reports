"""Model boundary tests use deterministic candidates and make zero model calls."""
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from universal_agent.ai_research_planner import (capability_registry, request_plan,
                                                  validate_candidate)
from universal_agent.engine import canonical
from universal_agent.rate_analysis import SIGNALS
from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.research_planner import plan_goal
from universal_agent.research_runtime import run, submit
from universal_agent.source_adapters import REGISTRY

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
    def test_treasury_archive_ranges_match_reviewed_official_files(self):
        source = REGISTRY['US_TREASURY']
        self.assertTrue(source.uri('UST_2Y', '2018-06-01', '2018-06-29').endswith(
            'par-yield-curve-rates-2010-2019.csv'))
        self.assertTrue(source.uri('UST_2Y', '2020-08-03', '2020-08-28').endswith(
            'par-yield-curve-rates-2020-2023.csv'))
        with self.assertRaisesRegex(ValueError, 'supported year'):
            source.uri('UST_2Y', '2024-08-01', '2024-08-30')

    def test_treasury_archive_schema_variants_parse_without_imputation(self):
        source = REGISTRY['US_TREASURY']
        old = b'Date,2 Yr,10 Yr\n08/03/18,0.20,0.40\n'
        newer = b'date,2 yr,10 yr\n08/03/2020,0.11,0.55\n'
        self.assertEqual(source.parse('UST_2Y', old, {'2018-08-03'}),
                         {'2018-08-03': '0.20'})
        self.assertEqual(source.parse('UST_10Y', newer, {'2020-08-03'}),
                         {'2020-08-03': '0.55'})
        with self.assertRaisesRegex(ValueError, 'columns changed'):
            source.parse('UST_2Y', b'date,unexpected\n08/03/2020,1\n',
                         {'2020-08-03'})

    def test_same_goal_accepts_reviewed_alternative_hypothesis_and_dag(self):
        base = candidate_for(GOAL)
        alternative = copy.deepcopy(base)
        alternative['hypothesis'] = SIGNALS['widening_spread']
        alternative['task_dag'][1]['dependencies'] = ['discover_ust_2y']
        first = validate_candidate(GOAL, base)
        second = validate_candidate(GOAL, alternative)
        self.assertNotEqual(first['research_hypotheses'], second['research_hypotheses'])
        self.assertNotEqual(first['tasks'], second['tasks'])
        self.assertEqual(second['goal_contract']['version'], 2)
        self.assertEqual(first['goal_contract']['original_research_goal'],
                         second['goal_contract']['original_research_goal'])
        self.assertEqual(first['resource_budget'], second['resource_budget'])
        self.assertEqual(capability_registry()['rate_signals']['widening_spread'],
                         alternative['hypothesis'])

    def test_candidate_can_add_reviewed_acquisition_with_dependency(self):
        candidate = candidate_for(GOAL)
        candidate['task_dag'].insert(3, {
            'task_id': 'collect_ust_2y', 'task_type': 'DATA_ACQUISITION',
            'dependencies': ['discover_ust_2y'], 'allowed_actions': ['DATA_RECOVERY']})
        candidate['task_dag'][-1]['dependencies'].append('collect_ust_2y')
        plan = validate_candidate(GOAL, candidate)
        self.assertEqual(plan['goal_contract']['version'], 2)
        self.assertEqual(next(t for t in plan['tasks'] if t['task_id'] ==
                              'collect_ust_2y')['resource_budget']['max_network_requests'], 1)
        self.assertEqual(capability_registry()['capabilities']['DATA_ACQUISITION'][
                         'validation_status'], 'IMPLEMENTED')
        missing_dependency = copy.deepcopy(candidate)
        missing_dependency['task_dag'][-1]['dependencies'].remove('collect_ust_2y')
        with self.assertRaisesRegex(ValueError, 'omits acquisition'):
            validate_candidate(GOAL, missing_dependency)
        unauthorized = copy.deepcopy(candidate)
        unauthorized['task_dag'][3]['allowed_actions'] = ['RUN_SHELL']
        with self.assertRaisesRegex(ValueError, 'unimplemented capability or action'):
            validate_candidate(GOAL, unauthorized)

    def test_acquisition_plan_is_sealed_in_existing_queue(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            candidate = candidate_for(GOAL)
            candidate['task_dag'].insert(3, {
                'task_id': 'collect_ust_2y', 'task_type': 'DATA_ACQUISITION',
                'dependencies': ['discover_ust_2y'], 'allowed_actions': ['DATA_RECOVERY']})
            candidate['task_dag'][-1]['dependencies'].append('collect_ust_2y')
            job = submit(GOAL, Path(folder), ai_candidate=candidate,
                         approval_required=True)
            self.assertIn('collect_ust_2y', job['tasks'])
            self.assertEqual(job['tasks']['collect_ust_2y']['resource_budget'][
                             'max_network_requests'], 1)
            self.assertEqual(run(Path(folder), max_jobs=1, max_seconds=30)['processed'], 0)
            self.assertEqual(job['status'], 'APPROVAL_REQUIRED')

    def test_unimplemented_hypothesis_and_unknown_dependency_fail_closed(self):
        candidate = candidate_for(GOAL)
        candidate['hypothesis'] = 'Novel neural macro model forecasts tomorrow SOFR'
        with self.assertRaisesRegex(ValueError, 'unimplemented'):
            validate_candidate(GOAL, candidate)
        candidate = candidate_for(GOAL)
        candidate['task_dag'][1]['dependencies'] = ['missing_task']
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            validate_candidate(GOAL, candidate)

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

    def test_nonfinite_or_boolean_model_budget_is_rejected_before_reservation(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            approval = {'status': 'APPROVED', 'goal_id': plan_goal(GOAL)['goal_id'],
                        'max_calls': 1, 'max_cost_usd': 1, 'max_seconds': 30,
                        'provider': 'INJECTED_TEST'}
            for key, value in [('max_cost_usd', float('nan')),
                               ('max_cost_usd', float('inf')),
                               ('max_cost_usd', True), ('max_calls', True),
                               ('max_seconds', True)]:
                invalid = dict(approval, **{key: value})
                result = request_plan(GOAL, directory, approval=invalid,
                                      timeout=30, caller=lambda *a, **k: self.fail('called'))
                self.assertEqual(result['status'], 'APPROVAL_REQUIRED')
            self.assertFalse((directory / 'ai_program_request.json').exists())

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

    def test_dynamic_plan_enters_runtime_without_changing_original_goal(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            candidate = candidate_for(GOAL)
            candidate['hypothesis'] = SIGNALS['widening_spread']
            candidate['task_dag'][1]['dependencies'] = ['discover_ust_2y']
            job = submit(GOAL, directory, ai_candidate=candidate)
            self.assertNotEqual(job['plan_sha256'], hashlib.sha256(
                canonical(plan_goal(GOAL))).hexdigest())
            result = run(directory, max_jobs=1, max_seconds=30)
            self.assertEqual(result['processed'], 1)
            saved = json.loads((directory / 'programs' / job['goal_id'] /
                                'state.json').read_text())
            self.assertEqual(saved['goal_contract_sha256'], job['goal_contract_sha256'])
            self.assertEqual(saved['plan']['research_goal'], GOAL)
            self.assertEqual(saved['plan']['research_hypotheses'],
                             [SIGNALS['widening_spread']])
            self.assertEqual(saved['records']['discover_ust_2y']['status'], 'VERIFIED')
            sealed = json.loads((directory / 'state.json').read_text())['jobs'][job['goal_id']]
            self.assertEqual(hashlib.sha256(canonical(sealed['ai_candidate'])).hexdigest(),
                             sealed['ai_candidate_sha256'])


if __name__ == '__main__':
    unittest.main()
