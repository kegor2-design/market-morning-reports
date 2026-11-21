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
    "failure_observation": {
      "issued_approval_sha256": "4749d1d7e76efe581b9056c229b854d788dbf4901cef824617b7818a5cc30c60",
      "rejected_budget": 2
    },
    "test_id": "R1",
    "goal_id": "research_a1c6e314ed8f",
    "original_goal_hash": "79fca008d45f90525f53862af0539c95c6cbd18bb8ebb43667b4405f60308c85",
    "contract_hash": "32e6718dffb80f4a63416caac2152a8bcb9a287fdeea77e93b882f36aa0767ad",
    "plan_hash": "042d8e951be7bb9f9edd3329d6536b27093ca1f15332c5c712841b2bbc905406",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "b63b6935837e6fd3a475df01340b737292c9e8462a54065330602e3f2730c0b7",
    "approval_ledger_hash": "404d074ef2e506e2ced72598869d5d1374a880cf8700904a5f28e7f3fb1724d6",
    "request_ledger_hash": "fb5298526d798f615b98d5e0c60bdb2a2fa53b7ba43bfbe3349cca7d81d6281c",
    "failure_evidence_hash": "8d9740de2dd5f6566ebde2e09d34abe9a0061dbb99b77a4c9c0d227dce6e3dfa",
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
    "failure_observation": {
      "journal_absent_after_failed_write": true,
      "state_unchanged": true
    },
    "test_id": "R2",
    "goal_id": "research_cad0218bb116",
    "original_goal_hash": "c5833856375337fa574c4fd945294516fc79d35adc9445c4f7969454c9b87148",
    "contract_hash": "ad2c39364feb69b8e40433c9a80531ac9a2c0d03e235c81297b02cf516e9d825",
    "plan_hash": "25a1701d91a6b263f4e5b906ed366f21c0ee1b1e1e9f6f336e4661d5556fc18f",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": "d8ae6a45155b067042227ca30b5759896cc18d068d920c7238f3fc6df64f406d",
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "b12937eda119e8b8b53a87c63dcaa4e3d23a67b7e5c33189b9ef39b9822b49da",
    "approval_ledger_hash": "3141ad1c2f6d59864f2bc50a336d7385e2b1b613b75b6c5b5f0e64533ca33ca3",
    "request_ledger_hash": "85aa597794851629a2de7e823adaa898f2925d2e072dadfa69b523c9ac0c17b5",
    "failure_evidence_hash": "0fedf300f6b500d98c9dcd843e37fb7fda9f81bdba10e65c7a7718dc6d7de044",
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
    "failure_observation": {
      "interrupted_prepared_revision": "f172b3fe17f0d6de3189d26861f0495a9419ffc170f20e0ce854e6018067d30d"
    },
    "test_id": "R3",
    "goal_id": "research_ddcca11b72c4",
    "original_goal_hash": "5d0852d0b4185570943ba49a04243ee921129f0d138bffd6d9633f295be39d16",
    "contract_hash": "0038232387fc61cfe8a41eb942b42252683fca7ce8b122a020a4d666f19102ed",
    "plan_hash": "46183c79bcfacfc0cb2a8495d40bd0d8547005f53d418aa2565ee72430080eac",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": "f172b3fe17f0d6de3189d26861f0495a9419ffc170f20e0ce854e6018067d30d",
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "bb712ade86d5f2f81354964c01f949d65b39170ea7c03c64f6a9052f33088e2c",
    "approval_ledger_hash": "78179d97daf206dd68ab225014405a56dbb4a4e62e28ca5440bbf7ca140cb918",
    "request_ledger_hash": "bdcffdaba0eef308847dc1c9b6957df5ca3fdead89e73dd7a54a11a620258fa0",
    "failure_evidence_hash": "cbca060fdb00d9e9ef786c56059b71f0246d62c16443a829894855a872e9cf5d",
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
    "failure_observation": {
      "worker_exit": -9,
      "recovery_reservations": 1
    },
    "test_id": "R4",
    "goal_id": "research_196ab1f564f1",
    "original_goal_hash": "ac29f3b557213a639b5573cb6feb9d91bc33001b4583bf27000e2f1cdc966edd",
    "contract_hash": "640ceef61da66f6383ba90c6ac836b8c19d8cf6002017255d67b86cca5a3839d",
    "plan_hash": "b1a3f8bbe6a67f77ede82f7b450646f1d73325ff42646cbb46cfcc34b94d50f9",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "95e8a672d2326d7bc046c5a7b05f913bef26f4ea1d8c052a4f537325921f8493",
    "approval_ledger_hash": "3a07e4c43b3d99e94041b841a00cbfbe98074df32e2df6bb9b239bdedd1bdbf4",
    "request_ledger_hash": "1a424f173f53c5a9c9dc7bec66172c60d18b462b6af1f2c1a95eed62a0ab71f7",
    "failure_evidence_hash": "ce523e7d9dc1672e1be54b843caee8e3fad564ad8f7398c651ad304b56a038e4",
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
    "failure_observation": {
      "retired_status": "BLOCKED_EVIDENCE",
      "malformed_response_sha256": "f82892290ec38e6650d4ed8a888cceefd7a0de13d8b017fa28b46ee7f993f1ec"
    },
    "test_id": "R5",
    "goal_id": "research_087dbdc256a4",
    "original_goal_hash": "1b7375e14bb925c2305d3bab817164fdb67f67bea1460f3b9008d3bae85b2abf",
    "contract_hash": "a5b710c36f962e8022b57876a2f4f0a43177ac0b7000a3338c441e52dd5276a7",
    "plan_hash": "df3b23956c87452041831116dca1ee0c3ca4edbf435b2194add020f9e4013cbb",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "ef26d93cc82e2c8f1473a0ed6720d72ea13f589ac594b08dc37faf1199aa7d89",
    "approval_ledger_hash": "3a0b62d3747c1672f714a003fb7bda7f0454d04def77b03438ae8165fa85d52d",
    "request_ledger_hash": "70c14b8a52261143e3d46684a8a31a851b34acdbb590aa59b2acf93d3101caa1",
    "failure_evidence_hash": "6169659eb3783525807f46c73cbb0a5024b8abbb6cc3f836f6320c176686ce9b",
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
    "failure_observation": {
      "retired_analysis_status": "FAILED",
      "retired_recovery_status": "VERIFIED"
    },
    "test_id": "R6",
    "goal_id": "research_cc8a1637112d",
    "original_goal_hash": "6998606d2d37f8f089fec20f57c08010a1908f945d3a8d8d8df063e3bde468d0",
    "contract_hash": "cf0f11ddce18daf0caa4713d8b37fa3ae1420d8aaf39ab14b1bd43e4a1e1784a",
    "plan_hash": "0bcae4680ec494c12c2e4ece702a2a7e050c11d43c4b5fdf7ddfac4b0dddfdfb",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "493c7427c05b2b0642e1222e30611f2333e20db47b7a00c58c2f442ac7c950bf",
    "approval_ledger_hash": "b27e66056e6947aa393c0b2e143f264577ce8d7951139ade927cb48c47e33e41",
    "request_ledger_hash": "df6331a962feb6bfb897b0ae738b9f828b38d52edda96189f759e53499781498",
    "failure_evidence_hash": "a3f1d2d79b6239c402766e8e390dc9c8ad080f069e4d1a85aa3db61d797f522f",
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
    "failure_observation": {
      "duplicate_rejection": "API recovery revision already exists"
    },
    "test_id": "R7",
    "goal_id": "research_ada757d273be",
    "original_goal_hash": "0fc45a4617a5a724c5ef46140b7a75046b7041fdb2b5e6d94d50fea5750cb89f",
    "contract_hash": "61e15069fab2af6ff99575693ad8c46ce1172cc245a19bfd86917b5fbdb5599a",
    "plan_hash": "6ee5c64db9f048d1ad9aa4cdfd5509016a44ff8dc22c02c43eefe5a300b6771f",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": "2fa17fe41b683d84cf9d57dfe71cf97db6e0ca3dbd964dd6398e702f34aa06f1",
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "70f7035451cc159380f3230d4c571448366670221bde3d46735df7ef9d0c0c37",
    "approval_ledger_hash": "5b3dda59fb34f9975c9cd8ed4858ab078c3d75a39c33784c36478c6eb3f357fe",
    "request_ledger_hash": "bc024639a18b082f7dc9136e88c0ff1f80272021158df6257b63a08e934e3c8a",
    "failure_evidence_hash": "fe5fd99f6bf7269dca7eda38ab1efc6816d49ed926fc4f6bc208b96334fbc524",
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
    "failure_observation": {
      "supervisor_exit": -9,
      "interrupted_journal": "REVISION_COMMITTED",
      "interrupted_state": "REVISION_ROLLED_BACK"
    },
    "test_id": "R8",
    "goal_id": "research_2d5fc0a1cbe4",
    "original_goal_hash": "ed1c6625fac1baa7503dcefc2b1d112d500045b857b6088e62fbbf4c68ff6b0f",
    "contract_hash": "8ce41b258edb8aa4b05a01cd0709a09f7b580017a78c5c3295bdedb53b3f9f07",
    "plan_hash": "6e23904074006a7d602b310caaa33f0700c16177d6941ce7847ccc7bb7a63537",
    "original_dag_hash": "4bc867c6f60b0f732d20add09cbeab6802a7e9742a72b24127880a09743426ed",
    "active_revision_hash": null,
    "source_hash": "92705563242cfd7c5c897d0a1a5bb61db62d5bc8a608dc2e30907333acebe4bb",
    "completed_task_hash": "40d023ef86770ce775839963daf6b0f11f1cbd80b57d0e63a69f33887af709ca",
    "approval_ledger_hash": "dc5379c6a7e0d199be618fad3b4cc0d82d1a51c45bb93cd8d6e6bb02706114b1",
    "request_ledger_hash": "24f8c9cbcccd1e6a03bdce45e7a6bd34171d9e73ec95c59108bfcfa0f6d9f951",
    "failure_evidence_hash": "541b63bfe83cf54c9b43d4439bc914126fd37d39d6d9f279d3735fad809616f5",
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

