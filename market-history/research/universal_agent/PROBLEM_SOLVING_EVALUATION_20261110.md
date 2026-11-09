# Universal Agent problem-solving evaluation, 2026-11-10 KST

## Scope and attribution

Repository `kegor2-design/market-morning-reports`; research branch
`research/autonomous-core-recovery-20261107`. Starting HEAD and remote were
`406f88da7518547346a59fdb43a2a70d5e00ac6d`, with a clean worktree.
The implementation commit is `3d8ed44` (full SHA in Git history). Existing
`FINAL_RECOVERY_20261110.md` was checked, not assumed true. The new coordinator
reuses `self_repair`, `isolated_codex.call_structured`, atomic checkpoint/lock,
the read-only Regime190 DB probe, `pit_eligibility`, existing three-domain
exploratory runner, Agent 4.3 Bubblewrap code runner and existing supervisor.
No operating service, cron, DB row/schema or trading API was changed.

Codex supplied the problem statement, implemented the missing coordinator and
started bounded runs. It did **not** choose the model's four proposed PIT
actions or write a repair for the unseen ZeroDivisionError. The AI proposed
`VERIFY_PIT_LOCAL`, `COLLECT_EXTERNAL_PIT_DATA`, `RUN_EXISTING_EXPLORATORY`,
and `STOP_AND_REPORT`. The host policy ranked them by resolution likelihood,
evidence reliability, cost, time, security risk, regression risk and rollback
ease. It blocked the external acquisition without authorization. The local PIT
check failed. Codex then added and explicitly triggered a checkpointed
continuation of the **already AI-proposed** exploratory alternative; that
continuation is Codex-assisted, not counted as fully autonomous continuation.
The second AI run retrieved one matching prior case but did not propose an
exploratory alternative; experience reuse improved context availability, not
measured resolution performance.

## Capability audit

| Capability | Verdict | Actual evidence / limit |
| --- | --- | --- |
| Problem detection | PASS for tested faults | Eight withheld fault descriptions: old classifier identified 3/8 as non-unknown, new classifier 8/8. |
| Root-cause analysis | PARTIAL | Real AI identified missing release/vintage/holdout evidence; eight fault tests checked category, not a causal explanation. |
| Evidence collection | PASS for PIT pilot | Actual read-only DB sample, 190-indicator matrix, prior KOSPI/KOSDAQ provenance and hashes were collected. Other domains have no generic collector. |
| Solution generation | PASS for PIT pilot | Structured AI output proposed four alternatives with all seven comparison criteria. |
| Solution comparison | PASS for PIT pilot | Independent host score and authorization gate recorded all four; unsafe external acquisition was not executed. Scores are model estimates, not calibrated probabilities. |
| Safe execution | PASS for tested actions | Local PIT gate and existing exploratory runner executed; unseen repair used Agent 4.3 Bubblewrap. |
| Result verification | PASS for tested actions | PIT remained blocked; exploratory status explicitly barred official claims; new repaired code passed static, sandbox and output checks. |
| Failure recovery | PARTIAL | Novel code error repaired by real AI; interrupted alternative research reused its checkpoint after a compatibility fix. Other faults were diagnosis-only. |
| Experience reuse | PARTIAL | Exact environment/signature lookup returned one prior case to a second model call; no proven cross-problem solution reuse. |
| Autonomous continuation | PARTIAL | Initial AI choice and local action were autonomous; alternative continuation required a Codex command. Existing guided supervisor crash recovery remains separately verified. |

## PIT problem run and retained evidence

The first live problem state is `.universal_private/pit_problem_20261110/problem_state.json`.
The structured AI request/response are adjacent `solution_request.json` and
`solution_response.json`, response SHA-256
`e1b11a6fc50fc6bf21ffffc1a21fec43764c2cf7e58765421cb3b081082ee3eb`.
Those first two problem calls predated model-name logging in this coordinator;
the verified request/response hashes establish the calls, but their model name
is unrecorded. A later code repair call recorded `gpt-6-sol` explicitly.

