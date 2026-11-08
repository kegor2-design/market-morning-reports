"""Bounded, exploratory three-domain research over an explicitly supplied snapshot.

This coordinator has no database, order, network, or production write capability.
An absent publication clock and unexamined holdout always block official claims.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .engine import locked_state, write_state
from .self_repair import Failure, diagnose, run_stage

STAGES = ('PENDING', 'PLANNING', 'DATA_CHECK', 'HYPOTHESIS_READY',
          'CODE_DEVELOPMENT', 'TESTING', 'BACKTESTING', 'VALIDATING')
TERMINAL = {'COMPLETED', 'REJECTED', 'BLOCKED', 'FAILED', 'PAUSED'}
DOMAINS = ('MARKET_REGIME', 'CHART_PATTERN', 'TRADING_STRATEGY')
HYPOTHESES = {
    'MARKET_REGIME': 'A 20-session drawdown and volatility threshold warns of a 5-session loss',
    'CHART_PATTERN': 'A 20-session breakout with positive volume change predicts a 5-session gain',
    'TRADING_STRATEGY': 'A 20-session trend filter reduces drawdown after explicit transaction costs',
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _metrics(returns: list[float], exposure: list[int]) -> dict:
    equity = peak = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    deviation = statistics.stdev(returns) if len(returns) > 1 else 0
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    return {'net_return': equity - 1, 'max_drawdown': drawdown,
            'sharpe': (_mean(returns) / deviation * math.sqrt(252) if deviation else None),
            'profit_factor': (sum(wins) / -sum(losses) if losses else None),
            'win_rate': len(wins) / len(returns) if returns else None,
            'average_return': _mean(returns),
            'exposure': _mean(exposure), 'observations': len(returns)}


@dataclass(frozen=True)
class ResearchGoal:
    text: str
    goal_id: str


class ResearchPlugin(Protocol):
    domain: str

    def evaluate(self, rows: list[dict], train_end: int, valid_end: int) -> dict: ...


class MarketRegime:
    domain = 'MARKET_REGIME'

    def evaluate(self, rows: list[dict], train_end: int, valid_end: int) -> dict:
        # The threshold is fixed before reading validation labels.
        def signal(i: int) -> int:
            closes = [r['close'] for r in rows[i-20:i]]
            daily = [closes[j] / closes[j-1] - 1 for j in range(1, len(closes))]
            return int(closes[-1] / max(closes) - 1 < -.05 and
                       statistics.stdev(daily) > .012)
        def score(start: int, end: int, prior: float) -> dict:
            pairs = [(signal(i), int(rows[i+5]['close'] / rows[i]['close'] - 1 < -.03))
                     for i in range(start, min(end, len(rows)-5))]
            tp = sum(s and y for s, y in pairs)
            fp = sum(s and not y for s, y in pairs)
            fn = sum(not s and y for s, y in pairs)
            tn = len(pairs) - tp - fp - fn
            brier = _mean([(s - y)**2 for s, y in pairs])
            baseline = _mean([(prior-y)**2 for _, y in pairs])
            return {'n': len(pairs), 'events': tp+fn, 'precision': tp/(tp+fp) if tp+fp else None,
                    'recall': tp/(tp+fn) if tp+fn else None,
                    'false_alarm_rate': fp/(fp+tn) if fp+tn else None,
                    'brier': brier, 'constant_prior_brier': baseline,
                    'pr_auc': None, 'detection_lead_time': None}
        training_labels = [int(rows[i+5]['close']/rows[i]['close']-1 < -.03)
                           for i in range(20, train_end-5)]
        prior = statistics.fmean(training_labels)
        return {'train': score(20, train_end-5, prior),
                'validation': score(train_end, valid_end-5, prior),
                'independent_holdout': 'NOT_AVAILABLE'}


class ChartPattern:
    domain = 'CHART_PATTERN'

    def evaluate(self, rows: list[dict], train_end: int, valid_end: int) -> dict:
        def score(start: int, end: int) -> dict:
            selected, baseline = [], []
            for i in range(start, min(end, len(rows)-5)):
                forward = rows[i+5]['close']/rows[i]['close']-1
                baseline.append(forward)
                prior = rows[i-20:i]
                if rows[i]['close'] > max(r['high'] for r in prior) and rows[i]['volume'] > 1.2 * statistics.fmean(r['volume'] for r in prior):
                    selected.append(forward)
            return {'signals': len(selected), 'mean_forward_return': _mean(selected),
                    'baseline_mean_forward_return': _mean(baseline),
                    'positive_rate': _mean([int(v > 0) for v in selected]),
                    'max_adverse_excursion': None, 'liquidity_verified': False}
        return {'train': score(20, train_end-5),
                'validation': score(train_end, valid_end-5),
                'independent_holdout': 'NOT_AVAILABLE'}


class TradingStrategy:
    domain = 'TRADING_STRATEGY'

    def evaluate(self, rows: list[dict], train_end: int, valid_end: int) -> dict:
        def score(start: int, end: int) -> dict:
            returns, exposure = [], []
            previous = 0
            turnover = 0
            for i in range(start, min(end, len(rows)-1)):
                position = int(rows[i]['close'] > statistics.fmean(r['close'] for r in rows[i-20:i]))
                trade = abs(position - previous)
                turnover += trade
                # Explicit exploratory round-trip components, per one-way trade.
                cost = trade * (.00015 + .00018 + .00030 + .00010)
                returns.append(position * (rows[i+1]['close']/rows[i]['close']-1)-cost)
                exposure.append(position)
                previous = position
            result = _metrics(returns, exposure)
            result.update(turnover=turnover, cost_per_one_way_trade=.00073,
                          tax_model_verified=False, spread_model_verified=False,
                          execution_feasibility_verified=False)
            return result
        return {'train': score(20, train_end-1),
                'validation': score(train_end, valid_end-1),
                'independent_holdout': 'NOT_AVAILABLE'}


PLUGINS = {p.domain: p for p in (MarketRegime(), ChartPattern(), TradingStrategy())}


def load_snapshot(path: Path) -> tuple[list[dict], int]:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Snapshot must be a regular file')
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not {'date', 'open', 'high', 'low', 'close', 'volume'} <= set(reader.fieldnames or []):
            raise ValueError('Missing OHLCV columns')
        rows = [{k: float(row[k]) if k != 'date' else row[k]
                 for k in ('date', 'open', 'high', 'low', 'close', 'volume')}
                for row in reader]
    if len(rows) < 1000 or any(rows[i]['date'] >= rows[i+1]['date'] for i in range(len(rows)-1)):
        raise ValueError('Insufficient or unordered data')
    clean = [row for row in rows if all(math.isfinite(row[k]) and row[k] > 0
             for k in ('open','high','low','close','volume')) and
             row['low'] <= row['high']]
    if len(clean) < 1000 or len(rows)-len(clean) > max(10, len(rows)//100):
        raise ValueError('Too many invalid OHLCV rows')
    return clean, len(rows)-len(clean)


def _transition(state: dict, domain: str, status: str, detail: str = '') -> None:
    record = state['cycles'][domain]
    old = record['status']
    allowed = ((old in STAGES and STAGES.index(old)+1 < len(STAGES)
                and status == STAGES[STAGES.index(old)+1]) or
               (old == 'VALIDATING' and status in TERMINAL) or
               (old in STAGES and status in {'BLOCKED','FAILED','PAUSED'}) or
               (old == 'PAUSED' and status == 'PLANNING'))
    if not allowed:
        raise ValueError(f'Invalid transition {old} -> {status}')
    record['status'] = status
    state['checkpoint_id'] += 1
    state['events'].append({'checkpoint_id': state['checkpoint_id'],
                            'research_id': record['research_id'], 'from': old,
                            'to': status, 'detail': detail})


def run(goal: ResearchGoal, snapshot: Path, state_dir: Path, max_cycles: int = 3,
        max_seconds: int = 120, ai_hypothesis: bool = False) -> dict:
    if not 1 <= max_cycles <= 3 or not 1 <= max_seconds <= 3600:
        raise ValueError('Budget outside permitted range')
    if state_dir.resolve() == snapshot.resolve() or snapshot.resolve().is_relative_to(state_dir.resolve()):
        raise ValueError('State and snapshot paths overlap')
    start = time.monotonic()
    snapshot_hash = digest(snapshot)
    engine_hash = digest(Path(__file__))
    with locked_state(state_dir):
        path = state_dir / 'autonomous_state.json'
        if path.exists():
            state = json.loads(path.read_text())
            if (state['snapshot_sha256'] != snapshot_hash or
                    state['goal'] != goal.__dict__ or
                    state['engine_sha256'] != engine_hash):
                raise ValueError('Goal or snapshot changed; use a new state directory')
            for record in state['cycles'].values():
                if record.get('result_sha256') != (hashlib.sha256(json.dumps(
                        record['result'], sort_keys=True).encode()).hexdigest()
                        if 'result' in record else None):
                    raise ValueError('Research result integrity mismatch')
        else:
            state = {'schema_version': 1, 'goal': goal.__dict__, 'snapshot': str(snapshot.resolve()),
                     'snapshot_sha256': snapshot_hash, 'engine_sha256': engine_hash,
                     'checkpoint_id': 0,
                     'cycles': {domain: {'research_id': f'{goal.goal_id}-{domain.lower()}',
                                        'status': 'PENDING', 'hypothesis': HYPOTHESES[domain],
                                        'generation_method': 'TEMPLATE_GENERATED'} for domain in DOMAINS},
                     'events': [], 'official_claim': False, 'orders_sent': 0}
            write_state(path, state)
        if (state_dir / 'STOP').exists():
            return {'status': 'STOPPED', 'checkpoint_id': state['checkpoint_id']}
        if ai_hypothesis and 'ai_hypothesis' not in state:
            from .isolated_codex import generate
            try:
                state['ai_hypothesis'] = generate(goal.text, state_dir)
            except Exception as exc:
                failure = diagnose(Failure(goal.goal_id, 'AI_HYPOTHESIS',
                                           type(exc).__name__, str(exc), 'isolated Codex'),
                                   state.get('repair_history', []))
                state.setdefault('repair_history', []).append(failure)
                state['ai_hypothesis'] = {'status': 'ENVIRONMENT_BLOCKED',
                                          'failure': failure}
            write_state(path, state)
        rows, excluded = load_snapshot(snapshot)
        train_end = next((i for i, row in enumerate(rows) if row['date'] >= '2012-01-01'), None)
        valid_end = next((i for i, row in enumerate(rows) if row['date'] >= '2018-01-01'), None)
        if train_end is None or valid_end is None or train_end < 1000 or valid_end-train_end < 500:
            raise ValueError('Chronological research windows unavailable')
        processed = 0
        for domain in DOMAINS:
            record = state['cycles'][domain]
            if record['status'] == 'PAUSED':
                _transition(state, domain, 'PLANNING', 'Resume prior research ID')
                write_state(path, state)
            if record['status'] in TERMINAL:
                continue
            if (state_dir / 'STOP').exists() or time.monotonic()-start > max_seconds:
                _transition(state, domain, 'PAUSED', 'STOP or wall-time budget')
                write_state(path, state)
                break
            while record['status'] != 'VALIDATING':
                old = record['status']
                _transition(state, domain, STAGES[STAGES.index(old)+1])
                write_state(path, state)
            outcome = run_stage(goal.goal_id, 'BACKTEST', domain,
                                lambda: PLUGINS[domain].evaluate(rows, train_end, valid_end),
                                state.setdefault('repair_history', []))
            if outcome['status'] != 'COMPLETED':
                failure = outcome['diagnosis']
                record['failure_type'] = failure['error_type']
                record['failure_reason'] = failure['message']
                record['next_action'] = failure['next_action']
                _transition(state, domain, 'FAILED', 'Research calculation failed; independent domains continue')
                write_state(path, state)
                processed += 1
                continue
            result = outcome['result']
            record['result'] = result
            record['result_sha256'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
            record['data_quality'] = {'status': 'OHLCV_CHECKED_PUBLICATION_TIME_UNVERIFIED',
                                      'excluded_invalid_rows': excluded}
            record['pit_status'] = 'PIT_UNVERIFIED'
            record['validation_status'] = 'EXPLORATORY_ONLY'
            record['code_developer'] = 'REPOSITORY_IMPLEMENTATION_NO_CODEX_CALL'
            record['independent_validation'] = 'BLOCKED_NO_UNEXAMINED_PIT_HOLDOUT'
            _transition(state, domain, 'COMPLETED', 'Exploratory calculation completed; official validation blocked')
            write_state(path, state)
            processed += 1
            if processed >= max_cycles:
                break
        state['next_research'] = {'status': 'BLOCKED', 'reason':
            'Acquire licensed PIT release/vintage evidence and an unexamined independent holdout'}
        write_state(path, state)
        return {'status': 'CHECKPOINTED', 'checkpoint_id': state['checkpoint_id'],
                'processed_this_run': processed,
                'cycles': {key: val['status'] for key, val in state['cycles'].items()},
                'ai_hypothesis_status': state.get('ai_hypothesis', {}).get('status'),
                'official_claim': False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--goal', required=True)
    parser.add_argument('--goal-id', required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--max-cycles', type=int, default=3)
    parser.add_argument('--ai-hypothesis', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(ResearchGoal(args.goal, args.goal_id), args.snapshot,
                         args.state_dir, args.max_cycles,
                         ai_hypothesis=args.ai_hypothesis), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
