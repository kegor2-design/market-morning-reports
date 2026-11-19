# Session C runtime continuity checkpoint (2026-11-17)

## Local API recovery Worker continuity — 2026-11-18

The new recovery test runs the existing persistent Runtime in a separate OS process and source/analysis Research Jobs in existing child Worker processes. Its original Goal keeps the baseline Goal Contract and Plan hashes. A versioned, hashed API recovery revision and separate approval are stored only in the private test program directory. One original failed request and its child checkpoint remain; the approved recovery uses a new Task/Job/request identity and one additional reserved network request. The durable private queue `.universal_private/session_c_api_recovery_e2e/state.json` reached generation 6 for Goal `research_b7188d9b5674`; its recorded transitions include the original `BLOCKED_ENV`, `API_RECOVERY_READY`, and final `COMPLETED_EXPLORATORY`. Completed fixture research was reopened through the Queue: `processed=0` and no additional HTTP request.

During a second isolated fixture run, SIGKILL stopped only the recovery child Worker while its HTTP request was pending. The Research Job checkpoint retained the reserved request; its bounded restart classified the outcome as uncertain and did not issue another HTTP call. The Queue remained blocked under the original Goal. This validates child Worker interruption safety for the local fixture. Strict outer wall-clock enforcement and actual SSH disconnect/reconnect remain unverified. No production Worker, scheduler or service changed.

## 2026-11-18 development resume after server restart

After the server restart, the Session C worktree was found clean at `3d3af77418ce4715b380829344e46764412d3781`. The previous private queue was read without rerunning its completed Goal; it remained `COMPLETED_EXPLORATORY` with generation 6. No research Worker was running. Development then resumed on the same isolated branch, added source-call failure evidence, passed 153 Universal Agent and 55 Regime190 tests, and pushed code commit `69fec86becd19103686ffc335a1836e6fa30f9ae` plus the handoff checkpoint. This verifies development checkpoint reuse across the restart. It does not verify that an active Worker survived an actual SSH disconnect or server reboot.

## 2026-11-18 dynamic Goal and schema recovery

Queue `.universal_private/session_c_dynamic_aug2020_fixed/state.json` first moved Goal `research_471a35e13cfa` from `PENDING` to `BLOCKED_EVIDENCE` after three official-source reservations. The second run diagnosed a sealed-source schema mismatch, added two zero-network recovery jobs, and reached `COMPLETED_EXPLORATORY` under the same Goal. The third run processed 0 jobs. All original collection tasks and recovery tasks show one attempt each; model calls remained 0. The original May 2018 calendar Goal still reads `COMPLETED_EXPLORATORY` from its preserved checkpoint. A Queue candidate aliasing bug surfaced during recovery; the original candidate hash and separately sealed candidate file allowed exact restoration, and the compiler/supervisor now copy mutable structures before checkpoint writes. Strict outer wall-time enforcement and an actual SSH disconnect/reconnect test remain unverified. No Worker was left running at handoff.

## 2026-11-18 AI proposal handoff

One synthetic, host-approved rates proposal was registered in the existing persistent queue and its first discovery task reached `VERIFIED` under the existing Research Program Supervisor. The proposal hash and private program copy were sealed. A repeated submission without the same proposal was rejected. The model request adapter was tested with simulated timeout and malformed response: both made one reserved test-provider call and refused automatic replay. The production Codex caller made zero calls because a monetary ceiling cannot be enforced by the available CLI. This run did not test a new detached shell/SSH lifecycle or strict outer wall-time limit; those remain blocked.

## 2026-11-18 recovery budget evidence

The original May 2018 Goal and the May 2019/July 2018 reproduction Goals each used three original approved provider requests, zero repair requests, and zero model calls. Their second launches created three local revalidation tasks and one analysis task; completed discovery tasks stayed at one attempt. Terminal reruns processed zero jobs. Strict outer runtime wall-time enforcement, model-provider-unavailable execution, and actual SSH disconnect/reconnect remain unverified.

The research runtime now stores an approved Goal queue under `.universal_private`, using the existing Research Program DAG and Research Job Supervisor for execution. Queue writes use `engine.write_state` (temporary file, fsync, atomic replace, directory fsync) and `locked_state` (exclusive flock). Each queue owns a separate program checkpoint tree. Terminal queue entries seal program and task artifact hashes. Unapproved and terminal jobs are never selected; launches are bounded to two per goal.

## Observed detached execution

- Queue: `.universal_private/session_c_disconnect_2/state.json`; goal `research_248bf5aefcbf`.
- The launch command returned PID 2733894 before the three-second startup delay ended. A separate command later observed `PENDING -> RUNNING -> BLOCKED_EVIDENCE` at 14:34:45–46 UTC. PIT evidence was absent, so no success claim was made.
- Queue: `.universal_private/session_c_rates_june2018/state.json`; goal `research_162ab26e5092`.
- The launch command returned PID 2734274 before work began. A separate command observed `PENDING -> RUNNING -> COMPLETED_EXPLORATORY` at 14:37:37–42 UTC. The program stored three source collection checkpoints and one analysis checkpoint.
- Reopening a terminal queue processed zero jobs. Dedicated tests also checked approval blocking, isolated checkpoints for equal goals in two queues, plan change rejection, output hash verification, and status reads while a worker holds the lock.

