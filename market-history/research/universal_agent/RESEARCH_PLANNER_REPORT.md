# Session B research planner

The isolated branch starts at `497782dff9fe911ff9e1c4ff727aec3423d259bf`. Existing Research Job, data recovery, Problem Solver evidence collection, process supervisor, and private checkpoints are reused. The rule based planner accepts reviewed US rates research and indicator 116 PIT context. Other goals fail closed. It uses zero model calls.

The host validates the JSON Schema, task identities, DAG acyclicity, source list, actions, task budgets, and read only policy. For the US rates goal, it created three discovery tasks and one analysis task. The supervisor added three collection tasks when discovery found missing data. The fixed window is 2018-04-03 through 2018-04-30; the default and the lack of a sealed independent market holdout are recorded in the plan. A Korean indicator 116 goal adds a separate PIT task and independent US rates work.

Support remains narrow: arbitrary markets, periods, hypotheses, and model generated plans are not implemented. No official investment claim is authorized.
