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


def bounded(seconds, followup=None):
    if seconds <= 0:
        raise ValueError('Regime analysis deadline exhausted')
    if followup not in (None, 'regime', 'crash'):
        raise ValueError('Unknown Korean evaluation')
    try:
        child = subprocess.run([sys.executable, '-m', 'universal_agent.kr_regime_analysis',
                                *([followup] if followup else [])],
            env={'PATH': os.defpath, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])},
            capture_output=True, check=True, timeout=seconds)
    except subprocess.CalledProcessError as exc:
        line = (exc.stderr or b'').decode(errors='replace').strip().splitlines()
        if followup and line and line[-1].startswith('ValueError:'):
            raise ValueError(line[-1][:200]) from exc
        raise ValueError('Regime analysis failed') from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Regime analysis timed out or failed') from exc
    return json.loads(child.stdout)


if __name__ == '__main__':
    if sys.argv[1:]:
        from .kr_forward_validation import evaluate as forward
        print(json.dumps(forward(regimes=sys.argv[1] == 'regime')))
    else:
        print(json.dumps(evaluate()))
