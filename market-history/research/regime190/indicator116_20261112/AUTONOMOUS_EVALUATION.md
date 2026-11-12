# Indicator 116 autonomous research evaluation — 2026-11-12 KST

Base SHA: `21f3bf65fa216ad323b3a4aa0d3b9f021a3554b5`. The established Universal Agent and Regime190 engines were reused without code changes. The checked tasks were: local annual-data integrity audit, two bounded live FRED sample requests, one Treasury comparison, read-only DB schema probe, existing PIT gate, two regression suites, and Worker/Supervisor interruption probes. No real order, service, scheduler, operating DB data, or schema was changed.

| Task | Verdict | Evidence |
| --- | --- | --- |
| Existing DGS2/DGS10 annual initial-release data | PASS for acquisition/integrity | 34 private files and manifests checked; 4,204 paired numeric dates |
| Live FRED sample | PASS | Two HTTP 200 responses, 23 rows each, private response SHA recorded |
| Independent Treasury numeric comparison | PASS for 21-day sample | 21 matched dates, 0 DGS2/DGS10 value mismatches |
| Publication/vintage/09:00 KST PIT | BLOCKED | Date-level vintage and scheduled H.15 clock do not prove actual historical provider access |
| Official backtest and independent holdout | BLOCKED | No PIT-approved full-period source and no sealed target/holdout |
| Existing Problem Solver | SKIPPED | Data acquisition succeeded. Its current allowlist verifies the unrelated KOSPI/KOSDAQ PIT gate; invoking that action for indicator 116 would produce irrelevant evidence. No blocked or unverified method was registered as a successful experience case |
| Universal Agent regression | PASS | 90 tests, 0 failures, 0 skips |
| Regime190 regression | PASS | 51 tests, 0 failures, 0 skips |
| Worker SIGKILL/recovery | PASS for fixture | 2 attempts, 1 restart, 1 crash, 0 duplicate completions |
| Supervisor SIGKILL/recovery | PASS for fixture | 1 Worker attempt, 0 duplicate completions; checkpoint artifact verified on restart |
| Current live-indicator interruption | SKIPPED | Data audit used bounded read-only files and did not run a long-lived indicator Worker |

Additional human **research instructions: 0**. One sandbox permission for bounded FRED access was needed; it was not an intervention in research logic. New AI model calls: **0**. New authorized external data calls: **3** (FRED DGS2, FRED DGS10, Treasury CSV), plus two sandbox-blocked FRED connection attempts before authorization. Automatically solved data-quality errors: **0**; two fixture process interruptions recovered. Unresolved PIT/holdout blockers: **2**. Model monetary cost: **0 new model calls**; no provider billing figure was exposed. The former broad-query HTTP 400 and current sandbox connection failure are recorded as failed attempts, not successful source acquisitions.

The bounded FRED monthly probe succeeded after the previously recorded broad-query 400, but the exact 400 cause remains unproven. Consequently no new solution was promoted into `problem_experience/cases.json`; only a method with independently verified cause, procedure, result, applicable conditions, and code SHA may be registered. Private audit/probe files under `.universal_private` hold raw hashes and run details and are not committed.

Independent gate values for this indicator: `AGENT_CORE_COMPLETED=TRUE` (inherited and regression-checked, not re-developed here); `LIVE_RESEARCH_E2E_VERIFIED=FALSE`; `PIT_VERIFIED=FALSE`. The first gate concerns the previously verified Agent execution core; it does not make indicator 116 PIT-ready.

## Follow-up attempt and regression ledger — isolated as-of branch

Base remote SHA: `4242f72347ed08bc0c3e54cc437c0be8e2e4c093`; branch `research/regime190-ind116-asof-20261112`. This pass used the existing read-only source files and engines. No new agent framework, agent allowlist entry, deployment bundle, service action, order, operating DB mutation, or experience success case was created.

| Work item | Verdict | Evidence and boundary |
| --- | --- | --- |
| 34 annual FRED/ALFRED initial-vintage files | PASS | Every SHA, size, row count and ID rechecked; 4,204 paired numeric dates preserved |
| Source revision comparison | PASS for two-snapshot detection | 2 DGS2 and 4 DGS10 differing dates; full revision timeline still BLOCKED |
| Official Treasury cross-check | PASS for 2010–2023 numeric overlaps | Two new official archives, 3,500/3,500 DGS2 and 3,498/3,501 DGS10 matching; three DGS10 differences align with later FRED snapshot; 2024–2026 comparison SKIPPED |
| Historical 2015 H.15 schedule | PASS for April 6 weekly document | Official PDF says 14:30 ET; actual April 1/2 daily FRED ingestion time BLOCKED |
| 09:00 KST row-level audit | PASS for date/DST arithmetic; BLOCKED for strict PIT | 4,204 metadata rows; no actual historical posting/ingest timestamps; Naver calendar proxy only |
| Problem Solver connection | BLOCKED for indicator-specific automated resolution | `collect_pit_evidence()` ran read-only and found zero eligible indicators, no holdout. Its executable actions still target KOSPI/KOSDAQ PIT or unrelated exploratory research; invoking `solve()` for indicator 116 would not validate H.15 clocks. Existing `self_repair.diagnose()` classified three indicator-specific blockers as `UNKNOWN_ERROR/SAFE_BLOCKED`; no AI answer was promoted to evidence |
| Official backtest / independent holdout | BLOCKED | All rate dates fail strict PIT; existing 2010–2026-10-20 Korean history was already inspected; future target frozen in `HOLDOUT_PROTOCOL.md`, no mature labels |
| Universal Agent regression | PASS | 90 tests, zero failures/skips |
| Regime190 regression | PASS | 54 tests, zero failures/skips, including 3 new DST/date-cutoff/snapshot tests; first attempt failed because ignored KOSPI/KOSDAQ CSVs were absent in the new worktree, then both manifest-hashed snapshots were restored and the entire suite passed |
| Worker SIGKILL and Supervisor SIGKILL | PASS for synthetic fixtures | Worker: 2 attempts, 1 restart, 1 crash, 0 duplicate completions; Supervisor: 1 Worker attempt, 0 duplicate completions; repeat supervisor call reused terminal checkpoint without new attempt |
| Read-only operating DB schema | PASS | Existing `_db_sample()` used `BEGIN READ ONLY`, 5-second statement timeout, 20-row limits; required columns present; 20/20 recent rates lacked both `released_at` and `vintage_date` |
| Direct live FRED API call this pass | SKIPPED | All 34 first-vintage files and two 2026 snapshots were locally available and hash checked; primary Fed/FRED public documents were consulted. Earlier two bounded live calls remain evidenced in the prior report, not recounted as new |

