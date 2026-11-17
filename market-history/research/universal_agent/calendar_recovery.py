"""Evidence-gated, zero-network calendar repair for blocked US rates programs.

The original plan, source jobs, raw bytes and blocked results remain immutable.
A versioned DAG revision adds new revalidation tasks that reuse sealed responses.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .data_recovery import verify_recovery
from .engine import canonical, write_state
from .research_job import manifest_load, plan_for, verify_artifact
from .research_planner import SERIES, _task, validate_plan
from .source_adapters import select
from .us_rates_calendar import expected_observations, publication_metadata


def _hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked calendar recovery evidence')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnose(plan: dict, state: dict, program_dir: Path) -> dict | None:
    """Classify only a fully explained closure gap; never infer missing values."""
    if (plan['market'] != 'US_RATES' or state['status'] != 'RESEARCH_BLOCKED'
            or state.get('calendar_revision') or
            state['goal_id'] != plan['goal_id']):
        return None
    start, end = plan['research_period']['start'], plan['research_period']['end']
    details = {}
    for series in SERIES:
        task_id = 'collect_' + series.lower()
        record = state['records'].get(task_id)
        if not record or record['status'] != 'BLOCKED_EVIDENCE' or record['attempts'] != 1:
            return None
        manifest_path = program_dir / 'manifests' / (task_id + '.json')
        job_dir = program_dir / 'jobs' / task_id
        manifest, digest = manifest_load(manifest_path)
        if manifest['mode'] != 'data_recovery' or manifest['data_request']['series'] != series:
            raise ValueError('Calendar recovery source identity changed')
        verify_artifact(manifest, plan_for(manifest, digest), job_dir)
        source = verify_recovery(manifest['data_request'], job_dir / 'data_recovery')
        valid, closures = expected_observations(start, end, series)
        if (source['status'] != 'BLOCKED_EVIDENCE' or not closures or
                source['still_missing'] != closures or
                sorted(source['recovered']) != sorted(valid) or
                source['mismatches']):
            return None
        adapter = select(series, manifest['data_request']['allowed_sources'])
        raw = job_dir / 'data_recovery' / ('source' + adapter.extension)
        if _hash(raw) != source['content_sha256'] or \
                adapter.parse(series, raw.read_bytes(), set(closures)):
            raise ValueError('Closure source bytes disagree with calendar')
        details[series] = {'original_task_id': task_id,
            'original_checkpoint_sha256': _hash(job_dir / 'job.json'),
            'source_sha256': source['content_sha256'],
            'valid_observation_count': len(valid), 'closures': closures,
            'publication_metadata': publication_metadata(series)}
    return {'schema_version': 1, 'goal_id': plan['goal_id'],
        'original_goal': plan['research_goal'],
        'original_plan_sha256': state['plan_sha256'],
        'goal_contract_sha256': state['goal_contract_sha256'],
        'problem_type': 'CALENDAR_MISMATCH',
        'root_cause': 'Weekday-only expectation included reviewed full closures',
        'calendar_version': 1, 'series': details,
        'new_network_requests': 0, 'new_model_calls': 0,
        'pit_status': 'PIT_UNVERIFIED',
        'solution_action': 'REVALIDATE_SEALED_SOURCE_WITH_REVIEWED_CALENDAR',
        'verification_rule': 'independently_parse_original_source_bytes',
        'rollback_rule': 'retain_original_plan_and_blocked_jobs'}


def replan(plan: dict, state: dict, program_dir: Path) -> bool:
    if state.get('calendar_revision'):
        return False
    proposal = diagnose(plan, state, program_dir)
    if proposal is None:
        return False
    path = program_dir / 'calendar_revision_v1.json'
    if path.is_symlink():
        raise ValueError('Symlinked calendar revision')
    if path.exists():
        prior = json.loads(path.read_text())
        prior.pop('updated_at_utc', None)
        if prior != proposal:
            raise ValueError('Calendar revision changed after reservation')
    else:
        write_state(path, dict(proposal))
    revision_hash = _hash(path)
    analysis = next(task for task in state['tasks'] if task['task_id'] == 'analyze_rates')
    if state['records']['analyze_rates']['attempts'] != 0:
        raise ValueError('Cannot replan an executed analysis')
    old_dependencies = list(analysis['dependencies'])
    analysis['dependencies'] = [dep for dep in old_dependencies
                                if not dep.startswith('collect_')]
    for priority, series in enumerate(SERIES, start=25):
        new_id = 'revalidate_' + series.lower()
        if new_id in state['records']:
            raise ValueError('Calendar task already exists without revision')
        task = _task(new_id, 'DATA_CALENDAR_REVALIDATION', priority,
                     dependencies=['discover_' + series.lower()],
                     inputs={'series': series, 'calendar_revision_sha256': revision_hash})
        state['tasks'].append(task)
        state['records'][new_id] = {'status': 'PENDING', 'attempts': 0}
        analysis['dependencies'].append(new_id)
    analysis['inputs']['calendar_revision_sha256'] = revision_hash
    state['records']['analyze_rates']['status'] = 'PENDING'
    validate_plan(dict(plan, tasks=state['tasks']))
    state['calendar_revision'] = {'path': str(path), 'sha256': revision_hash,
                                  'status': 'APPROVED_BY_HOST_POLICY'}
    state.setdefault('plan_versions', []).append({'version': 2,
        'original_plan_sha256': state['plan_sha256'],
        'revision_sha256': revision_hash,
        'reason': proposal['root_cause'],
        'changed_task': 'analyze_rates',
        'added_tasks': ['revalidate_' + series.lower() for series in SERIES],
        'removed_dependencies': [dep for dep in old_dependencies
                                 if dep.startswith('collect_')],
        'network_requests_added': 0})
    state['replanning_history'].append({'cause': 'CALENDAR_MISMATCH',
        'evidence_sha256': revision_hash,
        'solution_action': proposal['solution_action'],
        'resume_original_goal_id': plan['goal_id']})
    return True


def seed_revalidation(plan: dict, task: dict, manifest: dict,
                      program_dir: Path, job_dir: Path) -> None:
    """Seal a copy of the old response for a new zero-network Research Job."""
    series = task['inputs']['series']
    revision = program_dir / 'calendar_revision_v1.json'
    if _hash(revision) != task['inputs']['calendar_revision_sha256']:
        raise ValueError('Calendar revision hash changed')
    old_id = 'collect_' + series.lower()
    old_manifest, digest = manifest_load(program_dir / 'manifests' / (old_id + '.json'))
    old_dir = program_dir / 'jobs' / old_id
    verify_artifact(old_manifest, plan_for(old_manifest, digest), old_dir)
    old_source = verify_recovery(old_manifest['data_request'], old_dir / 'data_recovery')
    if old_source['status'] != 'BLOCKED_EVIDENCE':
        raise ValueError('Original source no longer has calendar gap')
    adapter = select(series, manifest['data_request']['allowed_sources'])
    raw = old_dir / 'data_recovery' / ('source' + adapter.extension)
    raw_hash = _hash(raw)
    if raw_hash != old_source['content_sha256']:
        raise ValueError('Original source hash changed')
    destination = job_dir / 'data_recovery'
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Symlinked revalidation directory')
    new_raw = destination / ('source' + adapter.extension)
    if new_raw.is_symlink():
        raise ValueError('Symlinked revalidation source')
    if not new_raw.exists():
        fd = os.open(new_raw, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
    if _hash(new_raw) != raw_hash:
        raise ValueError('Reused source hash differs from original')
    request = manifest['data_request']
    receipt = {'request_sha256': hashlib.sha256(canonical(request)).hexdigest(),
        'source_uri': adapter.uri(series, request['start'], request['end']),
        'content_sha256': raw_hash, 'network_requests': 0,
        'reused_from': str(raw), 'original_job_sha256': _hash(old_dir / 'job.json'),
        'calendar_revision_sha256': task['inputs']['calendar_revision_sha256']}
    receipt_path = destination / 'source_receipt.json'
    if receipt_path.is_symlink():
        raise ValueError('Symlinked revalidation receipt')
    if receipt_path.exists():
        saved = json.loads(receipt_path.read_text())
        saved.pop('updated_at_utc', None)
        if saved != receipt:
            raise ValueError('Revalidation receipt changed')
    else:
        write_state(receipt_path, receipt)
