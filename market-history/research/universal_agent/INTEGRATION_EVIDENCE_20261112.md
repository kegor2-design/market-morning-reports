# Universal Agent integration evidence — 2026-11-12 KST

## Basis and scope

Repository `kegor2-design/market-morning-reports`; base branch `research/universal-agent-orchestration-20261110`; remote and local base SHA `bd2eb4c80d354896fcd5ffa52fb761f8a81bb9a4`. Remote `main` was `d424f163f41056a9e19d41a160f7b26b4b4032d3` (2026-10-27), older than the research base (2026-11-10). Original worktrees were clean. Work took place only on `research/universal-agent-integration-20261112` in a separate worktree. Code commit: `fba417bf05b34926db6e4619f5d9729a0a20c88f`.

No production service, scheduler, trade path, operating DB row, or schema was changed. No deploy bundle is required: the changed code belongs to the market research repository, not MyDream2000 deployment. No executable script was added; existing Python module invocation is used. Private logs and raw snapshots remain ignored and untracked.

## Existing functions and change comparison

| Function | Base | Current | Remaining gap |
| --- | --- | --- | --- |
| Supervisor and Research Job | Bounded fixed action registry, checkpoint, worker restart, PIT Problem Solver | Registered `GUIDED_EXPERIMENT` action in the same job protocol | General multi-task planning remains absent |
| Guided Experiment | AI hypothesis, static gate, Bubblewrap folds, Self Repair, checkpoint | Called by Research Job worker; verified by a read-only independent replay of inputs, code, sealed output, and assessment | Current integrated run did not trigger a new repair |
| Problem Solver | Read-only PIT diagnosis, local cases, exploratory alternative | Existing action preserved, tests passed | No cross-action scheduler for independent blocked tasks |
| Hypothesis rejection | Negative fixture conclusion recorded | One bounded alternate-direction fixture experiment executed and independently checked | No new real-market hypothesis was executed |
| Regime190 | PIT gate and exploratory engine | Reused unchanged | Historical source release/vintage and untouched holdout unavailable |

Files changed: `research_job.py` (guided adapter, independent verification, fixture transition), `research_job.schema.json` (allowlisted guided mode and bounded inputs), `tests/test_research_job.py` (rejection, follow-on, checkpoint reuse). Existing guided CLI and checkpoint format remain unchanged. The new manifest mode is additive.

## Executed verification

| Check | Verdict | Evidence |
| --- | --- | --- |
| Universal Agent regression | PASS | 89 tests, 0 failed, 0 skipped; `python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q` |
| Regime190 regression | PASS | 51 tests, 0 failed; same discovery command with `regime190/tests` |
| Python compile and Git whitespace | PASS | `compileall -q` and `git diff --check` |
| Guided + Research Job integration | PASS | `.universal_private/guided_verified_job/job.json`: 1 attempt, 0 crashes, 0 duplicate completions, verified checkpoint; re-invocation returned the same completion |
| Static gate and Bubblewrap | PASS | `.universal_private/guided_ai/code_initial_request.json` verified; both folds in `market-history/research/.universal_private/guided_verified_20261112/guided_state.json` report `BWRAP_UNSHARE_ALL_NO_HOME_NO_NETWORK` |
| Actual model call and structured response | PASS | `.universal_private/guided_ai/decision_request.json` and response: `gpt-6-sol`, verified response SHA `eeacaeecbb0cf03b59e2952cdbdf2a449ca435ca2331ad9292570b349950ac7b`; decision was PIT validation required, no official claim |
| Worker SIGKILL recovery | PASS | `.universal_private/worker_kill_job/job.json`: attempts 2, restarts 1, crashes 1, duplicate completions 0 |
| Supervisor SIGKILL and restart | PASS | `.universal_private/supervisor_kill_job/job.json`: detached worker artifact verified after restart, attempts 1, duplicate completions 0 |
| Duplicate model call prevention | PASS for checkpoint reuse; SKIPPED for uncertain live model failure injection | Final guided job had one stored code request, reused; prior `isolated_codex` tests cover uncertain request handling, but no current live failure was injected |
| Synthetic rejection and follow-on | PASS for fixture only | New test rejects `mean_above` and executes one `mean_below` experiment; bound 1 of 2 |
| Real-market rejection and follow-on | FAIL | Crash hypothesis rejected in fold 1; model chose PIT validation required, no new market hypothesis ran |
| Current integrated fault injection and automatic code repair | SKIPPED | Earlier 2026-11-10 guided repair evidence remains valid for that code revision, but this integration did not rerun a fault injection through Research Job |
| PIT-unverified official approval block | PASS | Job ended `RESEARCH_BLOCKED_WITH_EVIDENCE`, reason `PIT_UNVERIFIED`; model-declared PIT completion rejection test passed |
| Read-only DB schema and access | PASS | `_db_sample()` used `BEGIN READ ONLY`, 5-second statement timeout and at most 20 rows per table; three required table schemas matched |

