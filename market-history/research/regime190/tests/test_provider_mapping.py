import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190.provider_mapping import build_mapping


class ProviderMappingTests(unittest.TestCase):
    def test_all_190_are_mapped_without_pit_promotion(self):
        names = ('KIS', 'KRX', 'BOK_ECOS', 'KOSIS', 'FRED', 'DART')
        presence = {name: {'credential_present': name != 'KOSIS'} for name in names}
        probes = {name: {'auth_result': 'SUCCESS'} for name in ('BOK_ECOS', 'DART')}
        fred = [{'auth_result': 'SUCCESS', 'series_id': 'DGS10'}]
        result = build_mapping(presence, probes, fred)
        self.assertEqual(result['indicator_count'], 190)
        self.assertEqual(result['pit_approvals_added'], 0)
        self.assertEqual({row['indicator_id'] for row in result['records']}, set(range(1, 191)))
        self.assertIn('FRED', result['records'][115]['candidate_providers'])
        self.assertEqual(result['records'][115]['next_task_class'], 'CODEX_REQUIRED')
        self.assertFalse(result['records'][115]['historical_universe_required'])
        self.assertEqual(result['access_results']['KOSIS'], 'NO_CREDENTIAL')


if __name__ == '__main__':
    unittest.main()
