import importlib.util
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / 'indicator116_20261112/build_asof_matrix.py'
spec = importlib.util.spec_from_file_location('indicator116_asof_audit', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class Indicator116AsOfTest(unittest.TestCase):
    def test_vintage_date_cannot_establish_next_korean_open(self):
        for day in (date(2015, 4, 1), date(2020, 1, 6), date(2020, 7, 6)):
            self.assertEqual(day + audit.timedelta(days=2),
                             audit.vintage_day_completed_by_kst_0900(day))

    def test_dst_offset_changes(self):
        eastern = audit.ZoneInfo('America/New_York')
        self.assertEqual('-0500', audit.datetime(2020, 1, 6, 12, tzinfo=eastern).strftime('%z'))
        self.assertEqual('-0400', audit.datetime(2020, 7, 6, 12, tzinfo=eastern).strftime('%z'))

    def test_missing_snapshot_row_is_not_a_revision(self):
        initial = {'2026-10-26': {'value': '4.00'}}
        self.assertFalse(audit.snapshot_differs({}, initial, '2026-10-26'))
        self.assertTrue(audit.snapshot_differs({'2026-10-26': '4.01'}, initial, '2026-10-26'))

    def test_treasury_xml_comparison_detects_current_value_change(self):
        xml = '''<feed xmlns="http://www.w3.org/2005/Atom"
            xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
            <entry><content><d:NEW_DATE>2024-01-02T00:00:00</d:NEW_DATE>
            <d:BC_2YEAR>4.33</d:BC_2YEAR><d:BC_10YEAR>3.95</d:BC_10YEAR>
            </content></entry></feed>'''
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'treasury.xml'
            path.write_text(xml)
            data = {'DGS2': {'2024-01-02': {'value': '4.33'}},
                    'DGS10': {'2024-01-02': {'value': '3.96'}}}
            result = audit.compare_treasury_xml(data, [path])
        self.assertEqual(result['counts']['overlap_DGS2'], 1)
        self.assertEqual(result['counts']['different_DGS10'], 1)
        self.assertEqual(result['difference_dates'], [('DGS10', '2024-01-02')])


if __name__ == '__main__':
    unittest.main()
