# Regime190 PIT evidence recovery — 2026-10-31

## Baseline and cutoff origin

Starting research HEAD was `00a9994872484d9e22ad55f92a0b2439a2a70a88`;
local and remote matched and the tree was clean. The current 190-indicator
audit and private SQLite checkpoint were recomputed, not copied from the
prior summary: 0 PIT_VERIFIED, 71 PIT_BLOCKED, 21 CALCULATION_PENDING and
98 SOURCE_MISSING. SQLite integrity was `ok`.

The read-only source snapshot has 1,791 symbols ending 2026-09-15 in both
source and export. Their latest row was collected on 2026-09-17 for 1,676,
2026-09-16 for 113 and 2026-09-15 for two. A fresh read-only aggregate of
`public.domestic_daily_price` found 4,241,230 KIS-labelled rows across 1,935
symbols collected on 2026-09-17. The recorded price backfill run at 16:40
that day requested 145 symbols and reported 870 inserted rows. The large
load was therefore separate from that recorded daily run. Collection hours
00:00–07:00 had market dates no later than 2026-09-15; the 16:00 daily run
reached 2026-09-17. The daily collector's default `candidates` scope draws
symbols from ranking, signal and paper-trade tables. Its run table stores
aggregate counts and `errors`, not a requested-symbol ledger.

This **partially confirms** an overnight broad load ending 2026-09-15 and a
later selective collection path. The original broad request, its target end
date, provider response, per-symbol request list and operator/job provenance
were not found. The exact cause of the original cutoff remains **BLOCKED_EVIDENCE**.
`collected_at` is ingestion/update time. The operating collector's UPSERT can
replace earlier `collected_at` and `raw_json`; neither field proves original
publication or decision-time availability. See
`cutoff_origin_evidence_20261031.json` for query results and limitations.

## Indicator evidence and source candidates

`indicator_pit_evidence_inventory_20261031.csv` contains one row per indicator
with required fields, provider, distinct date/time evidence, revision and
vintage evidence, historical universe, survivorship, corporate-action and
licensing status, alternative candidates and missing evidence. No indicator
was promoted. Price-derived SMA/EMA, returns, volatility, RSI and similar
indicators are calculation candidates. The first bounded review should target
SMA (ID 1), MACD (13), RSI (14), ATR (29), realized volatility (36) and
drawdown speed (40), using index series where their definition permits it.
Their source date, historical market
membership, adjustment policy and decision-time availability remain open.
The read-only economic vintage table has 54 OK rows from 2026-05-28 to
2026-10-29, with zero non-null `released_at` timestamps. Its vintage dates
alone cannot approve an indicator for historical trading decisions.

Official source candidates checked on 2026-10-31: [KRX new listings](https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT200.jsp)
offers market, listing and delisting fields but notes recent-ten-year
new-listing coverage; [KRX delistings](https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT238.jsp)
offers delisting dates and reasons; [FRED observations API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
supports real-time periods and vintage dates. No row-level historical
membership or vintage data was acquired from these pages in this run.
Provider usage and redistribution rights remain unverified.

## Autonomous execution and backtest gate

The existing supervisor ran the new declarative project
`universal_agent/regime190.evidence-recovery.json` with three tasks, 1
concurrent task, two retries per task and 30-minute cap. It selected
`reconcile_cutoff_ingestion`, then `inventory_indicator_pit_fields`, then
`evaluate_backtest_gate` after each dependency completed. Every task passed
independent checks and entered RUNNING, VERIFYING, COMPLETED once. The private
schema-3 checkpoint is mode 0600, has three selection records and three task
starts. A subsequent `resume` made no duplicate attempt. This demonstrates
automatic **evidence verification and next-task selection**, not autonomous
source acquisition or root-cause resolution. No Codex call was made in this
run; prior Phase 4/5 records contain real read-only Codex calls.

The research outcome remains partial. Zero indicators have a complete
decision-time PIT record, so historical regime backtesting is **BLOCKED**.
No train/validation/test split, walk-forward evaluation, crash/recovery
metrics or performance result was produced. Existing `backtest_results.csv`
was not used as a PIT-approved result.

## Safety, verification and next tasks

Common-agent tests: 39 passed. Regime190 tests: 10 passed. Python compile,
`git diff --check`, 190 unique CSV IDs, CSV newline check, JSON parse, private
checkpoint parse and SQLite integrity passed. Only research code/artifacts
and a new private supervisor checkpoint were written. No production code,
DB schema, DB data, service, credential or Codex security policy was changed
by this work. Independent verification of other actors' production changes
is outside this audit.

1. Obtain the overnight bulk-load request/response or job log and compare its
   target end and symbol ledger against the 1,791 cutoff symbols.
2. Acquire dated KRX listing, delisting and transfer records with usage rights;
   resolve historical market membership without current-universe substitution.
3. For the first price-derived indicator subset, verify raw OHLCV, calculation,
   source release time, correction history, adjustment policy and next-decision
   availability. Begin a limited chronological backtest only after that gate
   passes.
