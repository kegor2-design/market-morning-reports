"""Bounded Agent 3.0 research controller on the existing canonical worker queue."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from universal_agent import offline_worker
from universal_agent.engine import locked_state, write_state
from .agent3_experiments import BASELINE_STATE, patch_manifest, validate_patch
from .exploratory_backtest import pit_eligibility

TASKS = [('pit_investigation_v1', 'pit_investigation', 'agent3_pit_v1', []),
         ('label_alignment_v1', 'label_alignment', 'agent3_label_v1', ['pit_investigation_v1']),
         ('hysteresis_v1', 'hysteresis', 'agent3_hysteresis_v1', ['label_alignment_v1'])]


def _plan() -> dict:
    return {'schema_version': 1, 'research_project': 'regime190_agent3',
            'adapter': 'regime190_agent3', 'tasks': [
                {'task_id': task_id, 'task_type': kind, 'agent2_task_contract_version': 3,
                 'research_objective_id': 'regime190_first_cycle',
                 'hypothesis_id': task_id, 'required_tools': [tool],
                 'required_data': ['verified baseline artifact', 'existing Regime190 evidence'],
                 'pit_requirements': 'EXPLORATORY_PIT_UNVERIFIED',
                 'execution_class': 'SERVER_EXECUTABLE', 'priority': i,
                 'dependencies': deps, 'delay_hours': 0, 'input_artifacts': [],
                 'resource_budget': {'max_seconds': 30, 'max_attempts': 1},
                 'validation_rules': ['no PIT promotion', 'no official performance claim',
                                      'no final holdout candidate metrics'],
                 'expected_artifacts': ['versioned JSON result'],
                 'retry_policy': {'max_attempts': 1}}
                for i, (task_id, kind, tool, deps) in enumerate(TASKS)]}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_hashes() -> dict:
    root = Path(__file__).resolve().parent
    return {name: _sha(root / name) for name in
            ('agent3_controller.py', 'agent3_experiments.py', 'agent3_adapter.py')}


def _read_result(queue: dict, task_id: str) -> tuple[dict, Path]:
    task = queue['tasks'][task_id]
    if task['status'] != 'COMPLETED':
        raise ValueError('Research task incomplete')
    artifact = Path(task['output_artifacts'][0])
    payload = offline_worker._verify_output(offline_worker._adapter(queue['adapter']), task)
    return payload['result'], artifact


def cycle(state_dir: Path, repo: Path) -> dict:
    if pit_eligibility()['eligible_indicator_ids']:
        raise ValueError('PIT status changed; review plan before Agent 3.0 execution')
    validate_patch(patch_manifest())
    plan_path = state_dir / 'agent3_plan.json'
    with locked_state(state_dir):
        if (state_dir / 'STOP').exists():
            return {'status': 'STOPPED'}
        memory_path = state_dir / 'research_memory.json'
        if memory_path.exists():
            memory = json.loads(memory_path.read_text())
            queue = offline_worker._load_queue(state_dir)
            provenance = json.loads((BASELINE_STATE / 'research_memory.json').read_text())['source_provenance']
            source_dir = Path(__file__).resolve().parent.parent / 'daily-index-validation-20261021'
            if (memory.get('code_sha256') != _code_hashes()
                    or memory.get('checkpoint_id') != queue['checkpoint_id']
                    or memory.get('baseline_artifact_sha256') !=
                        json.loads((BASELINE_STATE / 'research_memory.json').read_text())['artifact_sha256']
                    or any(_sha(source_dir / ('naver_' + market.lower() + '_daily.csv')) != detail['sha256']
                           for market, detail in provenance.items())
                    or any(not Path(item['path']).is_file() or
                           _sha(Path(item['path'])) != item['sha256']
                           for item in memory['artifacts'])):
                raise ValueError('Agent 3.0 memory integrity mismatch')
            return {'status': 'ALREADY_EVALUATED', 'checkpoint_id': memory['checkpoint_id'],
                    'decision': memory['decision']}
        if plan_path.exists():
            stored = json.loads(plan_path.read_text())
            stored.pop('updated_at_utc', None)
            if stored != _plan():
                raise ValueError('Agent 3.0 stored plan changed')
        else:
            write_state(plan_path, _plan())
    offline_worker.prepare(plan_path, state_dir, repo)
    worker = offline_worker.run(state_dir, repo, max_tasks=3, max_seconds=120)
    with locked_state(state_dir):
        queue = offline_worker._load_queue(state_dir)
        if any(queue['tasks'][task_id]['status'] != 'COMPLETED' for task_id, *_ in TASKS):
            return {'status': 'INCOMPLETE', 'worker': worker,
                    'statuses': {key: value['status'] for key, value in queue['tasks'].items()}}
        pit, pit_path = _read_result(queue, TASKS[0][0])
        label, label_path = _read_result(queue, TASKS[1][0])
        hysteresis, hyst_path = _read_result(queue, TASKS[2][0])
        if (pit['eligible_after'] != 0 or label['next_hypothesis_id'] != hysteresis['hypothesis_id']
                or hysteresis['official_improvement_claim'] is not False):
            raise ValueError('Agent 3.0 decision chain invalid')
        memory = {'schema_version': 1, 'research_cycle_id': 'regime190_agent3_20261101',
            'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo,
                                                   text=True).strip(),
            'objective_id': 'regime190_first_cycle', 'baseline_code_commit':
                json.loads((BASELINE_STATE / 'research_memory.json').read_text())['code_commit'],
            'baseline_artifact_sha256':
                json.loads((BASELINE_STATE / 'research_memory.json').read_text())['artifact_sha256'],
            'code_sha256': _code_hashes(), 'patch': patch_manifest(),
            'checkpoint_id': queue['checkpoint_id'], 'iterations_used': 2,
            'iterations_limit': 5, 'concurrency_limit': 1, 'external_api_calls': 0,
            'diagnosis': {'pit': pit['status'], 'label': label['decision'],
                          'strategy': hysteresis['decision']},
            'experiments': [{'experiment_id': label['experiment_id'], 'decision': label['decision'],
                             'next_hypothesis_id': label['next_hypothesis_id']},
                            {'experiment_id': hysteresis['experiment_id'],
                             'decision': hysteresis['decision']}],
            'artifacts': [{'path': str(path), 'sha256': _sha(path)}
                          for path in (pit_path, label_path, hyst_path)],
            'pit_eligible_after': 0, 'final_holdout': 'FINAL_HOLDOUT_CONTAMINATED',
            'decision': 'MORE_EVIDENCE_REQUIRED',
            'next_action': 'Verify source release/vintage and obtain unexamined validation period',
            'model_status': 'DETERMINISTIC_NON_AI', 'deployment_readiness': 'NOT_READY'}
        write_state(state_dir / 'research_memory.json', memory)
        write_state(state_dir / 'agent3_handoff.json', {
            'schema_version': 1, 'research_cycle_id': memory['research_cycle_id'],
            'executed': [task_id for task_id, *_ in TASKS], 'failed': [],
            'blocked': ['official backtest: PIT', 'independent final holdout: contaminated'],
            'next_action': memory['next_action'], 'model_status': memory['model_status']})
        return {'status': 'BOUNDED_RESEARCH_STOPPED', 'checkpoint_id': queue['checkpoint_id'],
                'experiments_executed': 2, 'decision': memory['decision'],
                'pit_eligible_after': 0, 'model_status': memory['model_status']}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(cycle(args.state_dir, args.repo), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
