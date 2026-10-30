# Regime190 read-only audit — 2026-10-31 KST

## Scope and evidence

The fetched `origin/research/regime190-data-audit-20261027` and local HEAD were both `ad12cb7e3f1a99f2b0b16b8fc25f479a5abb64e1` before this report. The published inventory was generated on 2026-10-29 14:56 UTC. The private `progress.json` was updated on 2026-10-30 15:00 UTC, but the SQLite task and request records and FRED attempt log have not advanced since 2026-10-29. A later progress timestamp alone does not prove new collection. Private raw data, keys, and the operating database were not changed or published.

The 190-row, per-indicator evidence table is [`indicator_audit_20261031.csv`](indicator_audit_20261031.csv). It includes ID, name, provider, raw and calculation state, PIT evidence gaps, last task attempt, retry, alternative-provider status, cause and next action. Its source is the published inventory, quality and mapping tables reconciled against the private SQLite checkpoint in read-only mode. `audit_snapshot_20261031.py` reproduces it on this server. “Alternative provider: unconfirmed” is deliberate: a substitute cannot be accepted before indicator-definition, license and historical-release comparison.

## Reconciled totals

| Classification | Indicators | Interpretation |
|---|---:|---|
| A. Collection complete | 0 | No indicator has full target history and verified definition. |
| B. Collection incomplete | 190 | 71 partial, 21 raw acquired but calculation incomplete, 98 not acquired. These three exclusive groups sum to 190. |
| C. Calculation incomplete | 190 | 49 have some generated rows, but none has a complete validated indicator; 141 have zero generated rows. The 21 raw-only indicators are within this count. |
| D. PIT validated | 0 | No indicator has all release-time, as-of, vintage, leakage and universe checks. |
| E. PIT incomplete | 190 | Exclusive complement of D. |
| F. Backtest eligible | 0 | Regime190 backtest remains `NOT_RUN_PIT_GATE`. |
| G. Further action required | 190 | Source, calculation and PIT work remain. |

The generated-row sum of the 49 nonzero indicators is **36,831,658**. This is a count of candidate derived values, not 36.8 million PIT-approved observations. Published quality results are `PARTIAL` for 49 indicators and `NOT_VALIDATED` for 141. No indicator is marked PASS here.

## The 147 versus 0 discrepancy

`audit_190.py` defines `provider_requests_unattempted` as `provider_attempt_count == 0` in the 190 SQLite tasks. This is **147**. `worker_progress.json` uses `unattempted_provider_or_fallback`, which counts tasks with neither a direct-provider request nor a local/DB fallback attempt. That is **0**. All 147 provider-zero tasks have at least one fallback attempt. The remaining 43 have direct-provider attempts. The 147 group consists of 59 partially acquired, 8 raw-only, and 80 not acquired indicators. The checkpoint `requests` table has 18 acquired FRED request records across 12 indicators and 16 series; it is not a ledger of all 190 direct-provider obligations. A fallback attempt does not prove adequate coverage or a successful indicator calculation. The published `collection_attempts_complete=false` remains correct.

## Data integrity, missingness and PIT

The private checkpoint has 190 unique task IDs, 18 request records, and `PRAGMA integrity_check=ok`. Ten saved FRED initial-vintage JSON files match their SHA-256 manifests. All 2,497 private derived daily price files match manifest SHA-256 and size; the manifest records 4,605,978 source rows and 36,534,011 candidate indicator values across eight derived indicators. A full scan found zero duplicate `(symbol, market_date)` keys and zero manifest row-count mismatches in these files. **The daily-price manifest records 4,488,363 rows with missing market mapping**, a material scope defect. Published quality checks leave 141 indicators without a row-level duplicate audit; therefore a global duplicate-free claim is not supported.

Observation dates exist, but a source row's assumed `available_at` does not establish the actual publication hour. Historical as-of availability and revision history are not linked to each indicator's complete input set. FRED `output_type=4` provides initial-release values for some components, but release hour, target definition, Korean decision-time conversion, and all other components remain unresolved. The historical as-of stock universe is unverified, leaving survivorship bias possible. Forward leakage cannot be ruled out. `PIT_UNVERIFIED` applies to every indicator, including FRED files whose manifests were successfully hashed. The separate `phase2_baseline.py` file in the worktree is an untracked, assumption-only experiment and is not treated as a Regime190 PIT backtest.

## FRED HTTP 400 root cause

The adapter requests `output_type=4` with `file_type=json`, `observation_start=2010-01-01`, `observation_end=2026-10-27`, and the same full `realtime_start` and `realtime_end`. A minimal live read of each failed series returned the following FRED error: the real-time span exceeds **2,000 vintage dates for JSON**. The code saved only HTTP status 400, so the private `.bad_request.json` files do not contain this useful response detail. The series are valid FRED identifiers; HTTP 400 here does not establish absent data or a permanent provider restriction.