This verifies detached process survival after the launching shell exited, which simulates terminal disconnection. An actual SSH disconnect and reconnect was not performed. No service, linger setting, cron entry, or boot-time scheduler was changed. The runtime stops when its bounded queue is drained; it is not a continuously installed daemon. Worker and Supervisor SIGKILL recovery had passed in Session B and passed again in the Session C regression. A new queue test killed the runtime with SIGKILL after reservation; a later run recovered from the persistent `RUNNING` state, used its second bounded launch, executed the PIT task once, and did not execute it again. Injected checkpoint write failure left the Goal `PENDING` and prevented task execution. Injected provider `OSError` left the Goal `BLOCKED_ENV` with one attempt and zero network requests. These injections are not a live external-provider outage or real disk exhaustion. Model-unavailable and strict elapsed-time exhaustion remain unverified.

`AUTONOMOUS_RUNTIME_CONTINUITY=PASS` for bounded, already submitted jobs across launching-shell exit and checkpoint resume. Persistent service activation and all P0 fault gates are not yet verified.
# Recovery reliability continuation — 2026-11-18

New Research Program checkpoints persist `goal_budget_seconds` and `goal_deadline_utc`. A restart with a larger invocation budget retains the original deadline; a deadline fault test confirmed no additional Task attempts and a `GOAL_DEADLINE_EXHAUSTED` blocked result. Legacy checkpoints gain a one-time deadline on their next execution. The Supervisor uses a monotonic clock within an invocation and passes the stored Goal deadline into each child Research Job. A real delayed Worker was stopped at a one-second outer deadline and saved `FAILED_TERMINAL` with zero duplicate completions. Shutdown grace may extend past the exact deadline; Supervisor SIGKILL during rollback and repeated restart timing faults still need verification, so `STRICT_GOAL_DEADLINE_VERIFIED` remains BLOCKED.

The API recovery journal is saved under the existing program lock with atomic file replacement. Injecting a pre-commit journal write failure left the saved active Checkpoint in `REVISION_PREPARED`; a later replay committed it without changing original evidence. Prepared state is resumed by committing the journal after the candidate Checkpoint exists. Failed recovery retains its child Checkpoint hash and network reservation while restoring the prior DAG. A 429 queue wait stores the eligible UTC time and makes no busy-loop calls. The pre-existing completed fixture queue `research_b7188d9b5674` remained `COMPLETED_EXPLORATORY` at generation 6; it was inspected without rerunning its Tasks.

## 2026-11-19 fault and deadline continuation

The isolated code fixture added these reproducible fault points. `test_code_recovery.py` contains the assertions; each test uses a new private Goal directory, while the earlier completed API fixture Queue remains untouched.

| Fault point | Evidence | Result |
|---|---|---|
| R1–R3 | Existing API approval rejection, journal-write failure, prepared-Checkpoint replay | Prior active state retained; prepared Revision commits once on replay |
| R4–R5 | Existing API Recovery Worker SIGKILL and malformed HTTP 200 response | Uncertain request is not replayed; bad data restores prior DAG |
| R6 | Correct code patch followed by corrupted analysis output | Original source and DAG restored; both error records retained |
| R7 | Existing duplicate API Revision rejection | No second DAG mutation or request |
| R8 | Actual Supervisor SIGKILL after code rollback Checkpoint write | Restart returned blocked with the original DAG and one analysis attempt |

These cover the eight fault categories across two fixture capabilities. They do not yet prove every requested invariant for every fault point, nor an API-specific R6/R8 trial. The full P0 matrix gate stays BLOCKED. The fixture repair now reuses the API transaction journal primitives: a prepared Checkpoint commits the same Revision on restart; a Rollback Checkpoint finalizes the journal as `REVISION_ROLLED_BACK`. Injected journal-write and pre-commit failures left the active state intact and were replayed once. The pre-journal completed fixture Goal is accepted only as a terminal legacy Checkpoint.

For runtime, prior tests cover normal completion, persistent Deadline after restart and child timeout. A new slow repair candidate was terminated by its Goal Deadline; the source and DAG rolled back with zero network reservations. Actual Supervisor SIGKILL during patch application resumed from the source backup. A stopped research-only Worker ignored normal termination and was killed after the existing two-second shutdown grace; its terminal Checkpoint recorded `FAILED_TERMINAL` and the whole test finished within six seconds. Repeated restart tests retained the same Goal Deadline and did not increase Task attempts. System clock change and an exact whole-Goal elapsed-time bound remain pending, so the P1 eight-case matrix and strict Goal gate stay BLOCKED. The persistent completed code fixture Queue processed zero jobs on rerun.