Current pass: **0 new model calls**, **2 new Treasury archive downloads**, **0 new direct FRED data API calls**, **0 newly solved PIT blockers**, **3 classified unresolved blockers** (posting/ingest time, complete dated revisions, independent holdout). External primary-document reads were bounded to FRED/Fed/Treasury source research. Human research input after the task: **0**; one environment permission was required for the read-only Problem Solver DB probe after two network-blocked attempts. Provider model cost for this pass is exactly zero calls; monetary cost of inherited runs remains unknown. The process fixture elapsed about 8 seconds; regression suites about 33 seconds combined. No success was written to `problem_experience/cases.json` because no indicator 116 PIT method was independently verified.

**Final independent gates:** `AGENT_CORE_COMPLETED=TRUE` for the inherited, previously verified core with current regressions and fixture recovery; `LIVE_RESEARCH_E2E_VERIFIED=FALSE` for indicator 116; `PIT_VERIFIED=FALSE`. Neither the synthetic recovery PASS nor a conservative lag is counted as live-market PIT verification.

## 2026-11-13 continuation — new branch from the requested remote base

The requested base remote SHA was rechecked as `4242f72347ed08bc0c3e54cc437c0be8e2e4c093`. A separate worktree and branch, `research/regime190-ind116-pit-resolution-20261113`, imported the prior as-of research commit and extended its existing audit script. No new agent framework or operating component was added. The added parser compares bounded official Treasury annual XML against existing initial-vintage inputs; it cannot mark PIT verified. Its new test checks numeric mismatch detection.

| Check | Verdict | This pass |
| --- | --- | --- |
| 34 annual inputs / 4,204 paired dates / matrix reproduction | PASS | Every manifest checked; rebuilt matrix SHA equals tracked SHA |
| 2024–2026 Treasury alternative source | PASS for values | Three official XML requests; 715 Treasury rows; 704/704 numeric overlaps match for each series; private SHA recorded in DATA_REPORT |
| Complete revision timeline and actual H.15/FRED publication time | BLOCKED | Initial and later snapshots reveal changed dates but not all intermediate vintages or historic intraday access |
| 2015-04-01/02 exception | BLOCKED for daily posting time | Same-day ALFRED date and April 6 weekly H.15 values checked; 14:30 weekly clock cannot establish April 1/2 FRED arrival |
| Existing Problem Solver | PASS for read-only evidence collection; BLOCKED for indicator-specific repair | `collect_pit_evidence()` returned eligible IDs `[]`, holdout `NOT_AVAILABLE`, and read-only DB sample. Existing executable choices target KOSPI/KOSDAQ PIT or unrelated exploratory study, so `solve()` was not called to avoid irrelevant model output and unearned experience promotion |
| Operating DB schema | PASS read-only | `BEGIN READ ONLY`, 5-second statement timeout, at most 20 sampled rows per table; 20/20 recent rates missing `released_at` and `vintage_date` |
| Universal Agent regression | PASS | 90 tests, zero failures, one existing skip; suite includes checkpoint/recovery boundaries |
| Regime190 regression | PASS | 55 tests, zero failures; includes new Treasury XML mismatch test |
| Worker/Supervisor interruption and duplicate guard | PASS for bounded synthetic fixture | Worker SIGKILL: 2 attempts, 1 restart, 1 crash; Supervisor SIGKILL: 1 attempt; both zero duplicate completions and zero model calls. Repeating each supervisor command reused the terminal checkpoint without another attempt |
| Independent holdout / official backtest | BLOCKED / SKIPPED | Prespecified prospective target has no mature sealed outcomes; strict PIT rows remain blocked |

Automatic diagnosis separated **three unresolved research blockers**: historical actual posting and ingestion time, complete dated revisions, and independent mature holdout. **One value-coverage gap was resolved** by the 2024–2026 Treasury comparison; **zero PIT blockers were resolved**. New AI model calls: **0**. New successful external data requests: **3** (Treasury annual XML); one initial sandboxed XML request timed out and was retried with authorized network access. Human research decisions after the task: **0**; network/DB access required environment authorization. Raw XML, recovery state and result JSON remain ignored and private. The first regression attempt lacked ignored Naver CSVs; both manifest-hashed files were restored, then the complete suites passed. No operating service, order, DB data or schema was changed. The current pass repeated bounded **synthetic** Worker/Supervisor SIGKILL fixtures; no live indicator Worker was interrupted.

**Independent gates:** `AGENT_CORE_COMPLETED=TRUE` (inherited core and current regression PASS); `LIVE_RESEARCH_E2E_VERIFIED=FALSE` (indicator 116); `PIT_VERIFIED=FALSE`. No experience success case was registered.
