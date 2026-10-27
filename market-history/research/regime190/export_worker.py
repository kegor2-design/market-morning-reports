#!/usr/bin/env python3
"""Publish metadata only from the private worker checkpoint; no raw observations."""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from derive_more import COLS

HERE = Path(__file__).resolve().parent
DEFAULT_STATE = Path.home()/'MyDream2000/research/regime190'
DERIVED = {2,3,4,5,8,9,11,15,16,18,19,20,21,22,24,25,27,30,31,35}
FRED_COMPONENT = {117,118,119,120,121,122,125,127,133}
EXACT_DB = {73,74,75,76,78,82,174,175,178,181}
DART_SAMPLE = {152,153,154,155,156}
EVENT_ARCHIVE = set(range(164,172))

def read_csv(path):
    with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def write_csv(path, rows):
    temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
        f.flush()
    temp.replace(path)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--state-dir',type=Path,default=DEFAULT_STATE);args=ap.parse_args()
    state=args.state_dir
    conn=sqlite3.connect(f'file:{state/"checkpoint.sqlite"}?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    tasks={x['indicator_id']:dict(x) for x in conn.execute('SELECT * FROM tasks')}
    assert sorted(tasks)==list(range(1,191))
    probes=json.loads((state/'provider_probe_manifest.json').read_text()) if (state/'provider_probe_manifest.json').exists() else {}
    probe_by_id={i:x for x in probes.values() for i in x['indicator_ids']}
    fred_dates={}
    for path in (state/'raw').glob('fred_*.json'):
        obj=json.loads(path.read_text())
        fred_dates[obj['series_id']]={x['date'] for x in obj['observations'] if x.get('value') not in ('', '.', None)}
    db_metadata={}
    for path in (state/'raw').glob('db_component_*.json'):
        db_metadata[hashlib.sha256(path.read_bytes()).hexdigest()]=json.loads(path.read_text())
    addendum=read_csv(HERE/'derived_addendum.csv')
    derived={}
    for row in addendum:derived.setdefault(int(row['indicator_id']),[]).append(row)
    assert sorted(derived)==sorted(DERIVED)
    original=read_csv(HERE/'inventory_190.csv')
    weekday_denom=len(pd.bdate_range('2010-01-01','2026-10-27'))*2
    rows=[]
    for row in original:
        i=int(row['indicator_id']);task=tasks[i]
        if i in DERIVED:
            parts=derived[i];valid=sum(int(x['valid_count']) for x in parts)
            row.update(availability_status='일부 확보',valid_count=str(valid),
                       missing_pct=str(round(100*(8266-valid)/8266,2)),
                       target_coverage_pct=str(round(100*valid/weekday_denom,2)),
                       first_date=min(x['first_valid'] for x in parts),
                       last_date=max(x['last_valid'] for x in parts),
                       failure_reason='Target ends after raw series; PIT publication/vintage unverified; research parameterization requires reference comparison')
        elif i in FRED_COMPONENT and conn.execute("SELECT 1 FROM requests WHERE indicator_id=? AND result='ACQUIRED' LIMIT 1",(i,)).fetchone():
            ids=[x[0] for x in conn.execute("SELECT series_id FROM requests WHERE indicator_id=? AND result='ACQUIRED'",(i,))]
            dates=set.intersection(*(fred_dates[s] for s in ids if s in fred_dates)) if ids else set()
            row.update(availability_status='일부 확보',actual_source='FRED API current-vintage component',
                       source_url='https://api.stlouisfed.org/fred/series/observations',
                       raw_path='private:FRED series (see worker_source_manifest.csv)',
                       raw_sha256='see worker_source_manifest.csv',frequency='daily_or_weekly',
                       row_count=str(len(dates)),valid_count='0',first_date=min(dates) if dates else '',last_date=max(dates) if dates else '',
                       pit_status='PIT_UNVERIFIED',validation_status='PARTIAL',
                       failure_reason='FRED component acquired; full indicator definition, release timing, and vintages unverified')
        elif i in EXACT_DB and task['state']=='PARTIAL':
            meta=db_metadata.get(task['raw_sha256'])
            row.update(availability_status='원천 확보·계산 미완료' if i in {74,175,178,181} else '일부 확보',
                       actual_source='trading PostgreSQL read-only component',
                       source_url='read-only DB component (see worker_source_manifest.csv)',
                       raw_path='private:DB query summary (not raw observations)',
                       raw_sha256='see worker_source_manifest.csv',
                       row_count=str(meta['nonnull_rows']) if meta else '0',valid_count='0',
                       first_date=meta['first'] if meta else '',last_date=meta['last'] if meta else '',
                       frequency='intraday_or_daily',
                       pit_status='PIT_UNVERIFIED',validation_status='PARTIAL',
                       failure_reason='Short recent DB window; required indicator calculation/market scope/PIT not fully verified')
        elif i in DART_SAMPLE and task['state']=='PARTIAL':
            row.update(availability_status='원천 확보·계산 미완료',actual_source='OpenDART one-company 2025 annual financial statement sample',
                       source_url='https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json',
                       raw_path='private:dart_sample_2025_005930.json',raw_sha256=task['raw_sha256'] or '',
                       frequency='annual_sample',first_date='2025',last_date='2025',row_count='229',valid_count='0',
                       pit_status='PIT_UNVERIFIED',validation_status='PARTIAL_SAMPLE_ONLY',
                       failure_reason='Only one company and one reporting year; market-wide as-of history and calculations missing')
        elif i in EVENT_ARCHIVE and task['state']=='PARTIAL' and i in probe_by_id:
            probe=probe_by_id[i]
            row.update(availability_status='원천 확보·계산 미완료',actual_source='official release archive page',
                       source_url=probe['source_url'],raw_path='private:'+probe['raw_file'],
                       raw_sha256=probe['sha256'],frequency='event_archive_unparsed',
                       first_date='',last_date='',row_count='0',valid_count='0',
                       pit_status='PIT_UNVERIFIED',validation_status='UNPARSED_ARCHIVE',
                       failure_reason='Official page downloaded and hashed, but indicator-specific historical events and publication times are unparsed')
        elif task['state']=='NEEDS_REVIEW' and task['fallback_attempt_count']+task['provider_attempt_count']>0:
            row.update(availability_status='미확보(시도 실패)',
                       failure_reason='Candidate source was queried but the indicator-specific required fields, scope, or rights were not verified')
        row.update(attempt_count=task['attempt_count'],provider_attempt_count=task['provider_attempt_count'],
                   fallback_attempt_count=task['fallback_attempt_count'],last_attempt_at=task['last_attempt_at'] or '',
                   http_or_db_result=task['http_or_db_result'] or '',blocking_evidence=task['blocking_evidence'] or '',
                   next_action=task['next_action'] or '',worker_state=task['state'],pit_eligible='false',
                   derived_series_path=('private:kospi_derived_more.csv;private:kosdaq_derived_more.csv' if i in DERIVED else
                                        ('private:kospi_computed.csv;private:kosdaq_computed.csv' if i in {1,10,12,13,17,26,28,29,32,33,34,36,37,38,39,40} else '')))
        rows.append(row)
    write_csv(HERE/'inventory_190.csv',rows)
    pd.DataFrame(rows).to_excel(HERE/'inventory_190.xlsx',index=False)
    coverage=read_csv(HERE/'coverage_matrix.csv')
    derived_data={m:pd.read_csv(HERE/'private'/f'{m.lower()}_derived_more.csv',parse_dates=['date']) for m in ('KOSPI','KOSDAQ')}
    acquired_fred_dates={}
    for i in FRED_COMPONENT:
        ids=[x[0] for x in conn.execute("SELECT series_id FROM requests WHERE indicator_id=? AND result='ACQUIRED'",(i,))]
        if ids and all(s in fred_dates for s in ids): acquired_fred_dates[i]=set.intersection(*(fred_dates[s] for s in ids))
    for row in coverage:
        i=int(row['indicator_id'])
        if i in DERIVED:
            d=derived_data[row['market']]
            mask=d.date.between(row['start_date'],row['end_date']) & d[COLS[i]].notna().all(axis=1)
            valid=int(mask.sum());row['valid_indicator_rows']=str(valid)
            row['valid_coverage_pct']=str(round(100*valid/int(row['denominator_rows']),2))
        elif i in acquired_fred_dates:
            row['raw_component_rows']=str(sum(row['start_date']<=x<=row['end_date'] for x in acquired_fred_dates[i]))
            row['frequency']='daily_or_weekly'
    write_csv(HERE/'coverage_matrix.csv',coverage)
    pit=read_csv(HERE/'pit_audit.csv')
    for row in pit:
        i=int(row['indicator_id'])
        if i in FRED_COMPONENT and i in acquired_fred_dates:
            row.update(source='FRED API current-vintage component',observation_date='present',published_at='absent',ingested_at='worker collection timestamp',available_at='unverified',vintage='current snapshot only',revision_history='unverified',pit_status='PIT_UNVERIFIED')
        elif i in EXACT_DB and tasks[i]['state']=='PARTIAL':
            row.update(source='trading PostgreSQL component',observation_date='present',published_at='unverified',ingested_at='DB timestamp existence not row-audited',available_at='unverified',vintage='unverified',revision_history='unverified',pit_status='PIT_UNVERIFIED')
        elif i in DART_SAMPLE and tasks[i]['state']=='PARTIAL':
            row.update(source='OpenDART 2025 annual one-company sample',observation_date='2025 fiscal year',published_at='filing receipt time not joined',ingested_at='worker collection timestamp',available_at='unverified',vintage='current snapshot only',revision_history='unverified',pit_status='PIT_UNVERIFIED')
        elif i in EVENT_ARCHIVE and tasks[i]['state']=='PARTIAL':
            row.update(source='official release archive page',observation_date='archive dates unparsed',published_at='unparsed',ingested_at='worker retrieval timestamp',available_at='unverified',vintage='archive snapshot only',revision_history='unverified',pit_status='PIT_UNVERIFIED')
    write_csv(HERE/'pit_audit.csv',pit)
    manifest=[];quality=[]
    for path in sorted((state/'raw').glob('*.json')):
        data=json.loads(path.read_text());digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if path.name.startswith('fred_'):
            obs=data['observations'];dates=[x['date'] for x in obs];valid=sum(x.get('value') not in ('','. ','.',None) for x in obs)
            manifest.append(dict(kind='FRED_CURRENT_VINTAGE',identifier=data['series_id'],private_file=path.name,sha256=digest,bytes=path.stat().st_size,rows=len(obs),valid_rows=valid,first_date=min(dates),last_date=max(dates),pit_eligible='false',license='FRED/source-specific redistribution unreviewed'))
            quality.append(dict(kind='FRED_CURRENT_VINTAGE',identifier=data['series_id'],rows=len(obs),valid_rows=valid,missing_rows=len(obs)-valid,duplicate_dates=len(dates)-len(set(dates)),first_date=min(dates),last_date=max(dates),validation_status='PARTIAL_PIT_UNVERIFIED'))
        elif path.name.startswith('db_component_'):
            manifest.append(dict(kind='DB_COMPONENT_QUERY_SUMMARY',identifier=data['table']+'.'+data['required_component']+(('/'+data['source_family_filter']) if data.get('source_family_filter') else ''),private_file=path.name,sha256=digest,bytes=path.stat().st_size,rows=data['rows'],valid_rows=data['nonnull_rows'],first_date=data['first'],last_date=data['last'],pit_eligible='false',license='private DB metadata; raw rows not exported'))
        elif path.name.startswith('dart_sample_'):
            n=len(data['filing_accounts'])
            manifest.append(dict(kind='OPENDART_ONE_COMPANY_SAMPLE',identifier='2025 annual CFS sample',private_file=path.name,sha256=digest,bytes=path.stat().st_size,rows=n,valid_rows=n,first_date='2025',last_date='2025',pit_eligible='false',license='OpenDART source-specific redistribution unreviewed'))
            quality.append(dict(kind='OPENDART_ONE_COMPANY_SAMPLE',identifier='2025 annual CFS sample',rows=n,valid_rows=n,missing_rows=0,duplicate_dates='',first_date='2025',last_date='2025',validation_status='SAMPLE_ONLY_PIT_UNVERIFIED'))
    dart_zip=state/'raw/dart_corp_codes.zip'
    if dart_zip.exists():
        dart_info=json.loads((state/'dart_sample_manifest.json').read_text())
        manifest.append(dict(kind='OPENDART_CURRENT_CORPORATION_DIRECTORY',identifier='listed-company directory',private_file=dart_zip.name,
                             sha256=hashlib.sha256(dart_zip.read_bytes()).hexdigest(),bytes=dart_zip.stat().st_size,
                             rows=dart_info['listed_stock_codes_in_current_directory'],valid_rows=dart_info['listed_stock_codes_in_current_directory'],
                             first_date='',last_date='',pit_eligible='false',license='OpenDART source-specific redistribution unreviewed'))
    provider_rows=[]
    for item in probes.values():
        for indicator_id in item['indicator_ids']:
            provider_rows.append(dict(indicator_id=indicator_id,provider_group=item['provider_group'],source_url=item['source_url'],
                attempted_at_utc=item['attempted_at_utc'],http_status=item['http_status'] or '',result=item['result'],
                raw_sha256=item['sha256'],bytes=item['bytes'],date_tokens_not_event_rows=item['date_token_count'],
                acquired_indicator_data='no',next_action='Parse and verify exact historical data; source access alone is insufficient'))
        if item['raw_file']:
            path=state/'raw'/item['raw_file']
            assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
            manifest.append(dict(kind='SOURCE_ACCESS_PAGE_NOT_INDICATOR_DATA',identifier=item['provider_group'],
                private_file=path.name,sha256=item['sha256'],bytes=item['bytes'],rows=0,valid_rows=0,
                first_date='',last_date='',pit_eligible='false',license='source-specific redistribution unreviewed'))
    if provider_rows:write_csv(HERE/'provider_probe_20.csv',provider_rows)
    write_csv(HERE/'worker_source_manifest.csv',manifest)
    write_csv(HERE/'worker_quality_report.csv',quality)
    comparisons=[]
    for indicator_id,file_name,column,series_id in [
        (116,'macro-cpi-rates-monthly.csv','us10y','DGS10'),
        (126,'korea-market-monthly.csv','usdkrw','DEXKOUS'),
        (134,'macro-commodities-monthly.csv','wti','DCOILWTICO'),
        (134,'macro-commodities-monthly.csv','brent','DCOILBRENTEU'),
    ]:
        path=state/'raw'/f'fred_{series_id}.json'
        if not path.exists():continue
        local=pd.read_csv(HERE.parents[1]/'data'/file_name,parse_dates=['date'])[['date',column]].dropna()
        local['month']=local.date.dt.to_period('M')
        source=pd.DataFrame(json.loads(path.read_text())['observations'])[['date','value']]
        source=source[source.value!='.'].copy()
        source['date']=pd.to_datetime(source.date);source['value']=pd.to_numeric(source.value,errors='coerce')
        source['month']=source.date.dt.to_period('M')
        last=source.sort_values('date').groupby('month').tail(1)[['month','value']]
        joined=local.merge(last,on='month',how='inner')
        diff=(joined[column]-joined.value).abs()
        comparisons.append(dict(indicator_id=indicator_id,local_file=file_name,local_field=column,official_series=series_id,
                                method='local monthly value versus last available FRED daily observation of same month',
                                paired_months=len(joined),median_absolute_difference=round(float(diff.median()),6) if len(diff) else '',
                                max_absolute_difference=round(float(diff.max()),6) if len(diff) else '',
                                validation_status='DEFINITION_AND_PIT_UNVERIFIED'))
    if comparisons:write_csv(HERE/'source_comparison_detail.csv',comparisons)
    attempts=[]
    with (state/'attempts.jsonl').open(encoding='utf-8') as f:
        for line in f:
            x=json.loads(line)
            attempts.append(dict(indicator_id=x['indicator_id'],attempted_at_utc=x['attempted_at_utc'],
                                 local_result=(x.get('local') or {}).get('result',''),db_result=(x.get('db') or {}).get('result',''),
                                 official_result=(x.get('fred') or {}).get('result',''),
                                 official_series_results=';'.join(y['series_id']+':'+y['result'] for y in (x.get('fred') or {}).get('outcomes',[])),
                                 state=x['state'],blocking_evidence=x['blocking_evidence'],next_action=x['next_action']))
    if (state/'dart_sample_manifest.json').exists():
        d=json.loads((state/'dart_sample_manifest.json').read_text())
        for i in range(152,164):
            attempts.append(dict(indicator_id=i,attempted_at_utc=d['retrieved_at_utc'],local_result='',db_result='',
                                 official_result='OpenDART shared group probe: '+d['sample_result'],official_series_results='2025 annual CFS one-company sample',
                                 state=tasks[i]['state'],blocking_evidence='Shared group probe; not a full indicator collection',
                                 next_action='Market-wide as-of company/year collection'))
    for row in provider_rows:
        attempts.append(dict(indicator_id=row['indicator_id'],attempted_at_utc=row['attempted_at_utc'],
                             local_result='local report metadata only' if row['provider_group']=='local_youtube_report' else '',
                             db_result='',official_result=row['result'],official_series_results='shared group: '+row['provider_group'],
                             state=tasks[row['indicator_id']]['state'],blocking_evidence='Access probe only; indicator series not acquired',
                             next_action=row['next_action']))
    write_csv(HERE/'worker_attempts.csv',attempts)
    legacy=[x for x in read_csv(HERE/'sources_attempt_log.csv') if not x['source'].startswith('worker:')]
    for a in attempts:
        if a['official_series_results'].startswith('shared group:'):continue
        endpoint=('https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json' if 'OpenDART' in a['official_result'] else
                  ('https://api.stlouisfed.org/fred/series/observations' if a['official_series_results'] else
                   ('trading DB read-only (host redacted)' if a['db_result'] else 'existing local source (path redacted)')))
        legacy.append(dict(attempted_at_utc=a['attempted_at_utc'],indicator_ids=a['indicator_id'],
                           source='worker:local_db_official',endpoint=endpoint,
                           result='local='+a['local_result']+';db='+a['db_result']+';official='+a['official_result'],
                           http_status='',rows='',duration_ms='',retry='',detail=a['official_series_results']+'; '+a['state']))
    for row in provider_rows:
        legacy.append(dict(attempted_at_utc=row['attempted_at_utc'],indicator_ids=row['indicator_id'],
                           source='worker:provider_probe',endpoint=row['source_url'],result=row['result'],
                           http_status=row['http_status'],rows=0,duration_ms='',retry=0,
                           detail='shared group: '+row['provider_group']+'; no verified indicator series'))
    write_csv(HERE/'sources_attempt_log.csv',legacy)
    counts=dict(Counter(x['availability_status'] for x in rows))
    worker_counts=dict(Counter(x['state'] for x in tasks.values()))
    progress={'exported_at_utc':datetime.now(timezone.utc).isoformat(),'target_as_of':'2026-10-27',
              'indicator_count':190,'availability_counts':counts,'worker_counts':worker_counts,
              'unattempted_provider_or_fallback':sum(x['provider_attempt_count']+x['fallback_attempt_count']==0 for x in tasks.values()),
              'latest_attempt_at':max((x['last_attempt_at'] or '' for x in tasks.values()),default=''),
              'fred_request_records':conn.execute('SELECT count(*) FROM requests').fetchone()[0],
              'source_probe_groups':len(probes),
              'pit_eligible':0,'backtest':'NOT_RUN_PIT_GATE',
              'warning':'Worker PARTIAL is not equivalent to complete indicator acquisition; source mappings need manual review'}
    (HERE/'worker_progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n')
    run=json.loads((HERE/'run_manifest.json').read_text())
    run.update(resume_exported_at_utc=progress['exported_at_utc'],current_availability_counts=counts,
               current_unattempted_provider_or_fallback=progress['unattempted_provider_or_fallback'],
               collection_state='IN_PROGRESS',db='READ_ONLY_SCHEMA_QUERY_SUCCEEDED',
               service_worker='regime190-collection.service',worker_source_manifest_count=len(manifest),pit_eligible=0)
    (HERE/'run_manifest.json').write_text(json.dumps(run,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(progress,ensure_ascii=False))
    conn.close()

if __name__=='__main__':main()
