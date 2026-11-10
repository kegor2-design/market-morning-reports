#!/usr/bin/env python3
"""Publish only evidence-backed Phase 2 summary and per-ID blockers."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def records(name):
    with (HERE / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def write_csv(name, rows):
    path = HERE / name
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def run():
    attempts = {int(row['indicator_id']): row for row in records('provider_attempts.csv')}
    coverage = {int(row['indicator_id']): row for row in records('data_coverage.csv')}
    mapping = {int(row['indicator_id']): row for row in records('indicator_field_mapping.csv')}
    if any(sorted(table) != list(range(1, 191)) for table in (attempts, coverage, mapping)):
        raise RuntimeError('Per-ID evidence must cover 1..190 without duplication')
    blockers = []
    for i in range(1, 191):
        a, c, m = attempts[i], coverage[i], mapping[i]
        direct = int(a['provider_request_count'])
        blockers.append({
            'indicator_id': i, 'name': a['name'], 'priority': m['priority'],
            'worker_state': a['worker_state'], 'direct_provider_requests': direct,
            'actual_indicator_series_rows': c['actual_indicator_series_rows'],
            'initial_vintage_component_rows': a.get('initial_vintage_component_rows', '0'),
            'initial_yearly_vintage_component_rows': c.get('initial_yearly_vintage_component_rows', '0'),
            'initial_yearly_vintage_windows': a.get('initial_yearly_vintage_windows', '0'),
            'pit_status': m['pit_status'],
            'blocking_evidence': a['evidence'] or m['source_caveat'],
            'next_action': a['next_retry_or_action'],
            'direct_request_gap': 'yes' if direct == 0 else 'no',
            'verified_blocked': 'no',
        })
    write_csv('collection_blockers.csv', blockers)
    audit = json.loads((HERE / 'audit_190_summary.json').read_text())
    manifest = json.loads((HERE / 'phase2_baseline_manifest.json').read_text())
    crash = records('crash_warning_backtest_summary.csv')
    direction = records('regime_backtest_summary.csv')
    final_crash = [row for row in crash if row['split'] == 'final_holdout']
    final_direction = [row for row in direction if row['split'] == 'final_holdout']
    lines = [
        '# Regime190 Phase 2 research checkpoint',
        '',
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        '',
        '## Actual coverage and gates',
        '',
        f"- Unique indicator IDs: {audit['indicator_ids']}; duplicate IDs: {audit['duplicate_ids']}.",
        f"- Worker states: {audit['worker_states']}; direct provider requests still absent for {sum(x['direct_request_gap']=='yes' for x in blockers)} IDs.",
        f"- Derived indicator observations reported across series: {audit['actual_indicator_series_rows_total']:,}; this is not a count of unique source rows.",
        f"- FRED initial-vintage components: {audit.get('fred_initial_vintage_series', 0)} complete-window series, plus {audit.get('fred_initial_yearly_windows', 0)} verified yearly windows ({audit.get('fred_initial_yearly_rows', 0):,} raw observation rows). Six full-window requests exceeded the provider's JSON vintage-date limit and are being collected in bounded yearly windows.",
        '- Official PIT verified: 0 indicators. Official predictive backtest gate remains closed.',
        '',
        '## Assumption-based index baseline',
        '',
        'The signal uses only index prices known after session t close. Its first possible action is next trading day. Naver and Yahoo historical close values were required to agree within 0.0101 index points. The resulting data are retrospective snapshots without historical publication timestamps or revision proof.',
        f"Sources: KOSPI {manifest['sources'][0]['agreed_valid_rows']:,} agreed days; KOSDAQ {manifest['sources'][1]['agreed_valid_rows']:,} agreed days. Development 2010–2017, validation 2018–2021, frozen final period 2022–2026-10-20. A 20-row purge was applied to walk-forward folds.",
        '',
        '| Market | Five-day crash events | Precision | Recall | F1 | False positive rate |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for row in final_crash:
        lines.append(f"| {row['market']} | {row['crash_events']}/{row['test_rows']} | {float(row['precision']):.3f} | {float(row['recall']):.3f} | {float(row['f1']):.3f} | {float(row['false_positive_rate']):.3f} |")
    lines += [
        '',
        'Three-class rising/falling/flat balanced accuracy on the final period:',
        '',
        '| Market | Horizon (trading days) | Balanced accuracy | Macro F1 |',
        '|---|---:|---:|---:|',
    ]
    for row in final_direction:
        lines.append(f"| {row['market']} | {row['horizon_days']} | {float(row['balanced_accuracy']):.3f} | {float(row['macro_f1']):.3f} |")
    lines += [
        '',
        'The KOSDAQ crash warning has a high false positive rate. No feature set demonstrates robust deployment readiness. The target windows overlap, so these sample rows are not independent. Calibration, confidence intervals, trading costs, and official data vintages remain unverified. No profitability claim is made.',
        '',
        '## Reproduction',
        '',
        'Run phase2_baseline.py with REGIME190_INDEX_SOURCE pointing to a verified local daily-index-validation-20261021 directory. The manifest records the two source hashes per market. Run phase2_reporting.py after the baseline and the 190-ID audit. The official backtest_results.csv remains NOT_RUN under the PIT gate.',
        '',
    ]
    (HERE / 'final_research_report.md').write_text('\n'.join(lines), encoding='utf-8')
    return {'blocker_rows': len(blockers), 'final_crash_rows': len(final_crash),
            'final_directional_rows': len(final_direction)}


if __name__ == '__main__':
    print(json.dumps(run()))
