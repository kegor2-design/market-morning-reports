#!/usr/bin/env python3
"""Small official-source access probes for unresolved indicator families.

An archive landing page is never treated as a historical indicator time series.
"""
import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

STATE=Path.home()/'MyDream2000/research/regime190'
KEY_FILE=Path.home()/'mydream2000.env'
PROBES={
 'krx_microstructure':([77,79,80,81],'https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd'),
 'bok_policy':([164],'https://www.bok.or.kr/portal/main/contents.do?menuNo=200755'),
 'fed_fomc':([165],'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'),
 'treasury_auction':([166],'https://www.treasurydirect.gov/auctions/announcements-data-results/'),
 'msci_review':([167],'https://app2.msci.com/webapp/index_ann/Announcement?doc_type=ANNOUNCEMENT&format=html&lang=en&prod_type=STANDARD&visibility=public'),
 'fsc_policy':([168],'https://www.fsc.go.kr/no010101'),
 'ustr_press':([169],'https://www.ustr.gov/about-us/policy-offices/press-office/press-releases'),
 'boj_policy':([170],'https://www.boj.or.jp/en/mopo/mpmdeci/index.htm'),
 'ofac_actions':([171],'https://ofac.treasury.gov/press-releases'),
 'krx_options_rules':([172],'https://global.krx.co.kr/contents/GLB/02/0201/0201040402/GLB0201040402.jsp'),
 'fnguide_consensus':([177],'https://www.fnguide.com/'),
 'google_trends':([179],'https://trends.google.com/trends/'),
 'reddit_api':([180],'https://www.reddit.com/dev/api/'),
}

def api_key(name):
    for line in KEY_FILE.read_text().splitlines():
        if line.startswith(name+'='):return line.split('=',1)[1].strip().strip('"\'')
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output-dir',type=Path,default=STATE)
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--resume',action='store_true')
    ap.add_argument('--max-requests',type=int,default=20)
    ap.add_argument('--since',default='2010-01-01')
    ap.add_argument('--until',default='2026-10-27')
    args=ap.parse_args()
    if args.max_requests<0 or args.max_requests>20:ap.error('max-requests must be 0..20')
    if args.dry_run:
        print(json.dumps({'groups':len(PROBES)+2,'indicator_ids':sorted({i for v in PROBES.values() for i in v[0]}|{123,124,173,176}),
                          'max_requests':args.max_requests}))
        return
    raw=args.output_dir/'raw';raw.mkdir(parents=True,exist_ok=True,mode=0o700)
    report_path=args.output_dir/'provider_probe_manifest.json'
    results=json.loads(report_path.read_text()) if args.resume and report_path.exists() else {}
    calls=0
    key=api_key('FRED_API_KEY')
    probes=dict(PROBES)
    if key:
        probes['fred_move_search']=([123],'https://api.stlouisfed.org/fred/series/search')
        probes['fred_cds_search']=([124],'https://api.stlouisfed.org/fred/series/search')
    dart=api_key('DART_API_KEY')
    if dart:probes['dart_filings_candidate']=([173],'https://opendart.fss.or.kr/api/list.json')
    session=requests.Session();session.headers.update({'User-Agent':'Regime190ResearchAudit/1.0 (bounded source-access verification)'})
    for group,(ids,url) in probes.items():
        if group in results or calls>=args.max_requests:continue
        params={}
        if group=='fred_move_search':params={'api_key':key,'file_type':'json','search_text':'MOVE Index','limit':10}
        if group=='fred_cds_search':params={'api_key':key,'file_type':'json','search_text':'credit default swap','limit':10}
        if group=='dart_filings_candidate':params={'crtfc_key':dart,'bgn_de':'20261027','end_de':'20261027','page_count':100}
        item={'indicator_ids':ids,'provider_group':group,'source_url':url,'attempted_at_utc':datetime.now(timezone.utc).isoformat(),
              'result':'NOT_REQUESTED','http_status':None,'raw_file':'','sha256':'','bytes':0,
              'date_token_count':0,'first_date_token':'','last_date_token':'',
              'classification':'SOURCE_ACCESS_PROBE_ONLY'}
        try:
            response=session.get(url,params=params,timeout=(5,20),stream=True)
            calls+=1;item['http_status']=response.status_code
            if response.status_code==200:
                chunks=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>2_000_000:break
                    chunks.append(chunk)
                if size>2_000_000:
                    item['result']='RESPONSE_TOO_LARGE_TRUNCATED_NOT_STORED'
                else:
                    body=b''.join(chunks)
                    suffix='.json' if group.startswith(('fred_','dart_')) else '.html'
                    path=raw/('probe_'+group+suffix)
                    temp=path.with_suffix(path.suffix+'.tmp')
                    with temp.open('wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
                    temp.replace(path);path.chmod(0o600)
                    dates=sorted({x for x in re.findall(rb'20[0-2][0-9]-[01][0-9]-[0-3][0-9]',body) if args.since.encode()<=x<=args.until.encode()})
                    item.update(result='DOWNLOADED_SOURCE_PAGE_NOT_INDICATOR_SERIES',raw_file=path.name,
                                sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),
                                date_token_count=len(dates),first_date_token=dates[0].decode() if dates else '',
                                last_date_token=dates[-1].decode() if dates else '')
                    if group.startswith('fred_'):
                        payload=json.loads(body)
                        item['metadata_series_count']=payload.get('count',len(payload.get('seriess',[])))
                    if group=='dart_filings_candidate':
                        payload=json.loads(body)
                        item['dart_status']=payload.get('status')
                        item['filing_rows']=len(payload.get('list',[]))
            elif response.status_code==429:
                item['result']='HTTP_429_RETRY_AFTER_REQUIRED'
                item['retry_after']=response.headers.get('Retry-After','not supplied')
            else:item['result']='HTTP_'+str(response.status_code)
        except Exception as exc:
            item['result']=type(exc).__name__
        results[group]=item
        report_path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        report_path.chmod(0o600)
        if item['result']=='HTTP_429_RETRY_AFTER_REQUIRED':break
        time.sleep(1)
    # Local source check for YouTube-derived reports; these are not speech/chart originals.
    if 'local_youtube_report' not in results:
        files=sorted((Path.home()/'MMPData/reports').glob('**/*nightly-youtube-intelligence.md'))
        digest=hashlib.sha256()
        for p in files:digest.update(p.name.encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest())
        results['local_youtube_report']={'indicator_ids':[176],'provider_group':'local_youtube_report',
          'source_url':'local MMP-derived reports (path redacted)','attempted_at_utc':datetime.now(timezone.utc).isoformat(),
          'result':'DERIVED_REPORTS_ONLY_NO_TRANSCRIPT_OR_CHART_TIME' if files else 'NO_LOCAL_REPORTS',
          'http_status':None,'raw_file':'','sha256':digest.hexdigest() if files else '',
          'bytes':sum(p.stat().st_size for p in files),'date_token_count':len(files),
          'first_date_token':files[0].name[:10] if files else '',
          'last_date_token':files[-1].name[:10] if files else '',
          'classification':'FALLBACK_COMPONENT_NOT_RAW'}
        report_path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'groups_recorded':len(results),'requests_this_run':calls,
                      'indicator_ids_linked':sorted({i for x in results.values() for i in x['indicator_ids']})}))

if __name__=='__main__':main()
