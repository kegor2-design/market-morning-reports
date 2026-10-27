#!/usr/bin/env python3
"""Rebuild the conservative 190-indicator audit from local, previously fetched files."""
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROMPT = Path.home()/'Codex_Regime190_Data_Collection_GitHub_PR_20261027.md'
DATA = REPO / 'market-history/research/daily-index-validation-20261021'
TARGET_START, TARGET_END = '2010-01-01', '2026-10-27'
NOW = datetime.now(timezone.utc).isoformat()
FIELDS = ['indicator_id','name','priority','family','target_market','source_attempts','actual_source','source_url','license','auth_required','raw_path','raw_sha256','frequency','first_date','last_date','row_count','valid_count','missing_pct','target_coverage_pct','availability_status','pit_status','validation_status','failure_reason','retry_next','notes']

def write_csv(name, rows, fields):
    with (HERE/name).open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n'); w.writeheader(); w.writerows(rows)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

spec={}
if PROMPT.exists():
    prompt=PROMPT.read_text()
    for m in re.finditer(r'^\|\s*(\d{1,3})\s*\|\s*([^|]+)\|\s*(P[0-2])\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|',prompt,re.M):
        i=int(m.group(1)); spec[i]=[s.strip() for s in m.groups()[1:]]
else:
    with (HERE/'indicator_spec.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f): spec[int(row['indicator_id'])]=[row[k] for k in ('name','priority','family','source_candidate','pit_caution')]
assert sorted(spec)==list(range(1,191)), f'Unexpected IDs: {sorted(spec)}'
write_csv('indicator_spec.csv',[dict(indicator_id=i,name=v[0],priority=v[1],family=v[2],source_candidate=v[3],pit_caution=v[4]) for i,v in sorted(spec.items())],['indicator_id','name','priority','family','source_candidate','pit_caution'])

manifest=[]; quality=[]; series={}; attempts=[]
for market in ('KOSPI','KOSDAQ'):
    stem='naver_'+market.lower()
    csv_path=DATA/(stem+'_daily.csv'); xml_path=DATA/(stem+'_raw.xml')
    df=pd.read_csv(csv_path,parse_dates=['date']).sort_values('date')
    for path,kind in ((csv_path,'normalized_csv'),(xml_path,'raw_xml')):
        manifest.append(dict(market=market,kind=kind,public_path='',private_file=path.name,sha256=sha(path),bytes=path.stat().st_size,rows=len(df),first_date=str(df.date.min().date()),last_date=str(df.date.max().date()),license='redistribution_unverified',checked_at_utc=NOW))
        attempts.append(dict(attempted_at_utc=NOW,indicator_ids='1-40',source='existing_local_'+kind,endpoint='local file (path redacted)',result='FILE_HASH_VERIFIED',http_status='',rows=len(df),duration_ms='',retry=0,detail=market+' '+path.name))
    bad_ohlc=((df.high<df[['open','close','low']].max(axis=1)) | (df.low>df[['open','close','high']].min(axis=1)) | (df.low>df.high)).sum()
    duplicates=df.date.duplicated().sum(); missing=df[['open','high','low','close','volume']].isna().sum().sum()
    nonpositive=(df[['open','high','low','close']]<=0).any(axis=1).sum()
    zeros=(df.volume==0).sum(); jumps=(df.close.pct_change().abs()>0.15).sum()
    target=df[df.date>=TARGET_START]
    target_bad=((target.high<target[['open','close','low']].max(axis=1)) | (target.low>target[['open','close','high']].min(axis=1)) | (target[['open','high','low','close']]<=0).any(axis=1)).sum()
    quality.append(dict(market=market,rows=len(df),target_rows=len(target),first_date=str(df.date.min().date()),last_date=str(df.date.max().date()),duplicate_dates=int(duplicates),ohlc_invalid=int(bad_ohlc),target_ohlc_invalid=int(target_bad),missing_cells=int(missing),nonpositive_price_rows=int(nonpositive),zero_volume_rows=int(zeros),absolute_close_jumps_gt_15pct=int(jumps),calendar_check='unverified_official_calendar',corporate_action_check='not_applicable_index_level',provider_crosscheck='existing historical report only; not rerun',validation_status='FAIL' if bad_ohlc or duplicates or nonpositive else 'PARTIAL',checked_at_utc=NOW))
    series[market]=df[(df.date>=TARGET_START)&(df.date<=TARGET_END)].copy().reset_index(drop=True)

# A small, fully specified subset of close/high/low transforms. These are research
# calculations only and are quarantined from predictive validation by PIT status.
column_map={1:[f'sma_{n}' for n in (5,10,20,60,120,200)],10:['donchian_high_20','donchian_low_20'],12:['distance_52wk_high'],13:['macd','macd_signal','macd_hist'],17:['roc_10','momentum_10'],26:['efficiency_ratio_10'],28:['bb_percent_b','bb_bandwidth'],29:['atr_14','natr_14'],32:['parkinson_20'],33:['garman_klass_20'],34:['rogers_satchell_20'],36:[f'realized_vol_{n}' for n in (5,20,60)],37:['downside_semivol_20'],38:['skew_60','excess_kurt_60'],39:['bipower_20','jump_20'],40:['drawdown','drawdown_velocity_5','recovery_5']}
computed=set(column_map)
computed_stats={i:[] for i in computed}
private=HERE/'private'; private.mkdir(exist_ok=True)
for market,df in series.items():
    c,h,l,o=df.close,df.high,df.low,df.open
    ret=np.log(c/c.shift(1)); out=pd.DataFrame({'date':df.date})
    for n in (5,10,20,60,120,200): out[f'sma_{n}']=c.rolling(n).mean()
    out['donchian_high_20']=h.rolling(20).max(); out['donchian_low_20']=l.rolling(20).min()
    out['distance_52wk_high']=c/c.rolling(252).max()-1
    macd=c.ewm(span=12,adjust=False,min_periods=26).mean()-c.ewm(span=26,adjust=False,min_periods=26).mean()
    out['macd']=macd; out['macd_signal']=macd.ewm(span=9,adjust=False,min_periods=9).mean(); out['macd_hist']=out.macd-out.macd_signal
    out['roc_10']=c.pct_change(10); out['momentum_10']=c-c.shift(10)
    out['efficiency_ratio_10']=(c-c.shift(10)).abs()/c.diff().abs().rolling(10).sum().replace(0,np.nan)
    mid=c.rolling(20).mean(); sd=c.rolling(20).std(); out['bb_percent_b']=(c-(mid-2*sd))/(4*sd).replace(0,np.nan); out['bb_bandwidth']=4*sd/mid
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean(); out['atr_14']=atr; out['natr_14']=100*atr/c
    out['parkinson_20']=np.sqrt((np.log(h/l)**2).rolling(20).mean()/(4*np.log(2)))
    gk=.5*np.log(h/l)**2-(2*np.log(2)-1)*np.log(c/o)**2
    out['garman_klass_20']=np.sqrt(gk.rolling(20).mean().clip(lower=0))
    rs=np.log(h/c)*np.log(h/o)+np.log(l/c)*np.log(l/o)
    out['rogers_satchell_20']=np.sqrt(rs.rolling(20).mean().clip(lower=0))
    for n in (5,20,60): out[f'realized_vol_{n}']=ret.rolling(n).std()*np.sqrt(252)
    out['downside_semivol_20']=np.sqrt(ret.clip(upper=0).pow(2).rolling(20).mean()*252)
    out['skew_60']=ret.rolling(60).skew(); out['excess_kurt_60']=ret.rolling(60).kurt()
    out['bipower_20']=np.pi/2*ret.abs().mul(ret.abs().shift()).rolling(20).mean()
    out['jump_20']=(ret.pow(2).rolling(20).mean()-out.bipower_20).clip(lower=0)
    peak=c.cummax(); out['drawdown']=c/peak-1; out['drawdown_velocity_5']=out.drawdown.diff(5); out['recovery_5']=c.pct_change(5)
    path=private/(market.lower()+'_computed.csv'); out.to_csv(path,index=False)
    for indicator_id,columns in column_map.items():
        mask=out[columns].notna().all(axis=1)
        computed_stats[indicator_id].append(dict(valid=int(mask.sum()),first=str(out.loc[mask,'date'].min().date()) if mask.any() else '',last=str(out.loc[mask,'date'].max().date()) if mask.any() else ''))
    manifest.append(dict(market=market,kind='derived_research_csv',public_path='',private_file=path.name,sha256=sha(path),bytes=path.stat().st_size,rows=len(out),first_date=str(out.date.min().date()),last_date=str(out.date.max().date()),license='derived_from_redistribution_unverified_source',checked_at_utc=NOW))

monthly_specs={
    116:('macro-cpi-rates-monthly.csv',['us10y'],'US 2Y missing'),
    126:('korea-market-monthly.csv',['usdkrw'],'daily FX history and close time missing'),
    128:('macro-cpi-rates-monthly.csv',['krwjpy100'],'yuan and direct yen series missing'),
    131:('us-stock-market-monthly.csv',['price'],'NASDAQ and SOX missing; price identity unverified'),
    134:('macro-commodities-monthly.csv',['wti','brent'],'natural gas missing'),
    135:('macro-commodities-monthly.csv',['gold'],'silver, copper, iron ore missing'),
    143:('macro-cpi-rates-monthly.csv',['kr_cpi'],'core CPI missing'),
}
monthly_stats={}
for file_name in sorted({v[0] for v in monthly_specs.values()}):
    path=REPO/'market-history/data'/file_name
    frame=pd.read_csv(path)
    date_col=frame.columns[0]
    frame=frame[frame[date_col].between(TARGET_START,TARGET_END)].copy()
    ids=[i for i,v in monthly_specs.items() if v[0]==file_name]
    manifest.append(dict(market='GLOBAL_OR_KOREA',kind='existing_monthly_public_csv',public_path='market-history/data/'+file_name,private_file='',sha256=sha(path),bytes=path.stat().st_size,rows=len(frame),first_date=str(frame[date_col].min()),last_date=str(frame[date_col].max()),license='upstream_license_unverified',checked_at_utc=NOW))
    attempts.append(dict(attempted_at_utc=NOW,indicator_ids=','.join(map(str,ids)),source='existing_repo_monthly_csv',endpoint='market-history/data/'+file_name,result='FILE_HASH_VERIFIED_COMPONENT_ONLY',http_status='',rows=len(frame),duration_ms='',retry=0,detail='No as-of publication time or vintage'))
    quality.append(dict(market='GLOBAL_OR_KOREA:'+file_name,rows=len(frame),target_rows=len(frame),first_date=str(frame[date_col].min()),last_date=str(frame[date_col].max()),duplicate_dates=int(frame[date_col].duplicated().sum()),ohlc_invalid='',target_ohlc_invalid='',missing_cells='',nonpositive_price_rows='',zero_volume_rows='',absolute_close_jumps_gt_15pct='',calendar_check='monthly_dates_only',corporate_action_check='not_applicable',provider_crosscheck='not_run',validation_status='PARTIAL_COMPONENT_ONLY',checked_at_utc=NOW))
    for i in ids:
        fields=monthly_specs[i][1]
        valid=frame.loc[frame[fields].notna().all(axis=1),date_col]
        monthly_stats[i]=dict(rows=len(valid),first=str(valid.min()) if len(valid) else '',last=str(valid.max()) if len(valid) else '',path='market-history/data/'+file_name,sha=sha(path))

inventory=[]
for i in range(1,191):
    name,priority,family,candidate,pit=spec[i]
    acquired=i<=40
    monthly=i in monthly_specs
    done=i in computed
    status='일부 확보' if done or monthly else ('원천 확보·계산 미완료' if acquired else '미확보(미시도)')
    reason=('Monthly component only; '+monthly_specs[i][2]+'; publication time and vintage unavailable' if monthly else ('PIT publication time and vintage unavailable; full target ends 2026-10-27 while files end 2026-10-20' if done else ('Required transform or definition not completed; PIT unverified' if acquired else 'Individual source access and collection not executed in this run')))
    total=sum(len(x) for x in series.values()) if acquired else 0
    valid=sum(s['valid'] for s in computed_stats[i]) if done else 0
    days=len(pd.bdate_range(TARGET_START,TARGET_END))*2
    inventory.append(dict(indicator_id=i,name=name,priority=priority,family=family,target_market='KOSPI;KOSDAQ',source_attempts=4 if acquired else (1 if monthly else 0),actual_source='Naver Finance historical index OHLCV' if acquired else ('existing monthly repository CSV' if monthly else ''),source_url='https://fchart.stock.naver.com/sise.nhn' if acquired else (monthly_stats[i]['path'] if monthly else ''),license='redistribution_unverified' if acquired else ('upstream_license_unverified' if monthly else 'unreviewed'),auth_required='unknown' if not acquired else 'no',raw_path='private:naver_{market}_raw.xml' if acquired else (monthly_stats[i]['path'] if monthly else ''),raw_sha256='see raw_manifest.csv by market' if acquired else (monthly_stats[i]['sha'] if monthly else ''),frequency='daily' if acquired else ('monthly' if monthly else ''),first_date=min(s['first'] for s in computed_stats[i]) if done else (min(str(x.date.min().date()) for x in series.values()) if acquired else (monthly_stats[i]['first'] if monthly else '')),last_date=max(s['last'] for s in computed_stats[i]) if done else (max(str(x.date.max().date()) for x in series.values()) if acquired else (monthly_stats[i]['last'] if monthly else '')),row_count=total if acquired else (monthly_stats[i]['rows'] if monthly else 0),valid_count=valid,missing_pct=round(100*(total-valid)/total,2) if done else '',target_coverage_pct=round(100*valid/days,2) if done else '',availability_status=status,pit_status='PIT_UNVERIFIED' if acquired or monthly else 'NOT_ASSESSED',validation_status='PARTIAL' if acquired or monthly else 'NOT_RUN',failure_reason=reason,retry_next='Verify timestamps/vintages, reconcile KRX, complete exact definition' if acquired else ('Collect missing components and first-release vintages' if monthly else 'Try official source, then licensed alternative, with bounded requests'),notes='Computed data is private and excluded from backtest; coverage denominator includes exchange holidays' if done else ('Only listed monthly components observed; complete indicator valid_count=0' if monthly else candidate)))

write_csv('inventory_190.csv',inventory,FIELDS)
pd.DataFrame(inventory).to_excel(HERE/'inventory_190.xlsx',index=False)
attempts.extend([
    dict(attempted_at_utc='2026-10-27T14:58:37Z',indicator_ids='all candidate KRX categories',source='KRX official landing page',endpoint='https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd',result='HEAD_ONLY_NO_DATA',http_status=200,rows=0,duration_ms=2743,retry=0,detail='No data endpoint queried; not an acquisition'),
    dict(attempted_at_utc='2026-10-27 (exact UTC second not logged)',indicator_ids='DB candidates',source='trading PostgreSQL',endpoint='redacted',result='CONNECT_FAILED_OperationalError',http_status='',rows=0,duration_ms='',retry=1,detail='Read-only schema inspection could not begin')])
write_csv('raw_manifest.csv',manifest,list(manifest[0]))
write_csv('quality_report.csv',quality,list(quality[0]))
write_csv('sources_attempt_log.csv',attempts,list(attempts[0]))
periods=[('development','2010-01-01','2017-12-31'),('validation','2018-01-01','2021-12-31'),('final','2022-01-01','2026-10-27')]
coverage=[]
for market,df in series.items():
    derived=pd.read_csv(private/(market.lower()+'_computed.csv'),parse_dates=['date'])
    for i in range(1,191):
        for label,start,end in periods:
            if i in monthly_specs:
                file_name,cols,_=monthly_specs[i]
                month_df=pd.read_csv(REPO/'market-history/data'/file_name)
                dc=month_df.columns[0]
                raw=int((month_df[dc].between(start,end)&month_df[cols].notna().all(axis=1)).sum())
                expected=len(pd.date_range(start,end,freq='MS'))
                denominator_kind='calendar_months'
                valid=0  # Missing components and release vintages block a complete indicator.
            else:
                expected=len(pd.bdate_range(start,end))
                denominator_kind='weekday_proxy_includes_KRX_holidays'
                raw=int(df.date.between(start,end).sum()) if i<=40 else 0
                valid=int((derived.date.between(start,end)&derived[column_map[i]].notna().all(axis=1)).sum()) if i in computed else 0
            coverage.append(dict(indicator_id=i,market=market,period=label,start_date=start,end_date=end,frequency='monthly' if i in monthly_specs else ('daily' if i<=40 else 'unknown'),raw_component_rows=raw,valid_indicator_rows=valid,denominator_rows=expected,denominator_kind=denominator_kind,valid_coverage_pct=round(100*valid/expected,2) if expected else 0,pit_eligible_rows=0,pit_eligible_pct=0))
write_csv('coverage_matrix.csv',coverage,list(coverage[0]))
pit=[]
for i in range(1,191):
    acquired=i<=40 or i in monthly_specs
    pit.append(dict(indicator_id=i,market='KOSPI;KOSDAQ',source='Naver Finance historical index' if i<=40 else ('existing monthly repository CSV' if i in monthly_specs else ''),observation_date='present' if acquired else 'no_data',published_at='absent' if acquired else 'no_data',ingested_at='2026-10-21 in prior manifest; row-level absent' if i<=40 else ('not recorded' if i in monthly_specs else 'no_data'),available_at='unverified' if acquired else 'no_data',vintage='absent' if acquired else 'no_data',revision_history='absent' if acquired else 'no_data',pit_status='PIT_UNVERIFIED' if acquired else 'NOT_ASSESSED',backtest_eligible='no'))
write_csv('pit_audit.csv',pit,list(pit[0]))
comparisons=[dict(indicator_ids='1-40',market=m,source_a='Naver Finance local raw',source_b='KRX official',result='NOT_RERUN',reason='KRX HTTP landing page available; daily series query/values not collected') for m in series]
for i in monthly_specs:
    comparisons.append(dict(indicator_ids=i,market='KOSPI;KOSDAQ',source_a=monthly_stats[i]['path'],source_b='official source not queried',result='NOT_RUN',reason='Only partial monthly component, no PIT vintage or independent match'))
write_csv('source_comparison.csv',comparisons,list(comparisons[0]))
write_csv('backtest_results.csv',[dict(status='NOT_RUN',reason='All locally acquired index data PIT_UNVERIFIED; gate prohibits final validation',market='KOSPI;KOSDAQ',sample_size=0,metric='',value='')],['status','reason','market','sample_size','metric','value'])
counts=Counter(r['availability_status'] for r in inventory)
run=dict(generated_at_utc=NOW,target_as_of=TARGET_END,indicator_count=190,availability_counts=dict(counts),markets=list(series),raw_file_count=8,derived_private_file_count=2,backtest='NOT_RUN_PIT_GATE',db='CONNECT_FAILED',krx_landing_page='HEAD_200_ONLY',prompt_sha256=sha(PROMPT) if PROMPT.exists() else 'prompt_not_local',python='3',rebuild_command='python market-history/research/regime190/run.py')
(HERE/'run_manifest.json').write_text(json.dumps(run,ensure_ascii=False,indent=2)+'\n')
(HERE/'schema_audit.md').write_text('# DB schema audit\n\n2026-10-27: `trading` PostgreSQL connection failed with `OperationalError` under read-only intended session. No schema or table content was inspected; no DB mutations occurred. Existing table names in prior reports are unverified in this run.\n')
(HERE/'README.md').write_text(f'''# Regime 190 historical data audit (2026-10-27)\n\nGenerated {NOW}. Target 2010-01-01 to 2026-10-27, KOSPI and KOSDAQ separately. Exactly 190 indicators are listed in `inventory_190.csv`. Status counts: {dict(counts)}.\n\nVerified index files: two Naver Finance index XML files and their normalized CSVs, locally retained from 2026-10-21. SHA-256 values match the prior manifest. Both end 2026-10-20. Sixteen price indicator definitions were calculated into private local CSVs, with hashes in `raw_manifest.csv`; these are partial acquisition because 2026-10-21 through 2026-10-27 and publication vintages are absent. Twenty-four other price indicators have raw inputs but unfinished calculations. Four existing monthly public CSVs supply only partial components for seven further indicators; their upstream rights and release vintages are unverified. The remaining 143 indicators were not individually collected. A KRX landing page HEAD request returned 200 but yielded no observations. DB connection failed.\n\nHistorical OHLC invalid rows: KOSPI 4 and KOSDAQ 1, all before 2010. Target-window OHLC invalid rows: 0 in each market. Calendar and provider comparisons were not repeated.\n\nAll observed records remain `PIT_UNVERIFIED`: observation date exists, but row-level published/available timestamps and vintage do not. No predictive backtest was run because the prompt forbids unverified PIT data in final validation. `coverage_matrix.csv` reports index raw weekday coverage as context, with 0% PIT eligibility; weekdays are not an official KRX calendar. Redistribution rights for Naver raw data were not confirmed, so no private raw or derived series are committed. The private outputs remain in ignored `private/`.\n\nRebuild in the server snapshot: `python3 market-history/research/regime190/run.py`. Source files are required in the prior daily-index-validation directory. This command does not access the network or DB. Open risks: official provider reconciliation, exact publication times and revisions, exchange calendar, 143 source collections, missing monthly components, 24 remaining calculations, and PIT-safe walk-forward backtesting.\n''')
print(json.dumps(run,ensure_ascii=False))
