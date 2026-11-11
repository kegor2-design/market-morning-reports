# Universal Agent market E2E research — 2026-11-12 KST

## Basis and isolated change

Repository: `kegor2-design/market-morning-reports`. Base branch: `research/universal-agent-integration-20261112`; remote and local base SHA: `67bfc0da2a5f576756f026ff82919b42b7bc682e`. The base worktree was clean. All changes were made in a separate worktree on `research/universal-agent-e2e-20261112`. Code SHA: `8c3af9f6e433f76c5ca03a846a376a2ee4f240e4`. The previous [integration report](INTEGRATION_EVIDENCE_20261112.md) was compared before editing.

No operating service, scheduler, order path, DB data, DB schema, or production branch was changed. The worktree's ignored raw market snapshots and model logs stayed private. No new executable shell script or MyDream2000 deployment file was added; executable permission changes were unnecessary.

## Existing functions preserved and connected

| Capability | Base behavior | Current connection | Remaining risk |
| --- | --- | --- | --- |
| Supervisor / Research Job | One bounded action, hashed artifact, restart and duplicate guard | Add the allowlisted `guided_e2e` action under the same `job_id`, `task_id`, `task_key`, artifact, and checkpoint | A model call interrupted before its response remains uncertain and blocks rather than repeating automatically |
| Guided Experiment / Self Repair | Guided code generation, failure classifier, AI repair, existing checkpoints | A reviewed `library_call` fault is injected into verified model code; the existing Guided diagnosis and repair path handles it | Fault trial is a research-only manifest mode, not a production strategy path |
| Static Gate / Bubblewrap | Existing Agent 4.3 gate and no-home/no-network execution | Both original and repaired code use the same gates and sealed folds | This verifies isolation on the tested host only |
| Hypothesis assessment | One real-market hypothesis could be rejected | Up to two distinct model-generated alternatives run with independent assessments; incompatible proposals are recorded and skipped within budget | The model may propose data outside the staged five-feature contract; such work remains blocked |
| PIT / approval | Snapshot publication and revisions unverified | Every cycle stays exploratory and the Research Job concludes `PIT_UNVERIFIED` | No official performance claim, PIT approval, or untouched holdout |

Changed files: `research_job.py`, `research_job.schema.json`, `guided_e2e.py`, `fault_trial.py`, `tests/test_research_job.py`, and the compatibility wrapper `tests/manual_guided_auto_repair.py`. The original Guided CLI, Self Repair gate, checkpoint format, PIT Problem Solver, and Regime190 engine were not modified. No prior action was removed from the registry.

## Evidence and verdicts

| Check | Verdict | Evidence |
| --- | --- | --- |
| Current Universal Agent regression | PASS | 90 tests, 0 failed, 0 skipped; `unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q` |
| Current Regime190 regression | PASS | 51 tests, 0 failed, 0 skipped; corresponding `regime190/tests` discovery |
| Compile and whitespace | PASS | `compileall -q` and `git diff --check` |
| Read-only DB schema | PASS | Existing `_db_sample()` used `BEGIN READ ONLY`, 5-second timeout, at most 20 rows per relevant table; required columns present |
| Actual fault injection, diagnosis, and AI repair in Research Job | PASS | `.universal_private/market_fault_final_job/job.json`, `market-history/research/.universal_private/market_fault_final_20261112/integrated_fault_evidence.json`: `library_call` fault, Guided failure diagnosis, `REPAIRED`, new model call, repaired code SHA |
| AI response format and model identity | PASS | `.universal_private/guided_e2e_final/code_repair_request.json`: `gpt-6-sol`, `VERIFIED`, response SHA `89f13334ec2f973c48eb452201c6ec4de805f28bd6e381e4927349b7472bebcc`; two new alternative hypothesis requests and code requests also verified |
| Static gate, Bubblewrap, independent sealed-fold checks | PASS | All three completed cycles stored input/code/output SHA; independent verifier reread each AI response, staged input, generated source, predictions, and sealed-fold result. Both folds used the existing no-home/no-network Bubblewrap path |
| Real-market rejection and follow-on execution | PASS for exploratory execution | Initial hypothesis and two distinct alternatives executed, each assessed `REJECTED_EXPLORATORY`; `transition_count=2`, the configured maximum |
| Supervisor SIGKILL and restart in the same E2E mode | PASS | `.universal_private/supervisor_recovery_job/job.json`: Supervisor PID 2406686 killed while detached Worker PID 2406687 ran; resumed status blocked for PIT, attempts 1, duplicate completions 0, model request count 6 before and after restart |
| Worker SIGKILL in current live E2E mode | SKIPPED | Previous branch verified Worker interruption with a fixture; the current market E2E run tested Supervisor interruption |
| Early sandbox attempt | BLOCKED | First unprivileged trial returned `SECURE_RUNNER_UNAVAILABLE`; no sandbox bypass was used. The separately approved isolated run passed |
| First alternative in earlier live trial | BLOCKED | Model proposed features outside the staged contract; `DATA_ACQUISITION_REQUIRED` was recorded, not counted as execution success. Prompt and bounded continuation were corrected before the successful two-alternative run |
| Official strategy or profitability verification | BLOCKED | PIT publication/vintage evidence and an untouched independent holdout are absent; no official backtest or production strategy approval was attempted |

