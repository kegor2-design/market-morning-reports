import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.data_recovery import recover, classify_error, _fetch

CSV = (b'Date,2 Yr,10 Yr\n4/1/15,0.55,1.87\n4/2/15,0.55,1.92\n')


def request(**changes):
    item = {'goal_id': 'goal_a', 'job_id': 'job_a', 'task_id': 'task_a',
            'series': 'UST_10Y', 'market': 'US', 'unit': 'percent',
            'start': '2015-04-01', 'end': '2015-04-02',
            'expected_dates': ['2015-04-01', '2015-04-02'],
            'existing': {'2015-04-01': '1.87'}, 'allowed_sources': ['US_TREASURY'],
            'budget': {'max_network_requests': 1, 'max_seconds': 10,
                       'max_retries': 0, 'max_model_calls': 0}}
    item.update(changes)
    return item


class DataRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_gap_recovery_is_hash_sealed_and_pit_blocked(self):
        calls = []
        def fetch(uri, attempts, timeout):
            calls.append(uri)
            return CSV, 1
        first = recover(request(), self.root, fetch=fetch)
        self.assertEqual(first['status'], 'DATA_RECOVERED_PIT_UNVERIFIED')
        self.assertEqual(first['recovered'], {'2015-04-02': '1.92'})
        self.assertIsNone(first['source_records'][0]['first_accessible_at'])
        self.assertEqual(recover(request(), self.root, fetch=fetch)['recovered'], first['recovered'])
        self.assertEqual(len(calls), 1)
        (self.root / 'source.csv').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            recover(request(), self.root, fetch=fetch)

    def test_mismatch_is_preserved_and_not_silently_corrected(self):
        saved = recover(request(existing={'2015-04-01': '187'}), self.root,
                        fetch=lambda *_: (CSV, 1))
        self.assertEqual(saved['status'], 'DATA_MISMATCH')
        self.assertEqual(saved['mismatches']['2015-04-01']['existing'], '187')
        self.assertEqual(saved['mismatches']['2015-04-01']['source'], '1.87')

    def test_uncertain_call_does_not_repeat(self):
        item = request()
        def interrupted(*_):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            recover(item, self.root, fetch=interrupted)
        saved = recover(item, self.root, fetch=lambda *_: self.fail('API replay'))
        self.assertEqual(saved['status'], 'BLOCKED_UNCERTAIN_API_CALL')

    def test_source_errors_and_bad_budget(self):
        self.assertEqual(classify_error(urllib.error.HTTPError('x', 429, 'rate', {}, None)),
                         'RATE_LIMIT')
        self.assertEqual(classify_error(urllib.error.HTTPError('x', 403, 'auth', {}, None)),
                         'AUTHORIZATION_REQUIRED')
        item = request()
        item['budget']['max_network_requests'] = 4
        with self.assertRaisesRegex(ValueError, 'budget'):
            recover(item, self.root)
        self.assertFalse((self.root / 'data_recovery.json').exists())

    def test_http_retry_only_for_transient_error(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def geturl(self): return 'https://example.org/official.csv'
            def read(self, *_): return CSV
        uri = 'https://example.org/official.csv'
        rate = urllib.error.HTTPError(uri, 429, 'rate', {}, None)
        bad = urllib.error.HTTPError(uri, 400, 'bad', {}, None)
        with patch('universal_agent.data_recovery.urllib.request.urlopen',
                   side_effect=[rate, Response()]) as opener, \
             patch('universal_agent.data_recovery.time.sleep'):
            self.assertEqual(_fetch(uri, 2, 1), (CSV, 2))
            self.assertEqual(opener.call_count, 2)
        with patch('universal_agent.data_recovery.urllib.request.urlopen',
                   side_effect=bad) as opener:
            with self.assertRaises(urllib.error.HTTPError):
                _fetch(uri, 3, 1)
            self.assertEqual(opener.call_count, 1)

    def test_corrupt_checkpoint_and_invalid_csv_block(self):
        saved = recover(request(), self.root, fetch=lambda *_: (b'wrong', 1))
        self.assertEqual(saved['status'], 'BLOCKED_EVIDENCE')
        (self.root / 'data_recovery.json').write_text('{bad')
        with self.assertRaises(json.JSONDecodeError):
            recover(request(), self.root, fetch=lambda *_: self.fail('API replay'))


if __name__ == '__main__':
    unittest.main()