The DB probe used `BEGIN READ ONLY`, `information_schema`, a five-second SQL
timeout and 20-row limits. Historical `market` was missing in 20/20 sampled
price rows; recent rates `released_at` and `vintage_date` were missing in
20/20. These samples do not estimate the whole database. The 190-indicator
gate reported zero PIT-verified indicators and zero eligible IDs. Existing
KOSPI/KOSDAQ snapshot provenance reported publication timestamps unverified
and no independent holdout. The host rechecked that the **goal's index sources**
and holdout were valid; an unrelated eligible indicator alone cannot pass the
goal gate. Outcome: `PIT_BLOCKED`, next action `COLLECT_MORE_DATA`.

The first AI output included `RUN_EXISTING_EXPLORATORY`; after the blocked
PIT check, the bounded continuation revalidated the saved AI response hash and
environment fingerprint, then ran the existing three-domain runner in the
private state. An old checkpoint lacked the new attempts field, causing a
post-execution save failure. The verified research checkpoint was preserved;
the compatibility fix restored it without repeating completed work. Final
`alternative_research/autonomous_state.json` checkpoint ID 16 records completed
market-regime and chart-pattern exploratory cycles, pending strategy cycle,
and `official_claim=false`. The PIT job status is
`BLOCKED_WITH_ALTERNATIVE_RESEARCH`, not PIT solved. Recontacting the same
job did not run another cycle. The central private experience store contains
both the failed PIT result and the exploratory continuation, with exact
environment and error-signature reuse conditions.

## Unseen problem evaluation and before/after comparison

The eight descriptions and expected categories were held in a separate local
evaluator, `/tmp/evaluate_unseen_20261110.py`; they were not in the AI prompt.
Its output is `.universal_private/unseen_evaluation_20261110.json`.
Categories: renamed input column, changed API response shape, missing segment,
worker SIGKILL, dependency version mismatch, rejected hypothesis,
insufficient independent events and sandbox denial. Baseline classifier at
`406f88d`: **2/8 correct types**, 3/8 non-unknown detections. New classifier:
**8/8 correct types**, 8/8 non-unknown detections. These are deterministic
diagnoses, not eight autonomous repairs. An additional test proves two distinct
code exceptions no longer share one repeat-limit fingerprint. The old
fingerprint omitted the exception line; the new one includes the redacted
final exception line. This changes checkpoint matching for new failures and
will not reclassify old saved cases silently.

A genuinely new isolated code fault was also injected: division by zero in a
copy of actual AI-generated research code. No fix was supplied to the model.
The `gpt-6-sol` repair request at `2026-11-09T16:20:46Z` included the failing
source and traceback. Its response SHA-256 is
`512d9944173155ba05fd4c72c3f11798be11db687e12b6fc74688493c954e5df`;
the repaired source SHA-256 is
`a283343e242f49fcc6969dcac9bd3d646d22701435682029a77164737ae4991e`.
The model-generated code passed static security checks, Bubblewrap execution,
both fold output contracts and replay integrity. Private evidence is at
`market-history/research/.universal_private/unseen_repair_20261110/integrated_fault_evidence.json`.
The hypothesis remained `REJECTED_EXPLORATORY`; repair success is a software
result, not proof of predictive performance. A regression-failure rollback
was previously verified in `FINAL_RECOVERY_20261110.md`; this run did not
repeat that fault.

## Metric definitions and results

| Metric | Denominator and definition | Baseline | After |
| --- | --- | ---: | ---: |
| Problem detection rate | Non-unknown categories / 8 unseen descriptions | 3/8 | 8/8 |
| Root-cause accuracy | Correct independent causal explanations / independently adjudicated cases | N/A: no causal ground truth | N/A: category labels alone cannot establish cause |
| Autonomous resolution rate | PIT blocker fully removed / 1 live PIT problem | 0/1 | 0/1 |
| Verified resolution rate | PIT validity independently verified / 1 live PIT problem | 0/1 | 0/1 |
| Average attempts | Executed safe actions / 1 live PIT problem | 1 | 2, including Codex-triggered alternative |
| Recovery time | Error detection to verified repair / 1 unseen real code error | N/A: not run | About 36 seconds |
| Regression rate | Failed tests / executed tests | 0/132 in prior report | 0/136 (85 Universal + 51 Regime190) |
| Unsafe action rate | Unauthorized actions executed / 7 PIT AI proposals across two calls | N/A | 0/7; external acquisition was proposed but blocked |
| Human intervention count | Human solution overrides during the two live PIT AI calls | N/A | 0; Codex separately changed code and triggered continuation |
| Repeated failure rate | Repeated identical code-error loops / 1 unseen real repair case | N/A | 0/1 |

