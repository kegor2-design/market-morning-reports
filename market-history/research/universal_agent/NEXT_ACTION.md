# Next research actions

## Approved local API recovery DAG handoff — 2026-11-18

- Branch `research/universal-agent-session-c-api-recovery-20261118` from `51e08413dbb86817e084d441e9ac366562d02c8b`; verified code commit `8ac6101`. The new local-only `API_RECOVERY_RETRY` Task, separate approval/budget, versioned DAG Revision and original-Goal resumption passed a real child-process HTTP 503 fixture E2E. Durable private queue `.universal_private/session_c_api_recovery_e2e/state.json` retains Goal `research_b7188d9b5674` at `COMPLETED_EXPLORATORY`; reopening it processed zero jobs. Universal Agent 167 PASS, Regime190 55 PASS, compileall PASS and diff check PASS. Existing private Checkpoints were preserved. No long-running Worker remains.
- Local 429 with `Retry-After: 0`, 404, timeout, reset, malformed 200, approval tamper and recovery Worker SIGKILL are covered. External-provider approval and delayed 429 handling, general Self Repair, full rollback, strict outer time budget, actual SSH reconnect and official PIT remain blocked. Model calls: 0. Session C, general-purpose and production readiness remain false.
- Next coding task: replace the local-only approval with a reviewable external-provider approval and source-status proof that enforces the new request budget; add a bounded, scheduled Retry-After policy. Do not use the fixture contract for an external URL. Then test durable DAG rollback after an invalid recovery and the strict outer wall-clock deadline.
- Resume: `cd /home/kegor2/market-morning-reports-session-c` then `git status --short --branch` and `PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_api_recovery_e2e`. Run `PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q` after further code changes. The Universal Agent suite needs local loopback socket permission; Regime190 uses the same Python environment.

## Local HTTP source recovery follow-up — 2026-11-18

- Start SHA `7068cb2`, verified code SHA `0a58586`. A loopback server returned HTTP 503 then an approved fixture CSV. The source adapter used exactly two bounded attempts, sealed the payload, and reused the checkpoint without a third request. This exercised local source acquisition only; no official provider or model call was made. Existing private research checkpoints were unchanged, and no Worker is running. Universal Agent 157 PASS, Regime190 55 PASS, compileall PASS and diff check PASS.
- Next exact coding task: register an explicit API retry Task for a blocked original Goal with a new request identity and independently approved network budget; then verify original Task resumption and safe rollback. Do not treat the local fixture as `AUTONOMOUS_API_RECOVERY_VERIFIED` for the Research DAG.

## Transport retry safety follow-up — 2026-11-18

- Starting SHA `de7b982`, verified code SHA `1ce8da0`; source fetcher now retries only after definite retryable HTTP status. Timeout and transport errors remain blocked with their original reservation. Local fault tests use zero paid model calls and no official provider requests. Universal Agent 156 PASS, Regime190 55 PASS, compileall PASS and diff check PASS. `PROBLEM_SOLVING_REPORT.md` records the limit of this result.
- Next task remains the explicit new-request API retry Task and original-Goal DAG resume under a separately authorized bounded budget. Keep `AUTONOMOUS_API_RECOVERY_VERIFIED=BLOCKED` until that execution and verification pass.

## Reviewed acquisition candidate handoff — 2026-11-18

- Start SHA `73a92af`, verified code SHA `a5a1ee7` on `research/universal-agent-session-c-dynamic-planner-20261118`. This continuation adds host-compiled optional US rate acquisition Tasks and Capability Registry version 2. The candidate is registered only in an approval-gated synthetic queue. Existing private checkpoints and completed research were not changed. No Worker is running. Universal Agent 156 PASS, Regime190 55 PASS, compileall PASS, and diff check PASS.
- Real AI generation, enforceable per-call model cost, generic API recovery, isolated AI repair and rollback, official Korean PIT, and independent holdout remain blocked or unimplemented. Do not label the synthetic queue test as actual AI generation or source acquisition. Session C, general-purpose readiness and production readiness remain false.
- Next exact coding task: implement a reviewed API retry Task with a new request identity and a separately authorized bounded network budget, preserving the original blocked attempt. Validate against a local HTTP fault server, then integrate isolated repair and rollback. Do not replay uncertain requests.
- Resume: `cd /home/kegor2/market-morning-reports-session-c` then `git status --short --branch` and `PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q`.

