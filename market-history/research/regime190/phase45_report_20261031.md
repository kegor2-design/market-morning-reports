# Universal Research Agent Phase 4/5 execution audit

## Baseline and scope

The starting local and fetched remote research HEAD were both
`ef469eee22edb834c1e7119b6364faf3d686b425` on
`research/regime190-data-audit-20261027`. An unrelated untracked
`regime190/phase2_baseline.py` was preserved. The Phase 2 engine, Phase 3
Runner CLI, old Regime190 runner manifest and private checkpoints were not
reset. Existing tests passed: 22 common-engine tests and five Regime190 tests
using `/home/kegor2/stock_env/bin/python`, which already contains pandas.

## Implementation and bounded execution

`universal_agent/supervisor.py` adds a version 3 checkpoint and project
registry above the existing Runner. It uses the Phase 3 Codex adapter and
Phase 2 evidence checks. Task transitions are validated; only independent
evidence gates can complete a task. A RUNNING task found after a crash becomes
PAUSED with an uncertain outcome. VERIFYING can be independently rechecked.
Explicit recovery is required to retry PAUSED work. The supervisor stores run,
execution and idempotency identifiers, rationale, dependencies, attempts,
results, evidence, provenance, budgets and next task. Checkpoints use atomic
replace, file and directory fsync, and a project lock. CLI modes are inspect,
register, plan, dry-run, run-once, run-bounded, resume, status, report, stop
and explicit recover. Inactive systemd and cron examples are included.

The real isolated `/tmp` integration run selected two dependent Codex tasks,
called `codex-cli 0.166.0` twice with `--sandbox read-only --json --ephemeral`,
independently checked the fixture after each call, and recorded both tasks
COMPLETED. Its explicitly checked fixture criterion returned
RESEARCH_COMPLETED. Resume made no additional Codex call. This is a test
project result, not a Regime190 research completion claim.

Regime190 was run separately with a 30-minute, three-task, one-concurrent-task,
one-Codex-call cap; the run used two tasks and one Codex call. The initial
probe completed after independent checks on the price manifest and three
read-only source DB samples. The next Codex task returned a structured
read-only investigation, but its independent source-lineage review gate
failed. It is BLOCKED_DATA; market-membership and PIT tasks remain
BLOCKED_DEPENDENCY. Resume left all attempts unchanged (1, 1, 0, 0). The
research outcome is RESEARCH_BLOCKED. No PIT-dependent backtest was run.

## Price-history evidence

The checked private manifest lists 2,497 distinct symbol files and 4,605,978
rows. All files exist and match their recorded byte counts. Exactly 1,794
symbols end on 2026-09-15. The market field is missing for 4,488,363 rows.
The dedicated read-only DB role found `000040` and `000050` ending on
2026-09-15 (3,687 rows each), while `000020` extends to 2026-10-13 (3,696
rows). These three source dates match the manifest. The source table has
`collected_at` and `source_name` columns, but the current three-symbol sample
does not establish the full cohort's ingestion boundary or its cause.

The Codex response noted that the derivation query has no explicit 2026-09-15
cutoff, while cached symbol lists and completed exports can be reused. This is
an **inference and competing explanation**, not proof that exports were stale.
Provider/ingestion interruption, export selection and individual
suspensions/delistings remain UNVERIFIED. Historical market membership,
actual release times and vintage history remain unverified. The prior
190-indicator snapshot remains 71 partial, 21 raw-only, 98 unacquired, zero
PIT validated and zero backtest eligible. A service start or a model answer
does not alter these counts.

## Tests and gates

| Check | Result |
| --- | --- |
| Existing and new universal-agent tests | 34 passed |
| Regime190 tests in existing stock_env | 6 passed |
| Python compile and `git diff --check` | Passed |
| Isolated real Codex two-task loop | Passed, two independently verified tasks |
| Regime190 read-only bounded loop | One task completed; causal task BLOCKED_DATA |
| Crash, lock, retry, checkpoint, approval, stop/recovery injections | Passed in unit tests |
| Source DB full cohort and ingestion log reconciliation | Not tested; next research step |
| PIT/backtest gate | Blocked; zero eligible indicators |

| Readiness label | Result | Evidence or reason |
| --- | --- | --- |
| ENGINE_IMPLEMENTED | PASS | Registry, state machine, budgets and 34 common tests |
| RUNNER_VERIFIED | PASS | Real Codex calls plus independent fixture and Regime190 evidence checks |
| SUPERVISOR_VERIFIED | PASS | Two-task real Codex loop, dependency order and status transitions |
| RECOVERY_VERIFIED | PASS | Injected RUNNING/VERIFYING crashes and actual no-duplicate resume |
| RESEARCH_LOOP_VERIFIED | PASS | Regime190 profile verified, follow-up Codex task selected and correctly blocked |
| AUTONOMOUS_OPERATION_READY | BLOCKED | Full source-lineage, historical membership and PIT gates remain open |
| PERSISTENT_SERVICE_DEPLOYED | NOT_TESTED | No service or scheduler was installed or activated |

## Safety and next work

Only research repository files and a private supervisor checkpoint/registry
were written. The operating MyDream2000 and MarketMorningPublisher code trees
already contain unrelated local modifications; this work did not edit them.
The operating DB was queried using its existing read-only role and 20-second
statement timeout. No operating DB schema or data writes, service restarts,
orders, data deletion, large backfills or credential changes occurred.
`systemctl --user status` cannot connect to this environment's user bus, so
service state is not independently established here. The Codex rules file
ends with the same verified SHA256 as before this phase,
`1c9991c37e36731ea3ebcdb901764f26dc8569b3cf324b865dfd89f7ac679b55`;
temporary approval rules added during tests were removed. No `.env` content
was copied into the repository.

The next safe task is a bounded read-only reconciliation of the entire cutoff
cohort against source DB post-2026-09-15 rows, `source_name`, `collected_at`,
ingestion batch logs and provider responses, followed by historical listing
and delisting records. Then independently validate release/vintage and
availability timestamps for the 190 indicators. Large backfills, operating
changes, persistent service activation and a PIT-dependent backtest still
require their own gates or approval.

The initial live task records have source timestamps and manifest hashes but
precede the added per-task supervisor code-hash field. The checkpoint now
records the current supervisor code hash; later executions also record the
per-task hash. The first live execution's exact in-memory code hash cannot be
retrospectively certified from that checkpoint.

The private checkpoint is
`/home/kegor2/MyDream2000/research/universal_agent/regime190-phase45/state.json`.
The public machine-readable snapshot is `phase45_progress_20261031.json`.
Exact CLI, permission and recovery commands are in
`universal_agent/SUPERVISOR.md`. The private Phase 1 and Phase 3 checkpoints
remain in place.
