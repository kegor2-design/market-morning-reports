"""Bounded market-intelligence cycle on the canonical Agent 2.0 worker queue."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from universal_agent import offline_worker
from universal_agent.engine import locked_state, write_state
from .exploratory_backtest import SOURCE, pit_eligibility

CODE_FILES = ('agent4_market.py', 'agent4_adapter.py', 'agent4_controller.py',
              'exploratory_backtest.py')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_hashes() -> dict:
    root = Path(__file__).resolve().parent
    return {name: _sha(root / name) for name in CODE_FILES}


def _source_hashes() -> dict:
    return {name: _sha(SOURCE / name) for name in
            ('naver_source_manifest.json', 'naver_kospi_daily.csv', 'naver_kosdaq_daily.csv')}


def _plan() -> dict:
    return {'schema_version': 1, 'research_project': 'regime190_agent4',
            'adapter': 'regime190_agent4', 'tasks': [{
                'task_id': 'market_intelligence_v1', 'task_type': 'market_intelligence',
                'agent2_task_contract_version': 4,
                'research_objective_id': 'regime190_market_intelligence',
                'hypothesis_id': 'frozen_regime_conditional_forecast',
                'required_tools': ['agent4_market_intelligence_v1'],
                'required_data': ['hashed KOSPI and KOSDAQ daily snapshots'],
                'pit_requirements': 'EXPLORATORY_PIT_UNVERIFIED',
                'execution_class': 'SERVER_EXECUTABLE', 'priority': 0,
                'dependencies': [], 'delay_hours': 0, 'input_artifacts': [],
                'resource_budget': {'max_seconds': 60, 'max_attempts': 1},
                'validation_rules': ['no official probability claim',
                                     'no independent holdout claim', 'no PIT promotion'],
                'expected_artifacts': ['versioned intelligence JSON'],
                'retry_policy': {'max_attempts': 1}}]}


def cycle(state_dir: Path, repo: Path) -> dict:
    if pit_eligibility()['eligible_indicator_ids']:
        raise ValueError('PIT state changed; review Agent 4.0 plan')
    plan_path = state_dir / 'agent4_plan.json'
    with locked_state(state_dir):
        if (state_dir / 'STOP').exists():
            return {'status': 'STOPPED'}
        memory_path = state_dir / 'research_memory.json'
        if memory_path.exists():
            memory = json.loads(memory_path.read_text())
            queue = offline_worker._load_queue(state_dir)
            artifact = Path(memory['artifact_path'])
            if (memory['code_sha256'] != _code_hashes()
                    or memory['source_sha256'] != _source_hashes()
                    or memory['checkpoint_id'] != queue['checkpoint_id']
                    or queue['tasks']['market_intelligence_v1']['status'] != 'COMPLETED'
                    or not artifact.is_file() or _sha(artifact) != memory['artifact_sha256']):
                raise ValueError('Agent 4.0 memory integrity mismatch')
            return {'status': 'ALREADY_EVALUATED', 'checkpoint_id': memory['checkpoint_id'],
                    'decision': memory['research_decision']}
        if plan_path.exists():
            stored = json.loads(plan_path.read_text())
            stored.pop('updated_at_utc', None)
            if stored != _plan():
                raise ValueError('Agent 4.0 plan changed')
        else:
            write_state(plan_path, _plan())
    offline_worker.prepare(plan_path, state_dir, repo)
    worker = offline_worker.run(state_dir, repo, max_tasks=1, max_seconds=120)
    with locked_state(state_dir):
        queue = offline_worker._load_queue(state_dir)
        task = queue['tasks']['market_intelligence_v1']
        if task['status'] != 'COMPLETED':
            return {'status': 'INCOMPLETE', 'worker': worker, 'task_status': task['status'],
                    'error_reason': task.get('error_reason')}
        artifact = Path(task['output_artifacts'][0])
        result = offline_worker._verify_output(offline_worker._adapter(queue['adapter']), task)['result']
        memory = {'schema_version': 1, 'research_cycle_id': 'regime190_agent4_20261101',
            'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo,
                                                   text=True).strip(),
            'code_sha256': _code_hashes(), 'source_sha256': _source_hashes(),
            'artifact_path': str(artifact), 'artifact_sha256': _sha(artifact),
            'checkpoint_id': queue['checkpoint_id'], 'experiment_id': 'market_intelligence_v1',
            'research_decision': result['research_decision'],
            'pit_status': result['pit']['status'],
            'final_holdout': result['split']['final_holdout'],
            'model_runtime': result['model_runtime'], 'external_api_calls': 0,
            'next_action': 'Acquire PIT evidence and genuinely unexamined data'}
        write_state(state_dir / 'research_memory.json', memory)
        write_state(state_dir / 'daily_market_diagnosis.json', result['daily_report'])
        return {'status': 'EXPLORATORY_COMPLETE', 'checkpoint_id': queue['checkpoint_id'],
                'decision': memory['research_decision'],
                'asof': result['daily_report']['기준 거래일'],
                'pit_status': memory['pit_status']}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(cycle(args.state_dir, args.repo), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
