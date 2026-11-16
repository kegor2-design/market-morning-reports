"""Host-reviewed goal planner for the two currently supported research families.

This deterministic fallback uses zero model calls. It never turns a free-form
goal into a new executable action or relaxes the PIT/holdout policy.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from jsonschema import validate

from .engine import canonical

SCHEMA = Path(__file__).with_name('research_program.schema.json')
SERIES = ('UST_2Y', 'UST_10Y', 'NYFED_SOFR')
ACTIONS = {'DATA_DISCOVERY': 'CHECK_EXISTING_DATA',
           'DATA_ACQUISITION': 'DATA_RECOVERY',
           'PIT_VALIDATION': 'EVIDENCE_WORKFLOW',
           'EXPERIMENT_EXECUTION': 'RATE_ANALYSIS'}


def dates_for(plan: dict) -> list[str]:
    start = date.fromisoformat(plan['research_period']['start'])
    end = date.fromisoformat(plan['research_period']['end'])
    if start > end or (end - start).days > 31:
        raise ValueError('Unsupported research date span')
    return [(start + timedelta(days=i)).isoformat()
            for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5]


def validate_plan(plan: dict) -> None:
    validate(plan, json.loads(SCHEMA.read_text()))
    tasks = plan['tasks']
    ids = [task['task_id'] for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate task ID')
    identities = [(task['task_type'], canonical(task['inputs'])) for task in tasks]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate task type and inputs')
    graph = {task['task_id']: task['dependencies'] for task in tasks}
    for task in tasks:
        if task['allowed_actions'] != [ACTIONS[task['task_type']]]:
            raise ValueError('Unreviewed task action')
        if any(dep not in graph or dep == task['task_id'] for dep in task['dependencies']):
            raise ValueError('Unknown or self dependency')
        if task['task_type'] in {'DATA_DISCOVERY', 'DATA_ACQUISITION'} and \
                task['inputs'].get('series') not in SERIES:
            raise ValueError('Unreviewed data requirement')
        if task['resource_budget']['max_model_calls'] != 0 or \
                task['resource_budget']['max_network_requests'] != \
                (1 if task['task_type'] == 'DATA_ACQUISITION' else 0) or \
                task['resource_budget']['max_seconds'] > 60 or \
                task['estimated_cost'] != 0 or task['retry_policy'] != {'max_retries': 0}:
            raise ValueError('Unreviewed task budget or retry policy')
    visiting, visited = set(), set()
    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError('Cyclic research task graph')
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in graph[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)
    for task_id in ids:
        visit(task_id)
    if plan['resource_budget']['max_model_calls'] != 0 or \
            plan['safety_policy']['official_claim_allowed'] is not False or \
            plan['safety_policy']['read_only'] is not True or \
            plan['safety_policy']['production_changes'] is not False:
        raise ValueError('Planner attempted to alter safety policy')
    if set(plan['data_requirements']) != set(SERIES) or \
            set(plan['allowed_sources']) != {'US_TREASURY', 'NYFED_REFERENCE_RATES', 'FRED_ALFRED'}:
        raise ValueError('Unreviewed data or source set')
    if not dates_for(plan):
        raise ValueError('No reviewed observation dates')


def _task(task_id: str, kind: str, priority: int, *, dependencies=(), inputs=None) -> dict:
    return {'task_id': task_id, 'task_type': kind, 'dependencies': list(dependencies),
            'inputs': inputs or {}, 'outputs': [task_id + '_result'],
            'priority': priority, 'estimated_cost': 0,
            'resource_budget': {'max_seconds': 60, 'max_network_requests':
                                1 if kind == 'DATA_ACQUISITION' else 0,
                                'max_model_calls': 0},
            'allowed_actions': [ACTIONS[kind]], 'retry_policy': {'max_retries': 0},
            'verification_rule': 'independent_source_recompute'
            if kind == 'DATA_ACQUISITION' else 'independent_result_recompute',
            'status': 'PENDING', 'checkpoint': None, 'next_action': None}


def plan_goal(goal: str) -> dict:
    if not isinstance(goal, str) or not 10 <= len(goal) <= 1000:
        raise ValueError('Research goal length invalid')
    lowered = goal.lower()
    korean = ('한국' in goal and ('하락' in goal or '폭락' in goal or '증시' in goal)) or \
        'indicator 116' in lowered or '지표 116' in goal
    rates = any(word in lowered for word in ('sofr', 'treasury', 'yield', 'rate spread')) or \
        any(word in goal for word in ('금리차', '미국 금리'))
    if not korean and not rates:
        raise ValueError('Unsupported goal: no reviewed data and analysis contract')
    goal_id = 'research_' + hashlib.sha256(goal.encode()).hexdigest()[:12]
    tasks = []
    if korean:
        tasks.append(_task('pit_ind116', 'PIT_VALIDATION', 0,
                           inputs={'indicator': '116'}))
    for priority, series in enumerate(SERIES, start=10):
        tasks.append(_task('discover_' + series.lower(), 'DATA_DISCOVERY', priority,
                           inputs={'series': series}))
    tasks.append(_task('analyze_rates', 'EXPERIMENT_EXECUTION', 40,
                       dependencies=[task['task_id'] for task in tasks
                                     if task['task_type'] == 'DATA_DISCOVERY'],
                       inputs={'hypothesis': 'Positive 10Y-2Y spread predicts next-day SOFR rise',
                               'train_rows': 12}))
    result = {'schema_version': 1, 'goal_id': goal_id, 'research_goal': goal,
              'market': 'KR_EQUITY_CONTEXT' if korean else 'US_RATES',
              'research_period': {'start': '2018-04-03', 'end': '2018-04-30',
                                  'resolution': 'daily'},
              'data_requirements': list(SERIES),
              'research_hypotheses': ['Positive 10Y-2Y spread predicts next-day SOFR rise'],
              'evaluation_methods': ['predeclared chronological train/validation sign test',
                                     'independent recomputation from hashed official sources'],
              'pit_requirements': 'Historical first-access timestamps required for official use',
              'holdout_requirements': 'Sealed independent market holdout required for predictive claim',
              'allowed_sources': ['US_TREASURY', 'NYFED_REFERENCE_RATES', 'FRED_ALFRED'],
              'resource_budget': {'max_seconds': 300, 'max_network_requests': 3,
                                  'max_model_calls': 0, 'max_tasks': 12},
              'completion_criteria': 'Exploratory rates analysis and independent source recomputation; no investment claim',
              'safety_policy': {'read_only': True, 'official_claim_allowed': False,
                                'production_changes': False},
              'default_reasons': ['No dates supplied: fixed reviewed April 2018 window with published SOFR coverage',
                                  'No predictive target specified: predeclared exploratory next-day SOFR direction',
                                  'No sealed holdout available: official prediction claim blocked'],
              'tasks': tasks}
    validate_plan(result)
    return result
