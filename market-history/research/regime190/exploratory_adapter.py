"""Fixed offline-worker adapter. No database writes, network, or orders."""
from .exploratory_backtest import execute_exploratory, verify_exploratory
from . import autonomous_diagnosis


def execute(task: dict, queue: dict) -> dict:
    if queue['adapter'] != 'regime190_exploratory':
        raise ValueError('Unregistered exploratory task')
    if task['task_type'] == 'exploratory_backtest':
        return execute_exploratory()
    if task['task_type'] == 'diagnosis_experiment':
        return autonomous_diagnosis.execute()
    raise ValueError('Unregistered exploratory task')


def verify(task: dict, result: dict) -> None:
    if task['task_type'] == 'exploratory_backtest':
        verify_exploratory(result)
    elif task['task_type'] == 'diagnosis_experiment':
        autonomous_diagnosis.verify(result)
    else:
        raise ValueError('Unregistered exploratory task')
