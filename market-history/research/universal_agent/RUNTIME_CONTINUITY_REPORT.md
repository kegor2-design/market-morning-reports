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

## 2026-11-21 R1–R8 real loopback audit

Each trial used a separate Goal and temporary queue. Hashes below cover the original files and records, and the request hash includes the final local ledger. Generation and sealed references are checked through the normal queue loader. Model use is measured by zero program and queue counters. An empty active revision means the original DAG is active. R1 snapshots the rejected approval at injection. R4 initially detected two worker starts for one authorized request. The interrupted one-shot recovery now stops after its first child. R8 pins the prior sealed generation and reconciles the rollback without launching another task. Reproduce from the worktree root with:

```sh
PYTHONPATH=market-history/research UNIVERSAL_AUDIT_DIR=.universal_private/finalization /home/kegor2/stock_env/bin/python -m unittest universal_agent.tests.test_api_recovery
```

```json
[
  {
    "test_id": "R1",
    "goal_id": "research_a1c6e314ed8f",
    "original_goal_hash": "79fca008d45f90525f53862af0539c95c6cbd18bb8ebb43667b4405f60308c85",
    "contract_hash": "32e6718dffb80f4a63416caac2152a8bcb9a287fdeea77e93b882f36aa0767ad",
    "plan_hash": "042d8e951be7bb9f9edd3329d6536b27093ca1f15332c5c712841b2bbc905406",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "2cd31c115dae17bf694fe8efffb3947792e681a14536ffd84ac2934ea19d5662",
    "approval_ledger_hash": "565e786d46f24bd8b9809187e7cdcb7c90fd0afc13f4cddf99224d5a2e68467b",
    "request_ledger_hash": "39364d5555d8adf96958647ca1194138fd32a3a92bac964ec8b33ce7e5f5b1b3",
    "failure_evidence_hash": "f612284fa69f8de3ae987894210098a9f0e2365c49e6ca304a86995090f46956",
    "observed_http_calls": 3,
    "checkpoint_generation": [
      3,
      4
    ],
    "model_calls": 0,
    "duplicate_execution_count": 0,
    "invariant_violations": [],
    "final_verdict": "PASS"
  },
  {
    "test_id": "R2",
    "goal_id": "research_cad0218bb116",
    "original_goal_hash": "c5833856375337fa574c4fd945294516fc79d35adc9445c4f7969454c9b87148",
    "contract_hash": "ad2c39364feb69b8e40433c9a80531ac9a2c0d03e235c81297b02cf516e9d825",
    "plan_hash": "25a1701d91a6b263f4e5b906ed366f21c0ee1b1e1e9f6f336e4661d5556fc18f",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": "f1e794a7d74df64e16dc98f715516adb4575df58023cb10628e8c13237d4f9c3",
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "bd3681d1171680487ff6292f27a5f3c686ea5752c9ab2bad77135f17f98824d5",
    "approval_ledger_hash": "414c3856d7eaa65306b1642fb7b3d3817b1039bafa548020a8c2a1f39c25d2c9",
    "request_ledger_hash": "318f266ee632dd8f619a8080185f840e33f8cafdb56a5d8784cf620e86f90ad4",
    "failure_evidence_hash": "9f84fe063dc232f6bf10b143f77388535bca7d2a1404b666ecdb1a19030c4ea0",
    "observed_http_calls": 4,
    "checkpoint_generation": [
      3,
      6
    ],
    "model_calls": 0,
    "duplicate_execution_count": 0,
    "invariant_violations": [],
    "final_verdict": "PASS"
  },
  {
    "test_id": "R3",
    "goal_id": "research_ddcca11b72c4",
    "original_goal_hash": "5d0852d0b4185570943ba49a04243ee921129f0d138bffd6d9633f295be39d16",
    "contract_hash": "0038232387fc61cfe8a41eb942b42252683fca7ce8b122a020a4d666f19102ed",
    "plan_hash": "46183c79bcfacfc0cb2a8495d40bd0d8547005f53d418aa2565ee72430080eac",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": "b3e36e389f975b304dd8b4905fd36cec78c0abc9f775d00c7edc3fc291c83dd2",
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "fc1eaaa1f342ca5aad7b0de7631284c541f59caab902731e1cb748c488c5f03e",
    "approval_ledger_hash": "cf35b7dc822ceb55eeaa91ab51a1d367994c373a5f1ff7b5c168a28b4a94e011",
    "request_ledger_hash": "395633410df05860cdbb684e6737097b072218d4e9795fba76fbb8b146b2be36",
    "failure_evidence_hash": "858f408c3c61e6f10df62dbd0967004c9f989db41c1c1ae0f5abbe12e340e717",
    "observed_http_calls": 4,
    "checkpoint_generation": [
      3,
      6
    ],
    "model_calls": 0,
    "duplicate_execution_count": 0,
    "invariant_violations": [],
    "final_verdict": "PASS"
  },
  {
    "test_id": "R4",
    "goal_id": "research_196ab1f564f1",
    "original_goal_hash": "ac29f3b557213a639b5573cb6feb9d91bc33001b4583bf27000e2f1cdc966edd",
    "contract_hash": "640ceef61da66f6383ba90c6ac836b8c19d8cf6002017255d67b86cca5a3839d",
    "plan_hash": "b1a3f8bbe6a67f77ede82f7b450646f1d73325ff42646cbb46cfcc34b94d50f9",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "8237b28d3f0414b609bb1425b102e6e48f018c7f0180ef9187935a51984820bd",
    "approval_ledger_hash": "2c30ba7fdd2bad0092bcee6e2189b8c4da03eaacddd4beb85ca6c94787b92960",
    "request_ledger_hash": "05e537fac4e3398791a6ce31812d8c5faeea7b455cafab1b2d3181051f55d3f7",
    "failure_evidence_hash": "da12bf0896e20f47d9dae1acfd39d98a8cebc9cbf6f2ad15e5a84faffe1a07e4",
    "observed_http_calls": 4,
    "checkpoint_generation": [
      3,
      6
    ],
    "model_calls": 0,
    "duplicate_execution_count": 0,
    "invariant_violations": [],
    "final_verdict": "PASS"
  },
  {
    "test_id": "R5",
    "goal_id": "research_087dbdc256a4",
    "original_goal_hash": "1b7375e14bb925c2305d3bab817164fdb67f67bea1460f3b9008d3bae85b2abf",
    "contract_hash": "a5b710c36f962e8022b57876a2f4f0a43177ac0b7000a3338c441e52dd5276a7",
    "plan_hash": "df3b23956c87452041831116dca1ee0c3ca4edbf435b2194add020f9e4013cbb",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "1d71a1f5616512a60e70a6c05bb4cd5208d1e73faa36d3965879b10a4a583ffb",
    "approval_ledger_hash": "1ece677637a3cabfc38d2aa93f32396763e7dd158de39a4e53bb1a418d765e03",
    "request_ledger_hash": "53be638a1001e4882445a5dfcfe2616eb5bd48fe1735561eb02a1e7b2a2c758b",
    "failure_evidence_hash": "693bc3006c552551b2e04b70dab9b05dda87d6651500fad6d5b92d1ee3721b63",
    "observed_http_calls": 4,
    "checkpoint_generation": [
      3,
      6
    ],
    "model_calls": 0,
    "duplicate_execution_count": 0,
    "invariant_violations": [],
    "final_verdict": "PASS"
  },
  {
    "test_id": "R6",
    "goal_id": "research_cc8a1637112d",
    "original_goal_hash": "6998606d2d37f8f089fec20f57c08010a1908f945d3a8d8d8df063e3bde468d0",
    "contract_hash": "cf0f11ddce18daf0caa4713d8b37fa3ae1420d8aaf39ab14b1bd43e4a1e1784a",
    "plan_hash": "0bcae4680ec494c12c2e4ece702a2a7e050c11d43c4b5fdf7ddfac4b0dddfdfb",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "ed5b1605a1ced2c21ee367c338933b89a116e1026440f96e600764f3293c7200",
    "approval_ledger_hash": "c47f36daf7e607607bf1d5e6dd671ee2f6950ddafb6cc9fb309a74b5211ff64c",
    "request_ledger_hash": "e05ba260866dc1ef81675872544f6d737f4adfd8286b8eba860320573a053cea",
    "failure_evidence_hash": "8b8b2d3d36812a4bb11563f7697cae289d36b549d3f9105644660ae4e2bdc8a9",
    "observed_http_calls": 4,
    "checkpoint_generation": [
      3,
      6
    ],
    "model_calls": 0,
    "duplicate_execution_count": 0,
    "invariant_violations": [],
    "final_verdict": "PASS"
  },
  {
    "test_id": "R7",
    "goal_id": "research_ada757d273be",
    "original_goal_hash": "0fc45a4617a5a724c5ef46140b7a75046b7041fdb2b5e6d94d50fea5750cb89f",
    "contract_hash": "61e15069fab2af6ff99575693ad8c46ce1172cc245a19bfd86917b5fbdb5599a",
    "plan_hash": "6ee5c64db9f048d1ad9aa4cdfd5509016a44ff8dc22c02c43eefe5a300b6771f",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": "7e31fddbb5f6e6fcceea83f700e5bf08ec86a08b81b3b08958a10150c934cc38",
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "3102a448b05437a4caa5c8ebcc8b6d393ce24c0b9c5d656531f02a49aeb0a187",
    "approval_ledger_hash": "09a1c4548e8977bad9286c47b386c648a6a033c9de57a81d0cebf1a09a85e8d4",
    "request_ledger_hash": "d71ce8c8140dbb1ad787e6c1b95c4884de4a30786c26d4a3bcea863c7e5d10a2",
    "failure_evidence_hash": "36aadfd19311a0419d1c27c296e72c105bfc449bea6769077f8e6c25271903e6",
    "observed_http_calls": 4,
    "checkpoint_generation": [
      3,
      6
    ],
    "model_calls": 0,
    "duplicate_execution_count": 0,
    "invariant_violations": [],
    "final_verdict": "PASS"
  },
  {
    "test_id": "R8",
    "goal_id": "research_2d5fc0a1cbe4",
    "original_goal_hash": "ed1c6625fac1baa7503dcefc2b1d112d500045b857b6088e62fbbf4c68ff6b0f",
    "contract_hash": "8ce41b258edb8aa4b05a01cd0709a09f7b580017a78c5c3295bdedb53b3f9f07",
    "plan_hash": "6e23904074006a7d602b310caaa33f0700c16177d6941ce7847ccc7bb7a63537",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "bed13b443823a0f125f9cc73c1914257b898ad7a001b5f406ec87ac930bd6fa6",
    "approval_ledger_hash": "7ba44a7d1494b3b37569f826a2f28fc54d7eff5bfc285feacb1ad8fc427e2362",
    "request_ledger_hash": "121c22df81751ff171a2282665da394fdb0bdd8316f8be0e911057aaefbec0be",
    "failure_evidence_hash": "eb046793be3efa2e0f57f8d83965d4f2fc3f30d625e3600867db5a18fd424ab0",
    "observed_http_calls": 4,
    "checkpoint_generation": [
      3,
      7
    ],
    "model_calls": 0,
    "duplicate_execution_count": 0,
    "invariant_violations": [],
    "final_verdict": "PASS"
  }
]
```
