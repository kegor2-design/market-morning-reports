"""Host validation and restart checks for the bounded research program."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.research_planner import plan_goal, validate_plan, _task
from universal_agent.process_supervisor import run_research_program


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
        with self.assertRaisesRegex(ValueError, 'Unsupported goal'):
            plan_goal('Analyze Korean house prices without reviewed sources')

    def test_active_child_deferral_keeps_independent_tasks_running(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as root:
            program_dir = Path(root) / 'program'
            with patch('universal_agent.research_job.supervise',
                       return_value={'status': 'RUNNING'}):
                run_research_program(GOAL, program_dir)
                resumed = run_research_program(GOAL, program_dir)
            selected = [item['selected'] for item in resumed['selection_history']]
            self.assertIn('collect_ust_2y', selected)
            self.assertIn('collect_ust_10y', selected)
            self.assertIn('collect_nyfed_sofr', selected)
            self.assertNotIn('analyze_rates', selected)
            import json
            state = json.loads((program_dir / 'state.json').read_text())
            self.assertEqual(state['network_requests_reserved'], 3)
            self.assertTrue(all(state['records']['collect_' + series]['attempts'] == 1
                                for series in ('ust_2y', 'ust_10y', 'nyfed_sofr')))


if __name__ == '__main__':
    unittest.main()
