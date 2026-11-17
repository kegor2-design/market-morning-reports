import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_agent.calendar_recovery import replan
from universal_agent.engine import canonical
from universal_agent.isolated_codex import PRIVATE_ROOT
from universal_agent.research_planner import SERIES, _task, plan_goal, validate_plan
from universal_agent.research_runtime import _sync_tasks, _task as queue_task


GOAL = 'Study Treasury yield spread and SOFR from 2018-05-01 to 2018-05-31.'


class CalendarReplanTests(unittest.TestCase):
    def setUp(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=PRIVATE_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.program_dir = Path(self.temp.name)
        self.plan = plan_goal(GOAL)
        self.state = {'goal_id': self.plan['goal_id'],
            'status': 'RESEARCH_BLOCKED',
            'plan_sha256': hashlib.sha256(canonical(self.plan)).hexdigest(),
            'goal_contract_sha256': hashlib.sha256(
                canonical(self.plan['goal_contract'])).hexdigest(),
            'tasks': copy.deepcopy(self.plan['tasks']),
            'records': {}, 'replanning_history': []}
        for task in self.state['tasks']:
            self.state['records'][task['task_id']] = {
                'status': 'WAITING_DEPENDENCY' if task['task_id'] == 'analyze_rates'
                    else 'VERIFIED', 'attempts': 0 if task['task_id'] == 'analyze_rates' else 1}
        for offset, series in enumerate(SERIES, start=20):
            task = _task('collect_' + series.lower(), 'DATA_ACQUISITION', offset,
                         dependencies=['discover_' + series.lower()],
                         inputs={'series': series})
            self.state['tasks'].append(task)
            self.state['records'][task['task_id']] = {'status': 'BLOCKED_EVIDENCE',
                                                       'attempts': 1}
            self.state['tasks'][3]['dependencies'].append(task['task_id'])

    def test_replan_preserves_original_blocked_work_and_network_budget(self):
        proposal = {'root_cause': 'Reviewed full closure',
                    'solution_action': 'REVALIDATE_SEALED_SOURCE_WITH_REVIEWED_CALENDAR'}
        with patch('universal_agent.calendar_recovery.diagnose', return_value=proposal):
            self.assertTrue(replan(self.plan, self.state, self.program_dir))
        validate_plan(dict(self.plan, tasks=self.state['tasks']))
        self.assertEqual(self.state['goal_id'], self.plan['goal_id'])
        self.assertEqual(self.state['plan_sha256'], hashlib.sha256(canonical(self.plan)).hexdigest())
        self.assertEqual(len(self.state['plan_versions']), 1)
        self.assertEqual(self.state['records']['collect_ust_2y']['status'], 'BLOCKED_EVIDENCE')
        self.assertNotIn('collect_ust_2y', self.state['tasks'][3]['dependencies'])
        self.assertTrue(all(task['resource_budget']['max_network_requests'] == 0
            for task in self.state['tasks'] if task['task_type'] ==
            'DATA_CALENDAR_REVALIDATION'))

    def test_queue_accepts_only_sealed_unexecuted_analysis_revision(self):
        proposal = {'root_cause': 'Reviewed full closure',
                    'solution_action': 'REVALIDATE_SEALED_SOURCE_WITH_REVIEWED_CALENDAR'}
        with patch('universal_agent.calendar_recovery.diagnose', return_value=proposal):
            replan(self.plan, self.state, self.program_dir)
        job = {'checkpoint': str(self.program_dir / 'state.json'),
               'tasks': {task['task_id']: queue_task(task)
                         for task in self.plan['tasks']}}
        job['tasks']['analyze_rates']['status'] = 'WAITING_DEPENDENCY'
        _sync_tasks(job, self.state)
        self.assertEqual(job['tasks']['analyze_rates']['calendar_revision_sha256'],
                         self.state['calendar_revision']['sha256'])
        altered = copy.deepcopy(self.state)
        altered['tasks'][3]['inputs']['calendar_revision_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'input changed'):
            _sync_tasks({'checkpoint': str(self.program_dir / 'state.json'),
                         'tasks': {task['task_id']: queue_task(task)
                                   for task in self.plan['tasks']}}, altered)


if __name__ == '__main__':
    unittest.main()
