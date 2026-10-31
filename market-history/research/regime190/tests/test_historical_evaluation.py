import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190.historical_evaluation import (evaluate_project_test_rows, evaluate_test_rows,
                                             pit_gate, walk_forward_indices)


def verified_feature():
    return {'pit_status': 'PIT_VERIFIED', 'source_id': 'fixture',
            'observation_date': '2020-01-01', 'observed_at': '2020-01-01T15:30:00+09:00',
            'published_at': '2020-01-01T16:00:00+09:00',
            'available_at': '2020-01-01T16:01:00+09:00',
            'decision_at': '2020-01-02T09:00:00+09:00',
            'vintage_id': 'v1', 'universe_snapshot_id': 'u1',
            'lineage_sha256': 'a' * 64, 'calculation_sha256': 'b' * 64,
            'historical_membership_verified': True, 'delisted_included': True,
            'revision_asof_verified': True, 'security_price': False}


class HistoricalEvaluationTests(unittest.TestCase):
    def test_real_project_has_no_pit_features_and_gate_remains_closed(self):
        from regime190.blocker_resolution import inventory
        records = inventory()['records']
        self.assertEqual(sum(row['prior_pit_classification'] == 'PIT_VERIFIED' for row in records), 0)
        with self.assertRaisesRegex(ValueError, 'BACKTEST_BLOCKED'):
            pit_gate([])
        with self.assertRaisesRegex(ValueError, 'BACKTEST_BLOCKED'):
            evaluate_project_test_rows([], [verified_feature()], [1])

    def test_lookahead_and_universe_guard(self):
        item = verified_feature()
        item['available_at'] = '2020-01-02T09:01:00+09:00'
        with self.assertRaisesRegex(ValueError, 'look-ahead'):
            pit_gate([item])
        item = verified_feature()
        item['delisted_included'] = False
        with self.assertRaisesRegex(ValueError, 'universe'):
            pit_gate([item])

    def test_chronological_embargo_and_metrics(self):
        dates = [f'2020-01-{day:02d}' for day in range(1, 9)]
        folds = walk_forward_indices(dates, train_size=3, test_size=2, embargo=1)
        self.assertEqual([(list(a), list(b)) for a, b in folds],
                         [([0, 1, 2], [4, 5]), ([2, 3, 4], [6, 7])])
        rows = [
            {'date': '2020-01-05', 'crash_warning': True, 'crash_event': True,
             'recovery_signal': False, 'recovery_event': False, 'false_rebound': False,
             'regime_transition': True, 'transition_detected': False,
             'forward_return': -.1, 'strategy_return': -.1},
            {'date': '2020-01-06', 'crash_warning': False, 'crash_event': False,
             'recovery_signal': True, 'recovery_event': False, 'false_rebound': True,
             'regime_transition': False, 'transition_detected': True,
             'forward_return': .02, 'strategy_return': .02}]
        result = evaluate_test_rows(rows, [verified_feature()])
        self.assertEqual(result['crash_warning']['precision'], 1)
        self.assertEqual(result['false_rebound_frequency'], 1)
        self.assertEqual(result['transition_delay_rows']['median'], 1)
        self.assertAlmostEqual(result['maximum_drawdown'], -.1)


if __name__ == '__main__':
    unittest.main()
