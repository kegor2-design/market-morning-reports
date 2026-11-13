# Universal Agent evidence collector and automatic next task — 2026-11-13

## Basis and delta

Repository `kegor2-design/market-morning-reports`; requested remote branch `research/regime190-ind116-pit-resolution-20261113` was fetched and its remote HEAD confirmed as `2c5609260401eda25fd2965e06a4cc55735a63ca`. The worktree was clean. This work was isolated in `research/universal-agent-collector-autonext-20261113`. Existing action modes, Agent 4.3 isolated execution, Guided E2E, Regime190 data, and PIT gate were retained.

Before this change, `research_job.py` supervised one allowlisted action and `problem_solver.collect_pit_evidence()` collected read-only KOSPI/KOSDAQ-oriented evidence. Indicator 116 had no executable source-specific alternative and a blocked task could not advance to an independent task in that Research Job. The prior `AUTONOMOUS_E2E_REPORT_20261112.md` records real-model guided repair and two exploratory market alternatives, but its source PIT and independent holdout remain unverified.

The new `evidence_workflow` action uses the existing Research Job manifest, action registry, Worker, Supervisor, hashed output, and atomic `write_state`. `problem_solver.collect_indicator_evidence()` routes a structured request to a bounded read-only adapter. The reviewed offline adapter checks the 34 original DGS2/DGS10 JSON files against their sidecar manifests **and** a fixed manifest-chain SHA, then checks all 4,204 matrix dates and the tracked matrix SHA. It returns date and source metadata separately from `data`; unknown observation, actual publication, and first-access times are `null` with reasons. Other source/indicator pairs return `NOT_SUPPORTED`; an unapproved source returns `BLOCKED_APPROVAL`; missing local inputs return `BLOCKED_ENV`; inconsistent hashes or rows return `BLOCKED_EVIDENCE`. No network or model call is made by this mode.

After `PIT_BLOCKED`, the reviewed rule selects one declared, independent, allowlisted synthetic task. It records task keys, hashes, selected and rejected actions, zero calls, and the transition reason in `workflow.json`. The verifier rereads source evidence and independently recomputes fixture arithmetic before the Supervisor accepts the action artifact. The result stays `EXPLORATORY_ONLY`; the Research Job ends `RESEARCH_BLOCKED_WITH_EVIDENCE`, reason `PIT_BLOCKED`. A new model-generated market hypothesis or official investment result is **not** claimed.

## Actual run and failure injection

The final bounded run is the private manifest `.universal_private/ind116_bounded_manifest.json` and checkpoint `.universal_private/ind116_bounded_job/job.json`. It completed one Worker attempt with zero duplicate completions and zero model/network data calls. Source result: 34 original files, 4,204 paired dates, **4,204 strict PIT blocked rows**. The following `safe_fixture` task was executed and independently verified in the same Worker without a human follow-up command. The Worker plan limited CPU to 30 seconds, address space to 512 MB, output file size to 20 MB, and open files to 64; manifest wall time was 30 seconds, retries at most one, alternative tasks one, model and source network requests zero.

Private bounded interruption probes used the same mode and no model calls. Worker SIGKILL caused two attempts, one restart, one crash, two final task records, and zero duplicate completions. Supervisor SIGKILL left a detached Worker whose artifact was verified on restart: one Worker attempt and zero duplicates. Repeating both terminal Supervisor calls left attempt counts unchanged. A deliberate `STOP` is terminal with zero attempts in the test; a crash without `STOP` resumes. Corrupt evidence hash, corrupt checkpoint JSON, duplicate task ID, unauthorized source, unreviewed source, fabricated `PIT_VERIFIED`, missing inputs, and unsafe budgets are rejected in the new tests. Existing tests cover API 400/404/429, DNS, Git 403, uncertain AI calls, static gates, and rollback boundaries.

