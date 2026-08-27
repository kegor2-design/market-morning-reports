# Release Notes 1.6.5.6

## Added
- Official Forward Calendar source contract and coverage health.
- 2026-08-27 verified bootstrap seed for core upcoming events.
- Calendar impact level/score/badge and impacted-asset explanation.
- Conditional post-decision scenario tree for FOMC/BOK/CPI/PCE/NFP/Treasury/Election/Regulation.
- Scenario probabilities are null unless supplied by point-in-time `OUR_MI`.
- Post-event `matched_scenario_id` and scenario review.
- Official validator registry entries for BLS, BEA, ECB and BOJ.

## Guardrails
- Impact score is market reach, not prediction probability or forecast accuracy.
- Expert/rumor views cannot provide OUR_MI scenario probabilities.
- Official seed is bootstrap-only and must be reconciled with live official collectors.
- Required forward-calendar source with zero future events is a coverage FAIL.
