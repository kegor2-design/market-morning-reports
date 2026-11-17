# Session C runtime continuity checkpoint (2026-11-17)

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
