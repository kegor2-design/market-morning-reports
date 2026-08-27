# Release Notes — 1.6.5.7

## Scope
- Split public Blogger output into Morning Report and Pre-Market MI Scenario views.
- Keep Closing MI Review as the third linked record.
- Add a Short-Term Market Map alongside the existing long-term map.
- Preserve one-engine/multiple-renderer architecture so app and blog MI cannot drift.

## Publication principle
`MI Engine -> Frozen Scenario Object -> App Renderer + Blog MI Renderer`

The report view may summarize context but must not run a second MI inference.

## Short-term map
Adds five axes: FX/dollar, rates/bonds, credit, inflation/commodities, risk/liquidity. It uses short windows and point-in-time data freshness checks.
