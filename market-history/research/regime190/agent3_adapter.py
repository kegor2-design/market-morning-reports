"""Strict allowlist for Agent 3.0 research templates; no dynamic code execution."""
from __future__ import annotations

import json
from pathlib import Path

from . import agent3_experiments


def _completed(queue: dict, task_id: str) -> dict:
    record = queue['tasks'][task_id]
    if record['status'] != 'COMPLETED':
        raise ValueError('Prerequisite not completed')
    return json.loads(Path(record['output_artifacts'][0]).read_text())['result']


def execute(task: dict, queue: dict) -> dict:
    if queue.get('adapter') != 'regime190_agent3':
        raise ValueError('Unregistered Agent 3.0 adapter')
    kind = task['task_type']
    if kind == 'pit_investigation':
        return agent3_experiments.investigate_pit()
    if kind == 'label_alignment':
        parent = _completed(queue, 'pit_investigation_v1')
        if parent['eligible_after'] != 0:
            raise ValueError('PIT decision changed')
        return agent3_experiments.label_alignment_experiment()
    if kind == 'hysteresis':
        parent = _completed(queue, 'label_alignment_v1')
        return agent3_experiments.hysteresis_experiment(parent)
    raise ValueError('Unregistered Agent 3.0 task')


def verify(task: dict, result: dict) -> None:
    kind = task['task_type']
    if kind == 'pit_investigation':
        if (result.get('status') != 'PIT_REPAIR_INVESTIGATED_NO_PROMOTION'
                or result.get('eligible_after') != 0
                or len(result.get('blocked_indicators', [])) != 190):
            raise ValueError('Invalid PIT investigation result')
    elif kind == 'label_alignment':
        if (result.get('decision') != 'NONCOMPARABLE_MEASUREMENT_REPAIR'
                or result.get('official_improvement_claim') is not False
                or result.get('final_holdout') != 'FINAL_HOLDOUT_CONTAMINATED_NOT_EVALUATED'):
            raise ValueError('Invalid label alignment result')
    elif kind == 'hysteresis':
        if (result.get('decision') not in {'IMPROVEMENT_UNCONFIRMED', 'HYPOTHESIS_REJECTED_EXPLORATORY'}
                or result.get('official_improvement_claim') is not False
                or result.get('deployment_readiness') != 'NOT_READY'
                or result.get('final_holdout') != 'FINAL_HOLDOUT_CONTAMINATED_NOT_EVALUATED'):
            raise ValueError('Invalid hysteresis result')
    else:
        raise ValueError('Unregistered Agent 3.0 task')
