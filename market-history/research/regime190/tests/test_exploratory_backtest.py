import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190.exploratory_backtest import (PARAMETERS, _features, _metrics, classify,
                                           execute_exploratory, load_indices,
                                           pit_eligibility, validate_parameters,
                                           verify_exploratory)
from regime190.research_cycle import cycle
from regime190.eligibility_manifest import build_manifest


class ExploratoryBacktestTests(unittest.TestCase):
    def test_actual_snapshot_provenance_and_pit_gate(self):
        rows, provenance = load_indices()
        self.assertGreater(len(rows), 4000)
        self.assertEqual(provenance['KOSPI']['pit_status'], 'PIT_UNVERIFIED')
        self.assertEqual(pit_eligibility()['eligible_indicator_ids'], [])
        manifest = build_manifest()
        self.assertEqual(manifest['indicator_count'], 190)
        self.assertEqual(manifest['pit_eligible_count'], 0)
        self.assertTrue(all(not row['backtest_eligible'] for row in manifest['records']))

    def test_features_do_not_read_future_rows(self):
        rows, _ = load_indices()
        before = _features(rows, 100)
        rows[101]['kospi']['close'] = 999999
        self.assertEqual(before, _features(rows, 100))

    def test_six_regimes_are_reachable_and_deterministic(self):
        base = {'drawdown60': -0.02, 'volatility20': 0.01,
                'momentum20': 0.01, 'momentum5': 0,
                'relative_kosdaq20': -0.01, 'above_sma20': True}
        cases = [({'drawdown60': -0.2, 'volatility20': 0.03}, 'RISK_OFF_PANIC'),
                 ({'drawdown60': -0.09, 'momentum5': 0.04}, 'RECOVERY_EARLY'),
                 ({'momentum20': -0.06}, 'RISK_OFF_WEAK'),
                 ({'momentum20': 0.05}, 'RISK_ON_TREND'),
                 ({'momentum20': 0.02, 'relative_kosdaq20': 0.02}, 'RISK_ON_SELECTIVE'),
                 ({}, 'CHOPPY')]
        for change, expected in cases:
            self.assertEqual(classify(dict(base, **change))[0], expected)

    def test_next_session_and_cost(self):
        result = execute_exploratory()
        verify_exploratory(result)
        first = result['timeline'][0]
        self.assertLess(first['signal_after_close_date'], first['execution_open_date'])
        self.assertLess(first['execution_open_date'], first['settlement_open_date'])
        self.assertEqual(result['parameters']['transaction_cost_one_way'], 0.0015)
        self.assertLess(_metrics([0.0 - PARAMETERS['transaction_cost_one_way']], [1.0], 1)
                        ['cumulative_return'], 0)
        result['official_performance_claim'] = True
        with self.assertRaises(ValueError):
            verify_exploratory(result)
        with self.assertRaises(ValueError):
            validate_parameters(dict(PARAMETERS, crash_threshold=0.1))

    def test_official_block_and_exploratory_queue_memory_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'state'
            repo = Path(__file__).resolve().parents[4]
            blocked = cycle(state, repo, 'official')
            self.assertEqual(blocked['status'], 'BLOCKED_PIT')
            self.assertFalse(state.exists())
            first = cycle(state, repo, 'exploratory')
            self.assertEqual(first['status'], 'EXPLORATORY_COMPLETE_OFFICIAL_BLOCKED')
            memory = json.loads((state / 'research_memory.json').read_text())
            queue = json.loads((state / 'task_queue.json').read_text())
            self.assertEqual(memory['research_decision'], 'REQUIRE_PIT_EVIDENCE')
            self.assertEqual(memory['model_status'], 'DETERMINISTIC_NON_AI')
            self.assertEqual(queue['checkpoint_id'], 1)
            self.assertEqual(cycle(state, repo, 'exploratory')['status'], 'ALREADY_EVALUATED')
            self.assertEqual(json.loads((state / 'task_queue.json').read_text())['checkpoint_id'], 1)
            (state / 'research_memory.json').unlink()  # interruption after worker completion
            self.assertEqual(cycle(state, repo, 'exploratory')['status'],
                             'EXPLORATORY_COMPLETE_OFFICIAL_BLOCKED')
            self.assertEqual(json.loads((state / 'task_queue.json').read_text())['checkpoint_id'], 1)
            artifact = Path(memory['artifact_path'])
            artifact.write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'changed'):
                cycle(state, repo, 'exploratory')


if __name__ == '__main__':
    unittest.main()
