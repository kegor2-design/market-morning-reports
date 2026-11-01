"""Bounded Agent 2.0 research contracts and offline plan-execute-evaluate loop.

No model runtime is active. The deterministic adapter exists for fixtures and replay.
The offline worker task_queue.json remains the only task execution state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Protocol

from .engine import locked_state, now, write_state
from . import offline_worker

ID = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
SECRET = re.compile(r'(?i)(api[_-]?key|password|secret|access[_-]?token|postgres(?:ql)?://)')
TOOL = {'tool_id': 'synthetic_signal_check', 'version': '1.0',
        'category': 'STATISTICAL_ANALYSIS', 'input_schema': 'bounded_numeric_list_v1',
        'output_schema': 'synthetic_mean_v1', 'permissions': ['offline_fixture_only'],
        'resource_limits': {'max_seconds': 10, 'max_attempts': 1},
        'side_effects': [], 'test_status': 'fixture_only',
        'execution_environment': 'offline_worker:agent2_synthetic'}


class ModelAdapter(Protocol):
    """Future remote/local backends must provide bounded structured decisions."""
    model_status: str

    def plan(self, objective: dict) -> dict: ...
    def evaluate(self, result: dict) -> dict: ...


def _safe(value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) > 32768 or SECRET.search(encoded):
        raise ValueError('Sensitive or oversized decision content')


def validate_objective(value: dict) -> dict:
    if value.get('schema_version') != 1 or not ID.fullmatch(value.get('objective_id', '')):
        raise ValueError('Invalid objective contract')
    if not isinstance(value.get('question'), str) or not value['question'].strip():
        raise ValueError('Missing research question')
    if value.get('domain') not in {'korean_equity_regime', 'synthetic_fixture'}:
        raise ValueError('Unsupported domain')
    _safe(value)
    return value


def validate_plan(value: dict) -> dict:
    required = ('objective_id', 'hypothesis', 'required_data', 'pit_requirements',
                'experiment_method', 'evaluation_metrics', 'execution_budget',
                'dependencies', 'success_criteria', 'failure_criteria', 'next_actions')
    if value.get('schema_version') != 1 or any(k not in value for k in required):
        raise ValueError('Invalid plan contract')
    if not ID.fullmatch(value['objective_id']) or not ID.fullmatch(value.get('hypothesis_id', '')):
        raise ValueError('Invalid plan identifiers')
    if value.get('tool_id') != TOOL['tool_id'] or value.get('execution_class') != 'SERVER_EXECUTABLE':
        raise ValueError('Tool or execution class is not permitted')
    if value['pit_requirements'] != 'SYNTHETIC_ONLY' or value['dependencies'] != []:
        raise ValueError('Fixture plan cannot make PIT or external dependency claims')
    if value['execution_budget'] != {'max_tasks': 1, 'max_seconds': 10}:
        raise ValueError('Unbounded plan budget')
    if not all(isinstance(value[k], str) and value[k] for k in
               ('hypothesis', 'experiment_method', 'success_criteria', 'failure_criteria')):
        raise ValueError('Missing plan method or criterion')
    if not all(isinstance(value[k], list) and value[k] for k in
               ('required_data', 'evaluation_metrics', 'next_actions')):
        raise ValueError('Missing plan evidence or next action')
    _safe(value)
    return value


def validate_hypothesis(value: dict) -> dict:
    if (value.get('schema_version') != 1 or not ID.fullmatch(value.get('hypothesis_id', ''))
            or not ID.fullmatch(value.get('objective_id', ''))
            or not isinstance(value.get('statement'), str) or not value['statement'].strip()
            or not isinstance(value.get('falsification'), str) or not value['falsification'].strip()):
        raise ValueError('Invalid hypothesis contract')
    _safe(value)
    return value


def validate_evaluation(value: dict) -> dict:
    if (value.get('execution_success') is not True
            or value.get('data_validity') not in {'SYNTHETIC_VALID', 'INVALID'}
            or value.get('statistical_validity') != 'NOT_ASSESSED'
            or value.get('research_value') != 'FIXTURE_ONLY'
            or value.get('model_status') not in {'MOCKED_PLANNER_NOT_AI', 'OFFLINE_REPLAY_NOT_AI'}
            or not isinstance(value.get('next_proposal'), str)
            or not value['next_proposal'].startswith('CODEX_REQUIRED:')):
        raise ValueError('Invalid evaluation contract')
    _safe(value)
    return value


def validate_tool_candidate(value: dict) -> dict:
    """Record a tool proposal for review; never register or execute its code."""
    if (value.get('schema_version') != 1 or not ID.fullmatch(value.get('tool_id', ''))
            or value.get('status') != 'CODEX_REQUIRED'
            or not isinstance(value.get('specification'), str)
            or not value['specification'].strip()
            or value.get('review_steps') != [
                'isolated_implementation', 'static_validation', 'unit_tests',
                'security_review', 'regression_tests', 'approval', 'activation']):
        raise ValueError('Invalid tool candidate')
    _safe(value)
    return value


class DeterministicTestAdapter:
    model_status = 'MOCKED_PLANNER_NOT_AI'

    def plan(self, objective: dict) -> dict:
        return validate_plan({'schema_version': 1, 'objective_id': objective['objective_id'],
            'hypothesis_id': 'synthetic_mean_positive',
            'hypothesis': 'Fixture mean is positive', 'required_data': ['synthetic_values'],
            'pit_requirements': 'SYNTHETIC_ONLY', 'experiment_method': 'arithmetic_mean',
            'evaluation_metrics': ['sample_size', 'mean'],
            'execution_budget': {'max_tasks': 1, 'max_seconds': 10}, 'dependencies': [],
            'success_criteria': 'sample_size >= 3 and mean > 0',
            'failure_criteria': 'invalid output or nonpositive mean',
            'next_actions': ['review real data and PIT requirements'],
            'tool_id': TOOL['tool_id'], 'execution_class': 'SERVER_EXECUTABLE'})

    def evaluate(self, result: dict) -> dict:
        valid = result.get('synthetic') is True and result.get('sample_size', 0) >= 3
        return validate_evaluation({'execution_success': True, 'data_validity': 'SYNTHETIC_VALID' if valid else 'INVALID',
                'statistical_validity': 'NOT_ASSESSED',
                'research_value': 'FIXTURE_ONLY',
                'hypothesis_outcome': 'SUPPORTED_IN_FIXTURE' if valid and result['mean'] > 0
                                      else 'REJECTED_IN_FIXTURE',
                'next_proposal': 'CODEX_REQUIRED: design real PIT-gated experiment',
                'model_status': self.model_status})


class ReplayAdapter(DeterministicTestAdapter):
    model_status = 'OFFLINE_REPLAY_NOT_AI'

    def __init__(self, decision_path: Path):
        self.decisions = json.loads(decision_path.read_text())
        _safe(self.decisions)

    def plan(self, objective: dict) -> dict:
        plan = validate_plan(self.decisions['plan'])
        if plan['objective_id'] != objective['objective_id']:
            raise ValueError('Replay objective mismatch')
        return plan

    def evaluate(self, result: dict) -> dict:
        expected = self.decisions['expected_result_sha256']
        if hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest() != expected:
            raise ValueError('Replay result mismatch')
        evaluation = self.decisions['evaluation']
        _safe(evaluation)
        if evaluation.get('model_status') != self.model_status:
            raise ValueError('Replay evaluation status mismatch')
        return validate_evaluation(evaluation)


def _worker_plan(plan: dict) -> dict:
    return {'schema_version': 1, 'research_project': 'agent2_synthetic',
            'adapter': 'agent2_synthetic', 'tasks': [{
                'task_id': plan['hypothesis_id'], 'task_type': TOOL['tool_id'],
                'execution_class': 'SERVER_EXECUTABLE', 'priority': 0,
                'dependencies': [], 'delay_hours': 0, 'input_artifacts': [],
                'resource_budget': TOOL['resource_limits'],
                'agent2_task_contract_version': 2,
                'research_objective_id': plan['objective_id'],
                'hypothesis_id': plan['hypothesis_id'],
                'required_tools': [TOOL['tool_id']], 'required_data': plan['required_data'],
                'pit_requirements': plan['pit_requirements'],
                'validation_rules': ['agent2_synthetic.verify'],
                'expected_artifacts': ['result_json'],
                'retry_policy': {'max_attempts': 1},
                'synthetic_values': [1, 2, 3]}]}


def cycle(objective: dict, state_dir: Path, repo: Path, adapter=None) -> dict:
    validate_objective(objective)
    if objective['domain'] != 'synthetic_fixture':
        raise ValueError('Only synthetic fixture execution is enabled')
    adapter = adapter or DeterministicTestAdapter()
    plan = adapter.plan(objective)
    validate_plan(plan)
    plan_path = state_dir / 'agent2_worker_plan.json'
    with locked_state(state_dir):
        if (state_dir / 'STOP').exists():
            return {'stop_reason': 'STOP', 'model_status': adapter.model_status}
        memory_path = state_dir / 'research_memory.json'
        memory = json.loads(memory_path.read_text()) if memory_path.exists() else {
            'schema_version': 1, 'objective': objective, 'experiments': [], 'decisions': [],
            'required_approvals': [], 'next_action': 'execute fixture'}
        if memory['objective'] != objective:
            raise ValueError('Memory objective mismatch')
        if memory['experiments']:
            return {'stop_reason': 'ALREADY_EVALUATED', 'memory': memory,
                    'model_status': adapter.model_status}
        if not plan_path.exists():
            write_state(plan_path, _worker_plan(plan))
        elif {k: v for k, v in json.loads(plan_path.read_text()).items()
              if k != 'updated_at_utc'} != _worker_plan(plan):
            raise ValueError('Stored worker plan changed')
    queue = offline_worker.prepare(plan_path, state_dir, repo)
    if len(queue['tasks']) != 1:
        raise ValueError('Unexpected fixture queue')
    run = offline_worker.run(state_dir, repo, max_tasks=1, max_seconds=10)
    with locked_state(state_dir):
        queue = offline_worker._load_queue(state_dir)
        task = queue['tasks'][plan['hypothesis_id']]
        if task['status'] != 'COMPLETED':
            return {'stop_reason': task['status'], 'worker': run,
                    'model_status': adapter.model_status}
        result_path = Path(task['output_artifacts'][0])
        result = json.loads(result_path.read_text())['result']
        offline_worker._verify_output(offline_worker._adapter(queue['adapter']), task)
        evaluation = validate_evaluation(adapter.evaluate(result))
        memory['experiments'].append({'hypothesis_id': plan['hypothesis_id'],
            'plan': plan, 'task_id': task['task_id'], 'checkpoint_id': task['checkpoint_id'],
            'result_sha256': hashlib.sha256(result_path.read_bytes()).hexdigest(),
            'result': result, 'evaluation': evaluation, 'tool_version': TOOL['version'],
            'data_version': 'synthetic_fixture_v1', 'model_version': adapter.model_status,
            'executed_at_utc': now()})
        memory['decisions'].append({'at': now(), 'decision': evaluation['hypothesis_outcome']})
        memory['next_action'] = evaluation['next_proposal']
        write_state(memory_path, memory)
        write_state(state_dir / 'agent2_handoff.json', {
            'schema_version': 1, 'objective_id': objective['objective_id'],
            'changed': ['Agent 2.0 fixture memory'], 'executed': [task['task_id']],
            'succeeded': [task['task_id']], 'failed': [], 'blocked': [],
            'new_code_required': ['real model adapter', 'PIT-gated research tools'],
            'next_action': memory['next_action'], 'model_status': adapter.model_status})
        return {'stop_reason': 'BUDGET_EXHAUSTED', 'checkpoint_id': task['checkpoint_id'],
                'evaluation': evaluation, 'model_status': adapter.model_status}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--objective', type=Path, required=True)
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    objective = json.loads(args.objective.read_text())
    adapter = ReplayAdapter(args.replay) if args.replay else DeterministicTestAdapter()
    print(json.dumps(cycle(objective, args.state_dir, args.repo, adapter), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
