"""Allowlisted, side-effect-free fixture tool for Agent 2.0 loop tests."""
from __future__ import annotations


def execute(task: dict, queue: dict) -> dict:
    values = task['synthetic_values']
    if not isinstance(values, list) or not 3 <= len(values) <= 32 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not -100 <= v <= 100
            for v in values):
        raise ValueError('Invalid bounded synthetic values')
    return {'synthetic': True, 'sample_size': len(values),
            'mean': sum(values) / len(values), 'tool_version': '1.0',
            'pit_status': 'NOT_APPLICABLE_SYNTHETIC', 'performance_claim': False}


def verify(task: dict, result: dict) -> None:
    if (result.get('synthetic') is not True or result.get('performance_claim') is not False
            or result.get('sample_size') != len(task['synthetic_values'])
            or result.get('tool_version') != '1.0'
            or abs(result.get('mean', float('inf')) -
                   sum(task['synthetic_values']) / len(task['synthetic_values'])) > 1e-9):
        raise ValueError('Synthetic result verification failed')
