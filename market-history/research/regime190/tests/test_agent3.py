import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190.agent3_adapter import verify
from regime190.agent3_controller import _plan, cycle
from regime190.agent3_experiments import (investigate_pit, patch_manifest,
                                          validate_patch)
from universal_agent.offline_worker import load_plan


class Agent3Tests(unittest.TestCase):
    def test_pit_investigation_preserves_blockers(self):
        with patch('regime190.agent3_experiments._db_sample',
                   return_value={'status': 'TEST_READ_ONLY_SAMPLE'}):
            result = investigate_pit()
        self.assertEqual(result['indicator_count'], 190)
        self.assertEqual(result['eligible_after'], 0)
        self.assertEqual(len(result['blocked_indicators']), 190)
        self.assertTrue(all(row['blocking_reason'] for row in result['blocked_indicators']))
        verify({'task_type': 'pit_investigation'}, result)
        result['eligible_after'] = 1
        with self.assertRaises(ValueError):
            verify({'task_type': 'pit_investigation'}, result)

    def test_reviewed_patch_scope_and_worker_contract(self):
        manifest = patch_manifest()
        validate_patch(manifest)
        bad = dict(manifest, target_files=['market-history/live_trading.py'])
        with self.assertRaises(ValueError):
            validate_patch(bad)
        bad = dict(manifest, code_sha256='0' * 64)
        with self.assertRaises(ValueError):
            validate_patch(bad)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            plan = _plan()
            path.write_text(json.dumps(plan))
            load_plan(path)
            plan['tasks'][0]['required_tools'] = ['arbitrary_python']
            path.write_text(json.dumps(plan))
            with self.assertRaises(ValueError):
                load_plan(path)

    def test_claim_and_holdout_gates(self):
        task = {'task_type': 'hysteresis'}
        valid = {'decision': 'IMPROVEMENT_UNCONFIRMED',
                 'official_improvement_claim': False,
                 'deployment_readiness': 'NOT_READY',
                 'final_holdout': 'FINAL_HOLDOUT_CONTAMINATED_NOT_EVALUATED'}
        verify(task, valid)
        for key, value in [('official_improvement_claim', True),
                           ('deployment_readiness', 'READY'),
                           ('final_holdout', {'candidate_sharpe': 99})]:
            altered = dict(valid, **{key: value})
            with self.assertRaises(ValueError):
                verify(task, altered)

    def test_real_cycle_retry_resume_integrity_and_stop(self):
        repo = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'agent3'
            with patch('regime190.agent3_experiments._db_sample',
                       return_value={'status': 'TEST_READ_ONLY_SAMPLE'}):
                first = cycle(state, repo)
            self.assertEqual(first['status'], 'BOUNDED_RESEARCH_STOPPED')
            self.assertEqual(first['checkpoint_id'], 3)
            memory = json.loads((state / 'research_memory.json').read_text())
            self.assertEqual(memory['iterations_used'], 2)
            self.assertEqual(memory['pit_eligible_after'], 0)
            self.assertEqual(memory['decision'], 'MORE_EVIDENCE_REQUIRED')
            self.assertEqual(memory['model_status'], 'DETERMINISTIC_NON_AI')
            label = json.loads(Path(memory['artifacts'][1]['path']).read_text())['result']
            candidate = json.loads(Path(memory['artifacts'][2]['path']).read_text())['result']
            self.assertEqual(label['decision'], 'NONCOMPARABLE_MEASUREMENT_REPAIR')
            self.assertEqual(candidate['parent_experiment_id'], label['experiment_id'])
            self.assertFalse(candidate['official_improvement_claim'])
            self.assertTrue(all(fold['test_end'] < '2022-01-01' for fold in
                                candidate['walk_forward']['folds']))
            self.assertEqual(cycle(state, repo)['status'], 'ALREADY_EVALUATED')
            (state / 'research_memory.json').unlink()
            self.assertEqual(cycle(state, repo)['status'], 'BOUNDED_RESEARCH_STOPPED')
            self.assertEqual(json.loads((state / 'task_queue.json').read_text())['checkpoint_id'], 3)
            (state / 'STOP').write_text('stop')
            self.assertEqual(cycle(state, repo)['status'], 'STOPPED')
            (state / 'STOP').unlink()
            artifact = Path(memory['artifacts'][0]['path'])
            artifact.write_text('tampered')
            with self.assertRaises(ValueError):
                cycle(state, repo)


if __name__ == '__main__':
    unittest.main()
