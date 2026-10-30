#!/usr/bin/env python3
"""Assumption-only index trend and crash baseline; never claims verified PIT."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score, precision_score, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'daily-index-validation-20261021'
FEATURES = ['ret1', 'ret5', 'ret20', 'ma20_gap', 'vol20', 'drawdown60', 'range1']
HORIZONS = (1, 3, 5, 10, 20)


def output(name, rows):
    path = HERE / name
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def load(market):
    npath = SOURCE / f'naver_{market}_daily.csv'
    ypath = SOURCE / f'{market}_daily.csv'
    n = pd.read_csv(npath, parse_dates=['date']).rename(columns={'close': 'naver_close'})
    y = pd.read_csv(ypath, parse_dates=['date'])[['date', 'close']].rename(columns={'close': 'yahoo_close'})
    n = n[(n.date >= '2010-01-01') & (n.date <= '2026-10-20')]
    d = n.merge(y, on='date', validate='one_to_one').sort_values('date')
    d = d[(d.naver_close - d.yahoo_close).abs() <= .0101].copy()
    d = d[(d.open > 0) & (d.high >= d[['open', 'naver_close']].max(axis=1)) &
          (d.low <= d[['open', 'naver_close']].min(axis=1)) & (d.high >= d.low)]
    d = d.rename(columns={'naver_close': 'close'}).reset_index(drop=True)
    c = d.close
    d['ret1'] = c.pct_change()
    d['ret5'] = c.pct_change(5)
    d['ret20'] = c.pct_change(20)
    d['ma20_gap'] = c / c.rolling(20).mean() - 1
    d['vol20'] = d.ret1.rolling(20).std()
    d['drawdown60'] = c / c.rolling(60).max() - 1
    d['range1'] = (d.high - d.low) / c
    for h in HORIZONS:
        d[f'forward_{h}'] = c.shift(-h) / c - 1
    d['crash5'] = pd.concat([c.shift(-k) / c - 1 for k in range(1, 6)], axis=1).min(axis=1)
    d.loc[d.index >= len(d) - 5, 'crash5'] = np.nan
    source = {'market': market.upper(), 'agreed_valid_rows': len(d),
              'start': str(d.date.min().date()), 'end': str(d.date.max().date()),
              'naver_sha256': hashlib.sha256(npath.read_bytes()).hexdigest(),
              'yahoo_sha256': hashlib.sha256(ypath.read_bytes()).hexdigest()}
    return d, source


def mask(d, start, end, h):
    result = (d.date >= start) & (d.date <= end)
    last = d.index[d.date <= end].max()
    return result & (d.index <= last - h)


def model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight='balanced'))


def run():
    trend_rows, crash_rows, fold_rows, pit_rows, sources = [], [], [], [], []
    for market in ('kospi', 'kosdaq'):
        d, source = load(market)
        sources.append(source)
        valid_features = d[FEATURES].notna().all(axis=1)
        for h in HORIZONS:
            label = np.select([d[f'forward_{h}'] < -.005 * np.sqrt(h),
                               d[f'forward_{h}'] > .005 * np.sqrt(h)], [-1, 1], default=0)
            valid = valid_features & d[f'forward_{h}'].notna()
            train = valid & mask(d, '2010-01-01', '2017-12-31', h)
            fitted = model().fit(d.loc[train, FEATURES], label[train])
            for split, start, end in [('validation', '2018-01-01', '2021-12-31'),
                                      ('final_holdout', '2022-01-01', '2026-10-20')]:
                test = valid & mask(d, start, end, h)
                actual = label[test]
                pred = fitted.predict(d.loc[test, FEATURES])
                trend_rows.append({'market': market.upper(), 'split': split, 'horizon_days': h,
                                   'train_rows': int(train.sum()), 'test_rows': int(test.sum()),
                                   'balanced_accuracy': balanced_accuracy_score(actual, pred),
                                   'macro_f1': f1_score(actual, pred, average='macro', zero_division=0),
                                   'status': 'CONSERVATIVE_ASSUMPTION'})
        valid = valid_features & d.crash5.notna()
        label = (d.crash5 <= -.05).astype(int)
        train = valid & mask(d, '2010-01-01', '2017-12-31', 5)
        validation = valid & mask(d, '2018-01-01', '2021-12-31', 5)
        fitted = model().fit(d.loc[train, FEATURES], label[train])
        p = fitted.predict_proba(d.loc[validation, FEATURES])[:, 1]
        threshold = max(np.arange(.05, 1, .05),
                        key=lambda t: (f1_score(label[validation], p >= t, zero_division=0), t))
        for split, test in [('validation', validation),
                            ('final_holdout', valid & mask(d, '2022-01-01', '2026-10-20', 5))]:
            actual = label[test]
            pred = fitted.predict_proba(d.loc[test, FEATURES])[:, 1] >= threshold
            crash_rows.append({'market': market.upper(), 'split': split, 'horizon_days': 5,
                               'train_rows': int(train.sum()), 'test_rows': int(test.sum()),
                               'crash_events': int(actual.sum()), 'validation_threshold': threshold,
                               'precision': precision_score(actual, pred, zero_division=0),
                               'recall': recall_score(actual, pred, zero_division=0),
                               'f1': f1_score(actual, pred, zero_division=0),
                               'balanced_accuracy': balanced_accuracy_score(actual, pred),
                               'false_positive_rate': ((pred == 1) & (actual == 0)).sum() / max(1, (actual == 0).sum()),
                               'status': 'CONSERVATIVE_ASSUMPTION'})
        for start, end in [('2016-01-01', '2017-12-31'),
                           ('2018-01-01', '2019-12-31'), ('2020-01-01', '2021-12-31')]:
            first = d.index[d.date >= start].min()
            fold_train = valid & (d.index < first - 20)
            fold_test = valid & mask(d, start, end, 5)
            fold_model = model().fit(d.loc[fold_train, FEATURES], label[fold_train])
            prediction = fold_model.predict_proba(d.loc[fold_test, FEATURES])[:, 1] >= .5
            fold_rows.append({'market': market.upper(), 'start': start, 'end': end,
                              'embargo_rows': 20, 'fixed_threshold': .5, 'train_rows': int(fold_train.sum()),
                              'test_rows': int(fold_test.sum()), 'events': int(label[fold_test].sum()),
                              'precision': precision_score(label[fold_test], prediction, zero_division=0),
                              'recall': recall_score(label[fold_test], prediction, zero_division=0),
                              'f1': f1_score(label[fold_test], prediction, zero_division=0),
                              'status': 'CONSERVATIVE_ASSUMPTION'})
        pit_rows.append({'market': market.upper(), 'agreed_source_rows': len(d),
                         'official_pit_verified_rows': 0, 'assumption_based_rows': len(d),
                         'assumption': 'signal after session t close; first action next trading day',
                         'limitation': 'historical revision and publication timestamps unavailable',
                         'status': 'CONSERVATIVE_ASSUMPTION'})
    output('regime_backtest_summary.csv', trend_rows)
    output('crash_warning_backtest_summary.csv', crash_rows)
    output('walkforward_validation.csv', fold_rows)
    output('pit_validation_summary.csv', pit_rows)
    manifest = {'completed_at_utc': datetime.now(timezone.utc).isoformat(),
                'sources': sources, 'features': FEATURES, 'horizons': HORIZONS,
                'development': '2010-2017', 'validation': '2018-2021',
                'frozen_holdout': '2022-2026-10-20', 'embargo_rows': 20,
                'status': 'ASSUMPTION_ONLY_NOT_OFFICIAL_PIT'}
    (HERE / 'phase2_baseline_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    print(json.dumps(run()))