## Deadline trial measurements

T1/2/5/6 time the single Research Job including shutdown. T3/7/8 measure one shared 10-second Program from before creation, including actual waiting and repeated invocation. T4 times initial failure through rollback, with a shortened UTC deadline after approval. Scheduling tolerance is 100 ms for grace, 600 ms for checkpoint and reap. Whole multi-task Program coverage for the four single-job trials remains pending.

Reproduce with `PYTHONPATH=market-history/research UNIVERSAL_AUDIT_DIR=.universal_private/finalization /home/kegor2/stock_env/bin/python -m unittest universal_agent.tests.test_process_recovery universal_agent.tests.test_research_program universal_agent.tests.test_code_recovery`.

```json
[
  {
    "test_id": "T1",
    "scope": "single Research Job with outer Goal deadline",
    "goal_start_utc": "2026-11-21T13:04:17.646217+00:00",
    "deadline_utc": "2026-11-21T13:04:27.646217+00:00",
    "end_utc": "2026-11-21T13:04:21.124902+00:00",
    "elapsed_seconds": 3.4786842204630375,
    "approved_budget_seconds": 10.0,
    "remaining_seconds": 6.521315,
    "restarts": 0,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "started_at_utc": "2026-11-21T13:04:17.810350+00:00",
        "ended_at_utc": "2026-11-21T13:04:21.109186+00:00",
        "task_deadline_utc": "2026-11-21T13:04:27.646217+00:00"
      }
    ],
    "shutdown_grace": [],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T2",
    "scope": "single Research Job with outer Goal deadline",
    "goal_start_utc": "2026-11-21T13:04:21.126863+00:00",
    "deadline_utc": "2026-11-21T13:04:22.126863+00:00",
    "end_utc": "2026-11-21T13:04:22.144679+00:00",
    "elapsed_seconds": 1.0178148243576288,
    "approved_budget_seconds": 1.0,
    "remaining_seconds": 0,
    "restarts": 0,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "started_at_utc": "2026-11-21T13:04:21.217707+00:00",
        "ended_at_utc": "2026-11-21T13:04:22.135328+00:00",
        "task_deadline_utc": "2026-11-21T13:04:22.126863+00:00"
      }
    ],
    "shutdown_grace": [
      {
        "event": "SHUTDOWN_GRACE_STARTED",
        "at_utc": "2026-11-21T13:04:22.127606+00:00",
        "monotonic": 10703766.08182046
      },
      {
        "event": "SHUTDOWN_GRACE_ENDED",
        "at_utc": "2026-11-21T13:04:22.135143+00:00",
        "monotonic": 10703766.089352725
      }
    ],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T3",
    "scope": "Research Program",
    "goal_start_utc": "2026-11-21T13:04:36.490580+00:00",
    "deadline_utc": "2026-11-21T13:04:46.537997+00:00",
    "end_utc": "2026-11-21T13:04:36.993058+00:00",
    "elapsed_seconds": 0.5024767182767391,
    "approved_budget_seconds": 10,
    "remaining_seconds": 9.544939,
    "restarts": 1,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "selected": "discover_ust_2y",
        "started_at_utc": "2026-11-21T13:04:36.579331+00:00",
        "ended_at_utc": "2026-11-21T13:04:36.621534+00:00",
        "task_deadline_utc": "2026-11-21T13:04:46.537996+00:00"
      },
      {
        "selected": "discover_ust_10y",
        "started_at_utc": "2026-11-21T13:04:36.842735+00:00",
        "ended_at_utc": "2026-11-21T13:04:36.897024+00:00",
        "task_deadline_utc": "2026-11-21T13:04:46.537995+00:00"
      }
    ],
    "shutdown_grace": [],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T4",
    "scope": "Research Program",
    "goal_start_utc": "2026-11-21T13:04:54.166086+00:00",
    "deadline_utc": "2026-11-21T13:04:56.415896+00:00",
    "end_utc": "2026-11-21T13:04:56.591309+00:00",
    "elapsed_seconds": 2.425221975892782,
    "approved_budget_seconds": 300,
    "remaining_seconds": 0,
    "restarts": 1,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "selected": "analyze_fixture",
        "started_at_utc": "2026-11-21T13:04:54.242676+00:00",
        "ended_at_utc": "2026-11-21T13:04:54.319035+00:00",
        "task_deadline_utc": "2026-11-21T13:05:54.242654+00:00"
      },
      {
        "selected": "code_repair_fixture",
        "started_at_utc": "2026-11-21T13:04:54.549251+00:00",
        "ended_at_utc": "2026-11-21T13:04:56.431099+00:00",
        "task_deadline_utc": "2026-11-21T13:04:56.415891+00:00"
      }
    ],
    "shutdown_grace": [],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T5",
    "scope": "single Research Job with outer Goal deadline",
    "goal_start_utc": "2026-11-21T13:04:28.960154+00:00",
    "deadline_utc": "2026-11-21T13:04:30.960154+00:00",
    "end_utc": "2026-11-21T13:04:31.028664+00:00",
    "elapsed_seconds": 2.0685153175145388,
    "approved_budget_seconds": 2.0,
    "remaining_seconds": 0,
    "restarts": 1,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "started_at_utc": "2026-11-21T13:04:29.065432+00:00",
        "ended_at_utc": "2026-11-21T13:04:31.010925+00:00",
        "task_deadline_utc": "2026-11-21T13:04:30.960154+00:00"
      }
    ],
    "shutdown_grace": [
      {
        "event": "SHUTDOWN_GRACE_STARTED",
        "at_utc": "2026-11-21T13:04:31.010440+00:00",
        "monotonic": 10703774.964647615
      },
      {
        "event": "SHUTDOWN_GRACE_ENDED",
        "at_utc": "2026-11-21T13:04:31.010730+00:00",
        "monotonic": 10703774.96492593
      }
    ],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T6",
    "scope": "single Research Job with outer Goal deadline",
    "goal_start_utc": "2026-11-21T13:04:22.145937+00:00",
    "deadline_utc": "2026-11-21T13:04:23.145937+00:00",
    "end_utc": "2026-11-21T13:04:25.184163+00:00",
    "elapsed_seconds": 3.0382308959960938,
    "approved_budget_seconds": 1.0,
    "remaining_seconds": 0,
    "restarts": 0,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "started_at_utc": "2026-11-21T13:04:22.300853+00:00",
        "ended_at_utc": "2026-11-21T13:04:25.171354+00:00",
        "task_deadline_utc": "2026-11-21T13:04:23.145937+00:00"
      }
    ],
    "shutdown_grace": [
      {
        "event": "SHUTDOWN_GRACE_STARTED",
        "at_utc": "2026-11-21T13:04:23.163583+00:00",
        "monotonic": 10703767.117803052
      },
      {
        "event": "SHUTDOWN_GRACE_ENDED",
        "at_utc": "2026-11-21T13:04:25.165317+00:00",
        "monotonic": 10703769.11953277
      }
    ],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T7",
    "scope": "Research Program",
    "goal_start_utc": "2026-11-21T13:04:36.490580+00:00",
    "deadline_utc": "2026-11-21T13:04:46.537997+00:00",
    "end_utc": "2026-11-21T13:04:46.758218+00:00",
    "elapsed_seconds": 10.267635896801949,
    "approved_budget_seconds": 10,
    "remaining_seconds": 0,
    "restarts": 3,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "selected": "discover_ust_2y",
        "started_at_utc": "2026-11-21T13:04:36.579331+00:00",
        "ended_at_utc": "2026-11-21T13:04:36.621534+00:00",
        "task_deadline_utc": "2026-11-21T13:04:46.537996+00:00"
      },
      {
        "selected": "discover_ust_10y",
        "started_at_utc": "2026-11-21T13:04:36.842735+00:00",
        "ended_at_utc": "2026-11-21T13:04:36.897024+00:00",
        "task_deadline_utc": "2026-11-21T13:04:46.537995+00:00"
      }
    ],
    "shutdown_grace": [],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T8",
    "scope": "Research Program",
    "goal_start_utc": "2026-11-21T13:04:36.490580+00:00",
    "deadline_utc": "2026-11-21T13:04:46.537997+00:00",
    "end_utc": "2026-11-21T13:04:46.849212+00:00",
    "elapsed_seconds": 10.358628967776895,
    "approved_budget_seconds": 10,
    "remaining_seconds": 0,
    "restarts": 4,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "selected": "discover_ust_2y",
        "started_at_utc": "2026-11-21T13:04:36.579331+00:00",
        "ended_at_utc": "2026-11-21T13:04:36.621534+00:00",
        "task_deadline_utc": "2026-11-21T13:04:46.537996+00:00"
      },
      {
        "selected": "discover_ust_10y",
        "started_at_utc": "2026-11-21T13:04:36.842735+00:00",
        "ended_at_utc": "2026-11-21T13:04:36.897024+00:00",
        "task_deadline_utc": "2026-11-21T13:04:46.537995+00:00"
      }
    ],
    "shutdown_grace": [],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  }
]
```

