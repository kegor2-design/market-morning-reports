"""Host validation and restart checks for the bounded research program."""
import copy
import datetime
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from universal_agent import process_supervisor
from universal_agent.research_planner import (plan_goal, validate_plan, _task,
    APPROVED_INDEPENDENT_RATES_GOAL)
from universal_agent.process_supervisor import run_research_program
from universal_agent.engine import write_state
from universal_agent.isolated_codex import PRIVATE_ROOT


GOAL = 'Examine the Treasury yield rate spread and SOFR in a reviewed period.'


class ResearchProgramTests(unittest.TestCase):
    def test_goal_creates_reviewed_dag(self):
        plan = plan_goal(GOAL)
        validate_plan(plan)
        self.assertEqual(plan['resource_budget']['max_model_calls'], 0)
        self.assertFalse(plan['safety_policy']['official_claim_allowed'])
        self.assertEqual(plan['tasks'][-1]['task_type'], 'EXPERIMENT_EXECUTION')

    def test_cycle_and_duplicate_work_rejected(self):
        plan = plan_goal(GOAL)
        duplicate = copy.deepcopy(plan)
        duplicate['tasks'].append(_task('other_ust_2y', 'DATA_DISCOVERY', 30,
                                         inputs={'series': 'UST_2Y'}))
        with self.assertRaisesRegex(ValueError, 'Duplicate task type'):
            validate_plan(duplicate)
        cycle = copy.deepcopy(plan)
        cycle['tasks'][0]['dependencies'] = ['analyze_rates']
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            validate_plan(cycle)

    def test_task_cannot_expand_budget_or_permissions(self):
        plan = plan_goal(GOAL)
        plan['tasks'][0]['resource_budget']['max_network_requests'] = 1
        with self.assertRaisesRegex(ValueError, 'budget'):
            validate_plan(plan)

    def test_unreviewed_goal_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No reviewed data source'):
            plan_goal('Analyze Korean house prices without reviewed sources')

    def test_korean_goal_contract_does_not_become_us_rates(self):
        goal = '지표 116의 한국 증시 선행 신호 PIT를 검증하라.'
        plan = plan_goal(goal)
        self.assertEqual(plan['goal_contract']['original_research_goal'], goal)
        self.assertEqual(plan['market'], 'KR_EQUITY_CONTEXT')
        self.assertEqual([t['task_type'] for t in plan['tasks']], ['PIT_VALIDATION'])
        self.assertNotIn('NYFED_SOFR', plan['data_requirements'])
        changed = copy.deepcopy(plan)
        changed['research_goal'] = '미국 금리 연구로 전환'
        with self.assertRaisesRegex(ValueError, 'Goal contract'):
            validate_plan(changed)

    def test_explicit_independent_goal_has_separate_identity(self):
        goal = ('지표 116의 한국 증시 PIT를 검증하고 차단되면 독립적인 '
                '미국 국채 금리차와 SOFR 연구를 수행하라.')
        parent = plan_goal(goal)
        child = plan_goal(APPROVED_INDEPENDENT_RATES_GOAL)
        self.assertEqual(parent['market'], 'KR_EQUITY_CONTEXT')
        self.assertEqual([t['task_type'] for t in parent['tasks']], ['PIT_VALIDATION'])
        self.assertEqual(parent['goal_contract']['approved_independent_goal_ids'],
                         [child['goal_id']])
        self.assertNotEqual(parent['goal_id'], child['goal_id'])

    def test_explicit_date_window_preserved_or_rejected(self):
        goal = 'Study Treasury yield spread and SOFR from 2018-05-01 to 2018-05-31.'
        plan = plan_goal(goal)
        self.assertEqual(plan['research_period']['start'], '2018-05-01')
        self.assertEqual(plan['research_period']['end'], '2018-05-31')
        with self.assertRaisesRegex(ValueError, 'Unsupported Treasury/SOFR'):
            plan_goal('Study Treasury yield spread and SOFR from 2017-05-01 to 2017-05-31.')
        with self.assertRaisesRegex(ValueError, 'YYYY-MM-DD'):
            plan_goal('2018년 5월 Treasury yield spread와 SOFR의 관계를 연구하라.')

    def test_korean_crash_goal_has_distinct_exploratory_dag(self):
        plan = plan_goal('한국 증시 과거 급락 구간을 식별하고 급락 전 변동성 변화를 연구하라.')
        self.assertEqual(plan['market'], 'KR_EQUITY_EXPLORATORY')
        self.assertEqual([t['task_type'] for t in plan['tasks']],
                         ['KR_INDEX_VALIDATION', 'KR_CRASH_ANALYSIS'])
        self.assertEqual(plan['resource_budget']['max_network_requests'], 0)
        self.assertEqual(plan['data_requirements'], ['KOSPI_KOSDAQ_HASHED_SNAPSHOT'])

    def test_unsupported_goal_persists_and_preserves_contract(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            goal = 'Research bitcoin option implied volatility and on-chain volume.'
            result = run_research_program(goal, directory)
            self.assertEqual(result['status'], 'RESEARCH_UNSUPPORTED')
            self.assertEqual(result['network_requests_reserved'], 0)
            contract = directory / 'goal_contract.json'
            saved = json.loads(contract.read_text())
            self.assertEqual(saved['original_research_goal'], goal)
            saved['original_research_goal'] = 'Changed without approval'
            contract.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError, 'contract changed'):
                run_research_program(goal, directory)

    def test_goal_deadline_survives_restart_and_blocks_new_tasks(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            first = run_research_program(GOAL, directory, max_tasks=1, max_seconds=10)
            saved = json.loads((directory / 'state.json').read_text())
            self.assertEqual(saved['goal_budget_seconds'], 10)
            self.assertEqual(len(first['executed_tasks']), 1)
            attempts = {key: value['attempts'] for key, value in saved['records'].items()}
            saved['goal_deadline_utc'] = (datetime.datetime.now(
                datetime.timezone.utc) - datetime.timedelta(seconds=1)).isoformat()
            write_state(directory / 'state.json', saved)
            second = run_research_program(GOAL, directory, max_seconds=300)
            resumed = json.loads((directory / 'state.json').read_text())
            self.assertEqual(second['status'], 'RESEARCH_BLOCKED')
            self.assertEqual(second['next_action'], 'GOAL_DEADLINE_EXHAUSTED')
            self.assertEqual(resumed['goal_budget_seconds'], 10)
            self.assertEqual({key: value['attempts'] for key, value in
                              resumed['records'].items()}, attempts)
            for _ in range(3):
                repeated = run_research_program(GOAL, directory, max_seconds=300)
                self.assertEqual(repeated['next_action'], 'GOAL_DEADLINE_EXHAUSTED')
                repeat_state = json.loads((directory / 'state.json').read_text())
                self.assertEqual(repeat_state['goal_deadline_utc'],
                                 resumed['goal_deadline_utc'])
                self.assertEqual({key: value['attempts'] for key, value in
                                  repeat_state['records'].items()}, attempts)

    def test_clock_rollback_cannot_renew_persisted_goal_budget(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            run_research_program(GOAL, directory, max_tasks=1, max_seconds=10)
            saved = json.loads((directory / 'state.json').read_text())
            attempts = {key: value['attempts'] for key, value in saved['records'].items()}
            self.assertEqual(saved['goal_boot_id'], process_supervisor._boot_id())
            # Fault inject elapsed monotonic time and a wall clock ten minutes behind.
            saved['goal_deadline_monotonic'] = time.monotonic() - 1
            write_state(directory / 'state.json', saved)
            old_wall = datetime.datetime.now(datetime.timezone.utc) - \
                datetime.timedelta(minutes=10)
            with mock.patch.object(process_supervisor, '_wall_utc_now',
                                   return_value=old_wall):
                result = run_research_program(GOAL, directory, max_seconds=300)
            self.assertEqual(result['next_action'], 'GOAL_DEADLINE_EXHAUSTED')
            self.assertEqual({key: value['attempts'] for key, value in
                json.loads((directory / 'state.json').read_text())['records'].items()},
                attempts)

    def test_boot_change_blocks_new_tasks_until_review(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as folder:
            directory = Path(folder)
            run_research_program(GOAL, directory, max_tasks=1, max_seconds=10)
            saved = json.loads((directory / 'state.json').read_text())
            attempts = {key: value['attempts'] for key, value in saved['records'].items()}
            with mock.patch.object(process_supervisor, '_boot_id',
                                   return_value='injected-new-boot'):
                result = run_research_program(GOAL, directory, max_seconds=300)
            self.assertEqual(result['next_action'], 'GOAL_BOOT_CHANGED_REVIEW')
            self.assertEqual({key: value['attempts'] for key, value in
                json.loads((directory / 'state.json').read_text())['records'].items()},
                attempts)


if __name__ == '__main__':
    unittest.main()
