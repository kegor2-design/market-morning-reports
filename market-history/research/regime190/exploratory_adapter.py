"""Fixed offline-worker adapter. No database writes, network, or orders."""
from .exploratory_backtest import execute_exploratory, verify_exploratory


def execute(task: dict, queue: dict) -> dict:
    if task['task_type'] != 'exploratory_backtest' or queue['adapter'] != 'regime190_exploratory':
        raise ValueError('Unregistered exploratory task')
    return execute_exploratory()


def verify(task: dict, result: dict) -> None:
    if task['task_type'] != 'exploratory_backtest':
        raise ValueError('Unregistered exploratory task')
    verify_exploratory(result)
