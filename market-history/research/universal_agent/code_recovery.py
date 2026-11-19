"""Approved, fixture-only code repair in the existing Research Program DAG."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from copy import deepcopy
from pathlib import Path

from .engine import canonical, now, write_state
from .research_planner import _task, validate_plan
from .self_repair import repair_research_source

BROKEN_SOURCE = ('import json\n'
    'value = missing_fixture_value\n'
    'with open("result.json", "w", encoding="utf-8") as stream:\n'
    '    json.dump({"answer": value}, stream)\n')


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or symlinked code repair artifact')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_source(program_dir: Path) -> Path:
    if program_dir.is_symlink():
        raise ValueError('Symlinked fixture program')
    program_dir = program_dir.resolve()
    directory = program_dir / 'isolated_code_fixture'
    if program_dir.is_symlink() or directory.is_symlink() or not \
            directory.resolve().is_relative_to(program_dir.resolve()):
        raise ValueError('Fixture directory outside program')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / 'experiment.py'
    if path.is_symlink():
        raise ValueError('Symlinked fixture source')
    if not path.exists():
        path.write_text(BROKEN_SOURCE)
    return path.resolve()


def authorize_fixture(plan: dict, state: dict, program_dir: Path, *,
                      candidate: str, approved_by: str) -> dict:
    """Host supplies one bounded candidate; the model cannot mint approval."""
    from regime190.agent43_engine import _check_code
    if (plan['market'] != 'ISOLATED_CODE_FIXTURE' or
            state['status'] != 'RESEARCH_BLOCKED' or
            state['records']['analyze_fixture'].get('problem_type') != 'CODE_ERROR' or
            state.get('code_repair_revision') or not approved_by.strip()):
        raise ValueError('No eligible fixture code failure or approver')
    _check_code(candidate)
    source = fixture_source(program_dir)
    evidence = program_dir / 'code_error_evidence.json'
    if json.loads(evidence.read_text())['error_type'] != 'CODE_ERROR':
        raise ValueError('Code error evidence changed')
    approval = {'schema_version': 1, 'scope': 'ISOLATED_CODE_FIXTURE',
        'goal_id': plan['goal_id'], 'failed_task_id': 'analyze_fixture',
        'source_sha256': _sha(source), 'evidence_sha256': _sha(evidence),
        'candidate': candidate,
        'candidate_sha256': hashlib.sha256(candidate.encode()).hexdigest(),
        'approved_by': approved_by, 'approved_at_utc': now(),
        'allowed_path': str(source), 'max_candidates': 1,
        'max_seconds': 60, 'max_network_requests': 0, 'max_model_calls': 0,
        'verification_rule': 'exact_answer_42',
        'rollback_rule': 'restore_original_source_and_dag'}
    path = program_dir / 'code_repair_approval.json'
    if path.exists() or path.is_symlink():
        raise ValueError('Code repair approval already exists')
    write_state(path, approval)
    return approval


def diagnose(plan: dict, state: dict, program_dir: Path) -> dict | None:
    if (plan['market'] != 'ISOLATED_CODE_FIXTURE' or
            state['status'] != 'RESEARCH_BLOCKED' or
            state.get('code_repair_revision') or
            state['records']['analyze_fixture'].get('problem_type') != 'CODE_ERROR'):
        return None
    path = program_dir / 'code_repair_approval.json'
    if not path.is_file() or path.is_symlink():
        return None
    approval = json.loads(path.read_text())
    source = fixture_source(program_dir)
    evidence = program_dir / 'code_error_evidence.json'
    if (approval.get('scope') != 'ISOLATED_CODE_FIXTURE' or
            approval.get('goal_id') != plan['goal_id'] or
            approval.get('failed_task_id') != 'analyze_fixture' or
            approval.get('source_sha256') != _sha(source) or
            approval.get('evidence_sha256') != _sha(evidence) or
            approval.get('candidate_sha256') != hashlib.sha256(
                approval.get('candidate', '').encode()).hexdigest() or
            Path(approval.get('allowed_path', '')).resolve() != source or
            approval.get('max_candidates') != 1 or
            approval.get('max_seconds') != 60 or
            approval.get('max_network_requests') != 0 or
            approval.get('max_model_calls') != 0 or
            approval.get('verification_rule') != 'exact_answer_42' or
            approval.get('rollback_rule') != 'restore_original_source_and_dag'):
        raise ValueError('Code repair approval or evidence changed')
    return {'problem_type': 'CODE_ERROR', 'goal_id': plan['goal_id'],
        'original_task_id': 'analyze_fixture',
        'error_evidence_sha256': _sha(evidence),
        'approval_sha256': _sha(path),
        'solution_action': 'CODE_REPAIR_TASK',
        'rollback_rule': 'restore_original_source_and_dag',
        'resume_rule': 'resume_original_fixture_analysis'}


def replan(plan: dict, state: dict, program_dir: Path) -> bool:
    proposal = diagnose(plan, state, program_dir)
    if proposal is None:
        return False
    candidate = deepcopy(state)
    analysis = next(t for t in candidate['tasks'] if t['task_id'] == 'analyze_fixture')
    old_analysis = deepcopy(analysis)
    old_record = deepcopy(candidate['records']['analyze_fixture'])
    approval = json.loads((program_dir / 'code_repair_approval.json').read_text())
    revision = {**proposal, 'source_sha256': approval['source_sha256'],
        'original_source_text': fixture_source(program_dir).read_text(),
        'original_plan_sha256': state['plan_sha256'],
        'goal_contract_sha256': state['goal_contract_sha256'],
        'previous_dag_sha256': hashlib.sha256(canonical(state['tasks'])).hexdigest(),
        'previous_analysis_task': old_analysis, 'previous_analysis_record': old_record,
        'status': 'REVISION_PREPARED', 'created_at_utc': now()}
    revision_path = program_dir / 'code_repair_revision_v1.json'
    if revision_path.exists() or revision_path.is_symlink():
        raise ValueError('Code repair revision already exists')
    write_state(revision_path, revision)
    digest = _sha(revision_path)
    task = _task('code_repair_fixture', 'CODE_REPAIR_TASK', 10,
        inputs={'revision_sha256': digest, 'failed_task_id': 'analyze_fixture'})
    candidate['tasks'].append(task)
    candidate['records'][task['task_id']] = {'status': 'PENDING', 'attempts': 0}
    analysis['dependencies'] = ['code_repair_fixture']
    candidate['records']['analyze_fixture'] = {'status': 'PENDING',
        'attempts': old_record['attempts']}
    validate_plan(dict(plan, tasks=candidate['tasks']))
    candidate['code_repair_revision'] = {'path': str(revision_path),
        'sha256': digest, 'status': 'REVISION_ACTIVE',
        'previous_dag_sha256': revision['previous_dag_sha256']}
    candidate.setdefault('plan_versions', []).append({'version': 2,
        'reason': 'CODE_ERROR', 'revision_sha256': digest,
        'added_tasks': [task['task_id']], 'network_requests_added': 0})
    candidate['replanning_history'].append({'cause': 'CODE_ERROR',
        'evidence_sha256': proposal['error_evidence_sha256'],
        'approval_sha256': proposal['approval_sha256'],
        'new_task': task['task_id'], 'resume_original_goal_id': plan['goal_id']})
    state.clear()
    state.update(candidate)
    return True


def execute_task(plan: dict, task: dict, program_dir: Path,
                 goal_deadline_utc: datetime | None = None) -> dict:
    revision_path = program_dir / 'code_repair_revision_v1.json'
    if _sha(revision_path) != task['inputs']['revision_sha256']:
        raise ValueError('Code repair revision changed')
    revision = json.loads(revision_path.read_text())
    approval_path = program_dir / 'code_repair_approval.json'
    approval = json.loads(approval_path.read_text())
    source = fixture_source(program_dir)
    backup = source.with_name('.experiment.py.repair-backup')
    if backup.is_symlink():
        raise ValueError('Unsafe interrupted code repair backup')
    retained_source_sha = _sha(backup) if backup.exists() else _sha(source)
    completed_source_sha = approval['candidate_sha256']
    if (revision['goal_id'] != plan['goal_id'] or
            revision['approval_sha256'] != _sha(approval_path) or
            Path(approval['allowed_path']).resolve() != source):
        raise ValueError('Code repair source or approval changed')
    if not backup.exists() and retained_source_sha == completed_source_sha:
        output = source.parent / 'result.json'
        if output.is_symlink() or not output.is_file() or \
                json.loads(output.read_text()) != {'answer': 42}:
            raise ValueError('Uncheckpointed repair output failed verification')
        return {'status': 'REPAIRED', 'recovered_existing_output': True,
            'before_sha256': revision['source_sha256'],
            'after_sha256': completed_source_sha,
            'source_sha256': completed_source_sha,
            'candidate_sha256': completed_source_sha}
    if revision['source_sha256'] != retained_source_sha:
        raise ValueError('Code repair source or approval changed')
    result = repair_research_source(source, [approval['candidate']], source.parent,
        lambda path, execution: json.loads((path.parent / 'result.json').read_text()) ==
            {'answer': 42}, max_candidates=1, deadline_utc=goal_deadline_utc)
    result['source_sha256'] = _sha(source)
    result['candidate_sha256'] = approval['candidate_sha256']
    return result


def rollback_failed_repair(plan: dict, state: dict, program_dir: Path) -> bool:
    revision_ref = state.get('code_repair_revision')
    if not revision_ref or revision_ref['status'] == 'REVISION_ROLLED_BACK':
        return False
    record = state['records']['code_repair_fixture']
    analysis_record = state['records']['analyze_fixture']
    if (record['status'] not in {'BLOCKED_EVIDENCE', 'BLOCKED_ENV', 'FAILED'} and
            analysis_record['status'] not in {'BLOCKED_EVIDENCE', 'BLOCKED_ENV', 'FAILED'}):
        return False
    revision_path = program_dir / 'code_repair_revision_v1.json'
    if _sha(revision_path) != revision_ref['sha256']:
        raise ValueError('Code repair revision changed before rollback')
    revision = json.loads(revision_path.read_text())
    source = fixture_source(program_dir)
    original = revision['original_source_text'].encode()
    if hashlib.sha256(original).hexdigest() != revision['source_sha256']:
        raise ValueError('Code repair original source changed')
    current_sha = _sha(source)
    approval = json.loads((program_dir / 'code_repair_approval.json').read_text())
    if current_sha not in {revision['source_sha256'], approval['candidate_sha256']}:
        raise ValueError('Unknown code repair source at rollback')
    if current_sha != revision['source_sha256']:
        fd, temporary = tempfile.mkstemp(prefix='.code-rollback-', dir=source.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, source)
            directory_fd = os.open(source.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    candidate = deepcopy(state)
    candidate.setdefault('retired_recovery_tasks', []).append({
        'task': next(t for t in candidate['tasks'] if t['task_id'] == 'code_repair_fixture'),
        'record': deepcopy(record), 'analysis_record': deepcopy(analysis_record)})
    candidate['tasks'] = [t for t in candidate['tasks'] if t['task_id'] != 'code_repair_fixture']
    candidate['records'].pop('code_repair_fixture')
    candidate['tasks'][0] = revision['previous_analysis_task']
    candidate['records']['analyze_fixture'] = revision['previous_analysis_record']
    candidate['code_repair_revision']['status'] = 'REVISION_ROLLED_BACK'
    candidate['plan_versions'][-1]['status'] = 'REVISION_ROLLED_BACK'
    candidate['replanning_history'].append({'cause': 'CODE_REPAIR_FAILED',
        'revision_sha256': revision_ref['sha256'],
        'retired_task_id': 'code_repair_fixture',
        'resume_original_goal_id': plan['goal_id']})
    candidate['status'] = 'RESEARCH_BLOCKED'
    candidate['next_action'] = 'REVIEW_FAILED_CODE_REPAIR'
    validate_plan(dict(plan, tasks=candidate['tasks']))
    if hashlib.sha256(canonical(candidate['tasks'])).hexdigest() != revision['previous_dag_sha256']:
        raise ValueError('Original DAG not restored after code repair failure')
    state.clear()
    state.update(candidate)
    return True
