import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent import guided_experiment
from regime190.agent43_engine import _prompt


class GuidedExperimentTests(unittest.TestCase):
    def test_agent43_prompt_preserves_external_ai_hypothesis(self):
        brief = {'task_id': 'FORECAST-CRASH20',
                 'staged': {'target': 'crash', 'horizon': 20},
                 'input_hypothesis': {'hypothesis': 'Use momentum and drawdown for crash risk'}}
        prompt = _prompt(brief)
        self.assertIn('Implement the supplied AI hypothesis', prompt)
        self.assertIn('Use momentum and drawdown for crash risk', prompt)
        self.assertNotIn('Generate a genuinely new', prompt)

    def test_ai_checkpoint_hash_is_required(self):
        value = {'hypothesis': 'A 20-session crash can be predicted by lagged index features',
                 'economic_reason': 'Joint index weakness signals broad market fragility',
                 'required_data': ['KOSPI closes'], 'target': '20-session crash',
                 'horizon_sessions': 20,
                 'validation_method': 'Chronological walk-forward with a sealed validation label',
                 'rejection_condition': 'No lift versus the frozen baseline',
                 'metrics': ['PR-AUC']}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ai = root / 'run'
            ai.mkdir()
            response = ai / 'ai_response.json'
            response.write_text(json.dumps(value))
            (ai / 'ai_request.json').write_text(json.dumps({
                'status': 'VERIFIED', 'response_sha256': hashlib.sha256(response.read_bytes()).hexdigest()}))
            with patch.object(guided_experiment, 'AI_ROOT', root):
                self.assertEqual(guided_experiment._load_ai(ai)[0], value)
                response.write_text(response.read_text() + '\n')
                with self.assertRaisesRegex(ValueError, 'not verified'):
                    guided_experiment._load_ai(ai)

    def test_unsupported_ai_data_blocks_before_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hypothesis = {'horizon_sessions': 20,
                          'required_data': ['KOSPI closes', 'foreign flows']}
            with (patch.object(guided_experiment, 'PRIVATE_ROOT', root),
                  patch.object(guided_experiment, '_load_ai', return_value=(hypothesis, 'hash')),
                  patch.object(guided_experiment, '_stage') as stage):
                result = guided_experiment.run(root / 'run', root / 'run')
            self.assertEqual(result['status'], 'DATA_ACQUISITION_REQUIRED')
            stage.assert_not_called()
            self.assertFalse((root / 'run').exists())


if __name__ == '__main__':
    unittest.main()
