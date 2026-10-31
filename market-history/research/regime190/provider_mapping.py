"""Map verified provider access to all 190 blockers without promoting PIT."""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from .blocker_resolution import (CORPORATE_ACTION_FAMILIES,
                                 SECURITY_UNIVERSE_FAMILIES, inventory)
from .worker import FRED


def build_mapping(presence: dict, probes: dict, fred_results: list[dict]) -> dict:
    baseline = inventory()
    access = {
        'KIS': 'NOT_TESTED_TOKEN_STATE_PROTECTED' if presence['KIS']['credential_present'] else 'NO_CREDENTIAL',
        'KRX': 'NOT_TESTED_LOGIN_STATE_PROTECTED' if presence['KRX']['credential_present'] else 'NO_CREDENTIAL',
        'BOK_ECOS': probes['BOK_ECOS']['auth_result'],
        'KOSIS': 'NOT_TESTED' if presence['KOSIS']['credential_present'] else 'NO_CREDENTIAL',
        'FRED': 'SUCCESS' if any(item.get('auth_result') == 'SUCCESS' for item in fred_results)
                else fred_results[0].get('auth_result', 'NOT_TESTED') if fred_results else 'NOT_TESTED',
        'DART': probes['DART']['auth_result'],
    }
    records = []
    for item in baseline['records']:
        key = item['indicator_id']
        family = item['existing_data']['family']
        candidates = []
        if key in FRED:
            candidates.append('FRED')
        if family in {'금리·신용 별도 원천', '실물·경제통계 별도 원천'}:
            candidates.append('BOK_ECOS')
        if family in {'기업 공식공시+추정', '텍스트·원문 별도'}:
            candidates.append('DART')
        if family in SECURITY_UNIVERSE_FAMILIES or family == '가격 파생':
            candidates.extend(('KRX', 'KIS'))
        candidates = list(dict.fromkeys(candidates))
        license_status = {name: ('PUBLIC_DOMAIN_SAMPLE_PRIVATE_ONLY' if name == 'FRED' and key == 116
                                 else 'LICENSE_REVIEW_REQUIRED') for name in candidates}
        gaps = item['missing_evidence']
        next_class = ('SERVER_EXECUTABLE' if item['execution_class'] == 'SERVER_EXECUTABLE'
                      else 'HUMAN_APPROVAL_REQUIRED' if candidates and all(
                          license_status[name] == 'LICENSE_REVIEW_REQUIRED' for name in candidates)
                      else 'CODEX_REQUIRED')
        if key == 116:
            next_task = 'Verify official H.15 release hour and decision-time availability'
            next_class = 'CODEX_REQUIRED'
        else:
            next_task = item['possible_resolution']
        fingerprint = hashlib.sha256(json.dumps({
            'source_sha256': baseline['source_sha256'], 'indicator_id': key,
            'candidate_access': {name: access[name] for name in candidates},
            'gaps': gaps}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        records.append({'indicator_id': key, 'name': item['name'],
                        'required_source_fields': item['required_fields'],
                        'available_local_fields': item['existing_data'],
                        'existing_source': item['existing_data']['source'],
                        'missing_source': 'MISSING_SOURCE' in gaps,
                        'missing_timestamp_evidence': 'MISSING_TIMESTAMP' in gaps,
                        'historical_universe_required': family in SECURITY_UNIVERSE_FAMILIES,
                        'corporate_action_required': family in CORPORATE_ACTION_FAMILIES,
                        'revision_history_required': 'MISSING_REVISION_HISTORY' in gaps,
                        'candidate_providers': candidates,
                        'provider_access_status': {name: access[name] for name in candidates},
                        'licensing_status': license_status,
                        'pit_validation_requirements': item['validation_requirements'],
                        'next_task_class': next_class, 'next_task': next_task,
                        'dependency_ids': ['credential_presence', 'provider_auth_check',
                                           'fred_dgs10_sample', 'fred_dgs2_sample'],
                        'evidence_fingerprint': fingerprint,
                        'prior_pit_classification': item['prior_pit_classification']})
    return {'indicator_count': len(records), 'records': records,
            'access_results': access, 'root_cause_counts': baseline['root_cause_counts'],
            'next_class_counts': dict(Counter(row['next_task_class'] for row in records)),
            'pit_approvals_added': 0}
