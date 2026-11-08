import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190 import agent43_engine as engine


class Agent43Tests(unittest.TestCase):
    def test_secure_runner_mounts_inputs_read_only_and_classifies_cpu_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'experiment.py').write_text('print(1)\n')
            (work / 'data.csv').write_text('date\n2020-01-01\n')
            with patch.object(engine.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout='', stderr='')) as invoke:
                result = engine._isolated_python(work)
            self.assertEqual(result['exit_code'], 0)
            command = invoke.call_args.args[0]
            self.assertIn(['--ro-bind', str(work / 'data.csv'), '/work/data.csv'],
                          [command[i:i+3] for i in range(len(command)-2)])
            self.assertIn(['--ro-bind', str(work / 'experiment.py'), '/work/experiment.py'],
                          [command[i:i+3] for i in range(len(command)-2)])
            self.assertTrue(any('RLIMIT_NPROC' in item for item in command))
            with patch.object(engine.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=128 + engine.signal.SIGXCPU, stdout='', stderr='')):
                timeout = engine._isolated_python(work)
            self.assertEqual(timeout['error'], 'EXEC_TIMEOUT')

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
