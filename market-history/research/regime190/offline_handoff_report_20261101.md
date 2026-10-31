# Regime190 offline research handoff — 2026-11-01 KST

## Baseline

Starting branch `research/regime190-data-audit-20261027`; local and remote
HEAD both `6522db75821938119fcfc923f6ce7f9738d8430a`; working tree clean.
The existing Phase 4/5 supervisor, Runner, private checkpoints and research
registry were preserved. Recalculation from the current indicator audits and
private SQLite checkpoint returned 190 total, 0 PIT_VERIFIED, 71 PIT_BLOCKED,
21 CALCULATION_PENDING and 98 SOURCE_MISSING. The original
`resolve_cutoff_origin` evidence gap remains open: the overnight bulk request,
response, target list, historical universe and actual publication/availability
times were not found.

## Offline worker and bounded execution

`universal_agent/offline_worker.py` uses a canonical private `task_queue.json`
with atomic writes and the existing file lock. Checkpoint, research status,
handoff and summary files are derived views. The worker uses only allowlisted
server task types in `regime190/offline_tasks.py` and has no Codex invocation
path. A 48-hour plan schedules read-only source snapshots, 190-indicator PIT
rechecks and backtest-gate reevaluations at preparation, 24 and 48 hours. The
unresolved cutoff-design task is `CODEX_REQUIRED` and is skipped. No new
provider retrieval or historical backtest is authorized by this plan.

Actual offline execution: `source_snapshot_d0` completed first; checkpoint 1
selected `pit_recheck_d0` without another prompt. A second bounded run
completed `pit_recheck_d0` and `backtest_gate_d0`; checkpoint 3. The source
snapshot observed latest market date 2026-10-30, 676 rows and 160 symbols in
the seven-day query window, and five recent price runs. PIT recheck found zero
approved indicators, so the gate returned `BACKTEST_BLOCKED`. A further run
processed zero tasks; each completed task retains one attempt. The checkpoint
SHA256 matches the canonical queue. `codex_handoff.json` lists completed and
CODEX_REQUIRED tasks, PIT counts, the backtest gate, unresolved problems and
the Git reference. `stop` prevented another task; `clear-stop` restored
eligibility. Unit failure injection covers interrupted verification using an
existing artifact, delayed retry, resource stop and no duplicate execution.

## Server and safety

At preflight the host had two vCPUs, about 2.9 GiB available memory and 47
GiB free disk. The dedicated DB connection was verified read only, required
`domestic_daily_price` and `historical_backfill_run` columns existed, and SQL
queries use a 15-second statement timeout. The worker checks at least 256 MB
available memory and 1 GB free disk before each task. Task duration is capped
at 60 seconds in the plan, the worker at 120 seconds, and the wrapper process
at 150 seconds. Only one task runs at a time. The worker writes only under
`~/MyDream2000/research/universal_agent/regime190-offline` (private 0700;
state files 0600). No production DB writes, schema changes, trading changes,
service restarts, Codex calls or credential changes were made.

The host's user systemd bus was unavailable. The system cron daemon was
running. After bounded execution and tests, a single tagged 02:15 KST cron
entry was installed for the wrapper, protected by `flock`. The previous
crontab was backed up to `~/regime190_crontab_before_20261101.txt`; the
installed crontab was compared byte-for-byte with the syntax-checked candidate
and only the new tagged line differed from the backup. **A scheduled firing
has not yet occurred in this session.** Remove the tagged entry and run
`offline_worker stop` to halt future tasks; preserve the state directory.

## Verification and next handoff

Before changes, 39 common and 10 Regime190 tests passed. After changes, 44
common and 10 Regime190 tests passed; Python compile, Bash syntax and Git diff
checks passed. The PIT gate remains closed. When Codex becomes available,
fetch the research branch, inspect HEAD and the private handoff, validate
`checkpoint.json.queue_sha256` against `task_queue.json`, compare new server
artifacts, then review a new 24–72 hour plan. Quota reset alone does not start
Codex or approve any PIT indicator.
