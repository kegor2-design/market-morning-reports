# Short-Term Market Map 1.6.5.7

## Goal
Provide a 1-day to 20-day market-state map that complements, rather than replaces, the existing long-term market map.

## Five axes
1. Dollar / FX pressure
2. Rates / sovereign bonds
3. Corporate credit stress
4. Inflation / commodities
5. Risk appetite / liquidity

The map is a **state/pressure indicator**, not a return forecast or probability of profit.

## Minimum useful inputs
- DXY, USD/KRW
- US 2Y/10Y and KR 3Y/10Y yields
- US HY OAS and KR AA- corporate spread when available
- CPI surprise / core inflation trend
- Gold, WTI
- BTC, VIX, NASDAQ/SOX
- KOSPI foreign net flow

## Windows
Use 1D, 5D, 20D movement and optional 60D z-score. For low-frequency releases such as CPI, use the latest release surprise/trend and mark its age explicitly.

## Guardrails
- Stale data is excluded, not treated as neutral.
- Gold/oil are contextual signals.
- BTC is only a supporting risk/liquidity indicator.
- A strong composite score must not override active-event risk or MI invalidation rules.
