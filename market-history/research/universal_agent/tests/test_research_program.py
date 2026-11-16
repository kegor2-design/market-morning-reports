"""Host validation and restart checks for the bounded research program."""
import copy
import unittest

from universal_agent.research_planner import plan_goal, validate_plan, _task


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


if __name__ == '__main__':
    unittest.main()
