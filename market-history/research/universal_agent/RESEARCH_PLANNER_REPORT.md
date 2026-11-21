# Session B research planner

## Reviewed acquisition proposal continuation — 2026-11-18

The candidate compiler now accepts an optional `DATA_ACQUISITION` Task for a reviewed US rate series. It creates the executable Task on the host using the existing `DATA_RECOVERY` Action, requires its matching discovery dependency, and requires the analysis Task to depend on the acquisition. The unchanged Goal ID, original text, market, period, three required series, source allowlist, PIT and holdout policy, and total budget remain host controlled. Unknown Task IDs and Actions still fail. The Capability Registry now exposes implemented task IDs, Action IDs, sources, input/output schema descriptors, resource limits and exploratory PIT status (registry version 2). A synthetic proposal was sealed into an approval-gated persistent queue; it was not authorized to make a source request. This is a further reviewed DAG composition option, not general arbitrary planning or AI-generated E2E.

The existing Codex CLI still lacks a demonstrated enforceable request-level monetary cap. OpenAI documents project hard spend limits but says enforcement may lag and spending may slightly exceed the configured amount; prepaid credit exhaustion is also delayed. See [project spend controls](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform) and [prepaid billing](https://help.openai.com/en/articles/8264644-setting-up-and-managing-prepaid-api-billing). The local approval gate now also rejects NaN, infinity and Boolean values in monetary, call and duration budgets before reservation. No account-specific limit or paid-call approval was verified, so real model calls remain blocked. Model Adapter, AI-generated planning, generic recovery and official PIT remain incomplete.

## Dynamic plan and host compiler — 2026-11-18

Starting at `de9af2fe6c2de3669dc1a00243752d1ac5a6670a`, the host compiler now permits two implemented US rate signals: positive 10Y-2Y spread and widening 10Y-2Y spread. It also permits a different acyclic dependency order among reviewed discovery tasks. For the same original Goal, both proposals pass with distinct plan hashes, hypotheses and DAGs. The original Goal ID/text, market, period, required series, approved sources/actions, zero-model execution budget, PIT and holdout policy remain host controlled. The revised executable Goal Contract is sealed as version 2; version 1 checkpoints are still accepted. Unknown source/action, missing dependency, cycle and unimplemented hypothesis are rejected. A synthetic widening-spread proposal entered the existing persistent Queue and ran approved tasks. These results prove flexible host validation and execution of a synthetic proposal, not AI generation.

The available production Codex CLI still has no enforceable request-level dollar ceiling and no paid planning call was made. [OpenAI's project spend controls](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform) can enforce a hard monthly limit when configured by an owner, but enforcement is not instantaneous and recorded spend can exceed that limit slightly; [prepaid balance exhaustion](https://help.openai.com/en/articles/8264644-setting-up-and-managing-prepaid-api-billing) also has processing delay. Neither account configuration nor an explicit paid-call approval was available to this research worker. Real AI plan generation remains `BLOCKED`.

## Session C AI planner boundary — 2026-11-18

Starting from `8aa7af567124ec27e5ac7afb1d18467796ffa822`, the new `ai_research_planner.py` validates a structured model candidate against `ai_program_candidate.schema.json` and the independently generated, reviewed Research Program. The candidate must preserve the exact Goal ID/text, market, hypothesis, data requirements, approved sources, evaluation methods, and task DAG. A different source, action, dependency or PIT assertion is rejected before execution. The legacy `research_plan.schema.json` describes a hypothesis plan and remains unchanged; the executable `research_program.schema.json` remains the supervisor contract.

`research_runtime.submit` now accepts a candidate, records its hash in the persistent queue, and passes it to `run_research_program`. The supervisor revalidates and seals it before selecting tasks. A synthetic candidate for a June 2018 rates Goal entered the queue and completed the first reviewed discovery task with zero model calls and zero network requests. Synthetic candidates for rates, Korean crash and indicator 116 yielded three different reviewed DAGs; unsupported arbitrary goals remain unsupported. These tests establish the host boundary and queue handoff only. The model did not generate those candidates.

`request_plan` records prompt/schema hashes, request ID, one-call budget and finite duration before a test-provider call. A timeout or malformed response is recorded and never replayed automatically. The available isolated Codex CLI has no enforceable per-call dollar ceiling, so the production caller returns `BLOCKED_COST_ENFORCEMENT` before a paid call even when an amount is merely declared. No real model invocation occurred. `AI_PLAN_GENERATION_VERIFIED`, general dynamic planning and actual AI-to-DAG E2E therefore remain `BLOCKED`. A reviewed model adapter with enforceable spending limit and explicit cost approval is required before those gates can pass.

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
# Recovery reliability continuation — 2026-11-18

The reviewed dynamic Planner and existing Capability Registry were unchanged in the earlier recovery reliability step. The API Recovery Task carries a sealed transaction journal and bounded Retry-After schedule into the persistent queue. Local fixture approval is the only executable API recovery scope. No external Provider approval contract, enforceable paid-model cost ceiling, actual model-generated plan, or AI-generated code patch was established. Model calls in that step: **0**.

The 2026-11-19 continuation added a narrowly reviewed `ISOLATED_CODE_FIXTURE` plan and `CODE_REPAIR_TASK` capability. A host-approved candidate completed the fixture DAG through the persistent Queue. This does not expand the supported real-market research plan set. The Codex CLI still lacks a verified enforceable per-call monetary ceiling, so actual AI plan generation and AI-generated patch calls remain blocked; calls made here: **0**.

An external Provider recovery approval schema was also added as a policy-only validator. It does not authorize runtime execution or change the model cost gate.

## 2026-11-19 model boundary review

The installed Codex executable and its local authentication/configuration files exist; their contents were not copied to the research Worktree or reports. `isolated_codex.py` reserves a call before its external side effect, bounds time and output Schema, and runs under Bubblewrap. `ai_research_planner.request_plan` accepts only a separately supplied one-call cost contract and currently allows actual execution only through an injected test Provider. Its production Codex route explicitly returns `BLOCKED_COST_ENFORCEMENT` because the available CLI path has no reviewed enforceable per-call monetary ceiling. A declared dollar estimate is insufficient. No real planner or repair model call was made in this continuation; model-generated plan and patch gates remain BLOCKED.

New `AttributeError` and `TypeError` fixture Goals demonstrate Problem Solver and DAG repair reuse for different Python exception evidence, but their patches were host-supplied. The executable planner still supports only reviewed Capability Registry actions and cannot turn arbitrary new market goals into a validated DAG. No live external Provider request, official PIT acquisition or new market holdout was authorized here.

## 2026-11-21 model boundary
The planner and the repair proposer share a one-call, exclusive reservation, bounded timeout, validated response digest and 64 KB output-file limit. Repair additionally binds the approved purpose, failed source SHA, original Goal and fixed isolated file. Returning a proposal gives no permission to apply it. Tests exercise injected providers, schema failure, timeout, authentication failure, replay, invalid plans and a mock repair. Run `PYTHONPATH=market-history/research /home/kegor2/stock_env/bin/python -m unittest universal_agent.tests.test_ai_research_planner`. 17 tests passed. Real calls and real model-generated patches were both zero. Candidate bytes are distinct from provider output-token limits. Model charges authorized for this Goal are zero.

OpenAI documents project model restrictions, rate limits, spend alerts and optional enforced limits. Enforcement can lag recorded spending. No evidence of a dedicated project, enabled enforcement, authorized model, per-request output-token cap or accepted overrun was supplied. The live CLI path therefore blocks before reservation. [Provider project controls](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform)
