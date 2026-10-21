"""Read-only MMP audit. Writes only beside this script; no network or database calls."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
MMP = Path('/home/kegor2/MarketMorningPublisher')
DATA = Path('/home/kegor2/MMPData/runtime/data')
REPORTS = Path('/home/kegor2/MMPData/reports/2026-10')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_csv(name, rows, fields):
    with (HERE / name).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def iso(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def main():
    source_cfg = {s['id']: s for s in read(MMP / 'config/sources.json')}
    registry = {s['id']: s for s in read(MMP / 'config/source_registry.json')['sources']}
    days = [(date(2026, 9, 22) + timedelta(days=d)).isoformat() for d in range(30)]
    per_source = defaultdict(lambda: {'attempts7': 0, 'success7': 0, 'attempts17': 0,
                                      'success17': 0, 'attempts30':0, 'success30':0,
                                      'items7': 0, 'last_failure': '',
                                      'failure_reason': '', 'last_success': '', 'last_attempt': '',
                                      'latest_item_lag_minutes': ''})
    daily = []
    for day in days:
        p = DATA / 'raw' / day / 'collection_status.json'
        if not p.exists():
            if day >= '2026-10-05':
                daily.append({'date': day, 'source_attempts': '', 'source_successes': '', 'source_failed': '', 'source_status': 'NO_SNAPSHOT'})
            continue
        statuses = read(p)
        if day >= '2026-10-05':
            daily.append({'date': day, 'source_attempts': len(statuses),
                          'source_successes': sum(bool(s.get('ok')) for s in statuses),
                          'source_failed': sum(not s.get('ok') for s in statuses), 'source_status': 'OBSERVED'})
        for s in statuses:
            x = per_source[s['source_id']]
            x['attempts30'] += 1
            x['success30'] += bool(s.get('ok'))
            if day >= '2026-10-05':
                x['attempts17'] += 1
                x['success17'] += bool(s.get('ok'))
            if day >= '2026-10-15':
                x['attempts7'] += 1
                x['success7'] += bool(s.get('ok'))
                x['items7'] += int(s.get('items') or 0)
            x['last_attempt'] = day
            if s.get('ok'):
                x['last_success'] = day
            else:
                x['last_failure'] = day
                x['failure_reason'] = str(s.get('error') or '')[:180]
            x['latest_item_lag_minutes'] = s.get('latest_item_lag_minutes', '')
    source_rows = []
    for sid, x in sorted(per_source.items()):
        c = source_cfg.get(sid, registry.get(sid, {}))
        source_rows.append({'source_id': sid, 'source_name': c.get('name', ''),
                            'source_type': c.get('kind', c.get('platform', '')),
                            'source_url': c.get('url', ''), 'enabled': c.get('enabled', ''),
                            'collector_name': c.get('collector', ''), **x,
                            'success_rate_7d': round(x['success7']/x['attempts7'], 4) if x['attempts7'] else '',
                            'success_rate_17d': round(x['success17']/x['attempts17'], 4) if x['attempts17'] else '',
                            'success_rate_30d': round(x['success30']/x['attempts30'], 4) if x['attempts30'] else '',
                            'source_reliability': 'UNVERIFIED'})
    write_csv('sources.csv', source_rows, ['source_id','source_name','source_type','source_url','collector_name','enabled','last_attempt','last_success','last_failure','failure_reason','attempts7','success7','success_rate_7d','attempts17','success17','success_rate_17d','attempts30','success30','success_rate_30d','items7','latest_item_lag_minutes','source_reliability'])

    pub = read(DATA / 'state/publication_state.json')
    pipeline = []
    for row in daily:
        day = row['date']
        raw = DATA / 'raw' / day / 'articles.json'
        ev = DATA / 'normalized' / (day + '-events.json')
        outlook = REPORTS / (day + '-outlook.json')
        final = REPORTS / (day + '-premarket-mi-final.json')
        obj = read(outlook) if outlook.exists() else {}
        events = read(ev) if ev.exists() else []
        selection = read(REPORTS / (day + '-data-report.json')).get('news_selection', {}) if (REPORTS / (day + '-data-report.json')).exists() else {}
        quality = obj.get('quality') or {}
        premarket = quality.get('premarket') or {}
        record = pub.get(day) or {}
        row.update({'raw_snapshot_exists': raw.exists(), 'event_count': len(events),
                    'selected_news': selection.get('published', ''),
                    'selection_available': selection.get('available', ''),
                    'quality_status': quality.get('status', ''),
                    'quality_passed': quality.get('passed', ''),
                    'premarket_failed_checks': ';'.join(k for k,v in premarket.get('checks',{}).items() if v is False),
                    'publication_state': record.get('status', ''),
                    'premarket_final_exists': final.exists(),
                    'premarket_url_recorded': bool(record.get('blogger_url')),
                    'premarket_snapshot_match': ''})
        mi = REPORTS / (day + '-premarket-mi.json')
        if final.exists() and mi.exists():
            a, b = read(final), read(mi)
            row['premarket_snapshot_match'] = a.get('morning_snapshot_id') == b.get('snapshot_id')
        pipeline.append(row)
    write_csv('daily_pipeline.csv', pipeline, list(pipeline[0]))

    # The latest raw file is cumulative. Use article_id for uniqueness and only
    # measure records whose collection timestamp is inside the requested window.
    latest = DATA / 'raw/2026-10-21/articles.json'
    articles = read(latest)
    windows = {}
    for n, cutoff in [('7d','2026-10-15'), ('30d','2026-09-22'), ('90d','2026-07-24')]:
        picked = [a for a in articles if str(a.get('collected_at') or '')[:10] >= cutoff]
        ids = [a.get('article_id') for a in picked if a.get('article_id')]
        lags = []
        for a in picked:
            start,end = iso(a.get('published_at')),iso(a.get('collected_at'))
            if start and end:
                lag = (end-start).total_seconds()/3600
                if 0 <= lag <= 24*30: lags.append(lag)
        windows[n] = {'rows_in_latest_cumulative_snapshot': len(picked),
                      'distinct_article_ids': len(set(ids)),
                      'repeat_id_rows': len(ids)-len(set(ids)),
                      'content_stored_true': sum(a.get('content_stored') is True for a in picked),
                      'valid_nonnegative_lags': len(lags),
                      'median_publication_to_collection_hours': round(median(lags),2) if lags else None,
                      'publication_to_collection_over_24h': sum(v>24 for v in lags)}
    (HERE/'metrics.json').write_text(json.dumps({'windows':windows,
        'source_attempts_7d':sum(r['attempts7'] for r in source_rows),
        'source_successes_7d':sum(r['success7'] for r in source_rows),
        'source_attempts_17d':sum(r['attempts17'] for r in source_rows),
        'source_successes_17d':sum(r['success17'] for r in source_rows),
        'source_attempts_30d':sum(r['attempts30'] for r in source_rows),
        'source_successes_30d':sum(r['success30'] for r in source_rows),
        'events_2026_10_21':len(read(DATA/'normalized/2026-10-21-events.json')),
        'verified_events_2026_10_21':sum(e.get('verified') is True for e in read(DATA/'normalized/2026-10-21-events.json')),
        'multi_source_events_2026_10_21':sum(len(e.get('sources') or [])>1 for e in read(DATA/'normalized/2026-10-21-events.json')),
        'events_with_repeated_source_url_2026_10_21':sum(
            len([s.get('url') for s in e.get('sources') or [] if s.get('url')]) >
            len(set(s.get('url') for s in e.get('sources') or [] if s.get('url')))
            for e in read(DATA/'normalized/2026-10-21-events.json'))}, indent=2)+'\n')

    youtube = []
    for s in registry.values():
        if s.get('platform') != 'YOUTUBE': continue
        youtube.append({'channel_id':s['id'], 'channel_name':s['name'], 'url':s.get('url',''),
                        'enabled':s.get('enabled'), 'video_count_30d':'UNVERIFIED',
                        'transcript_success_30d':'UNVERIFIED', 'summary_success_30d':'UNVERIFIED',
                        'claim_extraction_30d':'UNVERIFIED', 'chart_validation_30d':'UNVERIFIED',
                        'MI_usage_30d':'UNVERIFIED'})
    write_csv('youtube_registry.csv', youtube, list(youtube[0]))

    # Descriptive monthly state only. This source has not passed an official
    # KRX cross-check and cannot support a tradeable early-warning backtest.
    market = Path('/home/kegor2/market-morning-reports/market-history/data/korea-market-monthly.csv')
    with market.open(newline='') as f: rows = list(csv.DictReader(f))
    regime = []
    for key in ('kospi','kosdaq'):
        peak = 0.0
        prior = None
        for r in rows:
            if not r.get(key): continue
            value = float(r[key]); peak = max(peak,value)
            dd = value/peak-1
            state = 'DRAWDOWN_20PCT' if dd <= -.2 else ('DRAWDOWN_10_TO_20PCT' if dd <= -.1 else 'OTHER')
            if state != prior:
                regime.append({'index': key.upper(), 'month':r['date'], 'level':round(value,2),
                               'drawdown_pct':round(dd*100,2), 'state':state})
            prior = state
    write_csv('monthly_drawdown_transitions.csv', regime, ['index','month','level','drawdown_pct','state'])


if __name__ == '__main__':
    main()
