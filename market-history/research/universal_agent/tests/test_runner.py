import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.engine import locked_state
from universal_agent.runner import CodexExecutor, classify, load_runner_project, operate


class FakeExecutor:
    def __init__(self, responses=None):
        self.responses = list(responses or [{'ok': True, 'response': {'task_id': 'first'}}])
        self.calls = 0

    def execute(self, project, task, state_dir):
        self.calls += 1
        return self.responses.pop(0)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'evidence.json').write_text('{"ready": true, "second": true}')
        self.config = self.root / 'project.json'
        self.state = self.root / 'state'
        self.spec = {
            'schema_version': 2, 'project_id': 'sample', 'workspace_root': str(self.root),
            'goal': 'Verify a generic research task', 'success_criteria': ['Two checks pass'],
            'codex_execution_enabled': True,
            'data_access': ['evidence.json'],
            'limits': {'min_free_bytes': 1, 'max_iterations': 2, 'max_external_calls': 2},
            'tasks': [
                {'id': 'first', 'goal_relation': 'First evidence', 'selection_reason': 'Priority',
                 'priority': 0, 'depends_on': [], 'method': 'codex', 'risk': 'read_only',
                 'prompt': 'Return the task result', 'success_condition': 'Evidence ready',
                 'verification_method': 'JSON equality',
                 'checks': [{'kind': 'json_equals', 'path': 'evidence.json',
                             'pointer': '/ready', 'equals': True}]},
                {'id': 'second', 'goal_relation': 'Second evidence', 'selection_reason': 'Depends on first',
                 'priority': 1, 'depends_on': ['first'], 'method': 'probe', 'risk': 'read_only',
                 'success_condition': 'Second evidence ready', 'verification_method': 'JSON equality',
                 'checks': [{'kind': 'json_equals', 'path': 'evidence.json',
                             'pointer': '/second', 'equals': True}]},
            ]}
        self.save()

    def save(self):
        self.config.write_text(json.dumps(self.spec))

    def test_register_plan_and_dry_run_do_not_call_codex(self):
        project, _ = load_runner_project(self.config)
        self.assertEqual(project['project_id'], 'sample')
        executor = FakeExecutor()
        dry = operate('dry-run', self.config, self.state, executor)
        self.assertEqual(dry['next_task'], 'first')
        self.assertEqual(dry['would_execute']['method'], 'codex')
        self.assertTrue(dry['dry_run_evidence'][0]['ok'])
        self.assertFalse(self.state.exists())
        planned = operate('plan', self.config, self.state, executor)
        self.assertEqual(planned['plan']['selected_task'], 'first')
        self.assertTrue(planned['plan']['evidence_preview'][0]['ok'])
        self.assertEqual(executor.calls, 0)

    def test_run_once_then_resume_skips_completed(self):
        executor = FakeExecutor()
        one = operate('run-once', self.config, self.state, executor)
        self.assertEqual(one['statuses']['first'], 'COMPLETED')
        self.assertEqual(one['statuses']['second'], 'PENDING')
        self.assertEqual(executor.calls, 1)
        final = operate('resume', self.config, self.state, executor)
        self.assertEqual(final['statuses']['second'], 'COMPLETED')
        self.assertEqual(executor.calls, 1)
        saved = json.loads((self.state / 'state.json').read_text())
        self.assertEqual(saved['tasks']['first']['attempts'], 1)
        self.assertTrue(saved['plan_changes'])

    def test_network_retry_is_capped(self):
        failure = {'ok': False, 'classification': 'NETWORK', 'reason': 'connection timeout'}
        executor = FakeExecutor([failure] * 3)
        for _ in range(3):
            result = operate('run-once', self.config, self.state, executor)
        self.assertEqual(result['statuses']['first'], 'FAILED')
        self.assertEqual(executor.calls, 3)
        self.assertIsNone(operate('status', self.config, self.state)['next_task'])

    def test_auth_failure_is_not_retried(self):
        executor = FakeExecutor([{'ok': False, 'classification': 'AUTH', 'reason': 'not logged in'}])
        operate('run-once', self.config, self.state, executor)
        operate('resume', self.config, self.state, executor)
        self.assertEqual(executor.calls, 1)

    def test_quota_failure_blocks_future_invocations(self):
        executor = FakeExecutor([{'ok': False, 'classification': 'QUOTA',
                                  'reason': 'Codex usage quota exhausted'}])
        first = operate('run-once', self.config, self.state, executor)
        self.assertEqual(first['statuses']['first'], 'BLOCKED')
        self.assertTrue(json.loads((self.state / 'state.json').read_text())['quota_blocked'])
        operate('resume', self.config, self.state, executor)
        self.assertEqual(executor.calls, 1)

    def test_approval_risk_blocks_without_executor(self):
        self.spec['tasks'][0]['risk'] = 'operating_db'
        self.save()
        executor = FakeExecutor()
        result = operate('run-once', self.config, self.state, executor)
        self.assertEqual(result['statuses']['first'], 'BLOCKED_APPROVAL')
        self.assertEqual(executor.calls, 0)

    def test_project_codex_execution_is_disabled_by_default(self):
        self.spec['codex_execution_enabled'] = False
        self.save()
        executor = FakeExecutor()
        result = operate('run-once', self.config, self.state, executor)
        self.assertEqual(result['statuses']['first'], 'BLOCKED_APPROVAL')
        self.assertEqual(executor.calls, 0)

    def test_interrupted_checkpoint_retries_safe_task(self):
        operate('plan', self.config, self.state)
        state_path = self.state / 'state.json'
        state = json.loads(state_path.read_text())
        state['tasks']['first'].update(status='IN_PROGRESS', attempts=1)
        state_path.write_text(json.dumps(state))
        executor = FakeExecutor()
        result = operate('resume', self.config, self.state, executor)
        self.assertEqual(result['statuses']['first'], 'COMPLETED')
        self.assertEqual(json.loads(state_path.read_text())['tasks']['first']['attempts'], 2)

    def test_duplicate_run_is_refused_by_lock(self):
        with locked_state(self.state):
            with self.assertRaisesRegex(RuntimeError, 'lock'):
                operate('run-once', self.config, self.state, FakeExecutor())

    def test_verification_failure_blocks_dependent_task(self):
        (self.root / 'evidence.json').write_text('{"ready": false, "second": true}')
        result = operate('resume', self.config, self.state, FakeExecutor())
        self.assertEqual(result['statuses']['first'], 'BLOCKED')
        self.assertEqual(result['statuses']['second'], 'PENDING')

    def test_actual_cli_argument_contract_with_fake_binary(self):
        fake = self.root / 'fake-codex'
        fake.write_text('''#!/usr/bin/env python3
import json,sys,pathlib
a=sys.argv[1:]
if a==['--version']: print('codex-cli 0.166.0');sys.exit(0)
if a==['login','status']: print('Logged in using ChatGPT');sys.exit(0)
if a==['exec','--help']:
 print('--sandbox --json --ephemeral --output-schema --output-last-message --cd');sys.exit(0)
assert a[0]=='exec' and a[a.index('--sandbox')+1]=='read-only'
assert '--json' in a and '--ephemeral' in a and '-C' in a
task=json.loads(pathlib.Path(a[a.index('--output-schema')+1]).read_text())
assert task['type']=='object'
pathlib.Path(a[a.index('-o')+1]).write_text(json.dumps({'task_id':'first','outcome':'ok','evidence':['fixture'],'next_action':'none'}))
print(json.dumps({'type':'turn.completed'}))
''')
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.state.mkdir()
        project, _ = load_runner_project(self.config)
        result = CodexExecutor(str(fake)).execute(project, project['tasks'][0], self.state)
        self.assertTrue(result['ok'])
        self.assertEqual(result['response']['task_id'], 'first')

    def test_codex_cli_quota_event_is_classified(self):
        fake = self.root / 'fake-quota-codex'
        fake.write_text('''#!/usr/bin/env python3
import json,sys
a=sys.argv[1:]
if a==['--version']: print('codex-cli 0.166.0');sys.exit(0)
if a==['login','status']: print('Logged in using ChatGPT');sys.exit(0)
if a==['exec','--help']:
 print('--sandbox --json --ephemeral --output-schema --output-last-message --cd');sys.exit(0)
print(json.dumps({'type':'turn.failed','error':{'message':"You've hit your usage limit. Try again at 2026-11-01 09:00 UTC"}}))
sys.exit(1)
''')
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.state.mkdir()
        project, _ = load_runner_project(self.config)
        result = CodexExecutor(str(fake)).execute(project, project['tasks'][0], self.state)
        self.assertEqual(result['classification'], 'QUOTA')
        self.assertEqual(result['reason'], 'Codex usage quota exhausted')

    def test_project_registration_rejects_unknown_capability(self):
        self.spec['tasks'][0]['method'] = 'shell'
        self.save()
        with self.assertRaisesRegex(ValueError, 'method or risk'):
            load_runner_project(self.config)

    def test_data_access_scope_is_enforced(self):
        (self.root / 'other.json').write_text('{"ready": true}')
        self.spec['tasks'][0]['checks'][0]['path'] = 'other.json'
        self.save()
        with self.assertRaisesRegex(ValueError, 'outside project data_access'):
            load_runner_project(self.config)

    def test_external_call_budget_is_per_run(self):
        self.spec['limits']['max_external_calls'] = 1
        second = self.spec['tasks'][1]
        second['method'] = 'codex'
        second['prompt'] = 'Return the second result'
        self.save()
        executor = FakeExecutor([{'ok': True}, {'ok': True}])
        result = operate('resume', self.config, self.state, executor)
        self.assertEqual(result['statuses']['first'], 'COMPLETED')
        self.assertEqual(result['statuses']['second'], 'BLOCKED')
        self.assertEqual(executor.calls, 1)

    def test_execpolicy_parse_error_is_nonretryable_code_failure(self):
        self.assertEqual(classify('Error loading rules: default.rules:977: starlark error', 1), 'CODE')


if __name__ == '__main__':
    unittest.main()