Completed fixture Tasks now compare the saved analysis or repair source hash with the current `experiment.py` before program resume. A source-tampering injection was rejected while retaining the completed Checkpoint; the terminal Queue itself was not replayed.

A manual inspection reopened the earlier completed fixture Program through a relative path and exposed a legacy behavior that rewrote terminal state and report timestamps. The Program now returns a validated completed report without rewriting either file; a regression test compares both hashes before and after reopening. The single affected private Queue was reconciled under its lock after verifying Goal and plan hashes, both Task attempt counts, exact answer 42, source hash, and zero network/model calls. Queue generation 9 records the previous and current Checkpoint/report hashes. A terminal rerun processed zero jobs and the Queue passed integrity loading.

## 2026-11-19 priority continuation: API rollback and Deadline faults

Starting code SHA `6ff0e02b1096320f721e4c9facce0bb347075f81`; verified code commit `f57f9b6`. All new fault trials used disposable private directories. The preserved API and NameError fixture Goals were not rerun. The API R6/R8 tests use an actual local HTTP server and child Research Workers; they do not use an external Provider.

| ID | Injection and direct evidence | Result | Remaining qualification |
|---|---|---|---|
| R1 | Existing approval rejection before Revision creation | PASS for unchanged active DAG | Full per-point ledger/hash matrix not recorded |
| R2 | Existing API journal write `OSError` | PASS for unchanged in-memory state and safe replay | Full per-point ledger/hash matrix not recorded |
| R3 | Existing prepared Checkpoint and pre-commit write failure | PASS for same Revision commit on replay | Full per-point ledger/hash matrix not recorded |
| R4 | Existing API recovery child Worker `SIGKILL` | PASS for one uncertain recovery reservation and no resend | Full per-point ledger/hash matrix not recorded |
| R5 | Existing malformed HTTP 200 recovery body | PASS for original DAG and blocked analysis | Full per-point ledger/hash matrix not recorded |
| R6 | New API recovery succeeds; parent independent analysis artifact verification raises injected `ValueError` | PASS: prior DAG and Goal/plan/contract hashes restored; retired recovery Task remains `VERIFIED`, failed analysis remains `FAILED`, original requests 3 plus one recovery request; no completed analysis | Real provider and full common invariant audit remain blocked |
| R7 | Existing duplicate Revision attempt | PASS for rejection without state mutation | Full per-point ledger/hash matrix not recorded |
| R8 | New API bad-response rollback Checkpoint is written, then only its Supervisor receives `SIGKILL` | PASS: restart marks the same Journal `REVISION_ROLLED_BACK`, restores original DAG, analysis attempts 0, request count 4 | Real provider and full common invariant audit remain blocked |

These API-specific R6/R8 results close the earlier capability gap. `ROLLBACK_FAULT_MATRIX_8_OF_8_VERIFIED` remains **BLOCKED** because each row has not yet captured every requested source/completed Task hash, ledger, approval and Checkpoint-generation invariant. Existing tests are retained without weaker assertions.

The Goal checkpoint now stores a Linux boot ID and absolute monotonic Deadline alongside its UTC Deadline. On the same boot, remaining time is the minimum of both clocks. Child analysis and code-repair tasks receive that smaller allowance. A mocked wall clock ten minutes behind did not renew an expired monotonic budget or start another Task. A simulated boot-ID change blocked new work with `GOAL_BOOT_CHANGED_REVIEW`; this is a deliberate fail-closed choice, so unattended continuation across a real reboot needs a separately reviewed clock reconciliation rule.

| ID | Current evidence | Result |
|---|---|---|
| T1 | Existing completed fixture Goal and terminal zero-work rerun | PASS for normal completion; exact time audit pending |
| T2 | Existing delayed child Worker outer Deadline | PASS for timeout and terminal Checkpoint; exact whole-Goal bound pending |
| T3 | Persistent UTC/monotonic Deadline and larger restart budget | PASS for no extension and unchanged Task attempts |
| T4 | Existing slow code-repair candidate reaches Goal Deadline | PASS for source/DAG rollback and zero network calls |
| T5 | New real Supervisor `SIGKILL`, restart with same outer Deadline | PASS for one Worker attempt, no duplicate completion, terminal timeout within six seconds |
| T6 | Existing `SIGSTOP` Worker ignores termination, then research-only `SIGKILL` after two-second grace | PASS within six seconds |
| T7 | Existing three repeated restarts plus new backward-clock injection | PASS for no budget renewal or new Task attempts |
| T8 | Existing expired Goal is invoked again | PASS for blocked result and no new Task attempts |

The test process measured the T5/T6 elapsed bounds with `time.monotonic()`. Exact start/end timestamps and allowed grace for every T1–T8 case are not yet in a unified audit artifact; `GOAL_DEADLINE_MATRIX_8_OF_8_VERIFIED` and `STRICT_GOAL_DEADLINE_VERIFIED` remain **BLOCKED**. Universal Agent 194 PASS, Regime190 55 PASS, `compileall` and `git diff --check` PASS for this code commit.
