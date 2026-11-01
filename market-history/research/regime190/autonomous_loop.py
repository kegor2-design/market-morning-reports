"""Bounded deterministic diagnosis loop on the existing Agent 2.0 worker queue."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from universal_agent import offline_worker
from universal_agent.engine import locked_state, write_state
from universal_agent.agent2 import validate_hypothesis, validate_objective
from .exploratory_backtest import pit_eligibility
from .autonomous_diagnosis import BASELINE_STATE

TASK_ID = 'diagnosis_experiment_v1'
OBJECTIVE_ID = 'regime190_first_cycle'
OBJECTIVE = {'schema_version': 1, 'objective_id': OBJECTIVE_ID,
             'domain': 'korean_equity_regime',
             'question': 'Diagnose and independently revalidate Regime190 research results'}
HYPOTHESIS = {'schema_version': 1, 'hypothesis_id': 'h_recovery_confirmation',
              'objective_id': OBJECTIVE_ID,
              'statement': 'Two-day recovery confirmation reduces false rebounds',
              'falsification': 'No gain or too few independent recovery events'}
SOURCE_DIR = Path(__file__).resolve().parent.parent / 'daily-index-validation-20261021'


def _code_hashes() -> dict:
    root = Path(__file__).resolve().parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ('autonomous_loop.py', 'autonomous_diagnosis.py',
                         'exploratory_backtest.py', 'exploratory_adapter.py')}


def _plan() -> dict:
    return {'schema_version': 1, 'research_project': 'regime190_exploratory',
            'adapter': 'regime190_exploratory', 'tasks': [{
                'task_id': TASK_ID, 'task_type': 'diagnosis_experiment',
                'agent2_task_contract_version': 2,
                'research_objective_id': OBJECTIVE_ID,
                'hypothesis_id': 'h_recovery_confirmation',
                'required_tools': ['regime190_diagnosis_v1'],
                'required_data': ['baseline experiment artifact', 'verified index snapshots'],
                'pit_requirements': 'EXPLORATORY_PIT_UNVERIFIED',
                'execution_class': 'SERVER_EXECUTABLE', 'priority': 0,
                'dependencies': [], 'delay_hours': 0, 'input_artifacts': [],
                'resource_budget': {'max_seconds': 30, 'max_attempts': 1},
                'validation_rules': ['exact baseline reproduction', 'no final holdout candidate metrics'],
                'expected_artifacts': ['structured diagnosis and experiment JSON'],
                'retry_policy': {'max_attempts': 1}}]}


def cycle(state_dir: Path, repo: Path) -> dict:
    validate_objective(OBJECTIVE)
    validate_hypothesis(HYPOTHESIS)
    if pit_eligibility()['eligible_indicator_ids']:
        raise ValueError('PIT decision changed; review new official research plan')
    plan_path = state_dir / 'agent2_diagnosis_plan.json'
    with locked_state(state_dir):
        if (state_dir / 'STOP').exists():
            return {'status': 'STOPPED'}
        memory_path = state_dir / 'research_memory.json'
        if memory_path.exists():
            memory = json.loads(memory_path.read_text())
            artifact = Path(memory['artifact_path'])
            baseline_memory = json.loads((BASELINE_STATE / 'research_memory.json').read_text())
            if (memory.get('experiment_id') != TASK_ID
                    or not artifact.is_relative_to((state_dir / 'artifacts').resolve())
                    or not artifact.is_file()
                    or hashlib.sha256(artifact.read_bytes()).hexdigest() != memory['artifact_sha256']
                    or memory.get('code_sha256') != _code_hashes()
                    or memory.get('baseline_artifact_sha256') != baseline_memory['artifact_sha256']
                    or any(hashlib.sha256((SOURCE_DIR / ('naver_' + market.lower() + '_daily.csv')).read_bytes()).hexdigest()
                           != info['sha256'] for market, info in memory['input_manifest'].items())
                    or offline_worker._load_queue(state_dir)['checkpoint_id'] != memory['checkpoint_id']):
                raise ValueError('Research memory integrity mismatch')
            return {'status': 'ALREADY_EVALUATED', 'checkpoint_id': memory['checkpoint_id'],
                    'decision': memory['decision']}
        if plan_path.exists():
            stored = json.loads(plan_path.read_text())
            stored.pop('updated_at_utc', None)
            if stored != _plan():
                raise ValueError('Stored plan changed')
        else:
            write_state(plan_path, _plan())
    offline_worker.prepare(plan_path, state_dir, repo)
    worker = offline_worker.run(state_dir, repo, max_tasks=1, max_seconds=60)
    with locked_state(state_dir):
        queue = offline_worker._load_queue(state_dir)
        task = queue['tasks'][TASK_ID]
        if task['status'] != 'COMPLETED':
            return {'status': task['status'], 'worker': worker}
        artifact = Path(task['output_artifacts'][0])
        payload = offline_worker._verify_output(offline_worker._adapter(queue['adapter']), task)
        result = payload['result']
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True,
                                capture_output=True, timeout=3, check=True).stdout.strip()
        memory = {'schema_version': 1, 'research_cycle_id': 'regime190_autoval_20261101',
                  'experiment_id': TASK_ID, 'parent_experiment_id': 'index_regime_exploratory_v1',
                  'hypothesis_id': result['experiment']['plan']['hypothesis_id'],
                  'baseline_version': result['diagnosis']['baseline_code_commit'],
                  'changed_parameters': result['experiment']['plan']['changed_variables'],
                  'input_manifest': result['diagnosis']['source_provenance'],
                  'baseline_artifact_sha256': result['diagnosis']['baseline_artifact_sha256'],
                  'code_commit': commit, 'result_sha256': hashlib.sha256(
                      json.dumps(result, sort_keys=True).encode()).hexdigest(),
                  'code_sha256': _code_hashes(),
                  'artifact_path': str(artifact),
                  'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                  'checkpoint_id': task['checkpoint_id'],
                  'diagnosis': result['diagnosis']['diagnoses'],
                  'evaluation': {key: result['experiment'][key] for key in
                      ('execution_success', 'data_validity', 'pit_validity',
                       'statistical_validity', 'out_of_sample_validity',
                       'research_value', 'deployment_readiness')},
                  'decision': result['research_decision'],
                  'next_action': result['next_action'],
                  'model_status': 'DETERMINISTIC_NON_AI',
                  'iterations_used': 1, 'iterations_limit': 3}
        write_state(memory_path, memory)
        write_state(state_dir / 'agent2_handoff.json', {
            'schema_version': 1, 'research_cycle_id': memory['research_cycle_id'],
            'executed': [TASK_ID], 'succeeded': [TASK_ID], 'failed': [],
            'blocked': ['official optimization: PIT', 'independent holdout: contaminated'],
            'next_action': memory['next_action'], 'model_status': memory['model_status']})
        return {'status': 'DIAGNOSIS_AND_EXPERIMENT_COMPLETE',
                'checkpoint_id': task['checkpoint_id'],
                'decision': memory['decision'], 'pit_validity': 'BLOCKED',
                'out_of_sample_validity': 'NOT_VALIDATED',
                'model_status': memory['model_status']}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(cycle(args.state_dir, args.repo), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
