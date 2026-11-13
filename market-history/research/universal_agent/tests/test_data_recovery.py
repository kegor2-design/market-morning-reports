import json
import hashlib
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.data_recovery import recover, classify_error, _fetch
from universal_agent.source_adapters import REGISTRY, select

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
        self.assertEqual(classify_error(urllib.error.HTTPError('x', 404, 'missing', {}, None)),
                         'SOURCE_NOT_FOUND')
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

    def test_source_unavailable_records_safe_next_action(self):
        def unavailable(*_):
            raise urllib.error.HTTPError('official', 503, 'unavailable', {}, None)
        state = recover(request(), self.root, fetch=unavailable)
        self.assertEqual(state['problem_type'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(state['next_action'], 'RUN_INDEPENDENT_ALLOWED_TASK')
        self.assertEqual(state['problem_history'][-1]['verification'], 'BLOCKED')
        self.assertEqual(recover(request(), self.root, fetch=lambda *_:
                         self.fail('failed request must not replay'))['status'], 'BLOCKED_ENV')

    def test_corrupt_checkpoint_and_invalid_csv_block(self):
        saved = recover(request(), self.root, fetch=lambda *_: (b'wrong', 1))
        self.assertEqual(saved['status'], 'BLOCKED_EVIDENCE')
        (self.root / 'data_recovery.json').write_text('{bad')
        with self.assertRaises(json.JSONDecodeError):
            recover(request(), self.root, fetch=lambda *_: self.fail('API replay'))

    def test_ny_fed_adapter_collects_distinct_reference_rate(self):
        item = request(series='NYFED_SOFR', start='2024-04-01', end='2024-04-03',
                       expected_dates=['2024-04-01', '2024-04-02', '2024-04-03'],
                       existing={'2024-04-01': '5.35'},
                       allowed_sources=['NYFED_REFERENCE_RATES'])
        payload = json.dumps({'refRates': [
            {'effectiveDate': '2024-04-01', 'type': 'SOFR', 'percentRate': 5.35},
            {'effectiveDate': '2024-04-02', 'type': 'SOFR', 'percentRate': 5.34},
            {'effectiveDate': '2024-04-03', 'type': 'SOFR', 'percentRate': 5.32}]}).encode()
        state = recover(item, self.root, fetch=lambda *_: (payload, 1))
        self.assertEqual(state['recovered'], {'2024-04-02': '5.34', '2024-04-03': '5.32'})
        self.assertEqual(state['source_records'][0]['source_id'], 'NYFED_REFERENCE_RATES')
        from universal_agent.data_recovery import verify_recovery
        self.assertEqual(verify_recovery(item, self.root)['status'],
                         'DATA_RECOVERED_PIT_UNVERIFIED')
        with self.assertRaisesRegex(ValueError, 'approved reviewed adapter'):
            select('NYFED_SOFR', ['US_TREASURY'])
        with self.assertRaisesRegex(ValueError, 'rate type'):
            REGISTRY['NYFED_REFERENCE_RATES'].parse('NYFED_SOFR',
                b'{"refRates":[{"effectiveDate":"2024-04-01","type":"OTHER","percentRate":1}]}',
                {'2024-04-01'})

    def test_real_revision_pattern_requires_hashed_vintage_and_notice(self):
        source_root = self.root / 'fred'
        folder = source_root / 'DGS10'
        folder.mkdir(parents=True)
        raw = json.dumps({'observations': [{'date': '2014-01-14',
            'value': '2.77', 'realtime_start': '2014-01-15'}]}).encode()
        (folder / '2014.json').write_bytes(raw)
        (folder / '2014.manifest.json').write_text(json.dumps({'sha256':
            hashlib.sha256(raw).hexdigest(), 'series': 'DGS10', 'year': 2014}))
        item = request(series='UST_10Y', start='2014-01-14', end='2014-01-14',
                       expected_dates=['2014-01-14'], existing={'2014-01-14': '2.77'},
                       existing_source='FRED_INITIAL_HASHED', cross_validate=True,
                       allowed_sources=['US_TREASURY', 'FRED_ALFRED', 'FED_H15'],
                       budget={'max_network_requests': 2, 'max_seconds': 10,
                               'max_retries': 0, 'max_model_calls': 0})
        treasury = b'Date,2 Yr,10 Yr\n1/14/14,0.10,2.88\n'
        notice = (b'Correction to the 10-year Treasury constant maturity rate for '
                  b'January 14, 2014. The rate should have been 2.88 (rather than 2.77).')
        calls = []
        def fetch(uri, *_):
            calls.append(uri)
            return (notice if 'federalreserve.gov' in uri else treasury), 1
        with patch('universal_agent.revision_evidence.SOURCE_ROOT', source_root):
            state = recover(item, self.root / 'revised', fetch=fetch)
            from universal_agent.data_recovery import verify_recovery
            verify_recovery(item, self.root / 'revised')
        self.assertEqual(state['status'], 'DATA_MISMATCH_RESOLVED_PIT_UNVERIFIED')
        self.assertEqual(len(calls), 2)
        self.assertEqual(state['resolved_mismatches']['2014-01-14']['corrected_value'], '2.88')
        self.assertIsNone(state['resolved_mismatches']['2014-01-14']['first_accessible_at'])
        (self.root / 'revised/revision_notice.html').write_bytes(b'changed')
        with patch('universal_agent.revision_evidence.SOURCE_ROOT', source_root):
            with self.assertRaisesRegex(ValueError, 'notice hash changed'):
                verify_recovery(item, self.root / 'revised')
        bad = dict(item, existing={'2014-01-14': '187'})
        with patch('universal_agent.revision_evidence.SOURCE_ROOT', source_root):
            blocked = recover(bad, self.root / 'unverified', fetch=lambda *_:
                              self.fail('Unverified input must not trigger fetch'))
        self.assertEqual(blocked['status'], 'BLOCKED_EVIDENCE')


if __name__ == '__main__':
    unittest.main()
