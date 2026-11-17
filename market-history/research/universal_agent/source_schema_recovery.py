"""Reparse sealed Treasury CSV after an independently verified header change.

Only the reviewed 2020-2023 official archive shape is eligible. The failed jobs
remain immutable; new zero-network jobs use the original hashed response bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .engine import canonical, write_state
from .research_job import manifest_load, plan_for, verify_artifact
from .research_planner import _task, dates_for, validate_plan
from .source_adapters import select

SERIES = ('UST_2Y', 'UST_10Y')


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked schema recovery evidence')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnose(plan: dict, state: dict, program_dir: Path) -> dict | None:
    if (plan['market'] != 'US_RATES' or state['status'] != 'RESEARCH_BLOCKED' or
            state.get('schema_revision') or state['goal_id'] != plan['goal_id'] or
            not 2020 <= int(plan['research_period']['start'][:4]) <= 2023 or
            state['records'].get('collect_nyfed_sofr', {}).get('status') != 'VERIFIED'):
        return None
    evidence = {}
    dates = set(dates_for(plan))
    for series in SERIES:
        task_id = 'collect_' + series.lower()
        record = state['records'].get(task_id, {})
        if record.get('status') != 'BLOCKED_EVIDENCE' or record.get('attempts') != 1:
            return None
        manifest, digest = manifest_load(program_dir / 'manifests' / (task_id + '.json'))
        if manifest['mode'] != 'data_recovery' or manifest['data_request']['series'] != series:
            raise ValueError('Schema recovery source manifest changed')
        old_dir = program_dir / 'jobs' / task_id
        verify_artifact(manifest, plan_for(manifest, digest), old_dir)
        source_dir = old_dir / 'data_recovery'
        source = json.loads((source_dir / 'data_recovery.json').read_text())
        adapter = select(series, manifest['data_request']['allowed_sources'])
        raw = source_dir / ('source' + adapter.extension)
        receipt_path = source_dir / 'source_receipt.json'
        if not receipt_path.is_file() or receipt_path.is_symlink():
            return None
        receipt = json.loads(receipt_path.read_text())
        if (source['status'] != 'BLOCKED_EVIDENCE' or
                source.get('problem_type') != 'DATA_MISMATCH' or
                source.get('failure_history') != [{
                    'type': 'ValueError', 'detail': 'Official CSV columns changed'}] or
                source['request_sha256'] != hashlib.sha256(canonical(
                    manifest['data_request'])).hexdigest() or
                source['content_sha256'] != _sha(raw) or
                receipt['content_sha256'] != _sha(raw) or
                receipt['request_sha256'] != source['request_sha256'] or
                receipt['source_uri'] != adapter.uri(series,
                    manifest['data_request']['start'], manifest['data_request']['end']) or
                set(adapter.parse(series, raw.read_bytes(), dates)) != dates):
            return None
        evidence[series] = {'original_task_id': task_id,
            'original_job_sha256': _sha(old_dir / 'job.json'),
            'source_sha256': _sha(raw), 'source_receipt_sha256': _sha(receipt_path)}
    return {'schema_version': 1, 'goal_id': plan['goal_id'],
            'original_goal': plan['research_goal'],
            'original_plan_sha256': state['plan_sha256'],
            'goal_contract_sha256': state['goal_contract_sha256'],
            'problem_type': 'SCHEMA_MISMATCH',
            'root_cause': 'Reviewed Treasury archive uses lowercase headers and four-digit dates',
            'series': evidence, 'new_network_requests': 0, 'new_model_calls': 0,
            'solution_action': 'REPARSE_SEALED_SOURCE_WITH_REVIEWED_SCHEMA',
            'verification_rule': 'independently_parse_original_source_bytes',
            'rollback_rule': 'retain_original_plan_and_blocked_jobs',
            'pit_status': 'PIT_UNVERIFIED'}


def replan(plan: dict, state: dict, program_dir: Path) -> bool:
    proposal = diagnose(plan, state, program_dir)
    if proposal is None:
        return False
    path = program_dir / 'schema_revision_v1.json'
    if path.is_symlink():
        raise ValueError('Symlinked schema revision')
    if path.exists():
        saved = json.loads(path.read_text())
        saved.pop('updated_at_utc', None)
        if saved != proposal:
            raise ValueError('Schema revision changed after reservation')
    else:
        write_state(path, proposal)
    digest = _sha(path)
    analysis = next(task for task in state['tasks'] if task['task_id'] == 'analyze_rates')
    if state['records']['analyze_rates']['attempts'] != 0:
        raise ValueError('Cannot revise executed analysis')
    analysis['dependencies'] = [dep for dep in analysis['dependencies']
                                if dep not in {'collect_ust_2y', 'collect_ust_10y'}]
    added = []
    for priority, series in enumerate(SERIES, start=25):
        task_id = 'schema_revalidate_' + series.lower()
        if task_id in state['records']:
            raise ValueError('Schema recovery task already exists')
        task = _task(task_id, 'DATA_SCHEMA_REVALIDATION', priority,
            dependencies=['discover_' + series.lower()],
            inputs={'series': series, 'schema_revision_sha256': digest})
        state['tasks'].append(task)
        state['records'][task_id] = {'status': 'PENDING', 'attempts': 0}
        analysis['dependencies'].append(task_id)
        added.append(task_id)
    analysis['inputs']['schema_revision_sha256'] = digest
    state['records']['analyze_rates']['status'] = 'PENDING'
    validate_plan(dict(plan, tasks=state['tasks']))
    state['schema_revision'] = {'path': str(path), 'sha256': digest,
                                'status': 'APPROVED_BY_HOST_POLICY'}
    state.setdefault('plan_versions', []).append({'version': 2,
        'original_plan_sha256': state['plan_sha256'], 'revision_sha256': digest,
        'reason': proposal['root_cause'], 'added_tasks': added,
        'network_requests_added': 0})
    state['replanning_history'].append({'cause': 'SCHEMA_MISMATCH',
        'evidence_sha256': digest, 'solution_action': proposal['solution_action'],
        'resume_original_goal_id': plan['goal_id']})
    return True


def seed_revalidation(plan: dict, task: dict, manifest: dict,
                      program_dir: Path, job_dir: Path) -> None:
    revision = program_dir / 'schema_revision_v1.json'
    if _sha(revision) != task['inputs']['schema_revision_sha256']:
        raise ValueError('Schema revision hash changed')
    series = task['inputs']['series']
    old_id = 'collect_' + series.lower()
    old_manifest, digest = manifest_load(program_dir / 'manifests' / (old_id + '.json'))
    old_dir = program_dir / 'jobs' / old_id
    verify_artifact(old_manifest, plan_for(old_manifest, digest), old_dir)
    adapter = select(series, manifest['data_request']['allowed_sources'])
    raw = old_dir / 'data_recovery' / ('source' + adapter.extension)
    expected = json.loads(revision.read_text())['series'][series]['source_sha256']
    if _sha(raw) != expected:
        raise ValueError('Original source bytes changed')
    destination = job_dir / 'data_recovery'
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Symlinked schema revalidation directory')
    new_raw = destination / ('source' + adapter.extension)
    if not new_raw.exists():
        fd = os.open(new_raw, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
    if _sha(new_raw) != expected:
        raise ValueError('Revalidation source bytes changed')
    request = manifest['data_request']
    receipt = {'request_sha256': hashlib.sha256(canonical(request)).hexdigest(),
        'source_uri': adapter.uri(series, request['start'], request['end']),
        'content_sha256': expected, 'network_requests': 0,
        'reused_from': str(raw), 'original_job_sha256': _sha(old_dir / 'job.json'),
        'schema_revision_sha256': task['inputs']['schema_revision_sha256']}
    receipt_path = destination / 'source_receipt.json'
    if receipt_path.is_symlink():
        raise ValueError('Symlinked schema revalidation receipt')
    if receipt_path.exists():
        saved = json.loads(receipt_path.read_text())
        saved.pop('updated_at_utc', None)
        if saved != receipt:
            raise ValueError('Revalidation receipt changed')
    else:
        write_state(receipt_path, receipt)
