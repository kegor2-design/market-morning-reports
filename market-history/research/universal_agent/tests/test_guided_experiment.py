import hashlib
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent import guided_experiment
from universal_agent.isolated_codex import validate_plan_for_agent43
from regime190.agent43_engine import _prompt


class GuidedExperimentTests(unittest.TestCase):
    def test_verified_plan_is_passed_into_agent43_brief(self):
        plan = {'method': 'frequency model', 'chronological_splits': ['fold1', 'fold2']}
        brief = guided_experiment._brief({'hypothesis': 'h'},
                                         {'target': 'crash', 'horizon': 20}, plan)
        self.assertEqual(brief['research_plan'], plan)
        self.assertIn('frequency model', _prompt(brief))

    def test_plan_adapter_rejects_incompatible_method_and_folds(self):
        plan = {'chronological_splits': ['2005-2011 train / 2012-2014 validation, 20-session embargo',
                                        '2005-2014 train / 2015-2017 validation, 20-session embargo'],
                'method': 'A standard-library binned frequency model'}
        validate_plan_for_agent43(plan)
        with self.assertRaisesRegex(ValueError, 'method'):
            validate_plan_for_agent43(plan | {'method': 'Logistic regression'})
        with self.assertRaisesRegex(ValueError, 'folds'):
            validate_plan_for_agent43(plan | {'chronological_splits': ['50% train', '50% validation']})

    def test_prediction_contract_rejects_misaligned_or_invalid_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            data = folder / 'data.csv'
            fields = ['date', 'split', 'target', 'momentum5', 'momentum20',
                      'volatility20', 'drawdown60', 'relative_kosdaq20']
            with data.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow(dict.fromkeys(fields, '0') |
                                {'date': '2020-01-01', 'split': 'train', 'target': '0'})
                writer.writerow(dict.fromkeys(fields, '0') |
                                {'date': '2020-01-02', 'split': 'validation', 'target': ''})
            digest = hashlib.sha256(data.read_bytes()).hexdigest()
            output = folder / 'predictions.csv'
            output.write_text('date,probability\n2020-01-02,0.2\n')
            self.assertEqual(guided_experiment.validate_fold_output(folder, digest)['rows'], 1)
            output.write_text('date,probability\n2020-01-03,0.2\n')
            with self.assertRaisesRegex(ValueError, 'dates'):
                guided_experiment.validate_fold_output(folder, digest)
            output.write_text('date,probability\n2020-01-02,nan\n')
            with self.assertRaisesRegex(ValueError, 'finite'):
                guided_experiment.validate_fold_output(folder, digest)
            output.write_text('date,score\n2020-01-02,0.2\n')
            with self.assertRaisesRegex(ValueError, 'column'):
                guided_experiment.validate_fold_output(folder, digest)

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
            saved = json.loads((root / 'run' / 'guided_state.json').read_text())
            self.assertEqual(saved['data_status'], 'DATA_ACQUISITION_REQUIRED')
            self.assertTrue(saved['next_action']['independent_research_can_continue'])


if __name__ == '__main__':
    unittest.main()
