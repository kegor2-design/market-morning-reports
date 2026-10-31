import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190.credential_evidence import collect_fred_dgs10, credential_presence, probe_ecos_dart
from universal_agent.offline_worker import load_plan


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def iter_content(self, _size):
        yield self.payload


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = {}
        self.trust_env = None
        self.calls = []

    def get(self, url, params, **kwargs):
        self.calls.append((url, params, kwargs))
        return next(self.responses)


class CredentialEvidenceTests(unittest.TestCase):
    def test_presence_has_only_provider_flags(self):
        with patch('regime190.credential_evidence.env_keys', side_effect=[
                {'FRED_API_KEY': 'secret-test-value', 'KIS_APP_KEY': 'k', 'KIS_APP_SECRET': 's'}, {}]):
            result = credential_presence()
        self.assertTrue(result['FRED']['credential_present'])
        self.assertFalse(result['KOSIS']['credential_present'])
        self.assertNotIn('secret-test-value', json.dumps(result))

    def test_bounded_fred_sample_keeps_secret_out_of_artifact(self):
        series = {'seriess': [{'id': 'DGS10', 'observation_start': '1962-01-02',
                               'observation_end': '2026-10-30', 'frequency': 'Daily', 'notes': 'Public data'}]}
        observations = {'observations': [
            {'date': '2020-01-02', 'value': '1.88', 'realtime_start': '2020-01-03',
             'realtime_end': '2020-01-03'}]}
        session = Session([Response(200, series), Response(200, observations)])
        with tempfile.TemporaryDirectory() as root:
            with patch('regime190.credential_evidence.env_keys', return_value={'FRED_API_KEY': 'secret-test-value'}), \
                 patch('regime190.credential_evidence.requests.Session', return_value=session):
                result = collect_fred_dgs10(Path(root))
            self.assertTrue(result['data_acquired'])
            self.assertEqual(result['requests'], 2)
            self.assertEqual(result['row_count'], 1)
            self.assertEqual(len(list((Path(root) / 'raw').glob('*.json'))), 1)
            self.assertNotIn('secret-test-value', json.dumps(result))
            self.assertNotIn(b'secret-test-value', Path(result['raw_path']).read_bytes())

    def test_copyright_blocks_data_request(self):
        session = Session([Response(200, {'seriess': [{'id': 'DGS10', 'notes': 'Copyright owner'}]})])
        with tempfile.TemporaryDirectory() as root:
            with patch('regime190.credential_evidence.env_keys', return_value={'FRED_API_KEY': 'x'}), \
                 patch('regime190.credential_evidence.requests.Session', return_value=session):
                result = collect_fred_dgs10(Path(root))
        self.assertEqual(result['license_status'], 'LICENSE_REVIEW_REQUIRED')
        self.assertEqual(result['requests'], 1)
        self.assertFalse(result['data_acquired'])

    def test_ecos_dart_auth_probe_discards_payloads_and_secrets(self):
        session = Session([Response(200, {'StatisticSearch': {'row': [{'STAT_CODE': '817Y002'}]}}),
                           Response(200, {'status': '000', 'list': [{'rcept_no': '20201005000001'}]})])
        with patch('regime190.credential_evidence.env_keys', return_value={
                'BOK_ECOS_API_KEY': 'ecos-secret', 'DART_API_KEY': 'dart-secret'}), \
             patch('regime190.credential_evidence.requests.Session', return_value=session):
            result = probe_ecos_dart()
        self.assertEqual(result['results']['BOK_ECOS']['auth_result'], 'SUCCESS')
        self.assertEqual(result['results']['DART']['auth_result'], 'SUCCESS')
        self.assertEqual(len(session.calls), 2)
        self.assertNotIn('ecos-secret', json.dumps(result))
        self.assertNotIn('dart-secret', json.dumps(result))
        self.assertFalse(result['provider_payloads_stored'])

    def test_fred_rate_limit_stops_without_raw_file(self):
        session = Session([Response(429, {'error': 'rate limit'})])
        with tempfile.TemporaryDirectory() as root:
            with patch('regime190.credential_evidence.env_keys', return_value={'FRED_API_KEY': 'secret'}), \
                 patch('regime190.credential_evidence.requests.Session', return_value=session):
                result = collect_fred_dgs10(Path(root))
            self.assertEqual(result['auth_result'], 'RATE_LIMITED')
            self.assertEqual(result['requests'], 1)
            self.assertFalse((Path(root) / 'raw').exists())

    def test_contract_accepts_human_task_without_execution(self):
        plan, _ = load_plan(Path(__file__).resolve().parents[1] / 'credential_pit_plan_20261101.json')
        self.assertEqual(plan['tasks'][-1]['execution_class'], 'HUMAN_APPROVAL_REQUIRED')


if __name__ == '__main__':
    unittest.main()
