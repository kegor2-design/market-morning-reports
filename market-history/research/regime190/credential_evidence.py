"""Safe credential presence audit and bounded FRED PIT evidence sample.

Only credential presence and sanitized provider results may leave this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from .worker import env_keys

ENV = Path.home() / 'mydream2000.env'
MMP_ENV = Path.home() / 'MarketMorningPublisher/.env'
FRED_SERIES = {'DGS10', 'DGS2'}
FRED_URL = 'https://api.stlouisfed.org/fred/series/observations'
FRED_META = 'https://api.stlouisfed.org/fred/series'
MAX_BYTES = 1_000_000


def credential_presence() -> dict:
    primary, mmp = env_keys(ENV), env_keys(MMP_ENV)
    return {
        'KIS': {'config_present': 'KIS_APP_KEY' in primary and 'KIS_APP_SECRET' in primary,
                'credential_present': bool(primary.get('KIS_APP_KEY') and primary.get('KIS_APP_SECRET'))},
        'KRX': {'config_present': 'KRX_ID' in mmp and 'KRX_PW' in mmp,
                'credential_present': bool(mmp.get('KRX_ID') and mmp.get('KRX_PW'))},
        'BOK_ECOS': {'config_present': 'BOK_ECOS_API_KEY' in primary,
                     'credential_present': bool(primary.get('BOK_ECOS_API_KEY'))},
        'KOSIS': {'config_present': 'KOSIS_API_KEY' in primary,
                  'credential_present': bool(primary.get('KOSIS_API_KEY'))},
        'FRED': {'config_present': 'FRED_API_KEY' in primary,
                 'credential_present': bool(primary.get('FRED_API_KEY'))},
        'DART': {'config_present': 'DART_API_KEY' in primary or 'OPENDART_API_KEY' in primary,
                 'credential_present': bool(primary.get('DART_API_KEY') or primary.get('OPENDART_API_KEY'))},
    }


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_bytes(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        raise FileExistsError('Evidence path already exists')
    temporary = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(data).hexdigest()


def _get(session: requests.Session, url: str, params: dict, key: str) -> tuple[int | None, bytes | None, str | None]:
    """Return status and bounded body. Never propagate a URL bearing the API key."""
    try:
        with session.get(url, params=params, timeout=(5, 15), stream=True) as response:
            status = response.status_code
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    return status, None, 'RESPONSE_TOO_LARGE'
                chunks.append(chunk)
            data = b''.join(chunks)
            if key.encode() in data:
                return status, None, 'SECRET_REFLECTED'
            return status, data, None
    except requests.RequestException as exc:
        return None, None, type(exc).__name__


def collect_fred_dgs10(state_dir: Path, env_path: Path = ENV, series_id: str = 'DGS10') -> dict:
    """At most three requests; no token generation or production state mutation."""
    if series_id not in FRED_SERIES:
        raise ValueError('Series not allowlisted')
    key = env_keys(env_path).get('FRED_API_KEY')
    run_id = uuid.uuid4().hex
    result = {'run_id': run_id, 'provider': 'FRED', 'series_id': series_id,
              'endpoint_id': 'fred/series + fred/series/observations',
              'source_url': 'https://fred.stlouisfed.org/series/' + series_id,
              'retrieved_at_utc': _utc(), 'auth_tested': False,
              'auth_result': 'NO_CREDENTIAL' if not key else 'NOT_TESTED',
              'license_status': 'PUBLIC_DOMAIN_CITATION_REQUESTED; PRIVATE_RESEARCH_ONLY',
              'requests': 0, 'data_acquired': False, 'pit_status': 'PIT_BLOCKED',
              'pit_reason': 'Historical publication hour and complete two-series indicator unverified'}
    if not key:
        return result
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    session = requests.Session()
    session.trust_env = False
    session.headers['User-Agent'] = 'Regime190PrivateResearch/1.0'
    base = {'api_key': key, 'file_type': 'json', 'series_id': series_id}
    status, body, error = _get(session, FRED_META, base, key)
    result['requests'] += 1
    result['metadata_http_status'] = status
    if error or status != 200 or body is None:
        result['auth_result'] = ('NETWORK_ERROR' if status is None else
                                 'RATE_LIMITED' if status == 429 else
                                 'INVALID_CREDENTIAL' if status in (400, 401, 403) else
                                 'ENDPOINT_UNAVAILABLE')
        result['error_type'] = error
        return result
    try:
        series = json.loads(body)['seriess'][0]
        if series['id'] != series_id:
            raise ValueError('Series identity mismatch')
    except (ValueError, KeyError, IndexError, TypeError):
        result['auth_result'] = 'SCHEMA_MISMATCH'
        return result
    result['auth_tested'] = True
    result['auth_result'] = 'SUCCESS'
    result['historical_coverage'] = {'first_observation': series.get('observation_start'),
                                     'last_observation': series.get('observation_end'),
                                     'frequency': series.get('frequency')}
    if 'copyright' in (series.get('notes') or '').lower():
        result['license_status'] = 'LICENSE_REVIEW_REQUIRED'
        result['pit_reason'] = 'Series metadata mentions copyright; data request skipped'
        return result
    # One-month sample. output_type=4 requests initial-release values; FRED may
    # reject it for a series, in which case a single as-of snapshot is attempted.
    data_params = dict(base, observation_start='2020-01-01', observation_end='2020-01-31',
                       realtime_start='2020-01-01', realtime_end='2020-02-28',
                       output_type=4, limit=50)
    status, body, error = _get(session, FRED_URL, data_params, key)
    result['requests'] += 1
    output_type = 4
    if status == 400 and not error:
        data_params.update(realtime_start='2020-02-03', realtime_end='2020-02-03', output_type=1)
        status, body, error = _get(session, FRED_URL, data_params, key)
        result['requests'] += 1
        output_type = 1
    result['data_http_status'] = status
    result['output_type'] = output_type
    if error or status != 200 or body is None:
        result['data_result'] = ('NETWORK_ERROR' if status is None else
                                 'RATE_LIMITED' if status == 429 else
                                 'DATA_UNAVAILABLE' if status == 400 else
                                 'ACCESS_DENIED' if status in (401, 403) else
                                 'ENDPOINT_UNAVAILABLE')
        result['error_type'] = error
        return result
    try:
        payload = json.loads(body)
        rows = payload['observations']
        if not isinstance(rows, list) or not rows or len(rows) > 50:
            raise ValueError('Observation count invalid')
        if any(not {'date', 'value', 'realtime_start', 'realtime_end'} <= set(row)
               or row['date'] < '2020-01-01' or row['date'] > '2020-01-31' for row in rows):
            raise ValueError('Observation schema or date range invalid')
        if len({(row['date'], row['realtime_start'], row['realtime_end']) for row in rows}) != len(rows):
            raise ValueError('Duplicate vintage observation')
    except (ValueError, KeyError, TypeError):
        result['data_result'] = 'SCHEMA_MISMATCH'
        return result
    raw_path = state_dir / 'raw' / f'fred_{series_id.lower()}_{run_id}.json'
    result['raw_sha256'] = _save_bytes(raw_path, body)
    result['raw_path'] = str(raw_path)
    result['raw_bytes'] = len(body)
    result['row_count'] = len(rows)
    result['numeric_rows'] = sum(1 for row in rows if _finite_number(row['value']))
    result['missing_value_rows'] = len(rows) - result['numeric_rows']
    result['first_observation'] = min(row['date'] for row in rows)
    result['last_observation'] = max(row['date'] for row in rows)
    result['first_vintage_date'] = min(row['realtime_start'] for row in rows)
    result['last_vintage_date'] = max(row['realtime_start'] for row in rows)
    result['revision_metadata'] = 'FRED realtime_start/realtime_end dates present'
    result['publication_timestamp'] = None
    result['data_result'] = 'SUCCESS'
    result['data_acquired'] = True
    return result


def _finite_number(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


def probe_ecos_dart(env_path: Path = ENV) -> dict:
    """One row per API for auth/capability only; discard provider payloads."""
    values = env_keys(env_path)
    session = requests.Session()
    session.trust_env = False
    session.headers['User-Agent'] = 'Regime190PrivateResearch/1.0'
    results = {}
    ecos_key = values.get('BOK_ECOS_API_KEY')
    if ecos_key:
        # Exact StatisticSearch shape and KTB code come from the installed
        # MyDream2000 market_rates_collector configuration.
        url = ('https://ecos.bok.or.kr/api/StatisticSearch/' + quote(ecos_key, safe='') +
               '/json/kr/1/1/817Y002/D/20201005/20201005/010210000/')
        status, body, error = _get(session, url, {}, ecos_key)
        item = {'provider': 'BOK_ECOS', 'auth_tested': True, 'http_status': status,
                'auth_result': 'NETWORK_ERROR' if status is None else 'ENDPOINT_UNAVAILABLE',
                'response_sha256': hashlib.sha256(body).hexdigest() if body else None,
                'row_count': 0, 'error_type': error, 'license_status': 'LICENSE_REVIEW_REQUIRED'}
        if status == 200 and body:
            try:
                payload = json.loads(body)
                rows = payload.get('StatisticSearch', {}).get('row', [])
                item['row_count'] = len(rows) if isinstance(rows, list) else int(bool(rows))
                item['auth_result'] = 'SUCCESS' if item['row_count'] else 'DATA_UNAVAILABLE'
                item['schema_fields'] = sorted(rows[0]) if isinstance(rows, list) and rows else []
                if payload.get('RESULT', {}).get('CODE') in {'ERROR-100', 'ERROR-101'}:
                    item['auth_result'] = 'INVALID_CREDENTIAL'
            except (ValueError, AttributeError, TypeError):
                item['auth_result'] = 'SCHEMA_MISMATCH'
        elif status in (401, 403):
            item['auth_result'] = 'ACCESS_DENIED'
        elif status == 429:
            item['auth_result'] = 'RATE_LIMITED'
        results['BOK_ECOS'] = item
    else:
        results['BOK_ECOS'] = {'provider': 'BOK_ECOS', 'auth_tested': False,
                               'auth_result': 'NO_CREDENTIAL'}
    dart_key = values.get('DART_API_KEY') or values.get('OPENDART_API_KEY')
    if dart_key:
        params = {'crtfc_key': dart_key, 'bgn_de': '20201005', 'end_de': '20201005',
                  'page_count': 1, 'page_no': 1}
        status, body, error = _get(session, 'https://opendart.fss.or.kr/api/list.json', params, dart_key)
        item = {'provider': 'DART', 'auth_tested': True, 'http_status': status,
                'auth_result': 'NETWORK_ERROR' if status is None else 'ENDPOINT_UNAVAILABLE',
                'response_sha256': hashlib.sha256(body).hexdigest() if body else None,
                'row_count': 0, 'error_type': error, 'license_status': 'LICENSE_REVIEW_REQUIRED'}
        if status == 200 and body:
            try:
                payload = json.loads(body)
                item['api_status'] = str(payload.get('status'))
                item['row_count'] = len(payload.get('list', []))
                item['auth_result'] = ('SUCCESS' if item['api_status'] == '000' else
                                       'DATA_UNAVAILABLE' if item['api_status'] == '013' else
                                       'INVALID_CREDENTIAL' if item['api_status'] in {'010', '011', '012'}
                                       else 'ACCESS_DENIED')
                item['schema_fields'] = sorted(payload['list'][0]) if item['row_count'] else []
            except (ValueError, AttributeError, TypeError):
                item['auth_result'] = 'SCHEMA_MISMATCH'
        elif status in (401, 403):
            item['auth_result'] = 'ACCESS_DENIED'
        elif status == 429:
            item['auth_result'] = 'RATE_LIMITED'
        results['DART'] = item
    else:
        results['DART'] = {'provider': 'DART', 'auth_tested': False,
                           'auth_result': 'NO_CREDENTIAL'}
    return {'checked_at_utc': _utc(), 'request_limit': 2, 'results': results,
            'provider_payloads_stored': False}
