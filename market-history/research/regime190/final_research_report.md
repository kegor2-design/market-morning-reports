# Regime190 Phase 2 research checkpoint

Generated UTC: 2026-11-10T22:08:10.237584+00:00

## Actual coverage and gates

- Unique indicator IDs: 190; duplicate IDs: 0.
- Worker states: {'PARTIAL': 92, 'NEEDS_REVIEW': 98}; direct provider requests still absent for 147 IDs.
- Derived indicator observations reported across series: 36,831,658; this is not a count of unique source rows.
- FRED initial-vintage components: 10 complete-window series, plus 14 verified yearly windows (5,009 raw observation rows). Six full-window requests exceeded the provider's JSON vintage-date limit and are being collected in bounded yearly windows.
- Official PIT verified: 0 indicators. Official predictive backtest gate remains closed.

## Assumption-based index baseline

The signal uses only index prices known after session t close. Its first possible action is next trading day. Naver and Yahoo historical close values were required to agree within 0.0101 index points. The resulting data are retrospective snapshots without historical publication timestamps or revision proof.
Sources: KOSPI 4,126 agreed days; KOSDAQ 4,129 agreed days. Development 2010–2017, validation 2018–2021, frozen final period 2022–2026-10-20. A 20-row purge was applied to walk-forward folds.

| Market | Five-day crash events | Precision | Recall | F1 | False positive rate |
|---|---:|---:|---:|---:|---:|
| KOSPI | 104/1164 | 0.303 | 0.423 | 0.353 | 0.095 |
| KOSDAQ | 171/1164 | 0.183 | 0.889 | 0.304 | 0.682 |

Three-class rising/falling/flat balanced accuracy on the final period:

| Market | Horizon (trading days) | Balanced accuracy | Macro F1 |
|---|---:|---:|---:|
| KOSPI | 1 | 0.342 | 0.340 |
| KOSPI | 3 | 0.365 | 0.365 |
| KOSPI | 5 | 0.362 | 0.358 |
| KOSPI | 10 | 0.327 | 0.317 |
| KOSPI | 20 | 0.314 | 0.295 |
| KOSDAQ | 1 | 0.364 | 0.365 |
| KOSDAQ | 3 | 0.393 | 0.390 |
| KOSDAQ | 5 | 0.379 | 0.370 |
| KOSDAQ | 10 | 0.356 | 0.335 |
| KOSDAQ | 20 | 0.369 | 0.362 |

The KOSDAQ crash warning has a high false positive rate. No feature set demonstrates robust deployment readiness. The target windows overlap, so these sample rows are not independent. Calibration, confidence intervals, trading costs, and official data vintages remain unverified. No profitability claim is made.

## Reproduction

Run phase2_baseline.py with REGIME190_INDEX_SOURCE pointing to a verified local daily-index-validation-20261021 directory. The manifest records the two source hashes per market. Run phase2_reporting.py after the baseline and the 190-ID audit. The official backtest_results.csv remains NOT_RUN under the PIT gate.