The existing read-only `_db_sample()` returned `SCHEMA_VERIFIED_READ_ONLY_BOUNDED` with `BEGIN READ ONLY`, 5-second statement timeout and 20-row samples. All 20 sampled recent rate rows lacked both `released_at` and `vintage_date`. The current sandbox denied Bubblewrap namespace creation during the research-only automatic code repair/rollback probe, so that live probe returned `SAFE_BLOCKED`. Its escalated attempt did not execute after an environment interruption. The existing Bubblewrap repair test is the one regression skip: `OS sandbox unavailable in this test process`. Earlier E2E evidence of a real isolated repair remains inherited evidence; this branch does **not** claim a new successful repair or rollback.

## Verification and gates

| Check or gate | Verdict | Evidence |
| --- | --- | --- |
| Baseline Universal Agent / Regime190 | PASS | 90 tests (one existing skip) / 55 tests before edits |
| Collector contract and negative tests | PASS | 9 new tests in `tests/test_evidence_workflow.py` |
| CORE_REGRESSION_VERIFIED | PASS | Final Universal Agent 99 tests (one existing skip), Regime190 55 tests; compileall and `git diff --check` PASS |
| GENERAL_EVIDENCE_COLLECTOR_CONNECTED | PASS for reviewed indicator 116 offline adapter | Actual Research Job/Supervisor run and independent reread; other pairs `NOT_SUPPORTED` |
| AUTONOMOUS_NEXT_TASK_VERIFIED | PASS for reviewed rule and synthetic independent task | `collect_116: PIT_BLOCKED → safe_fixture: VERIFIED_FIXTURE`, no follow-up command |
| AUTO_REPAIR_AND_RECOVERY_VERIFIED | BLOCKED for combined gate | Current interruption recovery PASS; new Bubblewrap code repair/rollback could not run in sandbox |
| SANDBOX_AND_POLICY_VERIFIED | BLOCKED for combined gate | Policy/budget negative tests PASS; current code repair isolation unavailable in sandbox |
| EXPLORATORY_E2E_VERIFIED | NOT_RUN on this branch | Prior real-model exploratory E2E is documented, but this branch ran a source audit plus fixture only |
| LIVE_RESEARCH_E2E_VERIFIED | BLOCKED | Actual source clocks and mature sealed holdout absent |
| PIT_VERIFIED_IND116 | BLOCKED / FALSE | 4,204/4,204 strict rows blocked; 2015-04-01/02 ALFRED dates and 14:30 weekly H.15 clock are not daily FRED arrival times |
| PRODUCTION_READY | NOT_RUN | No deploy, service, order, scheduler, operating DB row or schema changed |

Model calls in this branch: **0 actual, 0 simulated**. New external market-data requests: **0**. Provider billing for inherited E2E: **UNKNOWN**; incremental model charge for this offline run: zero calls. One candidate repair probe was blocked by the sandbox; no successful code fix is counted. Human follow-up commands *inside the automatic two-task run*: **0**. The prior synthetic fixture and the current one are not independent market holdouts. Taxes, slippage, fill behavior and costs remain unverified for any official strategy claim.

## Verified run order and next checkpoint command

From the same isolated worktree, the following files and module CLI were verified. There is no new executable script to mark with `chmod +x`; the private manifest may be restricted to mode 600. The DB probe is bounded and read-only.

```bash
cd /home/kegor2/market-morning-reports-autonext
chmod 600 .universal_private/ind116_bounded_manifest.json
test -x /home/kegor2/stock_env/bin/python
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from regime190.agent3_experiments import _db_sample; print(_db_sample())'
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from pathlib import Path; from universal_agent.research_job import manifest_load; print(manifest_load(Path(".universal_private/ind116_bounded_manifest.json"))[0]["mode"])'
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p test_evidence_workflow.py -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-manifest .universal_private/ind116_bounded_manifest.json --job-dir .universal_private/ind116_bounded_job
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

**Single next-session command:** the `process_supervisor --research-manifest ... --job-dir ...` command above. The job is terminal; re-invocation rereads hashes and returns the saved result without a new Worker. To continue source acquisition, obtain approved row-level historical H.15 posting/FRED access timestamps and complete revision vintages, then create a reviewed new adapter and a new job ID. Deliberate `STOP` ends a job; do not remove a STOP marker to reinterpret it as a crash. Research-code rollback, if needed, is a reviewed `git revert` on this research branch, with regression tests before any later integration.
