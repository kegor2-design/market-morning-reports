#!/usr/bin/env python3
"""Read-only reconciliation of the published inventory with the private checkpoint."""
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path.home() / 'MyDream2000/research/regime190'
OUT = HERE / 'indicator_audit_20261031.csv'


def rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def main():
    inventory = rows(HERE / 'inventory_190.csv')
    quality = {int(r['indicator_id']): r for r in rows(HERE / 'quality_report.csv')}
    mapping = {int(r['indicator_id']): r for r in rows(HERE / 'indicator_field_mapping.csv')}
    uri = 'file:' + str(STATE / 'checkpoint.sqlite') + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        tasks = {r['indicator_id']: dict(r) for r in db.execute('SELECT * FROM tasks')}
        requests = list(db.execute('SELECT * FROM requests'))
    ids = [int(r['indicator_id']) for r in inventory]
    assert len(ids) == len(set(ids)) == 190
    assert set(ids) == set(tasks) == set(quality) == set(mapping)
    assert sum(t['provider_attempt_count'] == 0 for t in tasks.values()) == 147
    assert sum(t['provider_attempt_count'] == 0 and t['fallback_attempt_count'] == 0
               for t in tasks.values()) == 0
    assert len(requests) == 18
    output = []
    for r in inventory:
        i = int(r['indicator_id'])
        t, q, m = tasks[i], quality[i], mapping[i]
        availability = r['availability_status']
        generated = int(q['actual_indicator_series_rows'] or 0)
        raw = '미확보' if availability.startswith('미확보') else '부분 확보'
        calculation = '부분 생성·정의 미검증' if generated else '미완료'
        reason = r['failure_reason'] or t['blocking_evidence']
        if t['provider_attempt_count'] == 0:
            reason = '직접 공급자 요청 미시도; ' + reason
        output.append({
            'indicator_id': i, 'name': r['name'], 'priority': r['priority'],
            'provider': r['actual_source'] or '미확인',
            'candidate_table': m['candidate_table'] or '미확인',
            'alternative_provider': '미확정; 공급자별 정의·라이선스 확인 필요',
            'raw_acquisition': raw, 'calculation': calculation,
            'generated_rows': generated, 'pit_validation': '미완료',
            'published_at_evidence': '행별 발표시각 미확인',
            'historical_availability': '행별 as-of 재현 미확인',
            'revision_vintage': '지표별 연결·완전성 미확인',
            'lookahead_risk': '배제되지 않음',
            'survivorship_risk': 'as-of 종목군 미확인',
            'backtest_eligible': '아니오',
            'last_collection_attempt_utc': t['last_attempt_at'] or '',
            'provider_request_count': t['provider_attempt_count'],
            'fallback_attempt_count': t['fallback_attempt_count'],
            'provider_unattempted': '예' if not t['provider_attempt_count'] else '아니오',
            'error_or_incomplete_reason': reason,
            'retry_possible': '예; 요청·매핑 검토 후' if not t['provider_attempt_count'] else '예; 원인별 검토 후',
            'next_action': t['next_action'] or r['next_action'],
            'availability_status': availability,
            'source_history_status': q['source_history_status'],
            'duplicate_check': q['duplicate_check'],
            'mapping_status': m['mapping_status'],
        })
    with OUT.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(output)
    print(json.dumps({'rows': len(output), 'availability': dict(Counter(r['availability_status'] for r in output)),
                      'provider_unattempted': sum(r['provider_unattempted'] == '예' for r in output),
                      'generated_rows': sum(r['generated_rows'] for r in output),
                      'generated_indicators': sum(r['generated_rows'] > 0 for r in output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
