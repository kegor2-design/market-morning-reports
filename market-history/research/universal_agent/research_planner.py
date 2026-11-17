"""Host-reviewed goal planner for the two currently supported research families.

This deterministic fallback uses zero model calls. It never turns a free-form
goal into a new executable action or relaxes the PIT/holdout policy.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

from jsonschema import validate

from .engine import canonical

SCHEMA = Path(__file__).with_name('research_program.schema.json')
SERIES = ('UST_2Y', 'UST_10Y', 'NYFED_SOFR')
ACTIONS = {'DATA_DISCOVERY': 'CHECK_EXISTING_DATA',
           'DATA_ACQUISITION': 'DATA_RECOVERY',
           'DATA_CALENDAR_REVALIDATION': 'DATA_RECOVERY',
           'DATA_SCHEMA_REVALIDATION': 'DATA_RECOVERY',
           'PIT_VALIDATION': 'EVIDENCE_WORKFLOW',
           'EXPERIMENT_EXECUTION': 'RATE_ANALYSIS',
           'KR_INDEX_VALIDATION': 'VERIFY_HASHED_INDEX',
           'KR_CRASH_ANALYSIS': 'ANALYZE_KR_CRASH_WINDOWS'}
APPROVED_INDEPENDENT_RATES_GOAL = (
    'Study Treasury yield spread and SOFR from 2018-04-03 to 2018-04-30 '
    'as an explicitly approved independent exploratory research goal.')


class UnsupportedGoal(ValueError):
    """The reviewed source and action registry cannot fulfill this goal."""


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
        if task['task_type'] in {'DATA_DISCOVERY', 'DATA_ACQUISITION',
                                'DATA_CALENDAR_REVALIDATION',
                                'DATA_SCHEMA_REVALIDATION'} and \
                task['inputs'].get('series') not in SERIES:
            raise ValueError('Unreviewed data requirement')
        if task['task_type'] == 'DATA_CALENDAR_REVALIDATION' and \
                (not isinstance(task['inputs'].get('calendar_revision_sha256'), str) or
                 len(task['inputs']['calendar_revision_sha256']) != 64):
            raise ValueError('Unreviewed calendar revision')
        if task['task_type'] == 'DATA_SCHEMA_REVALIDATION' and \
                (not isinstance(task['inputs'].get('schema_revision_sha256'), str) or
                 len(task['inputs']['schema_revision_sha256']) != 64):
            raise ValueError('Unreviewed schema revision')
        if task['resource_budget']['max_model_calls'] != 0 or \
                task['resource_budget']['max_network_requests'] != \
                (1 if task['task_type'] == 'DATA_ACQUISITION' else 0) or \
                task['resource_budget']['max_seconds'] > 60 or \
                task['estimated_cost'] != 0 or task['retry_policy'] != {'max_retries': 0}:
            raise ValueError('Unreviewed task budget or retry policy')
    visiting, visited = set(), set()
    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError('Cyclic research DAG task graph')
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
    if plan['goal_contract']['original_research_goal'] != plan['research_goal'] or \
            plan['goal_contract']['goal_id'] != plan['goal_id'] or \
            plan['goal_contract']['market'] != plan['market'] or \
            plan['goal_contract']['research_period'] != plan['research_period'] or \
            plan['goal_contract']['hypotheses'] != plan['research_hypotheses'] or \
            plan['goal_contract']['data_requirements'] != plan['data_requirements'] or \
            plan['goal_contract']['allowed_sources'] != plan['allowed_sources'] or \
            plan['goal_contract']['evaluation_methods'] != plan['evaluation_methods'] or \
            plan['goal_contract']['resource_budget'] != plan['resource_budget'] or \
            not ({a for t in tasks for a in t['allowed_actions']} <=
                 set(plan['goal_contract']['allowed_actions'])):
        raise ValueError('Goal contract diverges from research plan')
    allowed_child_id = 'research_' + hashlib.sha256(
        APPROVED_INDEPENDENT_RATES_GOAL.encode()).hexdigest()[:12]
    if plan['goal_contract']['approved_independent_goal_ids'] not in ([], [allowed_child_id]):
        raise ValueError('Unreviewed independent research goal')
    if plan['goal_contract']['approved_independent_goal_ids'] and \
            not ('차단' in plan['research_goal'] and '독립' in plan['research_goal'] and
                 'SOFR' in plan['research_goal'].upper()):
        raise ValueError('Independent research was not explicitly requested')
    if plan['goal_contract']['version'] == 2:
        from .rate_analysis import SIGNALS
        original = plan['goal_contract']['original_research_goal']
        baseline = plan_goal(original)
        if (plan['goal_id'] != baseline['goal_id'] or
                plan['research_goal'] != original or
                plan['market'] != 'US_RATES' or
                plan['research_period'] != baseline['research_period'] or
                plan['allowed_sources'] != baseline['allowed_sources'] or
                plan['data_requirements'] != baseline['data_requirements'] or
                plan['resource_budget'] != baseline['resource_budget'] or
                plan['safety_policy'] != baseline['safety_policy'] or
                plan['goal_contract']['target'] != baseline['goal_contract']['target'] or
                plan['goal_contract']['pit_policy'] != baseline['goal_contract']['pit_policy'] or
                plan['goal_contract']['holdout_policy'] != baseline['goal_contract']['holdout_policy'] or
                plan['goal_contract']['allowed_actions'] != baseline['goal_contract']['allowed_actions'] or
                plan['goal_contract']['terminal_conditions'] != baseline['goal_contract']['terminal_conditions'] or
                plan['goal_contract']['approved_independent_goal_ids'] != [] or
                plan['research_hypotheses'] != [SIGNALS.get(next((t['inputs'].get('signal')
                    for t in tasks if t['task_type'] == 'EXPERIMENT_EXECUTION'), None))] or
                plan['evaluation_methods'] != baseline['evaluation_methods']):
            raise ValueError('Dynamic plan changes immutable Goal or policy contract')
        base_tasks = {t['task_id']: t for t in baseline['tasks']}
        current = {t['task_id']: t for t in tasks}
        if not set(base_tasks) <= set(current) or len(current) > 12:
            raise ValueError('Dynamic DAG omits required reviewed tasks')
        for task_id, base_task in base_tasks.items():
            task = current[task_id]
            if task['task_type'] != base_task['task_type'] or \
                    task['allowed_actions'] != base_task['allowed_actions'] or \
                    task['resource_budget'] != base_task['resource_budget']:
                raise ValueError('Dynamic DAG changes reviewed capability')
            if task['task_type'] == 'DATA_DISCOVERY':
                if (task['inputs'] != base_task['inputs'] or
                        any(dep not in base_tasks or dep == 'analyze_rates'
                            for dep in task['dependencies'])):
                    raise ValueError('Dynamic discovery dependency is unsupported')
            elif (task['inputs'].get('signal') not in SIGNALS or
                  task['inputs'].get('hypothesis') != SIGNALS[task['inputs']['signal']] or
                  task['inputs'].get('train_rows') != 12 or
                  not set(base_tasks) <= set(task['dependencies']) | {'analyze_rates'}):
                raise ValueError('Dynamic analysis signal or dependencies invalid')
        for task_id in set(current) - set(base_tasks):
            task = current[task_id]
            series = task['inputs'].get('series')
            valid_collection = (task['task_type'] == 'DATA_ACQUISITION' and
                task_id == 'collect_' + series.lower())
            valid_schema = (task['task_type'] == 'DATA_SCHEMA_REVALIDATION' and
                series in ('UST_2Y', 'UST_10Y') and
                task_id == 'schema_revalidate_' + series.lower() and
                len(task['inputs'].get('schema_revision_sha256', '')) == 64)
            if (series not in SERIES or not (valid_collection or valid_schema) or
                    task['dependencies'] != ['discover_' + series.lower()]):
                raise ValueError('Dynamic DAG adds unreviewed acquisition')
        # The standard checks below still verify source coverage and DAG cycles.
    if plan['market'] == 'US_RATES':
        period = plan['research_period']
        start, end = date.fromisoformat(period['start']), date.fromisoformat(period['end'])
        if (set(plan['data_requirements']) != set(SERIES) or
                set(plan['allowed_sources']) != {'US_TREASURY', 'NYFED_REFERENCE_RATES'} or
                {t['task_type'] for t in tasks} - {'DATA_DISCOVERY', 'DATA_ACQUISITION',
                                                   'DATA_CALENDAR_REVALIDATION',
                                                   'DATA_SCHEMA_REVALIDATION',
                                                   'EXPERIMENT_EXECUTION'} or
                {t['inputs']['series'] for t in tasks if t['task_type'] == 'DATA_DISCOVERY'} != set(SERIES) or
                sum(t['task_type'] == 'EXPERIMENT_EXECUTION' for t in tasks) != 1 or
                plan['goal_contract']['allowed_actions'] !=
                ['CHECK_EXISTING_DATA', 'DATA_RECOVERY', 'RATE_ANALYSIS'] or
                start < date(2018, 4, 3) or end > date(2023, 12, 31) or
                start.year != end.year or
                not dates_for(plan)):
            raise ValueError('Unreviewed US rates research contract')
    elif plan['market'] == 'KR_EQUITY_EXPLORATORY':
        if (plan['data_requirements'] != ['KOSPI_KOSDAQ_HASHED_SNAPSHOT'] or
                plan['allowed_sources'] != ['NAVER_HASHED_LOCAL'] or
                [t['task_type'] for t in tasks] !=
                ['KR_INDEX_VALIDATION', 'KR_CRASH_ANALYSIS'] or
                tasks[1]['dependencies'] != [tasks[0]['task_id']] or
                plan['goal_contract']['allowed_actions'] !=
                ['ANALYZE_KR_CRASH_WINDOWS', 'VERIFY_HASHED_INDEX']):
            raise ValueError('Unreviewed Korean crash research contract')
    elif plan['market'] == 'KR_EQUITY_CONTEXT':
        if (plan['data_requirements'] != ['INDICATOR_116_PIT_EVIDENCE'] or
                plan['allowed_sources'] != ['FRED_ALFRED'] or
                len(tasks) != 1 or tasks[0]['task_type'] != 'PIT_VALIDATION' or
                tasks[0]['inputs'] != {'indicator': '116'} or
                plan['goal_contract']['allowed_actions'] != ['EVIDENCE_WORKFLOW']):
            raise ValueError('Unreviewed Korean indicator contract')
    else:
        raise ValueError('Unsupported research market')


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
    korean = 'indicator 116' in lowered or '지표 116' in goal
    kr_crash = '한국' in goal and '급락' in goal and '변동성' in goal
    rates = 'sofr' in lowered and ('treasury' in lowered or 'yield' in lowered or
                                  '금리차' in goal or '국채' in goal)
    if not korean and not rates and not kr_crash:
        raise UnsupportedGoal('No reviewed data source and analysis action for this goal')
    fallback_approved = (korean and rates and not kr_crash and
                         '차단' in goal and '독립' in goal)
    if sum((korean, rates, kr_crash)) > 1 and not fallback_approved:
        raise UnsupportedGoal('Multiple research goals require separate goal contracts')
    if fallback_approved:
        rates = False
    if re.search(r'\d{4}년\s*\d{1,2}월', goal):
        raise UnsupportedGoal('Specify a supported research window as two YYYY-MM-DD dates')
    goal_id = 'research_' + hashlib.sha256(goal.encode()).hexdigest()[:12]
    if korean:
        if re.search(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', goal):
            raise UnsupportedGoal('Indicator 116 date-specific PIT research is not reviewed')
        tasks = [_task('pit_ind116', 'PIT_VALIDATION', 0, inputs={'indicator': '116'})]
        period = {'start': '2010-01-04', 'end': '2026-10-26', 'resolution': 'daily'}
        requirements = ['INDICATOR_116_PIT_EVIDENCE']
        sources = ['FRED_ALFRED']
        hypothesis = 'Indicator 116 has verified first-access evidence before market decisions'
        evaluation = ['hashed source and as-of matrix validation']
        defaults = ['Existing reviewed indicator 116 evidence window retained']
    elif kr_crash:
        if re.search(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', goal):
            raise UnsupportedGoal('Date-specific Korean crash research is not reviewed')
        period = {'start': '2010-01-01', 'end': '2025-12-31', 'resolution': 'daily'}
        requirements = ['KOSPI_KOSDAQ_HASHED_SNAPSHOT']
        sources = ['NAVER_HASHED_LOCAL']
        hypothesis = 'Realized KOSPI volatility rises before daily declines of at least 5%'
        evaluation = ['descriptive crash-window volatility versus non-crash windows']
        defaults = ['Reviewed local snapshot window used; official KRX and PIT remain unverified']
        tasks = [_task('validate_kr_index', 'KR_INDEX_VALIDATION', 0),
                 _task('analyze_kr_crashes', 'KR_CRASH_ANALYSIS', 10,
                       dependencies=['validate_kr_index'])]
    else:
        found = re.findall(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', goal)
        if len(found) not in (0, 2):
            raise UnsupportedGoal('Specify both start and end dates in YYYY-MM-DD format')
        start, end = found if found else ('2018-04-03', '2018-04-30')
        if date.fromisoformat(start) < date(2018, 4, 3) or \
                date.fromisoformat(end) > date(2023, 12, 31) or \
                start[:4] != end[:4]:
            raise UnsupportedGoal('Unsupported Treasury/SOFR research period')
        period = {'start': start, 'end': end, 'resolution': 'daily'}
        requirements = list(SERIES)
        sources = ['US_TREASURY', 'NYFED_REFERENCE_RATES']
        hypothesis = 'Positive 10Y-2Y spread predicts next-day SOFR rise'
        evaluation = ['predeclared chronological train/validation sign test',
                      'independent recomputation from hashed official sources']
        defaults = ([] if found else ['No ISO dates supplied: reviewed April 2018 window'])
        tasks = [_task('discover_' + series.lower(), 'DATA_DISCOVERY', priority,
                       inputs={'series': series})
                 for priority, series in enumerate(SERIES, start=10)]
        tasks.append(_task('analyze_rates', 'EXPERIMENT_EXECUTION', 40,
                          dependencies=[task['task_id'] for task in tasks],
                          inputs={'hypothesis': hypothesis, 'train_rows': 12}))
        if len(dates_for({'research_period': period})) < 16:
            raise UnsupportedGoal('Research period too short for sealed chronological split')
    market = ('KR_EQUITY_CONTEXT' if korean else
              'KR_EQUITY_EXPLORATORY' if kr_crash else 'US_RATES')
    contract = {'version': 1, 'goal_id': goal_id, 'original_research_goal': goal,
                'market': market, 'research_period': period,
                'target': ('indicator 116 first-access PIT' if korean else
                           'KOSPI daily decline <= -5%' if kr_crash else 'next-day SOFR direction'),
                'hypotheses': [hypothesis], 'data_requirements': requirements,
                'allowed_sources': sources,
                'allowed_actions': sorted({a for t in tasks for a in t['allowed_actions']} |
                                          ({'DATA_RECOVERY'} if rates else set())),
                'evaluation_methods': evaluation,
                'pit_policy': 'No official claim without row-level historical first-access proof',
                'holdout_policy': 'No predictive claim without sealed independent market holdout',
                'resource_budget': {'max_seconds': 300,
                                    'max_network_requests': 0 if korean or kr_crash else 3,
                                    'max_model_calls': 0,
                                    'max_tasks': 1 if korean else 2 if kr_crash else 12},
                'terminal_conditions': ['RESEARCH_COMPLETED_EXPLORATORY', 'RESEARCH_BLOCKED',
                                        'RESEARCH_FAILED', 'RESEARCH_CANCELLED'],
                'approved_independent_goal_ids': [
                    'research_' + hashlib.sha256(APPROVED_INDEPENDENT_RATES_GOAL.encode()).hexdigest()[:12]
                ] if fallback_approved else []}
    result = {'schema_version': 1, 'goal_id': goal_id, 'research_goal': goal,
              'market': market, 'research_period': period,
              'data_requirements': requirements, 'research_hypotheses': [hypothesis],
              'evaluation_methods': evaluation,
              'pit_requirements': 'Historical first-access timestamps required for official use',
              'holdout_requirements': 'Sealed independent market holdout required for predictive claim',
              'allowed_sources': sources, 'resource_budget': contract['resource_budget'],
              'completion_criteria': ('Verified indicator PIT evidence' if korean else
                'Exploratory crash-window description with hashed snapshot' if kr_crash else
                'Exploratory rates analysis and independent source recomputation; no investment claim'),
              'safety_policy': {'read_only': True, 'official_claim_allowed': False,
                                'production_changes': False},
              'default_reasons': defaults + ['No sealed holdout available: official prediction claim blocked'],
              'goal_contract': contract,
              'tasks': tasks}
    validate_plan(result)
    return result
