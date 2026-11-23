"""Frozen retrospective follow-up after the last reviewed Regime190 snapshot."""
import hashlib
import json
import math
import os
import statistics

from regime190 import agent4_market as regime
from regime190.exploratory_backtest import load_indices
from .engine import canonical
from .isolated_codex import PRIVATE_ROOT, _try_reserve_request

RECORDS_SHA = 'a9564ce0ea2d4524ec3ddebfddc1fbfdca900b936ddf4f90f333a583f9fd6476'
START = '2026-10-21'
END = '2026-11-23'
SNAPSHOT = PRIVATE_ROOT / 'kr_forward_sources' / 'kis_closes.json'
CODES = {'0001': 'kospi', '1001': 'kosdaq'}
BASELINES = {5: 'moving_average', 10: 'momentum', 20: 'moving_average'}


def stage():
    """Host-only, bounded local SELECT. Never overwrite a previously observed vintage."""
    import psycopg2
    if SNAPSHOT.is_symlink() or SNAPSHOT.parent.is_symlink():
        raise ValueError('Invalid source path')
    SNAPSHOT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if SNAPSHOT.exists():
        return
    db = psycopg2.connect(host=os.environ['DB_HOST'], port=os.environ['DB_PORT'],
        dbname=os.environ['DB_NAME'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
        connect_timeout=3, options='-c default_transaction_read_only=on -c statement_timeout=2000')
    try:
        with db, db.cursor() as cur:
            cur.execute("""SELECT market_date, index_code, index_name, close, available_at, collected_at
                FROM public.domestic_index_daily WHERE market_date BETWEEN %s AND %s
                AND source_name = 'kis' AND index_code IN ('0001','1001')
                ORDER BY market_date, index_code LIMIT 101""", ('2026-10-12', END))
            records = [dict(zip(('day','code','name','close','available','collected'),
                                (str(day), code, name, close, str(available), str(collected))))
                       for day, code, name, close, available, collected in cur]
    finally:
        db.close()
    if not 1 <= len(records) <= 100:
        raise ValueError('Observed source range empty or exceeds row budget')
    _try_reserve_request(SNAPSHOT, {'table':'public.domestic_index_daily','source':'kis',
                                   'records':records,'records_sha256':hashlib.sha256(canonical(records)).hexdigest()})


def _joined(history, records, keys):
    series = {key:{} for key in keys}
    for item in records:
        key = CODES.get(item['code'])
        if key not in keys:
            continue
        day = item['day']
        value = item['close']
        if (day in series[key] or not '2026-10-12' <= day <= END or type(value) not in (int,float)
                or not math.isfinite(value) or value <= 0):
            raise ValueError('Invalid follow-up observation')
        series[key][day] = value
    for row in history[-5:]:
        for key in keys:
            close = series[key].get(row['date'])
            if close is None or abs(close - row[key]['close']) > 0.02000001:
                raise ValueError('Five-session overlap failed for ' + key + ' on ' + row['date'])
    days = sorted(day for day in series['kospi'] if day >= START)
    if not days or days[0] != START or days[-1] != END or any(
            set(days) != {d for d in series[key] if d >= START} for key in keys):
        raise ValueError('Follow-up market session coverage differs')
    extension = [{'date':day, **{key:{'close':series[key][day]} for key in keys}} for day in days]
    return history + extension


def _crashes(rows):
    closes = [row['kospi']['close'] for row in rows]
    returns = [b/a-1 for a,b in zip(closes,closes[1:])]
    obs = [(rows[i]['date'], statistics.pstdev(returns[i-21:i-1]), int(returns[i-1] <= -.05))
           for i in range(61,len(rows))]
    train = [(v,y) for day,v,y in obs if day <= '2025-12-31']
    test = [(v,y) for day,v,y in obs if day >= START]
    threshold = statistics.quantiles([v for v,_ in train], n=10, method='inclusive')[-1]
    base = (1+sum(y for _,y in train))/(2+len(train))
    groups = [[y for v,y in train if (v >= threshold) == group] for group in (False,True)]
    probs = [(sum(g)+2*base)/(len(g)+2) for g in groups]
    labels = [y for _,y in test]
    scores = [probs[v >= threshold] for v,_ in test]
    return {'n':len(test),'events':sum(labels),'training_n':len(train),
            'brier':statistics.mean((p-y)**2 for p,y in zip(scores,labels)),
            'baseline_brier':statistics.mean((base-y)**2 for y in labels),
            'average_precision':regime._average_precision(labels,scores),
            'baseline_average_precision':statistics.mean(labels) if any(labels) else None}


def _transitions(history, rows):
    train_rows = [r for r in history if r['date'] <= regime.TRAIN_END]
    signals = {i:regime._signal(train_rows,i) for i in range(60,len(train_rows))}
    labels = {i:r['regime'] for i,r in signals.items()}
    train = [dict(signals[i], labels=regime._labels(train_rows,i,signals[i],labels))
             for i in range(60,len(train_rows)-regime.EMBARGO)]
    fitted = regime._fit(train)
    forward = [regime._signal(rows,i) for i in range(len(history),len(rows))]
    scores = {}
    for horizon, baseline in BASELINES.items():
        pairs = list(zip(forward,forward[horizon:]))
        def loss(model):
            return statistics.mean((regime._predict(fitted,r,horizon,'transition',model)
                                    - (r['regime'] != future['regime']))**2 for r,future in pairs)
        scores[str(horizon)] = {'n':len(pairs),'baseline':baseline,
            'transitions':sum(r['regime'] != f['regime'] for r,f in pairs),
            'brier':loss('six_regime') if pairs else None,
            'baseline_brier':loss(baseline) if pairs else None}
    return {'training_n':len(train),'embargo':regime.EMBARGO,'horizons':scores}


def evaluate(regimes=False):
    if SNAPSHOT.is_symlink() or SNAPSHOT.parent.is_symlink() or SNAPSHOT.stat().st_size > 100000:
        raise ValueError('Unsafe follow-up snapshot')
    data = json.loads(SNAPSHOT.read_bytes())
    records = data['records']
    if (data['source'] != 'kis' or data['table'] != 'public.domestic_index_daily'
            or not 1 <= len(records) <= 100
            or data['records_sha256'] != RECORDS_SHA
            or hashlib.sha256(canonical(records)).hexdigest() != RECORDS_SHA):
        raise ValueError('Invalid staged KIS source')
    history, provenance = (load_indices('1996-01-01', skip_invalid_pre2010=True)
                           if regimes else load_indices('2010-01-01'))
    if history[-1]['date'] != '2026-10-20':
        raise ValueError('Frozen historical boundary changed')
    rows = _joined(history,records,('kospi','kosdaq') if regimes else ('kospi',))
    scores = _transitions(history,rows) if regimes else _crashes(rows)
    return {'status':'EXPLORATORY_ONLY','official_market_claim':False,'pit_status':'PIT_UNVERIFIED',
            'holdout':'RETROSPECTIVE_TEMPORAL_FOLLOWUP','period':[START,END],
            'source_sha256':{**{k:v['sha256'] for k,v in provenance.items()},'KIS':data['records_sha256']},
            'collection_after_1700_local':sum(r['collected'] > r['day'] + ' 17:00:00'
                for r in records if r['day'] >= START and (regimes or r['code'] == '0001')),
            'decision_scenario':'17:00 local wall clock; timezone and first access unverified',
            'scores':scores}


if __name__ == '__main__':
    stage()
    print(hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest())
