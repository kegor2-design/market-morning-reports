# Session B research planner

## Session C continuation (2026-11-18)

The host planner now accepts one versioned `DATA_CALENDAR_REVALIDATION` task type for an already blocked, reviewed US rates Goal. The Task DAG revision is evidence-gated, adds no network or model budget, retains original blocked tasks and the sealed Goal Contract, and records changed dependencies and the calendar revision hash. This is deterministic Problem Solver replanning, not an AI-generated research plan. The existing isolated Codex model path and secure runner were inspected; no new paid model invocation was authorized or made in this continuation. The AI Research Planner gate remains `BLOCKED`.

The original Session B branch started at `497782dff9fe911ff9e1c4ff727aec3423d259bf`; this follow-up starts at `ef87bb9028cee2d33f181132fd8a615f01c2c16d`. Existing Research Job, data recovery, Problem Solver evidence collection, process supervisor, and private checkpoints are reused. The rule based planner initially accepted reviewed US rates research and indicator 116 PIT context. It uses zero model calls.

The host validates the JSON Schema, task identities, DAG acyclicity, source list, actions, task budgets, and read only policy. For the US rates goal, it created three discovery tasks and one analysis task. The supervisor added three collection tasks when discovery found missing data. The fixed window is 2018-04-03 through 2018-04-30; the default and the lack of a sealed independent market holdout are recorded in the plan. A Korean indicator 116 goal adds a separate PIT task and independent US rates work.

Support remains narrow: arbitrary markets, periods, hypotheses, and model generated plans are not implemented. No official investment claim is authorized.

## 2026-11-17 completion follow-up

Goal Contracts are now sealed separately in each private program directory. The original goal, market, target, hypotheses, data and source requirements, allowed actions, evaluation, PIT and holdout policy, budgets, terminal conditions, and explicitly approved independent Goal IDs are compared against the plan on every resume. An unsupported goal receives its own `RESEARCH_UNSUPPORTED` checkpoint with zero calls.

The four tested goals now produce distinct contracts and DAGs:

| Goal | Goal ID | Tasks | Outcome |
|---|---|---|---|
| Indicator 116 PIT only | `research_248bf5aefcbf` | PIT evidence | `RESEARCH_BLOCKED` |
| US rates, explicit 2018-05-01 to 2018-05-25 | `research_f7aefaaf731e` | three discovery, three inserted acquisition, rate analysis | `RESEARCH_COMPLETED_EXPLORATORY` |
| Korean crash and prior volatility | `research_3185eccfc4c8` | hashed index validation, crash-window analysis | `RESEARCH_COMPLETED_EXPLORATORY` |
| Bitcoin options/on-chain volume | `research_7b94691cb148` | none | `RESEARCH_UNSUPPORTED` |

An explicit Korean PIT block plus independent US rates request creates parent `research_1cd527aaf330` and child `research_83885459d618` with separate contracts and statuses. The parent remains blocked when the child completes exploratory research. A Korean-only goal never creates US rates work. ISO date windows are honored within the reviewed Treasury/SOFR range; unsupported or ambiguous dates fail closed. The AI planner is still unavailable: this is a reviewed rule-based planner with zero model calls. General open-ended planning remains blocked.
