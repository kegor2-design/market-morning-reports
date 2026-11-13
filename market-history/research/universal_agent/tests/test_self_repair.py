import json
import csv
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent import autonomous
from universal_agent import self_repair
from universal_agent.self_repair import (Failure, classify, diagnose, probe_secure_runner,
                                         repair_research_source, run_stage)


class SelfRepairTests(unittest.TestCase):
    def test_contextual_fault_classification_and_redaction(self):
        cases = [
            ('API', 'HTTP_429', 'too many requests', 'API_RATE_LIMIT'),
            ('API', 'HTTP_400', 'bad request', 'API_REQUEST_ERROR'),
            ('API', 'HTTP_404', 'not found', 'API_NOT_FOUND'),
            ('GIT_PUSH', '', 'could not resolve host github.com', 'DNS_ERROR'),
            ('GIT_PUSH', 'HTTP_403', 'Authorization: secret123', 'AUTH_ERROR'),
            ('DB_SCHEMA', '', 'column x does not exist', 'SCHEMA_MISMATCH'),
            ('SECURE_RUNNER', '', 'bwrap: Operation not permitted', 'SANDBOX_ERROR'),
            ('BACKTEST', '', 'SyntaxError: invalid syntax', 'CODE_ERROR'),
            ('BACKTEST', '', 'ModuleNotFoundError: no module named missing', 'DEPENDENCY_ERROR'),
            ('BACKTEST_CODE', 'OUTPUT_CONTRACT_ERROR', 'bad probability', 'OUTPUT_CONTRACT_ERROR'),
            ('BACKTEST_CODE', 'TIMEOUT', 'time budget exceeded', 'TIMEOUT'),
        ]
        for stage, code, message, expected in cases:
            with self.subTest(stage=stage, code=code):
                self.assertEqual(classify(stage, message, code), expected)
        record = Failure('r1', 'GIT_PUSH', 'HTTP_403',
                         'Authorization: secret123', 'token=abc').record()
        self.assertNotIn('secret123', json.dumps(record))
        self.assertNotIn('abc', json.dumps(record))
        self.assertNotIn('Bearer live123', self_repair.redact('Authorization: Bearer live123'))

    def test_alternative_plan_and_bounded_repeats(self):
        failure = Failure('r1', 'API', 'HTTP_429', 'rate limited', 'FRED')
        first = diagnose(failure)
        self.assertEqual(first['next_action'], 'RETRY_WITH_BACKOFF')
        first['action'] = 'RETRY_WITH_BACKOFF'
        second = diagnose(failure, [first])
        self.assertEqual(second['next_action'], 'SAFE_BLOCKED')
        self.assertEqual(diagnose(Failure('r1', 'BACKTEST_CODE', 'TIMEOUT',
                                          'time budget exceeded', 'fold1'))['next_action'],
                         'SAFE_BLOCKED')

    def test_api_429_retries_once_then_recovers(self):
        attempts = []
        waits = []
        history = []
        def request():
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError('HTTP 429 rate limit')
            return {'rows': 1}
        result = run_stage('r1', 'DATA_ACQUISITION', 'FRED', request, history,
                           sleep=waits.append)
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(waits, [1])
        self.assertEqual(history[0]['error_type'], 'API_RATE_LIMIT')

    def test_repair_rolls_back_failed_candidate_then_accepts_alternative(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'market-history/research/test_project'
            root.mkdir(parents=True)
            source = root / 'experiment.py'
            source.write_text('value = 0\n')
            candidates = ['value = 1\n', 'value = 2\n']
            with (patch.object(self_repair, 'RESEARCH_ROOT', root),
                  patch.object(self_repair, 'probe_secure_runner',
                               return_value={'status': 'SECURE_RUNNER_VERIFIED'}),
                  patch('regime190.agent43_engine._isolated_python',
                        return_value={'exit_code': 0})):
                result = repair_research_source(source, candidates, root,
                    lambda path, _: path.read_text() == 'value = 2\n',
                    static_check=lambda _: None)
            self.assertEqual(result['status'], 'REPAIRED')
            self.assertEqual([x['status'] for x in result['attempts']],
                             ['ROLLED_BACK', 'VERIFIED'])
            self.assertEqual(source.read_text(), 'value = 2\n')
            blocked = repair_research_source(source, ['value = 3\n'], root,
                                             lambda *_: True)
            self.assertEqual(blocked['status'], 'SAFE_BLOCKED')
            self.assertEqual(source.read_text(), 'value = 2\n')

    def test_generated_script_repair_in_real_bubblewrap(self):
        probe = probe_secure_runner()
        if probe['status'] != 'SECURE_RUNNER_VERIFIED':
            self.skipTest('OS sandbox unavailable in this test process')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'market-history/research/test_project'
            root.mkdir(parents=True)
            source = root / 'experiment.py'
            source.write_text('raise RuntimeError("broken generated research")\n')
            candidate = ('import json\n'
                         'result = {"answer": %d, "method": "isolated fixture"}\n'
                         'with open("result.json", "w", encoding="utf-8") as stream:\n'
                         '    json.dump(result, stream)\n')
            def verify(path, output):
                return output['exit_code'] == 0 and json.loads(
                    (path.parent / 'result.json').read_text())['answer'] == 42
            with patch.object(self_repair, 'RESEARCH_ROOT', root):
                result = repair_research_source(source, [candidate % 0, candidate % 42],
                    root, verify)
            self.assertEqual(result['status'], 'REPAIRED')
            self.assertEqual([a['status'] for a in result['attempts']],
                             ['ROLLED_BACK', 'VERIFIED'])
            self.assertIn('"answer": 42', source.read_text())

    def test_failed_isolated_candidate_restores_original_source(self):
        probe = probe_secure_runner()
        if probe['status'] != 'SECURE_RUNNER_VERIFIED':
            self.skipTest('OS sandbox unavailable in this test process')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'market-history/research/test_project'
            root.mkdir(parents=True)
            source = root / 'experiment.py'
            original = ('import json\nresult = {"answer": 42}\n'
                        'with open("result.json", "w", encoding="utf-8") as stream:\n'
                        '    json.dump(result, stream)\n')
            source.write_text(original)
            bad = original.replace('"answer": 42', '"answer": 0')
            def verify(path, output):
                return output['exit_code'] == 0 and json.loads(
                    (path.parent / 'result.json').read_text())['answer'] == 42
            with patch.object(self_repair, 'RESEARCH_ROOT', root):
                result = repair_research_source(source, [bad], root, verify)
            self.assertEqual(result['status'], 'SAFE_BLOCKED')
            self.assertEqual(result['attempts'][0]['status'], 'ROLLED_BACK')
            self.assertEqual(source.read_text(), original)
            self.assertFalse((root / 'result.json').exists())

    def test_interrupted_repair_restores_original_on_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'market-history/research/test_project'
            root.mkdir(parents=True)
            source = root / 'experiment.py'
            source.write_text('value = 0\n')
            def interrupt(*_):
                raise KeyboardInterrupt()
            with (patch.object(self_repair, 'RESEARCH_ROOT', root),
                  patch.object(self_repair, 'probe_secure_runner',
                               return_value={'status': 'SECURE_RUNNER_VERIFIED'}),
                  patch('regime190.agent43_engine._isolated_python',
                        return_value={'exit_code': 0})):
                with self.assertRaises(KeyboardInterrupt):
                    repair_research_source(source, ['value = 1\n'], root, interrupt,
                                           static_check=lambda _: None)
                self.assertTrue((root / '.experiment.py.repair-backup').exists())
                resumed = repair_research_source(source, [], root, lambda *_: True,
                                                 static_check=lambda _: None)
            self.assertEqual(resumed['status'], 'SAFE_BLOCKED')
            self.assertTrue(resumed['recovered_interruption'])
            self.assertEqual(source.read_text(), 'value = 0\n')

    def test_candidate_cannot_pass_with_previous_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'market-history/research/test_project'
            root.mkdir(parents=True)
            source = root / 'experiment.py'
            source.write_text('value = 0\n')
            output = root / 'result.json'
            output.write_text('{"previous": true}')
            calls = []
            def execute(_):
                calls.append(1)
                if len(calls) == 1:
                    output.write_text('{"candidate": 1}')
                return {'exit_code': 0}
            with (patch.object(self_repair, 'RESEARCH_ROOT', root),
                  patch.object(self_repair, 'probe_secure_runner',
                               return_value={'status': 'SECURE_RUNNER_VERIFIED'}),
                  patch('regime190.agent43_engine._isolated_python', side_effect=execute)):
                result = repair_research_source(source, ['value = 1\n', 'value = 2\n'],
                    root, lambda path, _: len(calls) == 2 and output.exists(),
                    static_check=lambda _: None)
            self.assertEqual(result['status'], 'SAFE_BLOCKED')
            self.assertEqual([item['status'] for item in result['attempts']],
                             ['ROLLED_BACK', 'ROLLED_BACK'])
            self.assertEqual(len(calls), 2)
            self.assertEqual(json.loads(output.read_text()), {'previous': True})

    def test_plugin_failure_is_checkpointed_and_other_work_continues(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = root / 'prices.csv'
            state_dir = root / 'state'
            day = date(2002, 1, 1)
            with snapshot.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(('date', 'open', 'high', 'low', 'close', 'volume'))
                for i in range(4500):
                    while day.weekday() >= 5:
                        day += timedelta(days=1)
                    close = 100 + i * .03 + 3 * (i % 35) / 35
                    writer.writerow((day.isoformat(), close, close+1, close-1,
                                     close, 1000 + i % 100))
                    day += timedelta(days=1)
            goal = autonomous.ResearchGoal('Study market, charts, and strategy', 'fault-fixture')
            class Broken:
                def evaluate(self, *_):
                    raise SyntaxError('SyntaxError: invalid syntax')
            with patch.dict(autonomous.PLUGINS, {'MARKET_REGIME': Broken()}):
                result = autonomous.run(goal, snapshot, state_dir)
            self.assertEqual(result['cycles']['MARKET_REGIME'], 'FAILED')
            self.assertEqual(result['cycles']['CHART_PATTERN'], 'COMPLETED')
            saved = json.loads((state_dir / 'autonomous_state.json').read_text())
            self.assertEqual(saved['repair_history'][0]['error_type'], 'CODE_ERROR')
            self.assertEqual(autonomous.run(goal, snapshot, state_dir)['processed_this_run'], 0)


if __name__ == '__main__':
    unittest.main()