## Post-restart handoff — 2026-11-18

- Branch `research/universal-agent-session-c-dynamic-planner-20261118`; starting SHA `3d3af77418ce4715b380829344e46764412d3781`; last verified code commit `69fec86becd19103686ffc335a1836e6fa30f9ae` plus this handoff update. Existing private Goal checkpoints and source hashes were preserved. No research Worker is running.
- Completed in this iteration: development resumed after the server restart from the clean `3d3af77` checkpoint without rerunning the completed Goal (`DEVELOPMENT_RESUME_VERIFIED=PASS`). HTTP response versus uncertain transport outcome is saved in the data recovery checkpoint and carried into the Research Job and program Task record. Local HTTP 503 and timeout fault injection confirms no automatic replay. Universal Agent 153 PASS, Regime190 55 PASS, compileall PASS, `git diff --check` PASS. No model or live network call was added.
- Still blocked: autonomous API recovery with a separately authorized new request budget, AI plan generation with enforceable cost cap, general Source Discovery, AI Self Repair DAG integration, official Korean market PIT, a new independent holdout, strict outer runtime time budget, and actual SSH disconnect/reconnect. Session C, general-purpose and production readiness remain false.
- Next coding task: add a reviewed API retry Task with a new request identity and bounded budget. Preserve the blocked original attempt and never replay a request whose outcome is uncertain. Then validate the new Task under a local HTTP fault server before considering an official provider call.

Verified resume commands (module invocation requires no chmod):

```bash
cd /home/kegor2/market-morning-reports-session-c
git fetch --all --prune
git status --short --branch
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_dynamic_aug2020_fixed
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

## Dynamic planner and source-schema recovery handoff — 2026-11-18

- Branch `research/universal-agent-session-c-dynamic-planner-20261118`; start SHA `de9af2fe6c2de3669dc1a00243752d1ac5a6670a`; last verified code commit `48482c8` plus this report checkpoint commit.
- Completed: reviewed alternative rate hypothesis and DAG dependency compilation; version 2 Goal Contract with immutable policy; 2020 Treasury official URI/header support; autonomous zero-network schema recovery for original Goal `research_471a35e13cfa`; independent result recomputation; terminal deduplication. Universal Agent 152 PASS and Regime190 55 PASS; compileall and diff check PASS. No Worker running.
- Checkpoints: `.universal_private/session_c_dynamic_aug2020_fixed/state.json` completed exploratory; `.universal_private/session_c_dynamic_aug2020_verified/state.json` blocked on earlier official URI 404; `.universal_private/session_c_dynamic_aug2020/state.json` blocked under network-isolated execution; `.universal_private/session_c_rates_may2018/state.json` remains completed exploratory. All were preserved.
- Remaining: enforceable per-call model cost control and explicit paid-call approval; actual AI-generated plan; general capability registry with input/output contracts; safe API recovery with a new approved budget; isolated AI Self Repair/Rollback in DAG; official KRX/PIT and independent holdout; strict outer time budget and actual SSH disconnect/reconnect. A 404 Goal whose three network reservations were consumed must not be automatically retried.
- Required approval before real model invocation: provider, model, call count, maximum cost, validity window, purpose and evidence that the cap is enforceable. Existing Codex CLI authentication alone is insufficient. No production code, scheduler, DB, service or operating branch changed.

Verified resume commands (module invocation requires no chmod):

```bash
cd /home/kegor2/market-morning-reports-session-c
git fetch origin research/universal-agent-session-c-dynamic-planner-20261118
git status --short --branch
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_dynamic_aug2020_fixed
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

Next independent coding task: host-approved API fault recovery with an explicit new network budget, plus isolated fixture repair/rollback DAG integration. Preserve the completed Goal and source hashes.

## Session C AI planner boundary handoff — 2026-11-18

