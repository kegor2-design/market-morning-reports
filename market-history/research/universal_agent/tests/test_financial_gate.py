import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.engine import check_evidence


class FinancialGateTests(unittest.TestCase):
    def test_pit_and_duplicate_gate(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / 'prices.csv'
            header = 'symbol,date,source_id,release_at,vintage_at,available_at,asof_at,adjusted\n'
            good = 'A,2026-01-01,source,2026-01-01T17:00:00+00:00,2026-01-01T17:00:00+00:00,2026-01-01T17:00:00+00:00,2026-01-02T00:00:00+00:00,true\n'
            check = {'kind': 'csv_financial_quality', 'path': 'prices.csv',
                     'required_fields': ['adjusted'], 'min_rows': 1}
            path.write_text(header + good)
            self.assertTrue(check_evidence(root, check)['ok'])
            path.write_text(header + good + good)
            self.assertFalse(check_evidence(root, check)['ok'])
            path.write_text(header + good.replace('2026-01-02T00:00:00', '2026-01-01T00:00:00'))
            self.assertFalse(check_evidence(root, check)['ok'])


if __name__ == '__main__':
    unittest.main()
