import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190 import blocker_resolution as br
from regime190.offline_tasks import probe_source_catalog, verify


class BlockerResolutionTests(unittest.TestCase):
    def test_actual_inventory_is_complete_and_keeps_pit_decisions(self):
        result = br.inventory()
        self.assertEqual(result['indicator_count'], 190)
        self.assertEqual(set(row['indicator_id'] for row in result['records']), set(range(1, 191)))
        self.assertEqual(result['prior_pit_counts']['PIT_VERIFIED'] if 'PIT_VERIFIED' in result['prior_pit_counts'] else 0, 0)
        self.assertEqual(result['pit_approvals_added'], 0)
        self.assertTrue(all(row['pit_approved_by_this_task'] is False for row in result['records']))
        self.assertTrue(all(set(row['missing_evidence']) <= br.CLASSES for row in result['records']))

    def test_local_probe_cannot_promote_pit_or_read_outside_research(self):
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / 'checkpoint.sqlite'
            with sqlite3.connect(db_path) as db:
                db.execute('CREATE TABLE tasks (indicator_id INTEGER, state TEXT, raw_sha256 TEXT, '
                           'derived_series_path TEXT, pit_eligible INTEGER)')
                db.execute('INSERT INTO tasks VALUES (1,?,?,?,?)', ('done', 'hash', '/etc/passwd', 1))
            result = br.check_local(1, db_path)
        self.assertEqual(result['file_status'], 'MISSING_OR_OUTSIDE_RESEARCH_ROOT')
        self.assertIsNone(result['file_sha256'])
        self.assertFalse(result['pit_approval'])

    def test_source_probe_is_bounded_head_only_and_does_not_collect_data(self):
        response = MagicMock()
        response.status = 200
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch('regime190.offline_tasks.urllib.request.build_opener', return_value=opener):
            result = probe_source_catalog()
        self.assertEqual(result['request_count'], 6)
        self.assertEqual(opener.open.call_count, 6)
        self.assertTrue(all(call.args[0].get_method() == 'HEAD' for call in opener.open.call_args_list))
        self.assertTrue(all(row['data_collected'] is False for row in result['results']))
        self.assertFalse(result['pit_approval'])
        verify({'task_type': 'source_catalog_probe'}, result)


if __name__ == '__main__':
    unittest.main()
