import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_pit_readiness import classify
from source_lineage_reconcile import load_manifest


class ContinuationAuditTests(unittest.TestCase):
    def test_no_data_and_current_snapshot_are_not_pit_evidence(self):
        indicator = {'availability_status': '일부 확보'}
        self.assertEqual(classify(indicator, {'published_at': 'no_data',
                                               'available_at': 'no_data',
                                               'vintage': 'no_data'}, 0), 'PIT_BLOCKED')
        self.assertEqual(classify(indicator, {'published_at': 'absent',
                                               'available_at': 'unverified',
                                               'vintage': 'current snapshot only'}, 0), 'PIT_BLOCKED')

    def test_source_manifest_duplicate_fails_closed(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'manifest.jsonl'
            row = json.dumps({'symbol': '000001', 'rows': 1})
            path.write_text(row + '\n' + row + '\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                load_manifest(path)


if __name__ == '__main__':
    unittest.main()
