#!/usr/bin/env python3
"""Bounded OpenDART access check and one-company financial statement sample."""
import argparse
import hashlib
import io
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

KEY_FILE=Path.home()/'mydream2000.env'
DEFAULT_OUT=Path.home()/'MyDream2000/research/regime190/raw'

def key_from_file():
    for line in KEY_FILE.read_text().splitlines():
        if line.startswith('DART_API_KEY='):
            return line.split('=',1)[1].strip().strip('"\'')
    return None

def save(path,content):
    temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('wb') as f:
        f.write(content);f.flush();os.fsync(f.fileno())
    temp.replace(path);path.chmod(0o600)
    return hashlib.sha256(content).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output-dir',type=Path,default=DEFAULT_OUT)
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--resume',action='store_true')
    ap.add_argument('--since',default='2015-01-01')
    ap.add_argument('--until',default='2026-10-27')
    ap.add_argument('--max-requests',type=int,default=2)
    args=ap.parse_args()
    if args.max_requests<0 or args.max_requests>2:ap.error('max-requests must be 0..2 for this bounded sample adapter')
    if args.dry_run:
        print(json.dumps({'provider':'OpenDART','planned_endpoints':['corpCode.xml','fnlttSinglAcntAll.json'],
                          'target_window':[args.since,args.until],'max_requests':args.max_requests}))
        return
    key=key_from_file()
    if not key:raise SystemExit('DART_KEY_MISSING')
    args.output_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    corp_path=args.output_dir/'dart_corp_codes.zip'
    calls=0
    if args.resume and corp_path.exists(): body=corp_path.read_bytes()
    elif args.max_requests>=1:
        response=requests.get('https://opendart.fss.or.kr/api/corpCode.xml',params={'crtfc_key':key},timeout=(5,30))
        calls+=1
        if response.status_code!=200:raise SystemExit('DART_CORPCODE_HTTP_'+str(response.status_code))
        body=response.content
        if not zipfile.is_zipfile(io.BytesIO(body)):
            raise SystemExit('DART_CORPCODE_NONZIP_RESPONSE')
        save(corp_path,body)
    else:raise SystemExit('DART_CORPCODE_NOT_CACHED')
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        xml=archive.read(archive.namelist()[0])
    root=ET.fromstring(xml)
    listed=[];corp=None
    for node in root.findall('.//list'):
        code=(node.findtext('stock_code') or '').strip()
        if len(code)==6:listed.append(code)
        if code=='005930':corp=(node.findtext('corp_code') or '').strip()
    result={'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'provider':'OpenDART',
            'corp_code_archive_sha256':hashlib.sha256(body).hexdigest(),
            'listed_stock_codes_in_current_directory':len(listed),'sample_stock_code':'005930',
            'annual_report_year':2025,'requests_this_run':calls,
            'pit_warning':'Current corporation directory and 2025 filing snapshot do not reconstruct 2010-2026 vintages'}
    sample_path=args.output_dir/'dart_sample_2025_005930.json'
    if corp and args.max_requests-calls>=1 and not (args.resume and sample_path.exists()):
        response=requests.get('https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json',
            params={'crtfc_key':key,'corp_code':corp,'bsns_year':'2025','reprt_code':'11011','fs_div':'CFS'},
            timeout=(5,30))
        calls+=1
        if response.status_code==200:
            payload=response.json()
            if payload.get('status')=='000' and payload.get('list'):
                sample={'provider':'OpenDART','retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
                        'stock_code':'005930','business_year':2025,'report_code':'11011',
                        'filing_accounts':payload['list'],'pit_warning':'current-vintage only'}
                encoded=json.dumps(sample,ensure_ascii=False).encode()
                result['sample_sha256']=save(sample_path,encoded)
                result['sample_account_rows']=len(payload['list'])
                result['sample_result']='ACQUIRED'
            else:result['sample_result']='DART_STATUS_'+str(payload.get('status'))
        else:result['sample_result']='HTTP_'+str(response.status_code)
    elif sample_path.exists():
        result['sample_sha256']=hashlib.sha256(sample_path.read_bytes()).hexdigest()
        result['sample_account_rows']=len(json.loads(sample_path.read_text())['filing_accounts'])
        result['sample_result']='ALREADY_ACQUIRED'
    else:result['sample_result']='NOT_REQUESTED_BUDGET_OR_CORP_MISSING'
    result['requests_this_run']=calls
    report=args.output_dir.parent/'dart_sample_manifest.json'
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    report.chmod(0o600)
    print(json.dumps({k:v for k,v in result.items() if k!='sample_stock_code'},ensure_ascii=False))

if __name__=='__main__':main()
