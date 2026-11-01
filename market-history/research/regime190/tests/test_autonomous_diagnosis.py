import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190.autonomous_diagnosis import (BASELINE_STATE, _rates,
                                            controlled_experiment, run_diagnosis,
                                            verify)
from regime190.autonomous_loop import cycle


class AutonomousDiagnosisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.diagnosis = run_diagnosis()

    def test_reproduction_and_metric_definitions(self):
        value = self.diagnosis
        self.assertEqual(value['baseline_code_commit'],
                         '7009996f407dcf2266e7a4d64d3fa745fcb4a48d')
        self.assertEqual(tuple(value['crash20'][key] for key in ('tp', 'fp', 'fn', 'tn')),
                         (51, 621, 159, 3221))
        self.assertEqual(value['crash20']['prevalence'], 210 / 4052)
        self.assertEqual(value['crash_baselines']['always_negative']['recall'], 0)
        self.assertGreater(value['crash_baselines']['volatility']['precision'],
                           value['crash20']['precision'])
        self.assertLess(abs(value['strategy_attribution']['identity_error']), 1e-9)
        self.assertEqual(value['crash20_uncertainty']['block_sessions'], 20)

    def test_evidence_backed_diagnoses_and_negative_experiment(self):
        value = self.diagnosis
        categories = {item['failure_category'] for item in value['diagnoses']}
        self.assertIn('PIT_FAILURE', categories)
        self.assertIn('LABEL_DEFINITION_PROBLEM', categories)
        self.assertIn('UNKNOWN_CAUSE', categories)
        self.assertTrue(all(item['evidence'] and not item['causality_claimed']
                            for item in value['diagnoses']))
        self.assertEqual(value['recovery_definition_mismatch_days'], 15)
        result = controlled_experiment(value)
        self.assertEqual(result['plan']['changed_variables'],
                         ['recovery_signal_persistence_days:1_to_2'])
        self.assertEqual(result['train']['baseline']['tp'], 0)
        self.assertEqual(result['validation']['candidate']['tp'], 0)
        self.assertEqual(result['validation']['precision_delta_block_bootstrap']['status'],
                         'NO_TRUE_POSITIVE_SIGNALS')
        self.assertEqual(result['final_holdout']['status'], 'FINAL_HOLDOUT_CONTAMINATED')
        self.assertIsNone(result['final_holdout']['candidate_metrics'])
        self.assertGreater(len(result['walk_forward']['folds']), 1)
        self.assertTrue(all(fold['test_end'] < '2022-01-01' and
                            fold['train_end'] < fold['test_start']
                            for fold in result['walk_forward']['folds']))
        self.assertEqual(result['deployment_readiness'], 'NOT_READY')

    def test_invalid_metrics_and_tampered_baseline_fail_closed(self):
        with self.assertRaises(ValueError):
            _rates([True], [True, False])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            memory = json.loads((BASELINE_STATE / 'research_memory.json').read_text())
            artifact = root / 'artifact.json'
            artifact.write_text('tampered')
            memory['artifact_path'] = str(artifact)
            (root / 'research_memory.json').write_text(json.dumps(memory))
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                run_diagnosis(root)

    def test_claim_and_holdout_gates_fail_closed(self):
        valid = {'schema_version': 1, 'status': 'EXPLORATORY_DIAGNOSIS_COMPLETE',
                 'official_improvement_claim': False, 'model_status': 'DETERMINISTIC_NON_AI',
                 'diagnosis': {'pit_validity': 'BLOCKED'},
                 'experiment': {'final_holdout': {'candidate_metrics': None},
                                'deployment_readiness': 'NOT_READY'}}
        verify(valid)
        valid['official_improvement_claim'] = True
        with self.assertRaises(ValueError):
            verify(valid)
        valid['official_improvement_claim'] = False
        valid['experiment']['final_holdout']['candidate_metrics'] = {'precision': 1.0}
        with self.assertRaises(ValueError):
            verify(valid)

    def test_worker_checkpoint_memory_duplicate_and_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'diagnosis'
            repo = Path(__file__).resolve().parents[4]
            first = cycle(state, repo)
            self.assertEqual(first['status'], 'DIAGNOSIS_AND_EXPERIMENT_COMPLETE')
            self.assertEqual(first['model_status'], 'DETERMINISTIC_NON_AI')
            memory = json.loads((state / 'research_memory.json').read_text())
            self.assertEqual(memory['iterations_used'], 1)
            self.assertEqual(memory['evaluation']['pit_validity'], 'BLOCKED')
            self.assertEqual(cycle(state, repo)['status'], 'ALREADY_EVALUATED')
            queue = json.loads((state / 'task_queue.json').read_text())
            self.assertEqual(queue['checkpoint_id'], 1)
            (state / 'research_memory.json').unlink()  # interruption after worker completion
            self.assertEqual(cycle(state, repo)['status'], 'DIAGNOSIS_AND_EXPERIMENT_COMPLETE')
            self.assertEqual(json.loads((state / 'task_queue.json').read_text())['checkpoint_id'], 1)
            (state / 'STOP').write_text('stop')
            self.assertEqual(cycle(state, repo)['status'], 'STOPPED')


if __name__ == '__main__':
    unittest.main()
