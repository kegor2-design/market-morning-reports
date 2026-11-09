# Universal Agent bounded orchestration verification — 2026-11-10

## Scope and basis

Branch: `research/universal-agent-orchestration-20261110`. Remote base `research/autonomous-core-recovery-20261107` was checked at `91ae4d57593569710765184adb660b84b91208e1`, equal to the supplied comparison SHA. Code commit: `4c149d3` (full SHA in Git history). The original worktree and operating branch were not edited. No production service, scheduler, trading API, DB row, or DB schema was changed. Detailed run metadata and hashes: [E2E_RESEARCH_EVIDENCE_20261110.json](E2E_RESEARCH_EVIDENCE_20261110.json). Private run logs are in this worktree's `.universal_private` and `market-history/research/.universal_private`; they are intentionally untracked.

## Existing and added path

Existing `problem_solver` supplies bounded AI diagnosis, solution ranking, read-only PIT gate, and exploratory alternative. Existing `autonomous`, guided experiment, self repair, static gate, Bubblewrap, and Regime190 checks were reused. Existing `process_supervisor` only restarted a fixed guided experiment. Added `research_job.schema.json` and `research_job.py`: a bounded JSON manifest, fixed action registry, input/plan/task hashes, process-owned checkpoint, single artifact identity, independent result verification, restart/time/model-call budgets, stop marker/SIGTERM handling, and distinct terminal states. `process_supervisor --research-manifest` routes to this path; its guided CLI still passes existing tests. `problem_solver` can use hash-checked local index snapshots when the former private guided state is absent, while keeping publication and PIT status unverified.

The selected PIT action is passed from AI solution ranking to the existing read-only PIT verifier. A blocked gate can run the model-proposed, allowlisted `RUN_EXISTING_EXPLORATORY` once within the same worker, without a manual continuation command. The supervisor then verifies source, result, and checkpoint hashes before recording `RESEARCH_BLOCKED_WITH_EVIDENCE`. Unknown actions, shell commands, DB writes, external fetches, sandbox disabling, and credential requests are not manifest actions. The schema rejects their keys. The action registry does not run arbitrary generated code.

## Actual runs and verdicts

| Path | Evidence | Verdict |
| --- | --- | --- |
| Synthetic research goal and hypothesis | `synthetic_positive_job/job.json`: input/plan/output hashes, mean 2.0 from five values, independently recomputed, supported; one attempt, zero model calls | PASS for fixture-only conclusion |
| Negative hypothesis | `synthetic_restart_job/job.json`: mean -1.6, unsupported, still a valid negative fixture conclusion | PASS for rejection handling; PARTIAL for automatic next hypothesis |
| Worker crash and recovery | `synthetic_restart_job/job.json`: worker PID 2283943 killed with SIGKILL before output, independent supervisor PID 2283942 started PID 2283944; attempts 2, restarts 1, crashes 1, duplicate completions 0 | PASS for this fixture |
| Crash after artifact | `synthetic_kill_job/job.json`: worker PID 2283835 killed after output; artifact verified without rerun; attempts 1, crashes 1, duplicate completions 0 | PASS for idempotent recovery |
| Real PIT problem and alternative | `pit_block_verified_source_job/job.json` and `pit_solver/problem_state.json`: real `gpt-6-sol` solution response; `VERIFY_PIT_LOCAL` blocked; existing exploratory action completed, checkpoint 8; final `RESEARCH_BLOCKED_WITH_EVIDENCE`, model calls 1 | PASS for bounded handoff and honest blocking; PIT BLOCKED |
| Actual AI code repair | `market-history/research/.universal_private/guided_repair_20261110/integrated_fault_evidence.json`: injected library-call defect, new model repair response, static gate and Bubblewrap folds, exploratory result | PASS for existing guided path; PARTIAL for integration into new queue |
| Unsafe requests | `test_research_job.py`: unregistered DB write, network fetch, sandbox disable, credential disclosure, and excess model budget rejected by schema | PASS for manifest boundary; no live attack attempted |

The exploratory market run used a hash-checked local Naver KOSPI snapshot. It reported validation precision and recall 0.0, only four events in the second guided fold, and no untouched PIT holdout. Snapshot publication time and revision history remain unverified. Neither the exploratory result nor the successful process exit is an official prediction result. No new licensed provider data were acquired.

The first PIT orchestration attempt failed terminally when its exploratory source was absent in the separate worktree; the next attempt ended blocked on missing evidence. After copying the previously available local snapshots into private/ignored research space and checking their hashes against the tracked source manifest, the third run completed the alternative. These failed attempts remain in private job checkpoints and were not counted as success. Reinvoking the final job returned its checkpoint without another model request or action run.

## Regression and limitations

Executed from the new worktree:

```bash
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m compileall -q market-history/research/universal_agent market-history/research/regime190/agent43_engine.py
git diff --check
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-manifest .universal_private/orchestration_inputs/pit_block_verified_source.json --job-dir .universal_private/pit_block_verified_source_job
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python market-history/research/universal_agent/tests/manual_guided_auto_repair.py --ai-state-dir .universal_private/guided_repair_20261110 --state-dir market-history/research/.universal_private/guided_repair_20261110 --live-repair --fault-kind library_call
```

Results: 88 Universal tests ran (87 passed, 1 skipped), 51 Regime190 tests passed, compileall PASS, diff check PASS. Test output was preserved at `.universal_private/orchestration_universal_tests.log` and `.universal_private/orchestration_regime190_tests.log`. The guided repair command was run with host permissions needed by the existing Bubblewrap path. The other commands do not change operating services. No existing tests or limits were removed. The extra dependency is the already used `jsonschema` package. The new research job worker is a fixed Python module, not a general secure code runner; arbitrary code repair remains in the prior guided path. Worker crash recovery was tested with an independent detached process; actual Codex-session termination was not reproduced. This job registry offers one task per manifest, not a general persistent multi-task queue. There is no automatic new hypothesis cycle after a negative fixture result. Potential side effects are extra private files and bounded CPU/model use; operating DB queries were read-only through existing probes.

## Overall judgment and next priorities

`FULL_AUTONOMOUS_RESEARCH_VERIFIED=FALSE`; `E2E_VERIFIED=FALSE` for live market research; `PIT_VERIFIED=FALSE`. A bounded fixture E2E path and PIT-blocked alternative path were verified. `AGENT_CORE_COMPLETED` remains false under the earlier all-gates rule. Next work: add an approved generated-code task adapter to this checkpoint protocol; run repair and regression through the same supervisor; add a bounded hypothesis transition; obtain licensed publication/vintage evidence and untouched holdout before claiming market prediction performance. No safety gate should be relaxed to achieve those steps.
