# Recovery and isolation evidence — 2026-11-14

The first direct official-source request encountered a sandbox DNS failure. The checkpoint recorded a source-unavailable problem and a bounded next action. A separate approved network task fetched the official archive successfully. A simulated interruption after the network-call reservation is refused on resume with `BLOCKED_UNCERTAIN_API_CALL`. An existing terminal Research Job was invoked again and remained at one Worker attempt.

A real-value mismatch (`187` against `1.87`) was detected and retained as evidence; the agent did not silently divide by 100. The next action is `REVIEW_UNIT_DATE_AND_REVISION`. The existing indicator 116 evidence workflow again selected an independent synthetic fixture after PIT remained blocked; that fixture is not market validation.

Two additional live process probes used the reviewed Treasury archive. After a sealed result was written, killing the Worker produced one recorded crash and the Supervisor verified the existing artifact with one Worker attempt. Killing the Supervisor at the same point and restarting it also verified the existing artifact with one Worker attempt and one official request. Both recovered the same source SHA-256 `a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254`. The private probe drivers are ignored artifacts, not repository code.

Isolation probe: user `kegor2`, no effective capabilities, kernel unprivileged-user-namespace setting `1`, seccomp mode `2`, enforced AppArmor profile `bwrap//&unpriv_bwrap`. Bubblewrap returned exit 1: it could not create a new namespace. The existing safe runner was not weakened. A new real code patch and bad-patch rollback trial were not executed and are `BLOCKED_ENV`. Existing regression coverage does not substitute for this live trial.

No operating service, scheduler, strategy, DB schema or data, API secret, or security setting was modified. Its network call checkpoint is intentionally conservative: an interrupted call without a sealed response is blocked until reviewed. Process interruption before a source response is sealed was covered by uncertain-call injection, not by a live network kill.

## Follow-up isolation and real repair — 2026-11-14

The earlier Bubblewrap failure was specific to the tool sandbox's enforced `bwrap//&unpriv_bwrap` AppArmor profile. The same `probe_secure_runner()` under approved ordinary-user execution reported `unconfined`, seccomp `0`, no effective capabilities, home hidden, separate network namespace, exit `0`, and `SECURE_RUNNER_VERIFIED`. No security control was changed.

An existing verified real-model research source was copied into private worktree state. `fault_trial --live-repair` injected `math.no_such_log`, classified its actual isolated traceback as `CODE_ERROR`, made one new model repair call, and ran the corrected source in Bubblewrap. Generated repair SHA-256: `f54a06399cf30637f13a80b639a82778552d6d9e0bc13d428eb5cd0f8387458d`; verified response SHA-256: `ff419df1afc8d5a73e043114c531565f7d24281e180ac67b136019f370c6b672`. Integrated fault evidence SHA-256: `d5be97febf0972834743afefc4eb4eb1b281aaa91d4590b2f311d751ff6bcf3d`. The isolated code/output contract passed. The research hypothesis itself was `REJECTED_EXPLORATORY`; PIT and independent holdout remain unverified.

A separate Bubblewrap test ran an invalid research patch candidate. Validation failed, `repair_research_source` recorded `ROLLED_BACK`, restored the original source byte-for-byte, and removed candidate output. The first test draft hit `REJECTED_STATIC`; after correcting the sample to satisfy the static contract, the actual execution and rollback test passed. Both trials stayed in temporary/private research paths.