- Branch: `research/universal-agent-session-c-ai-planner-20261118`; starting commit `8aa7af567124ec27e5ac7afb1d18467796ffa822`; last verified code commit `737368b` plus the subsequent cost fail-closed check and report update in this handoff commit.
- Phase: C3 AI proposal schema, host validator and persistent queue handoff verified with synthetic input. Actual model-generated plan remains blocked. No research Worker is running at handoff. Existing May 2018, May 2019 and July 2018 checkpoints and source hashes were preserved.
- Verified: Universal Agent 147 tests and Regime190 55 tests after the final cost gate; compileall and diff check. The synthetic June 2018 candidate reached the first reviewed discovery task, with zero model and network requests. Simulated timeout, authentication failure and malformed model output were each reserved once and never replayed. The real Codex CLI path returns `BLOCKED_COST_ENFORCEMENT` before any call.
- Remaining: implement a reviewed model adapter with enforceable monetary ceiling and explicit cost approval, then obtain an actual AI-generated plan; expand the reviewed source/action registry and plan conversion beyond exact host templates; integrate non-calendar error repair and isolated AI Self Repair/Rollback into DAG; strict outer time budget, actual SSH reconnect, official KRX/PIT and independent holdouts. Do not mark these PASS on synthetic tests.
- Required approval: a provider and explicit maximum cost for paid model calls, with a way to enforce that cap. No service, scheduler, DB, trading system, or operating branch was changed.

Verified resume commands (module invocation requires no executable-bit change):

```bash
cd /home/kegor2/market-morning-reports-session-c
git fetch origin research/universal-agent-session-c-ai-planner-20261118
git status --short --branch
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_rates_may2018
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

Next independent coding task: add a bounded, evidence-backed non-calendar repair action to the existing Problem Solver and Research Program DAG. Preserve the existing calendar recovery and terminal task hashes.

## Session C continuation handoff — 2026-11-18

- Branch: `research/universal-agent-session-c-autonomous-recovery-20261118`; start commit `cd5aefef1479203fc994371e183cb7be31f9d295`; last tested code commit `eb9e67d`.
- Phase: C2 calendar recovery verified; C1 strict runtime time/model gates incomplete; C3 AI planner pending. No research Worker was running when this handoff was written.
- Completed: original May 2018 Goal `research_21ae71a8bd77` resumed with 22 official-source observation days and rejected its hypothesis exploratorily. May 2019 `research_48fa238a75b9` and July 2018 `research_c82cdf92d25e` independently reproduced and automatically repaired full-closure gaps. All retained original IDs, source hashes, three original network requests, zero model calls, and zero duplicate completed-task runs. PIT and new sealed holdouts remain unavailable.
- Private checkpoints: `.universal_private/session_c_rates_may2018/state.json`, `.universal_private/session_c_rates_may2018_before_calendar_recovery/state.json`, `.universal_private/session_c_rates_may2019/state.json`, `.universal_private/session_c_rates_july2018/state.json`. Private raw data and credentials are excluded from Git.
- Tests: Universal Agent 139 PASS under server user execution, Regime190 55 PASS, compileall and diff check PASS. The 2018 May and 2019 May/July analyses were independently recomputed from sealed source jobs. `reconcile-calendar` was used only to repair the original May queue projection after its program completed; the 2019/July automatic runs did not require it.
- Remaining: strict outer runtime time budget, model-unavailable task handling, actual SSH reconnect, host-validated AI planner and approved model-call budget, generic solver and isolated Self Repair DAG integration, official KRX data/PIT, new independent holdout, and Research A/C official E2E. Calendar recovery is reviewed only for 2018/2019; other years fail closed.
- Approval needed before any paid model call or new source: a reviewed model/provider cost limit and source access terms. No production service, scheduler, DB, or branch was changed.

Verified resume commands (module invocation needs no executable-bit change):

```bash
cd /home/kegor2/market-morning-reports-session-c
git fetch origin research/universal-agent-session-c-autonomous-recovery-20261118
git status --short --branch
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_rates_may2018
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

Continue with bounded P0 time/model fault checks and a host-validated AI planning candidate path. Do not rerun terminal research jobs or promote exploratory PIT-unverified outcomes.

## Prior handoff

## Session C development handoff — 2026-11-17

