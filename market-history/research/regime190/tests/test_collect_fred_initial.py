import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect_fred_initial as target


class FredInitialTests(unittest.TestCase):
    def test_one_series_then_resume_without_request(self):
        data = json.dumps({'observations': [{'date': '2026-10-01',
                                             'realtime_start': '2026-10-02',
                                             'value': '4.0'}]}).encode()

        class Response:
            status_code = 200

            def iter_content(self, _size):
                yield data

        class Session:
            trust_env = True

            def get(self, *_args, **_kwargs):
                return Response()

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with patch.object(target, 'SERIES', ('DGS10',)), \
                 patch.object(target, 'env_keys', return_value={'FRED_API_KEY': 'test'}), \
                 patch.object(target, 'KEY_ENV', state/'unused'), \
                 patch.object(target, 'MIN_FREE', 0), \
                 patch.object(target.requests, 'Session', return_value=Session()):
                first = target.fetch_one(state)
                self.assertEqual(first['state'], 'ACQUIRED_INITIAL_VINTAGE')
                self.assertEqual(first['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(target.fetch_one(state)['state'], 'COMPLETE')


if __name__ == '__main__':
    unittest.main()
