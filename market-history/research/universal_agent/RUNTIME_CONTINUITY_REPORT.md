# Session C runtime continuity checkpoint (2026-11-17)

The research runtime now stores an approved Goal queue under `.universal_private`, using the existing Research Program DAG and Research Job Supervisor for execution. Queue writes use `engine.write_state` (temporary file, fsync, atomic replace, directory fsync) and `locked_state` (exclusive flock). Each queue owns a separate program checkpoint tree. Terminal queue entries seal program and task artifact hashes. Unapproved and terminal jobs are never selected; launches are bounded to two per goal.

## Observed detached execution

- Queue: `.universal_private/session_c_disconnect_2/state.json`; goal `research_248bf5aefcbf`.
- The launch command returned PID 2733894 before the three-second startup delay ended. A separate command later observed `PENDING -> RUNNING -> BLOCKED_EVIDENCE` at 14:34:45–46 UTC. PIT evidence was absent, so no success claim was made.
- Queue: `.universal_private/session_c_rates_june2018/state.json`; goal `research_162ab26e5092`.
- The launch command returned PID 2734274 before work began. A separate command observed `PENDING -> RUNNING -> COMPLETED_EXPLORATORY` at 14:37:37–42 UTC. The program stored three source collection checkpoints and one analysis checkpoint.
- Reopening a terminal queue processed zero jobs. Dedicated tests also checked approval blocking, isolated checkpoints for equal goals in two queues, plan change rejection, output hash verification, and status reads while a worker holds the lock.

This verifies detached process survival after the launching shell exited. An actual SSH disconnect and reconnect was not performed. No service, linger setting, cron entry, or boot-time scheduler was changed. The runtime stops when its bounded queue is drained; it is not a continuously installed daemon. Worker and Supervisor SIGKILL recovery had passed in Session B and passed again in the Session C regression. Network failure, disk failure, and model-unavailable injection into this new queue remain unverified.

`AUTONOMOUS_RUNTIME_CONTINUITY=PARTIAL`: bounded, already submitted jobs can continue independently; persistent service activation and all P0 fault gates are not yet verified.
