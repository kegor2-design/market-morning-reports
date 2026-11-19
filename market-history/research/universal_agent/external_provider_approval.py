"""Fail-closed contract validation for a future external API recovery request.

This module never makes a request. The local fixture executor deliberately does
not consume this contract until source terms and live budget are approved.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import validate

from .engine import canonical
from .source_adapters import REGISTRY

SCHEMA = Path(__file__).with_name('external_provider_approval.schema.json')


def validate_contract(approval: dict, evidence: dict) -> dict:
    import json
    validate(approval, json.loads(SCHEMA.read_text()))
    if evidence.get('problem_type') != 'API_ERROR' or \
            evidence.get('network_call_outcome') != 'DEFINITE_HTTP_ERROR' or \
            evidence.get('http_status') not in {429, 500, 502, 503, 504}:
        raise ValueError('External recovery requires a definite retryable response')
    source = REGISTRY.get(approval['provider'])
    if source is None or approval['series'] not in source.series:
        raise ValueError('External provider is not in the reviewed registry')
    expected = source.uri(approval['series'], approval['period']['start'],
                          approval['period']['end'])
    uri = urlparse(expected)
    approved_uri = urlparse(approval['endpoint'])
    if (approval['endpoint'] != expected or uri.scheme != 'https' or
            approved_uri.hostname != approval['host'] or
            approved_uri.username or approved_uri.password or
            approved_uri.fragment or approved_uri.port not in (None, 443) or
            approval['redirect_policy'] != 'DENY_ALL' or
            approval['tls_verification'] is not True):
        raise ValueError('External endpoint or transport policy changed')
    issued = datetime.fromisoformat(approval['approved_at_utc'].replace('Z', '+00:00'))
    expiry = datetime.fromisoformat(approval['expires_at_utc'].replace('Z', '+00:00'))
    if (issued.tzinfo is None or expiry.tzinfo is None or
            issued > datetime.now(timezone.utc) or
            expiry <= issued or expiry <= datetime.now(timezone.utc)):
        raise ValueError('External approval expired')
    matching = {'goal_id': 'goal_id', 'original_task_id': 'original_task_id',
        'provider': 'source_id', 'series': 'series',
        'original_request_sha256': 'original_request_sha256',
        'error_evidence_sha256': 'error_evidence_sha256'}
    if any(approval[approved_key] != evidence.get(evidence_key)
           for approved_key, evidence_key in matching.items()) or \
            approval['period'] != evidence.get('requested_period') or \
            approval['endpoint'] != evidence.get('source_uri') or \
            approval['new_request_id'] == approval['original_request_sha256'][:24] or \
            approval['error_evidence_sha256'] != evidence.get('error_evidence_sha256'):
        raise ValueError('External approval does not match original evidence')
    if approval['max_additional_requests'] != 1 or \
            approval['max_duration_seconds'] > 25 or \
            approval['max_cost_usd'] != 0 or \
            approval['retry_policy'] != 'ONE_NEW_IDEMPOTENT_GET' or \
            approval['idempotency_policy'] != 'SAFE_GET_ONLY' or \
            approval['response_media_type'] != source.media_type or \
            approval['verification_rule'] != 'independent_source_recompute' or \
            approval['terms_reviewed'] is not True or \
            approval['access_reviewed'] is not True:
        raise ValueError('External provider budget or access is not approved')
    return {'status': 'POLICY_VALIDATED_ONLY',
        'contract_sha256': hashlib.sha256(canonical(approval)).hexdigest(),
        'provider': source.source_id, 'endpoint': expected,
        'live_execution_authorized': False}
