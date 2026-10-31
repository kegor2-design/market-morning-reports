import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_recovery import cutoff_snapshot, indicator_inventory


class EvidenceRecoveryTests(unittest.TestCase):
    def test_cutoff_bulk_observation_does_not_claim_root_cause(self):
        symbols = [{'export_last_date': '2026-09-15', 'source_last_date': '2026-09-15',
                    'last_collected_at': '2026-09-17T01:00:00'}]
        snapshot = cutoff_snapshot(symbols, [('2026-09-17', 'kis', 4_241_230, 1935)],
                                   [('2026-09-17', 145, 145, 870, 'OK', {'errors': {}})])
        self.assertTrue(snapshot['overnight_bulk_load_observed'])
        self.assertEqual(snapshot['cause_status'], 'PARTIALLY_CONFIRMED')
        self.assertEqual(snapshot['pit_status'], 'UNVERIFIED')

    def test_observation_date_cannot_promote_pit(self):
        matrix = [{'indicator_id': 1, 'name': 'SMA', 'provider': 'candidate',
                   'pit_classification': 'PIT_BLOCKED', 'evidence_refs': 'audit:1'}]
        audits = {1: {'calculation': '부분 생성', 'survivorship_risk': 'unverified',
                      'alternative_provider': 'candidate source'}}
        mappings = {1: {'required_inputs': 'OHLCV', 'market_scope_status': 'SOURCE_SCOPE_UNVERIFIED'}}
        pits = {1: {'observation_date': 'present', 'published_at': 'absent',
                    'ingested_at': '2026-10-31', 'revision_history': 'absent',
                    'available_at': 'unverified', 'vintage': 'absent'}}
        row = indicator_inventory(matrix, audits, mappings, pits)[0]
        self.assertEqual(row['backtest_eligible'], 'NO')
        self.assertIn('publication_timestamp', row['missing_evidence'])
        self.assertIn('historical_security_universe', row['missing_evidence'])


if __name__ == '__main__':
    unittest.main()
