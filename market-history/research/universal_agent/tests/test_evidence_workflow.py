import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent import evidence_workflow
from universal_agent.evidence_collector import collect
from universal_agent.research_job import PRIVATE_ROOT, manifest_load, supervise


def manifest(root):
    return {'schema_version': 1, 'job_id': 'evidence_test',
        'goal': 'Audit Treasury first-vintage PIT and continue safe research',
        'mode': 'evidence_workflow', 'max_seconds': 30, 'max_restarts': 1,
        'max_model_calls': 0,
        'evidence_request': {'goal_id': 'evidence_test', 'task_id': 'collect_116',
            'indicator': '116', 'source': 'FRED_ALFRED',
            'data_requirement': 'first_vintage_pit',
            'as_of': '2026-11-13T09:00:00+09:00',
            'allowed_sources': ['FRED_ALFRED'],
            'budget': {'max_seconds': 20, 'max_network_requests': 0, 'max_model_calls': 0},
            'policy': {'read_only': True, 'official_claim_allowed': False}},
        'next_task': {'task_id': 'safe_fixture', 'mode': 'synthetic_research',
            'independent_of': '116', 'priority': 1, 'synthetic_values': [1, 2, 3]}}


class EvidenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=PRIVATE_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = manifest(self.root)

    def test_manifest_rejects_unsafe_budget_and_duplicate_task(self):
        path = self.root / 'manifest.json'
        for change in ('network', 'duplicate', 'dependent', 'official'):
            with self.subTest(change=change):
                item = copy.deepcopy(self.data)
                if change == 'network':
                    item['evidence_request']['budget']['max_network_requests'] = 1
                elif change == 'duplicate':
                    item['next_task']['task_id'] = 'collect_116'
                elif change == 'dependent':
                    item['next_task']['independent_of'] = 'other'
                else:
                    item['evidence_request']['policy']['official_claim_allowed'] = True
                path.write_text(json.dumps(item))
                with self.assertRaises((ValidationError, ValueError)):
                    manifest_load(path)

    def test_collector_blocks_unreviewed_or_disallowed_source(self):
        request = copy.deepcopy(self.data['evidence_request'])
        request['indicator'] = '999'
        self.assertEqual(collect(request)['status'], 'NOT_SUPPORTED')
        request['allowed_sources'] = ['US_TREASURY']
        self.assertEqual(collect(request)['status'], 'BLOCKED_APPROVAL')

    def test_missing_local_evidence_blocks_without_publication_guess(self):
        request = copy.deepcopy(self.data['evidence_request'])
        with patch('universal_agent.evidence_collector.SOURCE_ROOT', self.root / 'missing'):
            result = collect(request)
        self.assertEqual(result['status'], 'BLOCKED_ENV')
        self.assertIsNone(result['actual_publication_time'])
        self.assertIsNone(result['first_accessible_time'])

    def test_blocked_pit_automatically_executes_independent_task_once(self):
        fake = {'request_sha256': 'a' * 64, 'status': 'PIT_BLOCKED',
                'actual_publication_time': None, 'first_accessible_time': None,
                'gaps': ['No historical intraday proof']}
        with patch.object(evidence_workflow, 'collect_indicator_evidence', return_value=fake):
            first = evidence_workflow.run(self.data, self.root)
            self.assertEqual(first['status'], 'EXPLORATORY_ONLY')
            state = evidence_workflow.verify(self.data, self.root)
            self.assertEqual([step['task_id'] for step in state['steps']],
                             ['collect_116', 'safe_fixture'])
            self.assertTrue(all(step['autonomous'] for step in state['steps']))
            self.assertEqual(state['steps'][0]['status'], 'PIT_BLOCKED')
            self.assertEqual(state['steps'][1]['status'], 'VERIFIED_FIXTURE')
            repeated = evidence_workflow.run(self.data, self.root)
            self.assertEqual(first['next_sha256'], repeated['next_sha256'])
            self.assertEqual(len(evidence_workflow.verify(self.data, self.root)['steps']), 2)

    def test_tampered_evidence_and_result_are_rejected(self):
        fake = {'request_sha256': 'a' * 64, 'status': 'PIT_BLOCKED', 'gaps': []}
        with patch.object(evidence_workflow, 'collect_indicator_evidence', return_value=fake):
            evidence_workflow.run(self.data, self.root)
            path = self.root / 'evidence_result.json'
            saved = json.loads(path.read_text())
            saved['status'] = 'PIT_VERIFIED'
            path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                evidence_workflow.verify(self.data, self.root)

    def test_interrupted_after_evidence_resumes_without_recollecting(self):
        fake = {'request_sha256': 'b' * 64, 'status': 'PIT_BLOCKED', 'gaps': []}
        with patch.object(evidence_workflow, 'collect_indicator_evidence', return_value=fake) as collector:
            with patch.object(evidence_workflow, 'synthetic_execute', side_effect=RuntimeError('injected')):
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    evidence_workflow.run(self.data, self.root)
            self.assertEqual(len(json.loads((self.root / 'workflow.json').read_text())['steps']), 1)
            resumed = evidence_workflow.run(self.data, self.root)
            self.assertEqual(resumed['status'], 'EXPLORATORY_ONLY')
            self.assertEqual(len(evidence_workflow.verify(self.data, self.root)['steps']), 2)
            self.assertEqual(collector.call_count, 4)  # initial, two read-only checks, final

    def test_unproven_pit_promotion_is_rejected(self):
        fake = {'request_sha256': 'c' * 64, 'status': 'PIT_VERIFIED',
                'actual_publication_time': '2015-04-01T14:30:00-04:00'}
        with patch.object(evidence_workflow, 'collect_indicator_evidence', return_value=fake):
            with self.assertRaisesRegex(ValueError, 'PIT promotion'):
                evidence_workflow.run(self.data, self.root)

    def test_corrupt_checkpoint_stops_before_reexecution(self):
        fake = {'request_sha256': 'd' * 64, 'status': 'PIT_BLOCKED', 'gaps': []}
        with patch.object(evidence_workflow, 'collect_indicator_evidence', return_value=fake) as collector:
            evidence_workflow.run(self.data, self.root)
            calls = collector.call_count
            (self.root / 'workflow.json').write_text('{invalid json')
            with self.assertRaises(json.JSONDecodeError):
                evidence_workflow.run(self.data, self.root)
            self.assertEqual(collector.call_count, calls)

    def test_deliberate_stop_is_terminal_and_distinct_from_crash(self):
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(self.data))
        state_dir = self.root / 'stopped_job'
        state_dir.mkdir()
        (state_dir / 'STOP').write_text('stop')
        first = supervise(path, state_dir)
        self.assertEqual(first['status'], 'RESEARCH_BLOCKED_WITH_EVIDENCE')
        self.assertEqual(first['reason'], 'STOP requested')
        self.assertEqual(first['attempts'], 0)
        resumed = supervise(path, state_dir)
        self.assertTrue(resumed['reused_checkpoint'])
        self.assertEqual(resumed['attempts'], 0)


if __name__ == '__main__':
    unittest.main()
