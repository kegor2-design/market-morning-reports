import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from price_cutoff_probe import profile


class PriceCutoffProbeTests(unittest.TestCase):
    def test_counts_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'one.csv.gz').write_bytes(b'abc')
            manifest = root / 'manifest.jsonl'
            item = {'symbol': 'one', 'last_date': '2026-09-15', 'rows': 4,
                    'missing_market_rows': 3, 'file': 'one.csv.gz',
                    'bytes': 3, 'sha256': 'fixture'}
            manifest.write_text(json.dumps(item) + '\n')
            report = profile(manifest, root)
            self.assertEqual(report['observed_counts']['shared_cutoff_2026_09_15'], 1)
            self.assertEqual(report['observed_counts']['missing_files'], 0)
            self.assertEqual(report['observed_counts']['rows'], 4)
            manifest.write_text(json.dumps(item) + '\n' + json.dumps(item) + '\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate symbol'):
                profile(manifest, root)


if __name__ == '__main__':
    unittest.main()
