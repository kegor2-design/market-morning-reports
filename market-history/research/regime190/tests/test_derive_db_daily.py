import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from derive_db_daily import derive, run_batch
from status_snapshot import snapshot


class DailyDerivationTests(unittest.TestCase):
    def test_causal_metrics_and_warmup(self):
        close = list(range(10, 35))
        data = pd.DataFrame({
            'open': close, 'high': [x + 1 for x in close],
            'low': [x - 1 for x in close], 'close': close,
            'volume': [100] * 25, 'turnover': [1000] * 25,
        })
        result = derive(data)
        self.assertEqual(result['obv'].iloc[-1], 2400)
        self.assertEqual(result['mfi14'].iloc[-1], 100)
        self.assertEqual(result['cmf20'].iloc[-1], 0)
        self.assertTrue(pd.isna(result['volume_z20'].iloc[-1]))
        self.assertTrue(pd.isna(result['amihud_krw_billion'].iloc[0]))
        self.assertGreater(result['amihud_krw_billion'].iloc[1], 0)

    def test_low_disk_stops_before_db_connection(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch('derive_db_daily.shutil.disk_usage') as usage, \
                 mock.patch('derive_db_daily.connection') as connect:
                usage.return_value.free = 4 * 1024**3
                result = run_batch(Path(root), 1)
                self.assertEqual(result['state'], 'DISK_WAIT')
                connect.assert_not_called()

    def test_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            conn = sqlite3.connect(state / 'checkpoint.sqlite')
            conn.executescript('''CREATE TABLE tasks(state TEXT,last_attempt_at TEXT);
                              CREATE TABLE requests(result TEXT,attempted_at TEXT,row_count INTEGER);
                              INSERT INTO tasks VALUES('NEEDS_REVIEW',NULL);''')
            conn.commit(); conn.close()
            (state / 'progress.json').write_text(json.dumps({'updated_at_utc': '2026-10-29T00:00:00+00:00'}))
            before = (state / 'progress.json').stat().st_mtime_ns
            result = snapshot(state)
            self.assertEqual(result['counts']['NEEDS_REVIEW'], 1)
            self.assertEqual(result['new_verified_rows_24h'], 0)
            self.assertEqual((state / 'progress.json').stat().st_mtime_ns, before)


if __name__ == '__main__':
    unittest.main()
