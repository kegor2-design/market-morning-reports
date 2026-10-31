import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.engine import write_state
from universal_agent.offline_worker import (QuotaBlocked, load_plan, prepare, run,
                                            _expand_classification, _expand_research_evidence)


class FakeAdapter:
    calls = 0

    def execute(self, task, queue):
        self.calls += 1
        return {'source_role': 'read_only', 'recent_rows': 1}

    def verify(self, task, result):
        if result['source_role'] != 'read_only':
            raise ValueError('bad evidence')


class OfflineWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.repo = Path(__file__).resolve().parents[4]
        self.plan = self.root / 'plan.json'
        self.plan.write_text(json.dumps({
            'schema_version': 1, 'research_project': 'regime190', 'adapter': 'regime190',
            'tasks': [
                {'task_id': 'source', 'task_type': 'source_snapshot',
                 'execution_class': 'SERVER_EXECUTABLE', 'priority': 0,
                 'dependencies': [], 'delay_hours': 0, 'input_artifacts': [],
                 'resource_budget': {'max_seconds': 10, 'max_attempts': 2}},
                {'task_id': 'design', 'task_type': 'research_design',
                 'execution_class': 'CODEX_REQUIRED', 'priority': 1,
                 'dependencies': [], 'delay_hours': 0, 'input_artifacts': [],
                 'resource_budget': {'max_seconds': 10, 'max_attempts': 1}}]}))
        self.adapter = FakeAdapter()
        self.adapter.calls = 0
        self.patch_adapter = patch('universal_agent.offline_worker._adapter', return_value=self.adapter)
        self.patch_adapter.start()
        self.addCleanup(self.patch_adapter.stop)

    def queue(self):
        return json.loads((self.state / 'task_queue.json').read_text())

    def test_prepare_run_handoff_and_no_duplicate(self):
        prepare(self.plan, self.state, self.repo)
        first = run(self.state, self.repo, max_tasks=1)
        self.assertEqual(first['checkpoint_id'], 1)
        self.assertEqual(first['statuses']['design'], 'CODEX_REQUIRED')
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(run(self.state, self.repo)['processed'], 0)
        self.assertEqual(self.adapter.calls, 1)
        handoff = json.loads((self.state / 'codex_handoff.json').read_text())
        self.assertIn('source', handoff['completed_tasks'])
        self.assertIn('design', handoff['codex_required_tasks'])

    def test_interrupted_verification_recovers_output_without_execution(self):
        prepare(self.plan, self.state, self.repo)
        artifact = self.state / 'artifact.json'
        write_state(artifact, {'task_id': 'source', 'plan_task_type': 'source_snapshot',
                               'result': {'source_role': 'read_only', 'recent_rows': 1}})
        queue = self.queue()
        queue['tasks']['source']['status'] = 'VERIFYING'
        queue['tasks']['source']['attempt_count'] = 1
        queue['tasks']['source']['output_artifacts'] = [str(artifact)]
        queue['generation'] += 1  # Simulate crash after queue replace, before projection replace.
        write_state(self.state / 'task_queue.json', queue)
        result = run(self.state, self.repo)
        self.assertEqual(result['statuses']['source'], 'COMPLETED')
        self.assertEqual(self.adapter.calls, 0)

    def test_resource_limit_and_retry_backoff(self):
        prepare(self.plan, self.state, self.repo)
        with patch('universal_agent.offline_worker._memory_available', return_value=1):
            self.assertEqual(run(self.state, self.repo)['processed'], 0)
        with patch.object(self.adapter, 'execute', side_effect=RuntimeError('temporary')):
            result = run(self.state, self.repo, max_tasks=1)
        self.assertEqual(result['statuses']['source'], 'RETRYABLE')
        self.assertIsNotNone(self.queue()['tasks']['source']['retry_after'])
        self.assertEqual(run(self.state, self.repo)['processed'], 0)

    def test_unsafe_task_id_is_rejected(self):
        plan = json.loads(self.plan.read_text())
        plan['tasks'][0]['task_id'] = '../escape'
        self.plan.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'unsafe task ID'):
            load_plan(self.plan)

    def test_checkpoint_hash_mismatch_fails_closed(self):
        prepare(self.plan, self.state, self.repo)
        queue = self.queue()
        queue['tasks']['source']['priority'] = 99
        write_state(self.state / 'task_queue.json', queue)
        with self.assertRaisesRegex(ValueError, 'Checkpoint integrity mismatch'):
            run(self.state, self.repo)

    def test_offline_provider_quota_blocks_without_retry(self):
        prepare(self.plan, self.state, self.repo)
        with patch.object(self.adapter, 'execute', side_effect=QuotaBlocked('provider limit')):
            result = run(self.state, self.repo)
        self.assertEqual(result['statuses']['source'], 'BLOCKED_QUOTA')
        self.assertEqual(run(self.state, self.repo)['processed'], 0)
        self.assertEqual(self.queue()['tasks']['source']['attempt_count'], 1)

    def test_generated_evidence_tasks_are_bounded_and_idempotent(self):
        prepare(self.plan, self.state, self.repo)
        queue = self.queue()
        task = {'task_id': 'source', 'task_type': 'blocker_classify'}
        _expand_classification(queue, task, {'followup_indicator_ids': [1, 5]})
        _expand_classification(queue, task, {'followup_indicator_ids': [1, 5]})
        self.assertEqual(len(queue['tasks']), 4)
        self.assertEqual(queue['tasks']['local_evidence_001']['dependencies'], ['source'])
        with self.assertRaisesRegex(ValueError, 'Invalid generated indicator'):
            _expand_classification(queue, task, {'followup_indicator_ids': [191]})

    def test_interrupted_classification_restores_followup_without_duplicate(self):
        prepare(self.plan, self.state, self.repo)
        artifact = self.state / 'classification.json'
        write_state(artifact, {'task_id': 'source', 'plan_task_type': 'blocker_classify',
                               'result': {'source_role': 'read_only', 'recent_rows': 1,
                                          'followup_indicator_ids': [41]}})
        queue = self.queue()
        queue['tasks']['source']['task_type'] = 'blocker_classify'
        queue['tasks']['source']['status'] = 'VERIFYING'
        queue['tasks']['source']['output_artifacts'] = [str(artifact)]
        queue['generation'] += 1
        write_state(self.state / 'task_queue.json', queue)
        run(self.state, self.repo, max_tasks=1)
        self.assertIn('local_evidence_041', self.queue()['tasks'])
        run(self.state, self.repo, max_tasks=1)
        self.assertEqual(len(self.queue()['tasks']), 3)

    def test_evidence_followup_uses_same_queue_and_fingerprint(self):
        template = {'task_id': 'fred_dgs10_sample', 'task_type': 'fred_pit_sample',
                    'research_state_dir': '/tmp/research', 'status': 'COMPLETED',
                    'resource_budget': {'max_seconds': 60, 'max_attempts': 1}}
        review = {'task_id': 'pit_reevaluate_116', 'task_type': 'evidence_reevaluate',
                  'status': 'COMPLETED', 'resource_budget': {'max_seconds': 20, 'max_attempts': 1}}
        queue = {'tasks': {'fred_dgs10_sample': template, 'pit_reevaluate_116': review}}
        _expand_research_evidence(queue, review, {'evidence_collected': True, 'evidence_sha256': 'abc'})
        _expand_research_evidence(queue, review, {'evidence_collected': True, 'evidence_sha256': 'abc'})
        self.assertEqual(queue['tasks']['fred_dgs2_sample']['series_id'], 'DGS2')
        self.assertEqual(len(queue['tasks']), 3)
        with self.assertRaisesRegex(ValueError, 'fingerprint changed'):
            _expand_research_evidence(queue, review, {'evidence_collected': True, 'evidence_sha256': 'changed'})


if __name__ == '__main__':
    unittest.main()
