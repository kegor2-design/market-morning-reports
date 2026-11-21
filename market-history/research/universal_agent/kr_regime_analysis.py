"""Host-selected Regime190 transition evaluation, excluding its contaminated final split."""
import json
import os
import subprocess
import sys
from pathlib import Path


def evaluate():
    from regime190.agent4_market import study
    data = study()
    return {'status': 'EXPLORATORY_ONLY', 'market': 'KR_EQUITY', 'pit_status': 'PIT_UNVERIFIED',
            'official_market_claim': False, 'split': data['split'],
            'event_definition': data['event_definitions']['transition'],
            'source_sha256': {k: v['sha256'] for k, v in data['source_provenance'].items()},
            'transition_comparison': {h: scores['transition'] for h, scores in
                                      data['baseline_comparison_exploratory'].items()}}


def bounded(seconds):
    if seconds <= 0:
        raise ValueError('Regime analysis deadline exhausted')
    try:
        child = subprocess.run([sys.executable, '-m', 'universal_agent.kr_regime_analysis'],
            env={'PATH': os.defpath, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
            capture_output=True, check=True, timeout=seconds)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise ValueError('Regime analysis timed out or failed') from exc
    return json.loads(child.stdout)


if __name__ == '__main__':
    print(json.dumps(evaluate()))
