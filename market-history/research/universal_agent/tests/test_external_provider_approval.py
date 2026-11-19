"""External Provider contract checks; no live request is made."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from jsonschema import ValidationError

from universal_agent.external_provider_approval import validate_contract
from universal_agent.source_adapters import REGISTRY


class ExternalProviderApprovalTests(unittest.TestCase):
    def setUp(self):
        period = {'start': '2018-06-01', 'end': '2018-06-29',
                  'resolution': 'daily'}
        uri = REGISTRY['US_TREASURY'].uri('UST_2Y', period['start'], period['end'])
        self.evidence = {'problem_type': 'API_ERROR',
            'network_call_outcome': 'DEFINITE_HTTP_ERROR', 'http_status': 503,
            'goal_id': 'research_' + 'a' * 12, 'original_task_id': 'collect_ust_2y',
            'source_id': 'US_TREASURY', 'series': 'UST_2Y',
            'requested_period': period, 'source_uri': uri,
            'original_request_sha256': 'a' * 64,
            'error_evidence_sha256': 'b' * 64}
        self.approval = {'schema_version': 1,
            'scope': 'EXTERNAL_PROVIDER_RECOVERY_APPROVAL',
            'goal_id': self.evidence['goal_id'],
            'original_task_id': self.evidence['original_task_id'],
            'provider': 'US_TREASURY', 'host': urlparse(uri).hostname,
            'endpoint': uri, 'series': 'UST_2Y', 'period': period,
            'original_request_sha256': 'a' * 64,
            'new_request_id': 'c' * 24, 'error_evidence_sha256': 'b' * 64,
            'approved_by': 'FIXTURE_POLICY_REVIEWER',
            'approved_at_utc': datetime.now(timezone.utc).isoformat(),
            'expires_at_utc': (datetime.now(timezone.utc) +
                timedelta(hours=1)).isoformat(),
            'max_additional_requests': 1, 'max_duration_seconds': 25,
            'max_cost_usd': 0, 'retry_policy': 'ONE_NEW_IDEMPOTENT_GET',
            'idempotency_policy': 'SAFE_GET_ONLY',
            'response_media_type': 'text/csv',
            'verification_rule': 'independent_source_recompute',
            'terms_reviewed': True, 'access_reviewed': True,
            'tls_verification': True, 'redirect_policy': 'DENY_ALL',
            'max_response_bytes': 2000000}

    def test_exact_registry_endpoint_is_policy_validated_without_live_authority(self):
        result = validate_contract(self.approval, self.evidence)
        self.assertEqual(result['status'], 'POLICY_VALIDATED_ONLY')
        self.assertFalse(result['live_execution_authorized'])

    def test_local_fixture_scope_and_unapproved_host_are_rejected(self):
        for key, value in [('scope', 'LOCAL_LOOPBACK_TEST'),
                           ('host', '127.0.0.1'),
                           ('endpoint', 'https://127.0.0.1/private'),
                           ('endpoint', self.approval['endpoint'] + '?redirect=1'),
                           ('redirect_policy', 'ALLOW'),
                           ('tls_verification', False)]:
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(self.approval)
                changed[key] = value
                with self.assertRaises((ValueError, ValidationError)):
                    validate_contract(changed, self.evidence)

    def test_uncertain_request_and_budget_or_evidence_change_are_rejected(self):
        changed_evidence = dict(self.evidence, network_call_outcome='UNCERTAIN_REQUEST_OUTCOME')
        with self.assertRaisesRegex(ValueError, 'definite retryable'):
            validate_contract(self.approval, changed_evidence)
        for key, value in [('max_additional_requests', 2),
                           ('max_cost_usd', 1), ('terms_reviewed', False),
                           ('error_evidence_sha256', 'd' * 64),
                           ('new_request_id', 'a' * 24),
                           ('expires_at_utc', '2020-01-01T00:00:00+00:00')]:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.approval)
                changed[key] = value
                with self.assertRaises((ValueError, ValidationError)):
                    validate_contract(changed, self.evidence)


if __name__ == '__main__':
    unittest.main()
