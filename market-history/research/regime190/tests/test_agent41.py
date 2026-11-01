import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190.agent41_research import _bin, cycle, pit_research


class Agent41Tests(unittest.TestCase):
    def test_pit_recheck_never_promotes_metadata(self):
        result = pit_research()
        self.assertEqual(len(result['records']), 190)
        self.assertEqual(result['counts'], {'PIT_BLOCKED': 71,
                                           'CALCULATION_PENDING': 21,
                                           'SOURCE_MISSING': 98})
        self.assertEqual(result['approved_after'], 0)
        self.assertTrue(all(not row['approved'] for row in result['records']))
        self.assertTrue(all(problem['root_cause'] is None
                            for problem in result['problems']))

    def test_template_allowlist_and_stop(self):
        row = {'feature': {'drawdown60': -.12, 'volatility20': .03,
                           'momentum20': -.05}}
        self.assertEqual(_bin(row, 'volatility_drawdown'), 'True:True')
        with self.assertRaises(ValueError):
            _bin(row, 'arbitrary_code')
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            (state / 'STOP').write_text('stop')
            self.assertEqual(cycle(state)['status'], 'STOPPED')

    def test_real_cycle_resume_and_hash_gate(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            first = cycle(state)
            self.assertEqual(first['status'], 'RESEARCH_CYCLE_RECORDED')
            self.assertEqual(cycle(state)['status'], 'ALREADY_EVALUATED')
            forecast = json.loads((state / 'forecast_research.json').read_text())
            self.assertEqual(forecast['final_holdout'], 'CONTAMINATED_NOT_REUSED')
            self.assertFalse(forecast['official_prediction_claim'])
            self.assertEqual(forecast['experiments'][0]['independent_validation'],
                             'NOT_VERIFIED')
            (state / 'forecast_research.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                cycle(state)


if __name__ == '__main__':
    unittest.main()
