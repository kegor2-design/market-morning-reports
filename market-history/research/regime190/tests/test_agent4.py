import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from regime190.agent4_controller import _plan, cycle
from regime190.agent4_market import (_average_precision, _score, _signal,
                                     study, verify)
from regime190.exploratory_backtest import load_indices
from universal_agent.offline_worker import load_plan


class Agent4Tests(unittest.TestCase):
    def test_causal_features_and_missing_history(self):
        rows, source = load_indices('1996-01-01', skip_invalid_pre2010=True)
        self.assertIn('2008-01-02', {item['date'] for item in rows})
        self.assertEqual(source['KOSPI']['excluded_invalid_pre2010_dates'],
                         ['1996-06-12', '1996-08-17', '2003-10-27', '2007-03-02'])
        original = _signal(rows, 100)
        changed = list(rows)
        changed[101] = dict(rows[101], kospi=dict(rows[101]['kospi'], close=999999))
        self.assertEqual(_signal(changed, 100), original)
        with self.assertRaises(ValueError):
            _signal(rows, 59)
        with self.assertRaises(ValueError):
            load_indices('1995-01-01')
        with self.assertRaises(ValueError):
            load_indices(skip_invalid_pre2010=True)

    def test_metrics_and_false_probability_gate(self):
        self.assertEqual(_average_precision([True, False], [.9, .1]), 1.0)
        score = _score([True, False], [.8, .2], .5)
        self.assertEqual((score['tp'], score['tn']), (1, 1))
        self.assertAlmostEqual(score['brier'], .04)
        with self.assertRaises(ValueError):
            _score([True], [1.1], .5)
        valid = study()
        verify(valid)
        with self.assertRaises(ValueError):
            verify(dict(valid, official_prediction_claim=True))
        with self.assertRaises(ValueError):
            verify(dict(valid, daily_report=dict(valid['daily_report'], **{'향후 5일 상승 확률': .9})))
        with self.assertRaises(ValueError):
            verify(dict(valid, final_holdout_metrics={'accuracy': 1.0}))

    def test_worker_contract_and_recovery(self):
        repo = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'agent4'
            state.mkdir()
            plan_path = state / 'plan.json'
            plan = _plan()
            plan_path.write_text(json.dumps(plan))
            load_plan(plan_path)
            plan['tasks'][0]['required_tools'] = ['arbitrary_code']
            plan_path.write_text(json.dumps(plan))
            with self.assertRaises(ValueError):
                load_plan(plan_path)
            first = cycle(state / 'run', repo)
            self.assertEqual(first['status'], 'EXPLORATORY_COMPLETE')
            self.assertEqual(first['checkpoint_id'], 1)
            memory_path = state / 'run/research_memory.json'
            memory = json.loads(memory_path.read_text())
            result = json.loads(Path(memory['artifact_path']).read_text())['result']
            self.assertEqual(result['model_runtime'], 'DETERMINISTIC_NON_AI')
            self.assertFalse(result['official_prediction_claim'])
            self.assertEqual(result['pit']['eligible_indicator_ids'], [])
            self.assertEqual(result['split']['final_holdout'], 'CONTAMINATED_NOT_INDEPENDENT')
            self.assertLess(result['split']['validation_last'], '2022-01-01')
            self.assertGreater(result['historical_cases_descriptive']['2008_financial_crisis']['sessions'], 200)
            self.assertEqual(result['daily_report']['현재 시장 국면'], None)
            self.assertTrue(result['daily_report']['자료 지연'])
            self.assertEqual(cycle(state / 'run', repo)['status'], 'ALREADY_EVALUATED')
            with patch('regime190.agent4_controller._source_hashes', return_value={'tampered': 'x'}):
                with self.assertRaisesRegex(ValueError, 'integrity'):
                    cycle(state / 'run', repo)
            memory_path.unlink()
            self.assertEqual(cycle(state / 'run', repo)['status'], 'EXPLORATORY_COMPLETE')
            queue = json.loads((state / 'run/task_queue.json').read_text())
            self.assertEqual(queue['checkpoint_id'], 1)
            (state / 'run/STOP').write_text('stop')
            self.assertEqual(cycle(state / 'run', repo)['status'], 'STOPPED')
            (state / 'run/STOP').unlink()
            Path(memory['artifact_path']).write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                cycle(state / 'run', repo)


if __name__ == '__main__':
    unittest.main()