| Series | Vintage dates reported by FRED | Limit | Relevant indicator IDs |
|---|---:|---:|---|
| DFEDTARL | 4,890 | 2,000 | 125 |
| DFEDTARU | 3,822 | 2,000 | 125 |
| DGS10 | 4,142 | 2,000 | 116, 117 |
| DGS2 | 4,143 | 2,000 | 116, 117 |
| RRPONTSYD | 2,630 | 2,000 | 122 |
| VIXCLS | 3,960 | 2,000 | 133 |

For a future collector change, paginate by bounded, nonoverlapping **real-time** intervals below the vintage limit, verify inclusive boundary handling and per-series date/observation keys, retain already hashed files, and write each new part with its own checksum before merging. A small interval probe should confirm that `output_type=4` and requested observation ranges yield the intended first-release semantics. `output_type=1` over the same full interval also returned HTTP 400 for DFEDTARL (4,891 vintage dates), so changing output type alone is insufficient. Check the API's JSON vintage limits and `vintagedates` endpoint before implementation: [FRED observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), [FRED vintage dates API](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html).

## Resume order and remaining risks

1. Preserve the 10 verified FRED files and 2,497 derived files. Diagnose the six 400 series with bounded requests and add response-code/message classification; do not rerun existing successful series.
2. Resolve missing market assignments for price rows against historical exchange membership; retain original source rows and compare as-of universe membership before market aggregation.
3. For the 80 no-source indicators with no direct-provider request, prioritize exact-definition provider mapping and a small documented probe. The other 67 provider-zero indicators also need evidence that their fallback matches the required definition.
4. Complete the 21 raw-only calculations and reconcile the 49 partial calculations with target frequency, field mapping, coverage, duplicates and formula reference values.
5. Attach row-level release timestamps, historical as-of and revision/vintage evidence. Only then reconsider the PIT gate and run a backtest.

Provider licensing, complete market scope, old revisions and survival-universe reconstruction remain material risks. Research service execution cannot substitute for any of these checks.

## Verification and service visibility

- `python3 -m compileall -q market-history/research/regime190`: passed.
- `stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -v`: 5 passed. System Python lacked pandas; the project environment passed all tests.
- SQLite schema read only: `tasks` and `requests`; 190 and 18 rows. `PRAGMA integrity_check`: `ok`. No operating DB schema was changed.
- Disk: 46 GiB available on the 94 GiB home filesystem at audit time, 51% used.
- Installed user service files exist, and the prior `service_audit.md` recorded a running worker. The current `systemctl --user status` could not connect to the user bus (`No medium found`); the system unit names were not found. The sandbox process view and journal had no useful worker entries. **Current service execution is unverified**, and the progress timestamp is not treated as proof of success.

## Phase 1 follow-up at 2026-10-30 15:14 UTC

The GitHub research branch still matched local HEAD `83b0bedbbdf8b270695b4566c4c5b910ec4af61d` before this follow-up. MyDream2000 and MarketMorningPublisher have extensive unrelated local changes and different remote histories; neither working tree was modified. The research branch's untracked `phase2_baseline.py` was also left untouched. No other Regime190 process was visible in the available process namespace, but this cannot prove that no host-side Codex or user service is active. `systemctl --user status` again failed with `No medium found`.

**Autonomously selected task 1 — verify a safe FRED request window.** All six previously failed series returned HTTP 200 for `output_type=4`, JSON, and observation and real-time bounds of `2019-01-01` through `2019-12-31`. Returned rows were 364 each for `DFEDTARL` and `DFEDTARU`, 260 each for `DGS10` and `DGS2`, and 261 each for `RRPONTSYD` and `VIXCLS`. Each response included `date`, `realtime_start`, `realtime_end`, and `value`; `count` equaled returned rows. A second spot check found 11 `value="."` rows in DGS10 and zero in DFEDTARL. Every checked row's `realtime_start` followed its observation date. A 2019-12-30 observation with `realtime_start=2019-12-31` illustrates why observation date cannot be used as availability date. These responses prove bounded requests are feasible, **not** that the complete historical series or release hour is verified. No probe response was persisted as research data.

**Autonomously selected task 2 — locate the price-data gap.** A full read-only scan of 2,497 hashed derived symbol files confirmed 4,605,978 source rows. The historical `market` field is absent in 4,488,363 rows: all rows through 2024, 435,301 of 488,280 in 2025, and 329,487 of 394,123 in 2026. Every derived row has `available_at` ending in `16:30:00`; this uniform value is not evidence of actual release time. Only 130 symbols have data through the 2026-10-27 target date; 2,185 end before October 2026, including 1,794 ending exactly on 2026-09-15. Read-only, five-second-timeout source DB queries for `000040`, `000050`, and `000020` matched the derived manifests' last dates (2026-09-15, 2026-09-15, and 2026-10-13). This limited sample does not identify why so many source histories stop together. It does show that blindly rerunning the same derivation would not fill these three gaps.

The companion [`phase1_checkpoint_20261031.json`](phase1_checkpoint_20261031.json) records task statuses, evidence, dependencies and the next resume step. The current 190-indicator totals remain 71 partially acquired, 21 raw-only, 98 unacquired, 0 PIT ready and 0 backtest eligible. No research or operating collection service was restarted, no database writes were made, and no existing data was deleted.
