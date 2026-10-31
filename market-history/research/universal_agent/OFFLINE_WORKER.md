# Regime190 offline research handoff

The offline worker extends the existing research state and evidence gates. It
never invokes Codex. Its only adapter is the allowlisted Regime190 read-only
adapter. `task_queue.json` is the canonical private state; `checkpoint.json`,
`research_status.json`, `codex_handoff.json` and `research_summary.md` are
regenerated views. Outputs stay under the private state directory. No trading
code, operating database row, schema, service or provider credential is changed.

## Installation and bounded execution

Run from `market-history/research/` with `/home/kegor2/stock_env/bin/python`.
The dedicated DB role in `~/mydream2000_backtest_ro.env` is required for source
snapshots; the connection is read only with a 15-second SQL timeout. The source
query covers the latest seven calendar days. PIT rechecks read the existing
private SQLite checkpoint and published audits. They cannot approve PIT by
themselves. The backtest gate always remains blocked or review required; this
worker does not run a backtest.

```sh
umask 077
chmod 700 /home/kegor2/MyDream2000/research/universal_agent
chmod +x /home/kegor2/market-morning-reports/market-history/research/universal_agent/run_offline_regime190.sh
cd /home/kegor2/market-morning-reports/market-history/research
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker prepare --plan regime190/offline_plan.json --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-offline --repo /home/kegor2/market-morning-reports --horizon-hours 48
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker run --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-offline --repo /home/kegor2/market-morning-reports --max-tasks 3 --max-seconds 120
```

The plan contains source, PIT and backtest-gate checks at preparation, 24
hours and 48 hours. Future tasks are not eligible early. A separate
`resolve_cutoff_origin` task remains `CODEX_REQUIRED` and is never passed to
the server executor. The worker checks disk and available memory before each
task, runs one task at a time, caps a task at its declared duration, and
retries transient errors at most twice with delayed exponential backoff.
An approved data provider's quota error enters `BLOCKED_QUOTA` and is not
retried automatically; this is separate from Codex's own usage quota.
An interrupted task with a complete output is verified without rerunning;
uncertain output becomes `BLOCKED_EVIDENCE`. Existing Phase 4/5 checkpoints
are untouched.

The bounded wrapper can be used in cron after reviewing host load. It runs at
most three tasks with a 120-second worker budget and a 150-second process
ceiling. One KST cron entry:

```cron
15 2 * * * /usr/bin/flock -n /tmp/regime190_offline_research.lock /home/kegor2/market-morning-reports/market-history/research/universal_agent/run_offline_regime190.sh >> /home/kegor2/MyDream2000/research/universal_agent/regime190-offline/worker.log 2>&1 # REGIME190_OFFLINE_RESEARCH
```

Use `stop` to prevent another task starting, then remove that single tagged
cron entry to stop future scheduled runs. An active task has a 150-second
process ceiling; do not delete its state. After reviewing the checkpoint,
`clear-stop` permits future runs. For manual status and handoff recovery:

```sh
cd /home/kegor2/market-morning-reports/market-history/research
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker status --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-offline --repo /home/kegor2/market-morning-reports
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker handoff --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-offline --repo /home/kegor2/market-morning-reports
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker stop --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-offline --repo /home/kegor2/market-morning-reports
/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker clear-stop --state-dir /home/kegor2/MyDream2000/research/universal_agent/regime190-offline --repo /home/kegor2/market-morning-reports
```

When Codex returns, inspect HEAD and fetch the remote branch, read the private
`codex_handoff.json`, validate its `queue_sha256` against `task_queue.json`,
review new artifacts and task statuses, then prepare a reviewed next horizon.
`prepare` refuses a changed plan for an existing queue. Do not reset or
overwrite a checkpoint to extend the plan; create a versioned plan and new
private queue after reviewing the prior handoff. Quota recovery does not
trigger an automatic Codex session.