- Branch: `research/universal-agent-session-c-20261117`; last verified implementation commit: `f22df0f`; last verified fault-test commit: `a6e19ed` (based on Session B `cea23c0070c445c402f1def51e324ddbb03a1a13`).
- Phase: C1 partial. The bounded Goal queue, queue-specific checkpoints, terminal deduplication, approval blocking, and detached shell-exit execution have been implemented. The remaining P0 fault matrix and actual SSH disconnect are not complete. No worker was still running at this checkpoint.
- Tests: Universal Agent 134 PASS under server user execution; Regime190 55 PASS; compileall and diff check PASS. The sandboxed Universal Agent run had three Worker-start failures; rerunning outside that process sandbox passed all tests. The new queue has SIGKILL-after-reservation recovery, injected storage failure, and injected provider outage tests.
- Private checkpoints: `.universal_private/session_c_disconnect_2/state.json`, `.universal_private/session_c_rates_may2018/state.json`, `.universal_private/session_c_rates_june2018/state.json`, `.universal_private/session_c_research_a_v2/state.json`, `.universal_private/session_c_research_c_v2/state.json`, `.universal_private/session_c_research_d_v2/state.json`. The June Goal finished exploratory; May remains blocked on market-day coverage; indicator 116 remains PIT blocked; A/C/D original goals are `UNSUPPORTED`.
- Pending: P0 strict time budget, model-unavailable execution, live provider outage, actual SSH disconnect/reconnect, and continuous-service behavior; P1 reviewed AI planner; P2 market calendar and official KRX; P3 solver/repair DAG integration; P4/P5 independent holdout and new A/C/D goals. The existing isolated Codex runner passed its secure-runner probe outside the process sandbox, but no Session C planner model call was made. KRX official access remains unavailable with the tested unauthenticated endpoint.
- Required approval: no approval to read or develop in the research worktree. A real independent service installation or scheduler change would require separate approval. Source/API costs and access must be reviewed before enabling new providers.

Verified resume commands (the Python environment and paths were checked on this host):

```bash
cd /home/kegor2/market-morning-reports-session-c
git fetch origin research/universal-agent-session-c-20261117
git status --short --branch
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_rates_june2018
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

Run process-kill tests in the approved server user execution environment; the restricted process sandbox prevents their workers from starting. Review the Session C reports and continue with the P0 fault matrix before promoting any gate.

## Session B handoff

1. Add a reviewed AI planning path with strict host validation, an explicit model-call budget, and an approved provider. The present planner is deterministic and supports only three narrow families.
2. Add official KRX series and a market calendar after source terms and access are approved. The current Korean crash study is exploratory and its local Naver CSVs are intentionally untracked. Restore only files matching the SHA-256 values in `daily-index-validation-20261021/naver_source_manifest.json` before reproducing it.
3. Acquire historical first-publication, first-access, and revision evidence for indicator 116 and the rate series. PIT-blocked goals must remain blocked until then.
4. Exercise an interrupted live provider call only in an approved, bounded research environment. Local HTTP tests prove the fail-closed and sealed-response paths, not provider-specific behavior.
5. Integrate additional Problem Solver outcomes and isolated AI Self Repair into the program DAG without changing production code. Validate long-running operation, paid-call budgets, and operational impact before deployment.

Resume the reviewed private goals from the follow-up worktree with the existing virtual environment:

```bash
cd /home/kegor2/market-morning-reports-session-b-completion
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.process_supervisor --research-goal '지표 116의 한국 증시 PIT를 검증하고 차단되면 독립적인 미국 국채 금리차와 SOFR 연구를 수행하라.' --max-seconds 180
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
```

The second command needs local loopback socket permission for the HTTP interruption tests. Both existing research programs are checkpointed; resuming them should not repeat completed source requests.
# Session C recovery reliability handoff — 2026-11-18

- Branch: `research/universal-agent-session-c-recovery-reliability-20261118`, based on `c903ef4f8a7bf93462689c34107465638496ed76`. The verified code and final report SHAs are recorded in the latest Git log and `AGENT_STATUS.json` after push.
- Completed locally: API Recovery DAG prepare/commit journal; malformed-response rollback to the original DAG with failed request evidence retained; bounded 429 Retry-After wait in the persistent queue; persistent Goal deadline without reset on restart; shared Calendar/Schema/API Problem Solver selection. Existing completed fixture Goal `research_b7188d9b5674` remains `COMPLETED_EXPLORATORY` at queue generation 6. No external Provider or model call was made.
- Remaining: full eight-point transaction fault matrix, exact child and Supervisor termination at Goal deadline, external Provider approval contract and approved live trial, isolated Self Repair DAG and rollback, actual AI plan with enforceable paid-model ceiling, official PIT and independent holdout. These gates remain BLOCKED.
- Required approval: explicit bounded external Provider recovery scope before a new live request; an enforceable monetary ceiling and explicit model/provider approval before paid AI generation. Local fixture approval does not transfer to either scope.
- Running research Worker: none expected after the test suite exits. Private Checkpoint: `.universal_private/session_c_api_recovery_e2e/state.json`. Do not delete or replay terminal Goals.

Resume commands (Python module invocation needs no `chmod`):

```bash
cd /home/kegor2/market-morning-reports-session-c
git fetch --all --prune
git status --short --branch
git log -3 --oneline
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_api_recovery_e2e
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

