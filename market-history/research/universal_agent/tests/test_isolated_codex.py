import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent import isolated_codex


class IsolatedCodexTests(unittest.TestCase):
    def test_one_call_is_recovered_without_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'private/run'
            state.mkdir(parents=True)
            value = {'hypothesis': 'KOSDAQ weakness precedes broad market crashes',
                     'economic_reason': 'Risk appetite weakens first in smaller shares',
                     'required_data': ['KOSPI closes', 'KOSDAQ closes'],
                     'target': '20-session crash', 'horizon_sessions': 20,
                     'validation_method': 'Chronological folds with point-in-time checks',
                     'rejection_condition': 'No lift over unconditional rate',
                     'metrics': ['Precision', 'Recall']}
            calls = []
            def invoke(command, **_):
                calls.append(command)
                (state / 'ai_response.json').write_text(json.dumps(value))
                return SimpleNamespace(returncode=0, stderr='model: fixture-model\n', stdout='')
            fake = Path(temp) / 'codex'
            with (patch.object(isolated_codex, '_inputs', return_value=(state, fake, fake, fake, fake)),
                  patch.object(isolated_codex, 'probe_secure_runner',
                               return_value={'status': 'SECURE_RUNNER_VERIFIED'}),
                  patch.object(isolated_codex.shutil, 'which', return_value='/usr/bin/bwrap'),
                  patch.object(isolated_codex.subprocess, 'run', side_effect=invoke)):
                first = isolated_codex.generate('Study crash risk', state)
                second = isolated_codex.generate('Study crash risk', state)
            self.assertEqual(first['status'], 'REAL_AI_VERIFIED')
            self.assertEqual(first['model'], 'fixture-model')
            self.assertTrue(second['recovered_existing_output'])
            self.assertEqual(len(calls), 1)
            self.assertIn('--sandbox', calls[0])
            self.assertIn('read-only', calls[0])
            self.assertIn('--ro-bind', calls[0])

    def test_uncertain_prior_call_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'private/run'
            state.mkdir(parents=True)
            goal = 'Study crash risk'
            prompt = isolated_codex.prompt_for(goal)
            request = {'prompt_sha256': isolated_codex.hashlib.sha256(prompt.encode()).hexdigest(),
                       'schema_sha256': isolated_codex.hashlib.sha256(
                           isolated_codex.SCHEMA.read_bytes()).hexdigest(),
                       'called_at_utc': '2026-11-07T00:00:00+00:00'}
            (state / 'ai_request.json').write_text(json.dumps(request))
            fake = Path(temp) / 'codex'
            with patch.object(isolated_codex, '_inputs', return_value=(state, fake, fake, fake, fake)):
                result = isolated_codex.generate(goal, state)
            self.assertEqual(result['status'], 'ENVIRONMENT_BLOCKED')
            self.assertEqual(result['codex_calls'], 1)

    def test_failed_isolation_does_not_consume_ai_call(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'private/run'
            state.mkdir(parents=True)
            fake = Path(temp) / 'codex'
            with (patch.object(isolated_codex, '_inputs', return_value=(state, fake, fake, fake, fake)),
                  patch.object(isolated_codex, 'probe_secure_runner',
                               return_value={'status': 'SECURE_RUNNER_UNAVAILABLE',
                                             'reason': 'namespace denied'}),
                  patch.object(isolated_codex.subprocess, 'run') as invoke):
                result = isolated_codex.generate('Study crash risk', state)
            self.assertEqual(result['status'], 'SECURE_RUNNER_UNAVAILABLE')
            self.assertEqual(result['codex_calls'], 0)
            self.assertFalse((state / 'ai_request.json').exists())
            invoke.assert_not_called()


if __name__ == '__main__':
    unittest.main()