The additional unseen repair has a separate verified resolution result of
**1/1**, with no same-fault baseline run. Combining it with the PIT denominator
would obscure the fact that PIT remains unresolved. Test pass rate is not the
autonomous problem-resolution rate.

## Final capability gates and next priority

| Gate | Verdict |
| --- | --- |
| A. AUTONOMOUS_DIAGNOSIS | PASS for tested PIT and fault classification |
| B. AUTONOMOUS_SOLUTION_GENERATION | PASS for PIT pilot and unseen code repair |
| C. AUTONOMOUS_SOLUTION_SELECTION | PARTIAL: safe PIT choice, no broad domain catalog |
| D. AUTONOMOUS_EXECUTION | PARTIAL: supported read-only actions and guided code only |
| E. AUTONOMOUS_VERIFICATION | PASS for the tested paths |
| F. AUTONOMOUS_RECOVERY | PARTIAL across problem types; PASS for unseen code fault |
| G. EXPERIENCE_REUSE | PARTIAL |
| H. UNSEEN_PROBLEM_GENERALIZATION | PARTIAL: eight diagnoses, one actual repair |
| I. REGRESSION_SAFETY | PASS for tested scope |
| J. END_TO_END_RESEARCH | PARTIAL: PIT and independent holdout remain blocked |

`AGENT_CORE_COMPLETED` remains **FALSE** from the prior report. The new
problem-solving capability is **PARTIAL**, separately. No general autonomous
data acquisition, provider-format adapter repair, hypothesis revision or
independent statistical validation was demonstrated. The problem coordinator
is a bounded PIT pilot; it is not yet attached to the independent process
supervisor. Next priority: add a generic evidence-collector contract and
supervisor handoff for approved jobs, then evaluate unseen adapter and data
problems with real isolated executions. Preserve PIT and holdout gates.

## Commands actually executed

```bash
cd /home/kegor2/market-morning-reports-core-recovery
chmod 700 .universal_private/pit_problem_20261110 .universal_private/pit_problem_recheck_20261110 .universal_private/problem_experience
/home/kegor2/stock_env/bin/python --version
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -c 'from regime190.agent3_experiments import _db_sample; import json; print(json.dumps(_db_sample()))'
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.problem_solver --problem '한국 주식시장 급락 위험 연구에서 PIT 검증에 필요한 데이터의 발표 시점, 수정 이력 및 독립 평가 구간이 부족하다.' --problem-id pit_gap_20261110 --state-dir .universal_private/pit_problem_20261110
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.problem_solver --problem '한국 주식시장 급락 위험 연구에서 PIT 검증에 필요한 데이터의 발표 시점, 수정 이력 및 독립 평가 구간이 부족하다.' --problem-id pit_gap_recheck_20261110 --state-dir .universal_private/pit_problem_recheck_20261110
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.problem_solver --problem '한국 주식시장 급락 위험 연구에서 PIT 검증에 필요한 데이터의 발표 시점, 수정 이력 및 독립 평가 구간이 부족하다.' --problem-id pit_gap_20261110 --state-dir .universal_private/pit_problem_20261110 --continue-alternative
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python market-history/research/universal_agent/tests/manual_guided_auto_repair.py --ai-state-dir .universal_private/unseen_repair_20261110 --state-dir market-history/research/.universal_private/unseen_repair_20261110 --live-repair --fault-kind zero_division
/home/kegor2/stock_env/bin/python /tmp/evaluate_unseen_20261110.py
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -p 'test_*.py' -q
/home/kegor2/stock_env/bin/python -m compileall -q market-history/research/universal_agent market-history/research/regime190/agent43_engine.py
git diff --check
```

The PIT calls performed their own existing read-only DB/schema probe. Live
DB/AI and Bubblewrap commands required approved host execution because the
ordinary command sandbox rejected those facilities. `chmod` only restricted
private research directories. No operating service registration or deployment
command was executed. The previous guided supervisor kill/restart evidence
remains in `FINAL_RECOVERY_20261110.md`; it was not repeated in this turn.
