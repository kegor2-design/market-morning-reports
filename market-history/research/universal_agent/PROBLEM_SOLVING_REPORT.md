# Session C problem solving checkpoint

| Problem | Evidence | Action | Result |
|---|---|---|---|
| Two queues with one Goal changed the same checkpoint hash | First detached queue failed integrity loading after a separate queue ran the same Goal | Put each program under its own queue directory; add a two-queue regression test | Verified by test; new detached queues keep separate checkpoints |
| Status could not be read during execution | `locked_state` rejected the status call while the worker held the lock | Read the atomically replaced JSON snapshot for status only | Verified by test |
| May 2018 rate analysis blocked | Three collection tasks reported `BLOCKED_EVIDENCE`; 23 weekday dates included a closure | Preserve blocked state and run a separate predeclared June goal | June goal completed exploratory; May goal remains blocked |
| Korean indicator 116 PIT absent | The detached queue returned `BLOCKED_EVIDENCE` | Preserve original Goal and source evidence checkpoint | No official claim |
| Unsupported A/C/D wording was classified as a generic queue failure | Program reports already said `RESEARCH_UNSUPPORTED` | Add explicit terminal `UNSUPPORTED` queue status and rerun each original goal | Three original contracts persisted with no executable tasks |

No AI Self Repair or code-generating model was used. No production branch or service changed. The calendar issue needs evidence-backed market-day handling before the May task is reopened; it must not be silently marked complete.