## Integrated whole-Goal follow-up

Four additional trials exercised the full Program path for normal completion, timeout, supervisor death and a stopped worker. Each includes initial planning, discovery or index validation, Task execution and final checkpoint. For the HTTP trials the owned Worker made one request. T5 attached to the existing Worker. T6 escalated after the measured grace. T3, T4, T7 and T8 above already used the Program path. Reproduce with `PYTHONPATH=market-history/research UNIVERSAL_AUDIT_DIR=.universal_private/finalization /home/kegor2/stock_env/bin/python -m unittest universal_agent.tests.test_whole_goal_deadline`.

```json
[
  {
    "test_id": "T1_program",
    "scope": "Research Program",
    "goal_start_utc": "2026-11-21T13:13:43.384617+00:00",
    "deadline_utc": "2026-11-21T13:13:53.453909+00:00",
    "end_utc": "2026-11-21T13:13:44.270809+00:00",
    "elapsed_seconds": 0.8861872795969248,
    "approved_budget_seconds": 10,
    "remaining_seconds": 9.1831,
    "restarts": 0,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "selected": "validate_kr_index",
        "started_at_utc": "2026-11-21T13:13:43.496035+00:00",
        "ended_at_utc": "2026-11-21T13:13:43.626630+00:00",
        "task_deadline_utc": "2026-11-21T13:13:53.453907+00:00"
      },
      {
        "selected": "analyze_kr_crashes",
        "started_at_utc": "2026-11-21T13:13:43.682650+00:00",
        "ended_at_utc": "2026-11-21T13:13:44.148220+00:00",
        "task_deadline_utc": "2026-11-21T13:13:53.453906+00:00"
      }
    ],
    "shutdown_grace": [],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T2_program",
    "scope": "Research Program",
    "goal_start_utc": "2026-11-21T13:14:07.422326+00:00",
    "deadline_utc": "2026-11-21T13:14:17.484924+00:00",
    "end_utc": "2026-11-21T13:14:17.664181+00:00",
    "elapsed_seconds": 10.241856344044209,
    "approved_budget_seconds": 10,
    "remaining_seconds": 0,
    "restarts": 1,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "selected": "discover_ust_2y",
        "started_at_utc": "2026-11-21T13:14:07.547133+00:00",
        "ended_at_utc": "2026-11-21T13:14:07.606584+00:00",
        "task_deadline_utc": "2026-11-21T13:14:17.484923+00:00"
      },
      {
        "selected": "discover_ust_10y",
        "started_at_utc": "2026-11-21T13:14:07.682734+00:00",
        "ended_at_utc": "2026-11-21T13:14:07.735898+00:00",
        "task_deadline_utc": "2026-11-21T13:14:17.484922+00:00"
      },
      {
        "selected": "discover_nyfed_sofr",
        "started_at_utc": "2026-11-21T13:14:07.789088+00:00",
        "ended_at_utc": "2026-11-21T13:14:07.830911+00:00",
        "task_deadline_utc": "2026-11-21T13:14:17.484922+00:00"
      },
      {
        "selected": "collect_ust_2y",
        "started_at_utc": "2026-11-21T13:14:12.827880+00:00",
        "ended_at_utc": "2026-11-21T13:14:17.503565+00:00",
        "task_deadline_utc": "2026-11-21T13:14:17.484923+00:00"
      }
    ],
    "shutdown_grace": [
      {
        "event": "SHUTDOWN_GRACE_STARTED",
        "at_utc": "2026-11-21T13:14:17.489146+00:00",
        "monotonic": 10704361.443364363
      },
      {
        "event": "SHUTDOWN_GRACE_ENDED",
        "at_utc": "2026-11-21T13:14:17.496737+00:00",
        "monotonic": 10704361.450951653
      }
    ],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T5_program",
    "scope": "Research Program",
    "goal_start_utc": "2026-11-21T13:13:56.885877+00:00",
    "deadline_utc": "2026-11-21T13:14:06.929279+00:00",
    "end_utc": "2026-11-21T13:14:07.192943+00:00",
    "elapsed_seconds": 10.307064272463322,
    "approved_budget_seconds": 10,
    "remaining_seconds": 0,
    "restarts": 2,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "selected": "discover_ust_2y",
        "started_at_utc": "2026-11-21T13:13:56.971253+00:00",
        "ended_at_utc": "2026-11-21T13:13:57.021664+00:00",
        "task_deadline_utc": "2026-11-21T13:14:06.929278+00:00"
      },
      {
        "selected": "discover_ust_10y",
        "started_at_utc": "2026-11-21T13:13:57.072535+00:00",
        "ended_at_utc": "2026-11-21T13:13:57.116567+00:00",
        "task_deadline_utc": "2026-11-21T13:14:06.929278+00:00"
      },
      {
        "selected": "discover_nyfed_sofr",
        "started_at_utc": "2026-11-21T13:13:57.170215+00:00",
        "ended_at_utc": "2026-11-21T13:13:57.229728+00:00",
        "task_deadline_utc": "2026-11-21T13:14:06.929277+00:00"
      },
      {
        "selected": "collect_ust_2y",
        "started_at_utc": "2026-11-21T13:14:02.308743+00:00",
        "ended_at_utc": "2026-11-21T13:14:06.987080+00:00",
        "task_deadline_utc": "2026-11-21T13:14:06.929277+00:00"
      }
    ],
    "shutdown_grace": [
      {
        "event": "SHUTDOWN_GRACE_STARTED",
        "at_utc": "2026-11-21T13:14:06.976629+00:00",
        "monotonic": 10704350.93083394
      },
      {
        "event": "SHUTDOWN_GRACE_ENDED",
        "at_utc": "2026-11-21T13:14:06.976808+00:00",
        "monotonic": 10704350.931000195
      }
    ],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  },
  {
    "test_id": "T6_program",
    "scope": "Research Program",
    "goal_start_utc": "2026-11-21T13:13:44.322727+00:00",
    "deadline_utc": "2026-11-21T13:13:54.374147+00:00",
    "end_utc": "2026-11-21T13:13:56.579769+00:00",
    "elapsed_seconds": 12.257046399638057,
    "approved_budget_seconds": 10,
    "remaining_seconds": 0,
    "restarts": 1,
    "boot_id": "5ed0dd23-000d-4627-b80f-64922cb34c39",
    "tasks": [
      {
        "selected": "discover_ust_2y",
        "started_at_utc": "2026-11-21T13:13:44.413639+00:00",
        "ended_at_utc": "2026-11-21T13:13:44.455005+00:00",
        "task_deadline_utc": "2026-11-21T13:13:54.374147+00:00"
      },
      {
        "selected": "discover_ust_10y",
        "started_at_utc": "2026-11-21T13:13:44.502899+00:00",
        "ended_at_utc": "2026-11-21T13:13:44.549523+00:00",
        "task_deadline_utc": "2026-11-21T13:13:54.374146+00:00"
      },
      {
        "selected": "discover_nyfed_sofr",
        "started_at_utc": "2026-11-21T13:13:44.622421+00:00",
        "ended_at_utc": "2026-11-21T13:13:44.664939+00:00",
        "task_deadline_utc": "2026-11-21T13:13:54.374145+00:00"
      },
      {
        "selected": "collect_ust_2y",
        "started_at_utc": "2026-11-21T13:13:49.833114+00:00",
        "ended_at_utc": "2026-11-21T13:13:56.424891+00:00",
        "task_deadline_utc": "2026-11-21T13:13:54.374143+00:00"
      }
    ],
    "shutdown_grace": [
      {
        "event": "SHUTDOWN_GRACE_STARTED",
        "at_utc": "2026-11-21T13:13:54.410215+00:00",
        "monotonic": 10704338.364461794
      },
      {
        "event": "SHUTDOWN_GRACE_ENDED",
        "at_utc": "2026-11-21T13:13:56.410735+00:00",
        "monotonic": 10704340.364968644
      }
    ],
    "post_deadline_starts": 0,
    "duplicates": 0,
    "final_verdict": "PASS"
  }
]
```

The additional T5_late fault kills the original supervisor and starts its replacement after the actual persistent deadline. Only the already-running research child is identified and terminated. The original API reservation remains on disk, observed HTTP count is one, new starts zero. The original boot-change review still blocks dispatch. These elapsed bounds describe the running/recoverable supervisor trials. A machine outage or an indefinitely unavailable supervisor has no observable host shutdown bound.
