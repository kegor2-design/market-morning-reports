import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect_fred_yearly as target


class FredYearlyTests(unittest.TestCase):
    def test_atomic_manifest_and_resume_without_repeat_request(self):
        payload = json.dumps({'count': 1, 'observations': [
            {'date': '2019-01-02', 'value': '2.5',
             'realtime_start': '2019-01-03', 'realtime_end': '2019-01-03'}]}).encode()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with patch.object(target, 'SERIES', ('DGS10',)), \
                 patch.object(target, 'YEARS', range(2019, 2020)), \
                 patch.object(target, 'MIN_FREE', 0), \
                 patch.object(target, 'env_keys', return_value={'FRED_API_KEY': 'test'}), \
                 patch.object(target, 'request_year', return_value=('ACQUIRED', {
                     'rows': 1, 'first_date': '2019-01-02', 'last_date': '2019-01-02'}, payload)) as request:
                self.assertEqual(target.run(state, delay_seconds=0)['state'], 'COMPLETE')
                self.assertEqual(target.run(state, delay_seconds=0)['state'], 'COMPLETE')
                self.assertEqual(request.call_count, 1)
                folder = state / 'fred_initial_yearly' / 'DGS10'
                self.assertTrue(target.valid_record(folder/'2019.json', folder/'2019.manifest.json'))

    def test_response_count_must_match_rows(self):
        class Response:
            status_code = 200

            def iter_content(self, _size):
                yield b'{"count":2,"observations":[]}'

        class Session:
            def get(self, *_args, **_kwargs):
                return Response()

        self.assertEqual(target.request_year(Session(), 'test', 'DGS10', 2019)[0],
                         'TRUNCATED_OR_INVALID')


if __name__ == '__main__':
    unittest.main()
