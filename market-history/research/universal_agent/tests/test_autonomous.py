import csv
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.autonomous import ResearchGoal, _transition, run


class AutonomousTests(unittest.TestCase):
    def _snapshot(self, path):
        day = date(2002, 1, 1)
        with path.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(('date', 'open', 'high', 'low', 'close', 'volume'))
            for i in range(4500):
                while day.weekday() >= 5:
                    day += timedelta(days=1)
                close = 100 + i * .03 + 3 * (i % 35) / 35
                writer.writerow((day.isoformat(), close, close+1, close-1, close,
                                 1000 + i % 100))
                day += timedelta(days=1)

    def test_three_domains_resume_and_hash_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = root / 'prices.csv'
            state_dir = root / 'state'
            self._snapshot(snapshot)
            goal = ResearchGoal('Study market, charts, and strategy', 'synthetic-fixture')
            first = run(goal, snapshot, state_dir)
            self.assertEqual(first['processed_this_run'], 3)
            self.assertFalse(first['official_claim'])
            stored = json.loads((state_dir / 'autonomous_state.json').read_text())
            self.assertEqual(len({r['research_id'] for r in stored['cycles'].values()}), 3)
            self.assertTrue(all(r['validation_status'] == 'EXPLORATORY_ONLY'
                                for r in stored['cycles'].values()))
            self.assertEqual(run(goal, snapshot, state_dir)['processed_this_run'], 0)
            self.assertEqual(first['checkpoint_id'], run(goal, snapshot, state_dir)['checkpoint_id'])
            snapshot.write_text(snapshot.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'changed'):
                run(goal, snapshot, state_dir)

    def test_stop_and_invalid_transition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = root / 'prices.csv'
            state_dir = root / 'state'
            self._snapshot(snapshot)
            state_dir.mkdir()
            (state_dir / 'STOP').write_text('stop')
            result = run(ResearchGoal('Goal', 'g1'), snapshot, state_dir)
            self.assertEqual(result['status'], 'STOPPED')
            state = json.loads((state_dir / 'autonomous_state.json').read_text())
            with self.assertRaisesRegex(ValueError, 'Invalid transition'):
                _transition(state, 'MARKET_REGIME', 'VALIDATING')


if __name__ == '__main__':
    unittest.main()