The final full job uses task ID `market_fault_final_20261112_execute` and task key `04c8116b3758ad341e75429d047808ff72b8f2bfb37a2c0a5f1876f3c63f866f`. Its `job.json` records one Worker attempt, zero crashes, eight total request records (three copied verified prerequisite requests and five newly made calls), two transitions, and no duplicate completion. Reinvoking the same manifest and job directory returned the verified checkpoint without new model requests. The code repair request was made during this trial; the initial hypothesis and initial code response were previously verified inputs, not falsely counted as new calls.

The three hypothesis SHA values were `dab85a33c500829b570bbbe3ab632fc34b9dca6a85280c94ef68e620e8e7b8a7`, `727a2c6c0d2a87127734767acafed436c4147fa51405a6a886b1baf5c801f7b0`, and `7bbfa58166b0c4ced34762f66b8aa673e6d54ab50fa01dde0395c5a22e74dff6`. The initial fold-1 candidate PR-AUC was `0.014245` versus volatility baseline `0.016667`. Both alternatives scored `0.016667` on fold 1, matching rather than exceeding that baseline, and were rejected. The second fold had only four crash events. These are exploratory diagnostics, not profitability estimates.

## Gates and unresolved conditions

`AGENT_CORE_COMPLETED=TRUE`: actual fault recovery, two market hypothesis transitions, independent verification, Supervisor recovery, and both regression suites passed in the bounded research path.

`LIVE_RESEARCH_E2E_VERIFIED=FALSE`: a real-data **exploratory** market E2E cycle was verified, but the historical snapshot's source publication timing, revisions, and independent holdout remain unverified. This flag is reserved for the complete live research claim.

`PIT_VERIFIED=FALSE`: the Naver snapshot's historical public availability and revisions have not been independently established. The checked DB rate sample had `released_at` and `vintage_date` missing in all 20 rows; `available_at` alone is not publication proof.

The remaining blockers are source-level PIT/vintage evidence, untouched holdout, and provider cost visibility. Monetary model cost was not exposed; it is **unknown**, not zero. The first accepted model call and each retry have bounded time and request counts. An interrupted, unanswered call remains BLOCKED to prevent a duplicate request.

## Run, stop, resume, rollback

From this research worktree, after checking the manifest's private paths and the read-only DB schema:

```bash
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-manifest .universal_private/market_fault_final_manifest.json --job-dir .universal_private/market_fault_final_job
touch .universal_private/market_fault_final_job/STOP
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-manifest .universal_private/market_fault_final_manifest.json --job-dir .universal_private/market_fault_final_job
```

The third command resumes after an unexpected Supervisor interruption if no `STOP` marker exists. A deliberate `STOP` is terminal for that job; a fresh experiment needs a new manifest and job ID. The shown job is already terminal, so its run command only rechecks and reuses its checkpoint. On this isolated research branch, roll back the code with `git revert 8c3af9f6e433f76c5ca03a846a376a2ee4f240e4`. No service restart or operating branch merge is involved.
