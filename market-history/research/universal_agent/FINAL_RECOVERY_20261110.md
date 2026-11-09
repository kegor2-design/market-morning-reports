# Universal Agent recovery and verification, 2026-11-10 KST

## Scope and disposition

Repository `kegor2-design/market-morning-reports`, research branch
`research/autonomous-core-recovery-20261107`. Starting HEAD and remote were
`b2c2de7642f122c4f00588636740e2dec84ac757`; the tree was clean. The
code change is `2007ff5f0f7aa6c6e02de54490969d4af4eaa322`. The prior
`PART1_GUIDED_EVIDENCE_20261109.md` and `FINAL_INTEGRATION_20261109.md`
were checked against code, private AI artifacts, checkpoints and new executions.

| Gate | Verdict | Evidence and limit |
| --- | --- | --- |
| A. Real AI hypothesis | PASS | `gpt-6-sol` request/response `ai_request.json`/`ai_response.json`, response SHA-256 `dab85a33c500829b570bbbe3ab632fc34b9dca6a85280c94ef68e620e8e7b8a7`. |
| B. Real code generation | PASS | Plan-first real code response SHA-256 `7a2f25a87d3127ac6c76b3551879f68fd0ff2b3396c753f2ea090d1e969007d6`; code SHA-256 `45b3d14aa7b1cf1410106cefd182f36d1e6cfc6afae3997d774f2c6c31089be9`. |
| C. Real self-repair | PASS for injected research-code fault | A **new** `gpt-6-sol` request at `2026-11-09T16:00:45Z` contained the failing source and `AttributeError` traceback. Response SHA-256 `7ce8a33a03ea133f02170fc225849c21eb71f4e1a20aa8ca21f597cc2d08c925`; repaired code SHA-256 `56e47bd3e4067f3a9759f3db47d0d4246457ada9659bd9ab937baa846a2e8595`. Static gate, Bubblewrap, output contract and both folds passed. The model response corrected `math.no_such_log` to `math.log`; the root cause is inferred from that change, not separately stated by the model. No spontaneous model defect or autonomous data-adapter repair was shown. |
| D. Secure execution | PASS for this host/run | `probe_secure_runner()` returned `SECURE_RUNNER_VERIFIED`, home hidden and separate network namespace; generated code ran under Agent 4.3's Bubblewrap limits. The ordinary tool sandbox cannot nest Bubblewrap, so live experiments used an approved host process. |
| E. End-to-end | PARTIAL | Goal, real AI hypothesis and plan, staged actual index snapshots, generated code, secure execution, two-fold backtest, host evaluation, real AI decision and checkpoint are connected. Only the fixed crash20 adapter is supported; acquisition of new PIT-valid data and a further research cycle were not demonstrated. |
| F. Autonomous decision | PASS for supported goal | AI decision response SHA-256 `7f70caa94133bc15f8d02382356e5a855a0ca39a704c7909743b0ce91f48061b`; policy accepted `PIT_VALIDATION_REQUIRED` after a rejected exploratory hypothesis. |
| G. Autonomous resume | PASS for bounded worker crash | Independent supervisor PID `2278121` observed worker PID `2278122` exit `-9`, then started PID `2278123` without a Codex restart command. Final status `COMPLETED`, launches 2, restarts 1. Launcher had already exited; an actual Codex session termination was not reproduced. |
| H. Regression | PASS for tested scope | Universal 81 tests and Regime190 51 tests passed after changes; compileall and `git diff --check` passed. No tests were deleted or thresholds relaxed. |
| I. GitHub remote | PASS | Research-branch push succeeded. `git ls-remote origin refs/heads/research/autonomous-core-recovery-20261107` matched local HEAD after publication; the final SHA is recorded in the delivery response. No operating-branch merge. |

`AGENT_CORE_COMPLETED = FALSE` because E is PARTIAL. Regime190 190-indicator
PIT coverage and long-term PIT backtest remain separate and incomplete.

## New recovery execution and retained evidence

Private request/response artifacts: `.universal_private/live_repair_20261110/`.
Execution and traceback: `market-history/research/.universal_private/live_repair_20261110/guided_state.json`
and `integrated_fault_evidence.json`. Original model code SHA-256 was
`45b3d14aa7b1cf1410106cefd182f36d1e6cfc6afae3997d774f2c6c31089be9`;
injected failing research copy SHA-256 was
`7b21c3aaded01a2a88d01284f8b6470204247cc103270eeca5dce0819decdcb7`.
The actual isolated error was `AttributeError: module 'math' has no attribute
'no_such_log'`, classified `CODE_ERROR`. The new repair request has prompt
SHA-256 `8119e4cf76b2f5e25552d00d2ac0ca162931c0bfb5b41df8074a878c527bee6f`.
The output contract and secure reexecution passed. Earlier rollback evidence
at `market-history/research/.universal_private/guided_crash_20261109/fault_trial/fault_evidence.json`
shows a rejected candidate rolled back before a successful alternative.

