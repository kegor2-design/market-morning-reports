import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect_ecos_history as target


class EcosHistoryTests(unittest.TestCase):
    def test_page_is_hashed_and_resumed_without_repeat_request(self):
        rows = [{'TIME': '20100104', 'DATA_VALUE': '4.0',
                 'ITEM_CODE1': target.ITEMS['KTB_3Y']}]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with patch.object(target, 'MIN_FREE', 0), \
                 patch.object(target, 'env_keys', return_value={'BOK_ECOS_API_KEY': 'test'}), \
                 patch.object(target, 'fetch', return_value=('ACQUIRED', {
                     'rows': rows, 'total_count': 1, 'first_row': 1, 'last_row': 1})) as fetch:
                self.assertEqual(target.run(state, ('KTB_3Y',), delay_seconds=0)['state'], 'COMPLETE')
                self.assertEqual(target.run(state, ('KTB_3Y',), delay_seconds=0)['state'], 'COMPLETE')
                self.assertEqual(fetch.call_count, 1)
                folder = state / 'ecos_rate_history' / 'KTB_3Y'
                self.assertIsNotNone(target.verified(folder/'page_000.json',
                                                     folder/'page_000.manifest.json'))

    def test_wrong_item_code_is_rejected(self):
        class Response:
            status_code = 200

            def iter_content(self, _size):
                yield json.dumps({'StatisticSearch': {'list_total_count': 1,
                    'row': [{'TIME': '20100104', 'DATA_VALUE': '4.0',
                             'ITEM_CODE1': 'WRONG'}]}}).encode()

        class Session:
            def get(self, *_args, **_kwargs):
                return Response()

        self.assertEqual(target.fetch(Session(), 'test', 'KTB_3Y', 0)[0],
                         'ITEM_CODE_MISMATCH')


if __name__ == '__main__':
    unittest.main()
