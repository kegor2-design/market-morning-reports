import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.supervisor import operate, register, resolve_project, transition
from universal_agent.runner import classify


class FakeExecutor:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = 0

    def execute(self, project, task, state_dir):
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return {'ok': True, 'response': {'task_id': task['id'], 'outcome': 'done',
                                         'evidence': [], 'next_action': 'none'}}


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'evidence.json').write_text('{"one":true,"two":true}')
        self.manifest = self.root / 'project.json'
        self.state_dir = self.root / 'state'
        self.config = {
            'schema_version': 2, 'project_id': 'testproject',
            'workspace_root': str(self.root), 'goal': 'Verify two research steps',
            'success_criteria': ['Both evidence gates pass'],
            'codex_execution_enabled': True, 'data_access': ['evidence.json'],
            'limits': {'min_free_bytes': 1, 'max_iterations': 3, 'max_external_calls': 3},
            'tasks': [self.task('first', 0), self.task('second', 1, ['first'])]}
        self.save()

    def task(self, name, priority, deps=None):
        return {'id': name, 'goal_relation': name, 'selection_reason': 'high information value',
                'priority': priority, 'depends_on': deps or [], 'method': 'codex', 'risk': 'read_only',
                'prompt': 'Return structured JSON only', 'success_condition': 'Independent evidence',
                'verification_method': 'JSON equality',
                'checks': [{'kind': 'json_equals', 'path': 'evidence.json',
                            'pointer': '/' + ('one' if name == 'first' else 'two'), 'equals': True}]}

    def save(self):
        self.manifest.write_text(json.dumps(self.config))

    def state(self):
        return json.loads((self.state_dir / 'state.json').read_text())

    def test_registry_and_manifest_immutability(self):
        registry = self.root / 'registry.json'
        register(registry, self.manifest)
        self.assertEqual(resolve_project(None, registry, 'testproject'), self.manifest)
        self.config['goal'] = 'changed'
        self.save()
        with self.assertRaises(ValueError):
            resolve_project(None, registry, 'testproject')

    def test_multi_task_loop_and_resume_skips_completed(self):
        executor = FakeExecutor()
        result = operate('run-bounded', self.manifest, self.state_dir, executor)
        self.assertEqual(result['statuses'], {'first': 'COMPLETED', 'second': 'COMPLETED'})
        self.assertEqual(executor.calls, 2)
        self.assertEqual(result['outcome'], 'RESEARCH_PARTIAL')
        self.assertEqual(self.state()['budgets']['codex_calls'], 2)
        operate('resume', self.manifest, self.state_dir, executor)
        self.assertEqual(executor.calls, 2)

    def test_run_once_selects_one_then_resume(self):
        executor = FakeExecutor()
        first = operate('run-once', self.manifest, self.state_dir, executor)
        self.assertEqual(first['statuses']['first'], 'COMPLETED')
        self.assertEqual(first['next_task'], 'second')
        final = operate('resume', self.manifest, self.state_dir, executor)
        self.assertEqual(final['statuses']['second'], 'COMPLETED')

    def test_verification_failure_blocks_dependency(self):
        (self.root / 'evidence.json').write_text('{"one":false,"two":true}')
        result = operate('run-bounded', self.manifest, self.state_dir, FakeExecutor())
        self.assertEqual(result['statuses']['first'], 'BLOCKED_EVIDENCE')
        self.assertEqual(result['statuses']['second'], 'BLOCKED_DEPENDENCY')

    def test_blocked_task_does_not_stop_independent_safe_task(self):
        independent = self.task('third', 2)
        independent['checks'] = [{'kind': 'json_equals', 'path': 'evidence.json',
                                  'pointer': '/two', 'equals': True}]
        self.config['tasks'].append(independent)
        (self.root / 'evidence.json').write_text('{"one":false,"two":true}')
        self.save()
        executor = FakeExecutor()
        result = operate('run-bounded', self.manifest, self.state_dir, executor)
        self.assertEqual(result['statuses']['first'], 'BLOCKED_EVIDENCE')
        self.assertEqual(result['statuses']['second'], 'BLOCKED_DEPENDENCY')
        self.assertEqual(result['statuses']['third'], 'COMPLETED')
        self.assertEqual(executor.calls, 2)

    def test_approval_block_never_calls_executor(self):
        self.config['tasks'][0]['risk'] = 'operating_db'
        self.save()
        executor = FakeExecutor()
        result = operate('run-bounded', self.manifest, self.state_dir, executor)
        self.assertEqual(result['statuses']['first'], 'BLOCKED_APPROVAL')
        self.assertEqual(executor.calls, 0)

    def test_license_review_blocks_without_retry(self):
        self.config['tasks'][0]['method'] = 'probe'
        self.config['tasks'][0]['checks'] = [{'kind': 'review_required',
                                              'reason': 'Provider license does not permit redistribution'}]
        self.save()
        executor = FakeExecutor()
        result = operate('run-bounded', self.manifest, self.state_dir, executor)
        self.assertEqual(result['statuses']['first'], 'BLOCKED_LICENSE')
        operate('resume', self.manifest, self.state_dir, executor)
        self.assertEqual(executor.calls, 0)

    def test_retry_classification_and_bound(self):
        executor = FakeExecutor([{'ok': False, 'classification': 'NETWORK', 'reason': 'timeout'}] * 3)
        for i in range(3):
            result = operate('run-once', self.manifest, self.state_dir, executor)
        self.assertEqual(executor.calls, 3)
        self.assertEqual(result['statuses']['first'], 'FAILED_TERMINAL')
        self.assertEqual(self.state()['tasks']['first']['attempts'], 3)

    def test_quota_blocks_all_codex_until_reviewed_recovery(self):
        self.assertEqual(classify("You've hit your usage limit. Try again at 2026-11-01 09:00 UTC", 1), 'QUOTA')
        executor = FakeExecutor([{'ok': False, 'classification': 'QUOTA',
                                  'reason': 'Codex usage quota exhausted',
                                  'reported_retry_time': '2026-11-01 09:00 UTC',
                                  'partial_output_path': '/tmp/partial'}])
        blocked = operate('run-bounded', self.manifest, self.state_dir, executor)
        self.assertEqual(blocked['statuses']['first'], 'BLOCKED_QUOTA')
        self.assertEqual(blocked['statuses']['second'], 'BLOCKED_DEPENDENCY')
        self.assertEqual(self.state()['tasks']['first']['execution']['partial_output_path'], '/tmp/partial')
        self.assertEqual(self.state()['tasks']['first']['reported_retry_time'], '2026-11-01 09:00 UTC')
        operate('resume', self.manifest, self.state_dir, executor)
        self.assertEqual(executor.calls, 1)
        self.assertEqual(self.state()['tasks']['first']['attempts'], 1)
        operate('recover', self.manifest, self.state_dir, executor,
                task_id='first', resolution='retry')
        resumed = operate('run-bounded', self.manifest, self.state_dir, executor)
        self.assertEqual(resumed['statuses'], {'first': 'COMPLETED', 'second': 'COMPLETED'})
        self.assertEqual(executor.calls, 3)

    def test_crash_running_pauses_uncertain_outcome(self):
        operate('plan', self.manifest, self.state_dir)
        state = self.state()
        transition(state, 'first', 'RUNNING')
        (self.state_dir / 'state.json').write_text(json.dumps(state))
        executor = FakeExecutor()
        result = operate('resume', self.manifest, self.state_dir, executor)
        self.assertEqual(result['statuses']['first'], 'PAUSED')
        self.assertEqual(executor.calls, 0)

    def test_crash_after_execution_rechecks_without_rerun(self):
        operate('plan', self.manifest, self.state_dir)
        state = self.state()
        transition(state, 'first', 'RUNNING')
        transition(state, 'first', 'VERIFYING')
        (self.state_dir / 'state.json').write_text(json.dumps(state))
        executor = FakeExecutor()
        result = operate('resume', self.manifest, self.state_dir, executor, max_tasks=1)
        self.assertEqual(result['statuses']['first'], 'COMPLETED')
        self.assertEqual(executor.calls, 1)  # Only the newly eligible second task ran.

    def test_corrupt_checkpoint_fails_closed(self):
        self.state_dir.mkdir()
        (self.state_dir / 'state.json').write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):
            operate('resume', self.manifest, self.state_dir, FakeExecutor())

    def test_stop_and_resource_budget(self):
        self.state_dir.mkdir()
        (self.state_dir / 'STOP').write_text('stop')
        executor = FakeExecutor()
        result = operate('run-bounded', self.manifest, self.state_dir, executor)
        self.assertEqual(executor.calls, 0)
        self.assertEqual(result['statuses']['first'], 'PENDING')
        operate('recover', self.manifest, self.state_dir, resolution='clear-stop')
        self.assertFalse((self.state_dir / 'STOP').exists())
        self.config['limits']['min_free_bytes'] = 10**18
        self.save()
        result = operate('run-bounded', self.manifest, self.root / 'resource_state', executor)
        self.assertEqual(result['statuses']['first'], 'PAUSED')
        self.assertEqual(executor.calls, 0)

    def test_explicit_recovery_and_budgeted_outcome(self):
        executor = FakeExecutor()
        first = operate('run-once', self.manifest, self.state_dir, executor)
        self.assertEqual(first['outcome'], 'RESEARCH_BUDGET_EXHAUSTED')
        self.assertEqual(first['next_task'], 'second')
        state = self.state()
        transition(state, 'second', 'RUNNING')
        (self.state_dir / 'state.json').write_text(json.dumps(state))
        paused = operate('resume', self.manifest, self.state_dir, executor)
        self.assertEqual(paused['statuses']['second'], 'PAUSED')
        self.assertEqual(executor.calls, 1)
        recovered = operate('recover', self.manifest, self.state_dir, executor,
                            task_id='second', resolution='retry')
        self.assertEqual(recovered['statuses']['second'], 'READY')
        operate('resume', self.manifest, self.state_dir, executor)
        self.assertEqual(executor.calls, 2)


if __name__ == '__main__':
    unittest.main()