An initial verification attempt exposed that calling Guided `run()` as a verifier rewrote its checkpoint. That job's reuse failed its integrity check. The verifier was changed to read-only recomputation and a fresh job passed initial and repeated verification. The failed private checkpoints were retained as evidence, not registered as successful cases.

## Actual Regime190 research and PIT decision

The existing `FORECAST-CRASH20` guided study ran on hash-checked local Naver KOSPI/KOSDAQ snapshots (4,133 aligned sessions). Missing and malformed source rows, date ordering, fold contracts, and sealed validation labels were checked by existing code. Both Bubblewrap folds ran and their predictions were independently verified. The hypothesis was rejected: fold 1 candidate PR-AUC `0.014245` versus volatility baseline `0.016667`; fold 2 candidate PR-AUC `0.024000` versus baseline `0.023952`, with only four events. The snapshots have no independently verified historical publication clock or revisions, and there is no untouched holdout. No official backtest performance or strategy approval follows.

Regime190 indicator 116 (US 2-year/10-year Treasury yields) was identified as a future PIT candidate from `indicator_spec.csv`; its FRED/ALFRED source still requires US release-time to KST alignment and vintage checks. A formal Phase 2 indicator acquisition/backtest was **SKIPPED** because Phase 1 core conditions did not all pass. No missing source values were estimated or filled.

The live read-only DB check found 20/20 historical price rows without `market`, 20/20 recent rate rows without `released_at`, and 20/20 without `vintage_date`. A column named `available_at` is not independent publication evidence. Schema compatibility is confirmed for the checked columns, not PIT readiness.

## Autonomous problem-solving measurement

| Measure | Observed |
| --- | --- |
| Current discrete research/probe jobs | 4: guided job, worker interruption probe, supervisor interruption probe, model next-action decision |
| Additional human research instructions | 0; sandbox approval prompts were required for model/Bubblewrap/DB access |
| Automatically resolved errors | 2 process interruptions; 1 verifier defect fixed by this code change, not autonomously |
| Unresolved errors or dependencies | 2: real-market follow-on hypothesis and PIT provenance/holdout |
| Duplicate execution / model calls | 0 duplicate completions in the measured jobs; 1 current live model decision call, no repeat |
| Verified conclusions | 1 fixture-only follow-on conclusion; 0 official market conclusions |
| Model calls, time, cost | 1 new live decision call, about 9 seconds; guided job reused a prior model code artifact and reports one checkpointed code call. The final guided run and two interruption probes took about 11.3 seconds combined, excluding regression tests. Provider monetary cost was not exposed, so cost is unknown |
| Historical case reuse | Existing guided code artifact and checkpoint were reused; no new repair case was demonstrated or registered |

Validated case: `PROCESS_INTERRUPTION`; cause `SIGKILL` of a worker or supervisor; procedure: inspect the artifact identity and hashes, restart the worker at most once if absent, then independently verify the result. Verification: the two private recovery logs above show `VERIFIED_RESEARCH_CONCLUSION` with zero duplicate completions. Applicable to allowlisted idempotent fixture actions only. Related code SHA: `fba417bf05b34926db6e4619f5d9729a0a20c88f`. The guided hash-verifier defect was fixed and regression-checked by a human code change. It is not counted as autonomous repair.

## Gates, risks, and commands

`AGENT_CORE_COMPLETED=FALSE`; `LIVE_RESEARCH_E2E_VERIFIED=FALSE`; `PIT_VERIFIED=FALSE`. The first gate remains false because current integrated AI code fault repair and a real-market follow-on hypothesis were not demonstrated. The other gates are independently false for missing publication/vintage evidence and holdout. Phase 3 is an interim measurement, not a completed capability evaluation.

Main risks are mutable upstream AI checkpoints after a job finalizes (tampering is detected but prevents reuse), incomplete model-call accounting for earlier hypothesis/plan requests, no multi-task continuation after a blocked PIT task, and no licensed historical vintage source. Research artifacts stay private. No operating change or production trading use is authorized by this work.

Run from the research worktree:

```bash
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-manifest .universal_private/guided_verified_manifest.json --job-dir .universal_private/guided_verified_job
touch .universal_private/guided_verified_job/STOP
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-manifest .universal_private/guided_verified_manifest.json --job-dir .universal_private/guided_verified_job
```

The third command resumes after an unexpected Supervisor interruption when no `STOP` marker exists. A deliberate `STOP` makes the job terminal; remove its marker only after review and use a new manifest/job ID for a new run. The supplied final job is already terminal, so re-invocation only verifies/reuses it. To roll back the research code, on this research branch use `git revert fba417bf05b34926db6e4619f5d9729a0a20c88f`. No operating branch merge or service restart is involved.

The next most important task is to execute a fault-injected Guided repair and a bounded real-market follow-on hypothesis through the same Research Job checkpoint, then repeat independent verification.
