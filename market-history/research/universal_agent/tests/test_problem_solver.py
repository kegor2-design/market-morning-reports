import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from universal_agent.problem_solver import _rank, _execute
from universal_agent.self_repair import Failure, diagnose


class NewProblemBoundaryTests(unittest.TestCase):
    def test_distinct_code_failures_do_not_exhaust_each_others_retry_budget(self):
        first = diagnose(Failure('one', 'BACKTEST_CODE', 'CODE_ERROR',
                                 'AttributeError: missing_method', 'fold1'))
        second = diagnose(Failure('two', 'BACKTEST_CODE', 'CODE_ERROR',
                                  'ZeroDivisionError: division by zero', 'fold1'), [first])
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual(second['repeat_count'], 0)
        self.assertEqual(second['next_action'], 'REPAIR_RESEARCH_CODE')

    def test_unseen_faults_are_classified_without_automatic_unsafe_repair(self):
        cases = [
            ('DATA_INPUT', 'KeyError', "'renamed_price'", 'DATA_CONTRACT_ERROR'),
            ('API_RESPONSE', 'JSONDecodeError', 'response is now an array', 'API_REQUEST_ERROR'),
            ('DATA_INPUT', 'FileNotFoundError', 'missing data segment', 'DATA_GAP'),
            ('WORKER', 'SIGKILL', 'worker exited -9', 'PROCESS_CRASH'),
            ('IMPORT', 'RuntimeError', 'dependency version mismatch', 'DEPENDENCY_ERROR'),
            ('BACKTEST', 'ValueError', 'hypothesis rejected on validation', 'HYPOTHESIS_FAILURE'),
            ('RESULT_EVALUATION', 'ValueError', 'insufficient independent events', 'STATISTICAL_INSUFFICIENCY'),
            ('SECURE_RUNNER', 'PermissionError', 'sandbox denied namespace', 'SANDBOX_ERROR'),
        ]
        for stage, code, message, expected in cases:
            with self.subTest(stage=stage, code=code):
                result = diagnose(Failure('blind_case', stage, code, message, 'sealed'))
                self.assertEqual(result['error_type'], expected)
                self.assertNotEqual(result['next_action'], 'DISABLE_SANDBOX')

    def test_model_cannot_rank_unsafe_action_into_execution(self):
        proposal = {'action': 'CHANGE_DB_SCHEMA', 'reason': 'claimed shortcut',
                    'resolution_likelihood': 5, 'evidence_reliability': 5,
                    'cost': 0, 'time': 0, 'security_risk': 0,
                    'regression_risk': 0, 'rollback_ease': 5}
        result = _rank(proposal)
        self.assertFalse(result['authorized'])
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            _execute('CHANGE_DB_SCHEMA', Path('/tmp'), 'blind problem', 'blind', {})

    def test_unrelated_pit_indicator_cannot_validate_index_goal(self):
        with patch('regime190.exploratory_backtest.pit_eligibility',
                   return_value={'eligible_indicator_ids': [116]}):
            result = _execute('VERIFY_PIT_LOCAL', Path('/tmp'), 'index risk', 'blind',
                              {'index_snapshot_provenance': {'KOSPI': {'pit_status': 'PIT_UNVERIFIED'},
                                                             'KOSDAQ': {'pit_status': 'PIT_UNVERIFIED'}},
                               'independent_holdout': 'NOT_AVAILABLE'})
        self.assertEqual(result['status'], 'PIT_BLOCKED')
        self.assertFalse(result['official_claim'])


if __name__ == '__main__':
    unittest.main()