2026-11-19 continuation: verified code commit `90dcefd`; the parent Goal deadline is now passed to each child Research Job. A real delayed child was stopped at the outer deadline and saved `FAILED_TERMINAL` with no duplicate completion. A pre-commit transaction write failure left the prepared state intact and a replay committed it. Universal Agent 172 PASS, Regime190 55 PASS, compileall and diff check PASS. This is bounded child termination with shutdown grace; an exact whole-Goal deadline and the remaining P0 fault matrix are still pending. No external Provider or model calls were made.

Additional P0 check at verified code commit `38a031b`: journal commit followed by an interrupted active-Checkpoint write resumes the same Revision; a duplicate Revision proposal is rejected before DAG mutation. The full eight-case matrix is still pending. Universal Agent 172 PASS after this change; Regime190 55 PASS on the preceding code commit.

Next implementation: complete the P0 rollback fault matrix and strict whole-Goal deadline, then design a separate external Provider approval contract and isolated Self Repair DAG. Keep model and official-source claims blocked until their approval and evidence exist.

## Session C Self Repair continuation — 2026-11-19

- Worktree: `/home/kegor2/market-morning-reports-session-c-selfrepair`; branch: `research/universal-agent-session-c-selfrepair-completion-20261119`, from `eb13f9977226a708d1238218db7d445d880a05ff`. Latest verified code commit: `421e0a1`.
- Completed: fixture-only `CODE_ERROR` detection, approval-gated `CODE_REPAIR_TASK`, existing Bubblewrap static and runtime validation, failed-patch code/DAG rollback, analysis-verification rollback, actual Supervisor SIGKILL during patch and rollback recovery, original Goal resumption, persistent Queue terminal deduplication. Local Goal `research_8b7007261c55` is `COMPLETED_EXPLORATORY` in `.universal_private/session_c_code_repair_e2e/state.json`; network/model calls are zero. The first blocked path-alias attempt was preserved and then recovered. No actual market or AI-generated repair result follows from this fixture.
- External Provider approval: policy schema and exact Registry URL validator exist; live execution remains disabled. No external request or model call was made.
- Still required: all P0 fault invariants at each of eight points, API-specific analysis-failure and rollback-SIGKILL trials, full P1 eight-case deadline matrix including system-clock and total elapsed-time audits, live Provider terms/access and bounded request approval, enforceable paid-model cost ceiling, official PIT and independent market holdout. The code repair transaction journal and shutdown-grace test are now implemented. Session C, general-purpose and production readiness remain false.
- The new Worktree lacks Git-ignored Naver snapshots by default. Two files were copied from the preserved prior Worktree with SHA-256 `b243b958aae4ac360527f8d85e38c2696b8be4379bd77a0833ef977ec2595ae3` and `a3cccdd46ef9b6eb3cb6edf69f753f3b4e888f2b887b7b26f4c2e31126ade9fd`; they remain ignored and must not be committed.

Resume commands:

```bash
cd /home/kegor2/market-morning-reports-session-c-selfrepair
git fetch --all --prune
git status --short --branch
git log -3 --oneline
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m universal_agent.research_runtime status --queue-dir .universal_private/session_c_code_repair_e2e
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/universal_agent/tests -q
PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest discover -s market-history/research/regime190/tests -q
```

The Universal Agent suite needs local loopback socket and Bubblewrap namespace permission. Python module execution needs no `chmod`. Next code task: finish the remaining API-specific P0 faults and P1 time/clock audits without rerunning terminal Goals. The pre-journal completed fixture Queue was reconciled at generation 9 with a recorded previous/current hash event after terminal state and report timestamp rewrites; no Task was rerun.
