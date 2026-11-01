"""Agent 2.0 Regime190 cycle: PIT gate or explicitly exploratory real-data run."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from universal_agent.engine import locked_state, now, write_state
from universal_agent import offline_worker
from universal_agent.agent2 import validate_hypothesis, validate_objective

from .exploratory_backtest import pit_eligibility

CODE_PATH = Path(__file__).with_name('exploratory_backtest.py')
SOURCE_DIR = Path(__file__).resolve().parent.parent / 'daily-index-validation-20261021'

OBJECTIVE = {'schema_version': 1, 'objective_id': 'regime190_first_cycle',
             'domain': 'korean_equity_regime',
             'question': 'Can historical Korean equity data support crash, recovery and regime research?'}
HYPOTHESIS = {'schema_version': 1, 'hypothesis_id': 'index_regime_exploratory_v1',
              'objective_id': OBJECTIVE['objective_id'],
              'statement': 'Trailing index features can define six diagnostic regimes',
              'falsification': 'Insufficient or invalid historical index observations'}


def _plan() -> dict:
    return {'schema_version': 1, 'research_project': 'regime190_exploratory',
            'adapter': 'regime190_exploratory', 'tasks': [{
                'task_id': HYPOTHESIS['hypothesis_id'], 'task_type': 'exploratory_backtest',
                'agent2_task_contract_version': 2,
                'research_objective_id': OBJECTIVE['objective_id'],
                'hypothesis_id': HYPOTHESIS['hypothesis_id'],
                'required_tools': ['regime190_exploratory_v1'],
                'required_data': ['naver_kospi_daily.csv', 'naver_kosdaq_daily.csv'],
                'pit_requirements': 'EXPLORATORY_PIT_UNVERIFIED',
                'execution_class': 'SERVER_EXECUTABLE', 'priority': 0,
                'dependencies': [], 'delay_hours': 0, 'input_artifacts': [],
                'resource_budget': {'max_seconds': 30, 'max_attempts': 1},
                'validation_rules': ['verify_exploratory', 'official_performance_claim=false'],
                'expected_artifacts': ['chronological_timeline', 'metrics_json'],
                'retry_policy': {'max_attempts': 1}}]}


def _summary(result: dict, task: dict, artifact: Path, repo: Path) -> dict:
    rows = result['timeline']
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True,
                            capture_output=True, timeout=3, check=True).stdout.strip()
    return {'schema_version': 1, 'objective': OBJECTIVE, 'hypothesis': HYPOTHESIS,
            'experiment_id': 'index_regime_exploratory_v1',
            'parent_hypothesis_id': None, 'changed_parameters': {},
            'reason_for_change': 'First fixed exploratory hypothesis',
            'execution_success': True, 'data_validity': 'INDEX_SNAPSHOT_VALIDATED',
            'pit_validity': 'BLOCKED', 'statistical_validity': 'INCONCLUSIVE_OVERLAPPING_EVENTS',
            'out_of_sample_validity': 'NOT_VALIDATED', 'research_value': 'EXPLORATORY_ONLY',
            'deployment_readiness': 'NOT_READY', 'research_decision': 'REQUIRE_PIT_EVIDENCE',
            'model_status': 'DETERMINISTIC_NON_AI',
            'code_commit': commit,
            'code_sha256': hashlib.sha256(CODE_PATH.read_bytes()).hexdigest(),
            'random_seed': None,
            'execution_assumptions': {'signal': 'after unverified daily close',
                'fill': 'next common session open', 'settle': 'following common session open',
                'cost_one_way': 0.0015, 'position_cap': 1.0},
            'checkpoint_id': task['checkpoint_id'],
            'artifact_path': str(artifact),
            'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
            'source_provenance': result['source_provenance'],
            'parameter_version': result['strategy_version'],
            'tested_period': [rows[0]['date'], rows[-1]['date']],
            'timeline_rows': len(rows),
            'regime_counts': result['regime_counts'],
            'crash_warning_exploratory': result['crash_warning_exploratory'],
            'crash_episode_proxy_exploratory': result['crash_episode_proxy_exploratory'],
            'recovery_exploratory': result['recovery_exploratory'],
            'strategy_metrics_exploratory': result['strategy_metrics_exploratory'],
            'segment_metrics_exploratory': result['segment_metrics_exploratory'],
            'walk_forward_diagnostic': result['walk_forward_diagnostic'],
            'next_action': 'Verify source publication times, vintages, market membership and execution assumptions',
            'limitations': result['limitations']}


def cycle(state_dir: Path, repo: Path, mode: str) -> dict:
    validate_objective(OBJECTIVE)
    validate_hypothesis(HYPOTHESIS)
    if mode not in {'official', 'exploratory'}:
        raise ValueError('Unknown research mode')
    eligibility = pit_eligibility()
    if mode == 'official':
        if not eligibility['eligible_indicator_ids']:
            return {'status': 'BLOCKED_PIT', 'pipeline_executed': False,
                    'real_data_backtest_complete': False, 'eligibility': eligibility,
                    'next_action': 'Obtain independently verified row-level PIT evidence'}
        raise ValueError('Official strategy not implemented; eligible features need reviewed plan')
    if eligibility['eligible_indicator_ids']:
        raise ValueError('Exploratory plan requires review after PIT eligibility changes')
    path = state_dir / 'agent2_regime190_plan.json'
    with locked_state(state_dir):
        if (state_dir / 'STOP').exists():
            return {'status': 'STOPPED'}
        if (state_dir / 'research_memory.json').exists():
            memory = json.loads((state_dir / 'research_memory.json').read_text())
            if memory.get('experiment_id') != HYPOTHESIS['hypothesis_id']:
                raise ValueError('Existing memory belongs to another experiment')
            artifact = Path(memory['artifact_path'])
            if (not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != memory['artifact_sha256']
                    or memory.get('code_sha256') != hashlib.sha256(CODE_PATH.read_bytes()).hexdigest()
                    or any(hashlib.sha256((SOURCE_DIR / ('naver_' + market.lower() + '_daily.csv')).read_bytes()).hexdigest()
                           != detail['sha256'] for market, detail in memory['source_provenance'].items())):
                raise ValueError('Stored experiment inputs or artifact changed; use a new reviewed state directory')
            return {'status': 'ALREADY_EVALUATED', 'checkpoint_id': memory['checkpoint_id'],
                    'research_decision': memory['research_decision']}
        if path.exists():
            stored = json.loads(path.read_text())
            stored.pop('updated_at_utc', None)
            if stored != _plan():
                raise ValueError('Stored plan changed')
        else:
            write_state(path, _plan())
    offline_worker.prepare(path, state_dir, repo)
    run = offline_worker.run(state_dir, repo, max_tasks=1, max_seconds=60)
    with locked_state(state_dir):
        queue = offline_worker._load_queue(state_dir)
        task = queue['tasks'][HYPOTHESIS['hypothesis_id']]
        if task['status'] != 'COMPLETED':
            return {'status': task['status'], 'pipeline_executed': False,
                    'real_data_backtest_complete': False, 'worker': run}
        artifact = Path(task['output_artifacts'][0])
        payload = offline_worker._verify_output(offline_worker._adapter(queue['adapter']), task)
        memory = _summary(payload['result'], task, artifact, repo)
        write_state(state_dir / 'research_memory.json', memory)
        write_state(state_dir / 'agent2_handoff.json', {'schema_version': 1,
            'objective_id': OBJECTIVE['objective_id'], 'executed': [task['task_id']],
            'succeeded': [task['task_id']], 'failed': [], 'blocked': ['official_backtest:PIT'],
            'new_code_required': ['PIT-approved source adapter', 'independent regime calibration'],
            'next_action': memory['next_action'], 'model_status': 'DETERMINISTIC_NON_AI'})
        return {'status': 'EXPLORATORY_COMPLETE_OFFICIAL_BLOCKED', 'pipeline_executed': True,
                'real_data_backtest_complete': False, 'checkpoint_id': task['checkpoint_id'],
                'timeline_rows': memory['timeline_rows'], 'tested_period': memory['tested_period'],
                'research_decision': memory['research_decision'],
                'model_status': memory['model_status']}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('official', 'exploratory'), required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(cycle(args.state_dir, args.repo, args.mode), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
