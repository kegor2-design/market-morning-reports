# Regime190 historical integrity continuation — 2026-10-31

## Execution and checkpoint

The starting local and fetched remote branch HEAD were both
`31f070d29f4a58afcd3ba11c8dec72eb449456e2`. The pre-existing
`phase2_baseline.py` remained untracked and untouched. The Phase 4/5
supervisor and its old Regime190 checkpoint were inspected, not reset.
Its 34 baseline tests passed. A new declarative continuation project uses
the same supervisor and a separate private schema-3 checkpoint. The
supervisor selected and independently verified three tasks in priority
order: source/export reconciliation, universe evidence coverage, and the
190-indicator PIT readiness matrix. Each was attempted once, assigned a
distinct execution and idempotency ID, and reached COMPLETED through the
VERIFYING gate. The initial bound was 30 minutes, three tasks, one
concurrent task and up to three attempts per task. The three-task cap was
reached; no further run was started. `resolve_cutoff_origin` is the next
eligible task, still READY. The overall research goal remains blocked.

## Price-data boundary — confirmed and unresolved

The read-only source snapshot through 2026-10-27 has **2,499 symbols and
4,606,027 rows**. The existing export manifest has **2,497 symbols and
4,605,978 rows**. The per-symbol comparison has 2,481 exact source/export
matches, 16 mismatches and two source-only symbols. The export contains
1,794 symbols last dated 2026-09-15: **1,791** still end on that date in
the source snapshot, while **three** have later source rows. This confirms
that the shared cutoff is located in the source data for 1,791 symbols at
the time of the query; simply rerunning the same export cannot fill them.
The 16 mismatches and two new symbols show that the 2026-10-29 export is
older than the current source snapshot. They do not, by themselves, prove
an export-code defect. The source was being updated by an existing daily
job during this research session; the source query completed after the
price step of that job.

For the 1,791 source-cutoff symbols, the last price row's `collected_at`
falls on 2026-09-17 for 1,676, 2026-09-16 for 113, and 2026-09-15 for
two. All last-row `source_name` values are `kis`. The operating backfill
history shows 30 subsequent price runs from 2026-09-18 to 2026-10-30,
requesting 94–133 symbols per run (mean 110.8); the 2026-10-30 run
requested 107 and recorded 107 successes. The daily script defaults to
`candidates` and seven-day lookback, and no scope override was present in
the inspected non-secret setting. This **partially confirms** selective
ongoing collection as a mechanism for continuing gaps. It does not prove
which of the 1,791 symbols were requested, nor why the earlier broad
collection stopped at 2026-09-15. The run table stores aggregate counts
and error summaries, not requested symbol IDs. In the collector, a
successful API call increments `success_symbols` even when zero price rows
are returned, so `OK` alone is not evidence of complete price coverage.
An initial broad collection around 2026-09-16/17 is **inferred** from
`collected_at`, but its run record or request ledger was not found.

| Candidate cause | Finding |
| --- | --- |
| Original source collection | **CONFIRMED boundary** for 1,791 symbols; underlying request/provider cause unresolved |
| Export snapshot lag | **CONFIRMED** for 16 changed and two new source symbols relative to the older export |
| Export date filter | No explicit 2026-09-15 cutoff in derivation code; defect **NOT CONFIRMED** |
| Daily candidate selection | **PARTIALLY_CONFIRMED** by code and aggregate run history; per-symbol omission unproven |
| Delisting, suspension, provider limit | **UNVERIFIED** without dated lifecycle and request/response records |

## Historical market universe

The current `symbol_master` has 4,319 rows; 4,315 contain a plausible
listing-date string. Of the 2,499 source price symbols, 2,482 occur in
that current master and 17 do not. Only 700 source symbols have KOSPI or
KOSDAQ in their latest source price row. Local KOSPI/KOSDAQ MST files are
2026 snapshots, not a dated membership archive. The database's
`symbol_historical_context_mart` contains dated indicators but no market
membership column. Thus current master coverage is **PARTIAL** evidence
about identifiers, while historical as-of membership is **UNVERIFIED**;
the local delisting archive is **UNAVAILABLE**. No current-market value
was copied backward in time.

Official candidate sources are the KRX [new listing statistics](https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT200.jsp),
[delisted securities statistics](https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT238.jsp),
and [KIND listing/transfer notices](https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain).
Their complete historical rows were not acquired in this bounded run.
A valid universe needs dated listing, delisting and transfer events,
suspension intervals, stable symbol/ISIN links and evidence covering
delisted securities. The KRX new-listing page notes a recent-ten-year
coverage limit, so earlier history needs an additional verified source.

## PIT readiness and backtest gate

The new 190-row machine-readable matrix reconciles unique indicator IDs
across the published indicator and PIT audits and the private SQLite
checkpoint (`PRAGMA integrity_check=ok`). Classification is exclusive:

| Class | Count | Reason |
| --- | ---: | --- |
| PIT_VERIFIED | 0 | No traceable row-level release, availability and vintage evidence |
| PIT_PARTIAL | 0 | `no_data` and current snapshots are not counted as PIT evidence |
| PIT_BLOCKED | 71 | Partially acquired but publication/as-of/vintage evidence absent |
| SOURCE_MISSING | 98 | Source not acquired |
| CALCULATION_PENDING | 21 | Raw source acquired; calculation unfinished |
| **Total** | **190** | Counts reconcile |

The private checkpoint has zero `pit_eligible` flags. Observation dates
are not treated as publication dates. A uniform 16:30 `available_at`
assumption in price derivation remains unverified. Revised economic
series need actual historical vintages before backtesting. **No Regime190
backtest is eligible or was run.**

## Verification, safety and next task

The source per-symbol CSV has 2,499 unique symbols; the PIT matrix has
190 unique IDs. The supervisor's three completed tasks have independent
checks, one attempt each, and distinct execution IDs. The checkpoint is
private mode `0600`. Python compile and 35 supervisor/engine tests plus
eight Regime190 tests passed. SQLite integrity, diff and secret checks
were run before publication. Only research files and the new private
supervisor state were written by this work. The operating DB was queried
using the existing read-only role. An independent scheduled collector did
update source data on 2026-10-30; this agent did not write it, restart the
service, or change trading code, DB schema, credentials, security policy
or historical datasets. The prior unrelated working files and checkpoints
were preserved.

The automatically selected next task is `resolve_cutoff_origin`. It needs
per-symbol KIS request/response or job target logs for the 1,791 source
cutoff symbols, the 2026-09-16/17 broad run provenance, and dated KRX
listing/suspension records. A bounded read-only continuation needs no
new approval; a large backfill or operating collector change does.
The next run should use `python3 -m universal_agent.supervisor_cli run-once
--project universal_agent/regime190.continuation.json --state-dir
/home/kegor2/MyDream2000/research/universal_agent/regime190-continuation-20261031`
from `market-history/research`, after new independent evidence is added.
Running it now would only hit the `review_required` gate, so this session
stopped at the three-task cap.
