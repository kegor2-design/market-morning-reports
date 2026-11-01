import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190 import agent43_engine as engine


class Agent43Tests(unittest.TestCase):
    def test_pit_ranking_covers_all_and_remains_blocked(self):
        ranking = engine._rank_pit()
        self.assertEqual(len(ranking), 190)
        self.assertEqual({row['indicator_id'] for row in ranking}, set(range(1, 191)))
        self.assertEqual(ranking[0]['indicator_id'], 2)
        self.assertNotIn('PIT_VERIFIED', {row['pit_status'] for row in ranking})

    def test_generated_code_gate_rejects_escape(self):
        engine._check_code('import csv\n' + 'x = 1\n' * 50)
        engine._check_code('from collections import defaultdict\n' + 'x = 1\n' * 50)
        for source in ('import os\n' + 'x = 1\n' * 50,
                       'from os import system\n' + 'x = 1\n' * 50,
                       "eval('1+1')\n" + 'x = 1\n' * 50,
                       'import csv\nprint(csv.__dict__)\n' + 'x = 1\n' * 50):
            with self.assertRaises(ValueError):
                engine._check_code(source)

    def test_preparation_seals_validation_labels_and_stops(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            self.assertEqual(engine.prepare(state)['status'], 'PREPARED')
            queue = json.loads((state / engine.QUEUE).read_text())
            self.assertEqual(queue['order'], list(engine.TASKS))
            fold = state / 'tasks/FORECAST-CRASH20/fold1/data.csv'
            with fold.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(all(row['target'] == '' for row in rows
                                if row['split'] == 'validation'))
            self.assertTrue(all(row['target'] in {'0', '1'} for row in rows
                                if row['split'] == 'train'))
            self.assertTrue((state / 'sealed/FORECAST-CRASH20_fold1.json').exists())
            (state / 'STOP').write_text('stop')
            self.assertEqual(engine.run(state)['status'], 'STOPPED')
            fold.write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                engine.prepare(state)


if __name__ == '__main__':
    unittest.main()
