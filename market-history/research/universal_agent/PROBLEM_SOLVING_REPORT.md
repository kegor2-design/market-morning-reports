# Session C problem solving checkpoint

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
