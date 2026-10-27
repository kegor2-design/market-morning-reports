#!/usr/bin/env python3
"""Push metadata checkpoints only when private worker state advances.

This deliberately refuses dirty branches, remote divergence, raw files, and
unreviewed paths. Publication failures never stop the collection worker.
"""
import argparse
import fcntl
import json
import re
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
STATE=Path.home()/'MyDream2000/research/regime190'
BRANCH='research/regime190-data-audit-20261027'
FILES=[
    'inventory_190.csv','inventory_190.xlsx','coverage_matrix.csv','pit_audit.csv',
    'sources_attempt_log.csv','source_comparison_detail.csv','worker_source_manifest.csv',
    'worker_quality_report.csv','worker_attempts.csv','provider_probe_20.csv',
    'worker_progress.json','run_manifest.json',
]

def git(*args):
    return subprocess.run(['git',*args],cwd=REPO,text=True,capture_output=True,timeout=45)

def fingerprint():
    conn=sqlite3.connect(f'file:{STATE/"checkpoint.sqlite"}?mode=ro',uri=True)
    counts=dict(conn.execute('SELECT state,count(*) FROM tasks GROUP BY state'))
    latest=conn.execute('SELECT max(last_attempt_at) FROM tasks').fetchone()[0] or ''
    request_count=conn.execute('SELECT count(*) FROM requests').fetchone()[0]
    conn.close()
    probes=STATE/'provider_probe_manifest.json'
    return {'worker_counts':counts,'latest_attempt_at':latest,
            'fred_request_records':request_count,
            'source_probe_groups':len(json.loads(probes.read_text())) if probes.exists() else 0}

def has_public_secret():
    for name in FILES:
        path=HERE/name
        if not path.exists():return 'missing:'+name
        if path.suffix=='.xlsx':
            with zipfile.ZipFile(path) as archive:
                data=''.join(archive.read(n).decode('utf-8',errors='ignore') for n in archive.namelist() if n.endswith('.xml'))
        else:data=path.read_text(errors='replace')
        if (str(Path.home()) in data or ('postgresql'+ '://') in data or
            re.search(r'gh' + r'p_[A-Za-z0-9]{20,}',data) or
            re.search(r'(?:api_key|crtfc_key|token)=[A-Za-z0-9]{12,}',data,re.I)):
            return 'private marker:'+name
    return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/'publisher.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('PUBLISHER_ALREADY_RUNNING');return 0
        branch=git('branch','--show-current')
        if branch.returncode or branch.stdout.strip()!=BRANCH:
            print('SKIP_WRONG_BRANCH');return 0
        status=git('status','--porcelain')
        if status.returncode or status.stdout.strip():
            print('SKIP_DIRTY_WORKTREE');return 0
        current=fingerprint()
        old=json.loads((HERE/'worker_progress.json').read_text())
        changed=any(current[k]!=old.get(k) for k in current)
        if args.dry_run:
            print(json.dumps({'safe_branch':True,'clean':True,'new_progress':changed,
                              'counts':current['worker_counts']}));return 0
        fetched=git('fetch','origin')
        if fetched.returncode:
            print('PUBLISH_RETRY_FETCH_FAILED');return 1
        ahead=git('rev-list','--left-right','--count',f'HEAD...origin/{BRANCH}')
        if ahead.returncode:
            print('PUBLISH_RETRY_REMOTE_COMPARE_FAILED');return 1
        local_ahead,remote_ahead=map(int,ahead.stdout.split())
        if remote_ahead:
            print('SKIP_REMOTE_ADVANCED_REVIEW_REQUIRED');return 1
        if local_ahead:
            pushed=git('push','origin',BRANCH)
            print('PUSH_RETRIED' if pushed.returncode==0 else 'PUBLISH_RETRY_PUSH_FAILED')
            return 0 if pushed.returncode==0 else 1
        if not changed:
            print('NO_NEW_PROGRESS');return 0
        result=subprocess.run([sys.executable,str(HERE/'export_worker.py')],cwd=REPO,text=True,capture_output=True,timeout=120)
        if result.returncode:
            print('PUBLISH_RETRY_EXPORT_FAILED');return 1
        risk=has_public_secret()
        if risk:
            print('PUBLISH_BLOCKED_SECURITY_SCAN',risk);return 1
        paths=[str((HERE/name).relative_to(REPO)) for name in FILES]
        staged=git('add','--',*paths)
        if staged.returncode:
            print('PUBLISH_RETRY_STAGE_FAILED');return 1
        staged_names=git('diff','--cached','--name-only')
        if staged_names.returncode or not set(staged_names.stdout.splitlines()).issubset(set(paths)):
            print('PUBLISH_BLOCKED_STAGED_PATH');return 1
        check=git('diff','--cached','--check')
        if check.returncode:
            print('PUBLISH_BLOCKED_DIFF_CHECK');return 1
        diff=git('diff','--cached','--quiet')
        if diff.returncode==0:
            print('NO_METADATA_DIFF');return 0
        committed=git('commit','-m','Update regime190 metadata checkpoint')
        if committed.returncode:
            print('PUBLISH_RETRY_COMMIT_FAILED');return 1
        pushed=git('push','origin',BRANCH)
        print('PUBLISHED_METADATA_CHECKPOINT' if pushed.returncode==0 else 'PUBLISH_RETRY_PUSH_FAILED')
        return 0 if pushed.returncode==0 else 1

if __name__=='__main__':raise SystemExit(main())
