# Session C problem solving checkpoint

## Post-restart API failure evidence — 2026-11-18

The approved data recovery path now records whether an exception includes a definite HTTP response or has an uncertain transport outcome. It records the numeric HTTP status only when available, carries the problem type and call outcome through the Research Job conclusion into the Task record, and preserves the original network reservation. Local injected HTTP 503 and timeout tests confirmed both classifications and confirmed that a second call was not made. This change adds diagnosis and checkpoint evidence; it does not authorize or execute a new provider request. `AUTONOMOUS_API_RECOVERY_VERIFIED` remains BLOCKED until a separately reviewed retry Task with a new request identity and explicit budget is implemented and tested. No live provider call or AI Self Repair occurred in this iteration.

## Sealed-source schema recovery — 2026-11-18

New 2020-08-03 to 2020-08-28 Goal `research_471a35e13cfa` collected official NY Fed SOFR but blocked on both Treasury series because the 2020 archive CSV uses lowercase `date`, `2 yr`, `10 yr` columns and four-digit years. The host corrected the shared parser to accept both reviewed CSV layouts. On the next Queue run, `solve_schema_gap` checked the two original failed Research Jobs, request receipts, source hashes, exact parser failure and complete expected-date coverage. It appended two zero-network `DATA_SCHEMA_REVALIDATION` tasks, versioned the revision, reconnected the original `analyze_rates` task and resumed the same Goal ID. The old failed jobs and raw bytes remain. Original and revalidation Treasury SHA-256 both equal `25877e5541442e8c8c642a3cf9709d8c20eb2c1603556e3ebd84545f1f0acfe2`; the revision SHA-256 is `3eb4553f755e9416a7b171430c047e5a1b633101c6d53a31bec0864d09b53f46`. Network reservations remained 3, model calls 0, and a terminal rerun processed 0 tasks. The initial parser code fix was manual; evidence inspection, DAG repair, revalidation and Goal resumption were automatic.

An earlier 2020 Goal `research_6a662b98e720` correctly blocked after two Treasury 404s because the old URL targeted a nonexistent 2020-2029 archive. The adapter URI was manually corrected to the [official 2020-2023 archive](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives). That Goal retained its `BLOCKED_ENV` checkpoint: all three network request reservations were consumed, so it was not retried under an enlarged budget. This is an API failure classified and preserved, not autonomous API recovery. AI generated code repair and rollback were not executed.

## AI-planner continuation boundary — 2026-11-18

The new planner boundary rejected synthetic proposals that changed the original Goal, source registry, action or DAG dependency. A simulated model timeout and malformed JSON were each reserved once and then blocked from automatic replay. These are model-call safety tests, not new autonomous repair cases. Existing calendar recovery remains the only demonstrated automatic return to the original Goal. General API/schema fault repair and isolated AI Self Repair with rollback remain `BLOCKED`; no new production or research code was modified by a model.

## 2026-11-18 original Goal recovery

The original May 2018 Goal `research_21ae71a8bd77` is now `RESEARCH_COMPLETED_EXPLORATORY`. The original plan, blocked child jobs, source bytes, and Goal Contract remain in place. The host identified `2018-05-28` as the sole missing day in all three series, matched it to the reviewed full-closure calendar, and added three zero-network revalidation tasks in `calendar_revision_v1.json`. The analysis task was reconnected to those tasks and ran once. Queue projection initially failed because its old input hash rejected the versioned analysis dependency. The completed program was verified and reconciled without reexecuting a task; this queue projection correction was manual code repair. Network requests remained at three. The original pre-repair private queue is preserved as `.universal_private/session_c_rates_may2018_before_calendar_recovery`.

The same type of problem was then reproduced independently in May 2019 (`research_48fa238a75b9`, missing `2019-05-27`) and July 2018 (`research_c82cdf92d25e`, missing `2018-07-04`). On the second queue run, the existing Problem Solver entry point classified `CALENDAR_MISMATCH`, checked original source bytes and full-closure evidence, selected the reviewed zero-network action, revised the original DAG, verified the result, and resumed each original Goal. Both ended `COMPLETED_EXPLORATORY` with no additional provider or model calls. Terminal reruns processed zero jobs. The July checkpoint records all solver stages, selected action, revision hash, and rollback rule.

The calendar repair is limited to reviewed 2018 and 2019 SIFMA full closures. It does not repair arbitrary missing observations. A failed policy check leaves the original blocked jobs intact. No AI Self Repair was used; the generic multi-error solver and rollback fault experiment remain unverified.

| Problem | Evidence | Action | Result |
|---|---|---|---|
| Two queues with one Goal changed the same checkpoint hash | First detached queue failed integrity loading after a separate queue ran the same Goal | Put each program under its own queue directory; add a two-queue regression test | Verified by test; new detached queues keep separate checkpoints |
| Status could not be read during execution | `locked_state` rejected the status call while the worker held the lock | Read the atomically replaced JSON snapshot for status only | Verified by test |
| May 2018 rate analysis blocked | Three collection tasks reported `BLOCKED_EVIDENCE`; 23 weekday dates included a closure | Initially preserved blocked state and ran a separate June goal | Superseded by the original-Goal recovery above |
| Korean indicator 116 PIT absent | The detached queue returned `BLOCKED_EVIDENCE` | Preserve original Goal and source evidence checkpoint | No official claim |
| Unsupported A/C/D wording was classified as a generic queue failure | Program reports already said `RESEARCH_UNSUPPORTED` | Add explicit terminal `UNSUPPORTED` queue status and rerun each original goal | Three original contracts persisted with no executable tasks |

No AI Self Repair or code-generating model was used. No production branch or service changed.
