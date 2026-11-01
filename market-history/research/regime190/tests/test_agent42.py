import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError, validate

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190 import agent42_orchestrator as orchestrator


def _fixtures(source: Path):
    (source / 'agent41_research_memory.json').write_text('{"test":true}')
    pit = {'approved_after': 0, 'records': [{'indicator_id': 1,
            'indicator_rows': 7868, 'source_candidate': 'OHLCV',
            'evidence_gap': ['publication time', 'vintage']}]}
    forecast = {'experiments': [{'baseline_brier': .045,
                'validation_metrics': {'brier': .044}}],
                'validation': ['2018-01-02', '2021-12-02', 966],
                'hypotheses': [], 'baseline_metrics': {},
                'train': [], 'final_holdout': 'CONTAMINATED_NOT_REUSED'}
    return ({'artifacts_sha256': {'pit_research.json': 'a'}}, pit, forecast)


def _fake_dispatch(task_dir: Path, timeout: int):
    pit = task_dir.name.startswith('A-')
    result = {'task_id': task_dir.name, 'evidence_findings': ['staged evidence reviewed'],
              'root_cause': None, 'confidence': 'INSUFFICIENT',
              'hypothesis': 'Unconfirmed source or effect',
              'experiment_result': 'staged calculation only',
              'validation_result': 'independent evidence missing',
              'decision': 'EVIDENCE_BLOCKED' if pit else 'EXPLORATORY_ONLY',
              'failure_reason': 'missing evidence', 'next_action': 'obtain new evidence',
              'source_references': []}
    (task_dir / 'answer.json').write_text(json.dumps(result))
    (task_dir / 'stdout.log').write_text('')
    (task_dir / 'stderr.log').write_text('')
    return 0, None


class Agent42Tests(unittest.TestCase):
    def test_task_schema_rejects_extra_operation(self):
        schema = json.loads(orchestrator.TASK_SCHEMA.read_text())
        valid = {'task_id': 'A-PIT-001', 'research_objective': 'Investigate PIT evidence',
                 'problem_id': 'PIT-001', 'evidence': ['inventory row'],
                 'hypothesis': 'Source may supply closes', 'required_inputs': ['evidence.json'],
                 'allowed_paths': ['/tmp/research'], 'forbidden_paths': ['/tmp/operating'],
                 'allowed_operations': ['read staged evidence'],
                 'validation_method': 'Check independent source',
                 'success_criteria': 'Prove dated availability',
                 'failure_criteria': 'Missing publication time',
                 'rollback_method': 'Discard read-only output',
                 'expected_outputs': ['answer.json'],
                 'generation_method': 'DETERMINISTIC_RULE_TEMPLATE'}
        validate(valid, schema)
        with self.assertRaises(ValidationError):
            validate(dict(valid, arbitrary_command='rm'), schema)

    def test_priority_formula(self):
        self.assertEqual(orchestrator._score_factors(3, 3, 2, 2, 1, 0)['score'], 22)

    def test_queue_dispatch_resume_and_integrity(self):
        with tempfile.TemporaryDirectory() as root:
            state, source = Path(root) / 'state', Path(root) / 'source'
            source.mkdir()
            fixtures = _fixtures(source)
            with patch.object(orchestrator, '_source', return_value=fixtures), patch.object(
                    orchestrator, '_pit_formula_probe', return_value={'pit_approved': False}), patch.object(
                    orchestrator, '_dispatch', side_effect=_fake_dispatch):
                first = orchestrator.run(state, source, max_tasks=1)
                self.assertEqual(first['checkpoint_id'], 1)
                self.assertEqual(first['tasks']['A-PIT-001'], 'BLOCKED')
                self.assertEqual(first['tasks']['B-CRASH20'], 'READY')
                second = orchestrator.run(state, source, max_tasks=1)
                self.assertEqual(second['checkpoint_id'], 2)
                self.assertEqual(second['tasks']['B-CRASH20'], 'COMPLETED')
                self.assertEqual(orchestrator.run(state, source)['checkpoint_id'], 2)
                memory = json.loads((state / orchestrator.MEMORY).read_text())
                self.assertEqual(memory['llm_runtime'], 'CODEX_CLI')
                self.assertEqual(memory['next_research']['status'], 'BLOCKED')
                (state / 'tasks/B-CRASH20/answer.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'integrity'):
                    orchestrator.prepare(state, source)

    def test_stop_prevents_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            state, source = Path(root) / 'state', Path(root) / 'source'
            source.mkdir()
            fixtures = _fixtures(source)
            with patch.object(orchestrator, '_source', return_value=fixtures), patch.object(
                    orchestrator, '_pit_formula_probe', return_value={'pit_approved': False}), patch.object(
                    orchestrator, '_dispatch', side_effect=AssertionError('dispatched')):
                orchestrator.prepare(state, source)
                (state / 'STOP').write_text('stop')
                self.assertEqual(orchestrator.run(state, source)['status'], 'STOPPED')


if __name__ == '__main__':
    unittest.main()
