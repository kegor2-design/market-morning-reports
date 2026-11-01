"""Existing offline worker adapter for the reviewed Agent 4.0 study."""
from .agent4_market import study, verify as verify_study


def execute(task: dict, queue: dict) -> dict:
    if queue.get('adapter') != 'regime190_agent4' or task.get('task_type') != 'market_intelligence':
        raise ValueError('Unregistered Agent 4.0 task')
    return study()


def verify(task: dict, result: dict) -> None:
    if task.get('task_type') != 'market_intelligence':
        raise ValueError('Unregistered Agent 4.0 result')
    verify_study(result)