The new supervisor state is
`market-history/research/.universal_private/supervisor_trial_20261110/job.json`.
It recorded `DATA_STAGED` before the deliberate kill, crash detection at
`2026-11-09T16:02:46.609Z`, and a restart at `16:02:46.614Z` from checkpoint
`2026-11-09T16:02:46.528Z`. The worker completed at `16:02:47.620Z`.
Reinvoking the same Job ID returned `COMPLETED` with launch count 2 and no
further process. No test process remains. The supervisor uses a bounded retry
and wall-time budget, a persistent job file, a STOP marker and graceful SIGTERM.
An interrupted model request with uncertain output still fails closed rather
than repeating an AI call.

## Data, evaluation and side effects

Actual Naver Finance KOSPI/KOSDAQ snapshot dates span 1996-01-03 to
2026-10-20 and 1996-07-02 to 2026-10-20. The generated fold used 1,721
training rows for 2005-2011 and 720 validation rows for 2012-2014; fold 2
used 2,461 training rows through 2014 and 717 validation rows for 2015-2017.
The 20-session embargo and sealed validation labels were enforced. There is
no untouched test period; previous work inspected both validation periods.
Publication/vintage timing and historical index composition remain unverified,
so survivorship and look-ahead risks cannot be ruled out. This is index risk
classification, not a traded portfolio: transaction costs, slippage and
maximum drawdown are not applicable, and no trading-performance claim is made.

The plan-first original code scored validation PR-AUC 0.014245 versus a
volatility-only 0.016667 in fold 1, and 0.024000 versus 0.023952 in fold 2.
At the fixed threshold precision and recall were 0 in both folds; false
positive rates were 0.15960 and 0.02945. High-risk decile event rates were
0 and 0.01389, versus overall 0.01667 and 0.00558. The hypothesis was
`REJECTED_EXPLORATORY`; improving its score was not treated as a code repair.
The repaired code also passed both folds, but its result is not an independent
performance test.

The live PostgreSQL probe used `BEGIN READ ONLY`, `information_schema`, a
5-second statement timeout and 20-row sample caps; status was
`SCHEMA_VERIFIED_READ_ONLY_BOUNDED`. Historical price `market` values were
missing in 20/20 sampled rows; rates `released_at` and `vintage_date` values
were missing in 20/20. These are missing values, not inferred missing columns.
No DB schema or row was changed. No production branch, cron/systemd service,
trading API or operating process was changed. Existing Agent 2.0, 3.x, 4.3,
Universal, checkpoint, runner and Regime190 interfaces remained intact. The
only new persistent control is a per-job private file; the supervisor process
exits when the bounded job completes. Runtime overhead is one small host
supervisor process during a job. Its current limitation is one approved guided
crash20 job per state directory, with no general research-goal queue adapter.

## Recovery checkpoint and next work

Completed: live fault-specific AI repair, secure reexecution, bounded crash
restart, actual exploratory research, read-only DB inspection, and regression.
Blocked: independent PIT validation and a fresh holdout; all 190 Regime190
indicators and long-term PIT backtest. Current checkpoint is the completed
`supervisor_trial_20261110` job and the plan-first guided state. Next action:
obtain verifiable publication/vintage timestamps and an untouched evaluation
period, then rerun the frozen protocol and allow the policy engine to decide
the next research cycle. Do not label the current scores as validated risk
forecasting performance.

## Commands verified in this worktree

```bash
cd /home/kegor2/market-morning-reports-core-recovery
/home/kegor2/stock_env/bin/python --version
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from regime190.agent3_experiments import _db_sample; import json; print(json.dumps(_db_sample()))'
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from universal_agent.self_repair import probe_secure_runner; import json; print(json.dumps(probe_secure_runner()))'
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m compileall -q market-history/research/universal_agent market-history/research/regime190/agent43_engine.py
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.guided_experiment --ai-state-dir .universal_private/plan_first_crash_20261109 --state-dir market-history/research/.universal_private/plan_first_crash_20261109 --ai-next-action
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python market-history/research/universal_agent/tests/manual_guided_auto_repair.py --ai-state-dir .universal_private/live_repair_20261110 --state-dir market-history/research/.universal_private/live_repair_20261110 --live-repair
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --ai-state-dir .universal_private/plan_first_crash_20261109 --state-dir market-history/research/.universal_private/supervised_crash_20261110 --job-dir market-history/research/.universal_private/supervisor_trial_20261110
git diff --check
```

The live repair command was executed in the approved host context. The
supervisor's initial detached launch and worker kill used the bounded temporary
launcher `/tmp/launch_guided_supervisor_20261110.py`; the displayed supervisor
command was executed afterward to verify duplicate prevention. `chmod` was
unnecessary because Python modules were invoked through the interpreter.
The historical rollback and broader fault-injection commands were executed in
the previous work and their private outputs were inspected here; they were not
rerun in this session. No new provider acquisition, PIT-valid test, full
Regime190 backtest or operating service deployment command was executed.
