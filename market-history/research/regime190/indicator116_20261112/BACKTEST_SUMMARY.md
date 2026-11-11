# Indicator 116 BACKTEST_SUMMARY — 2026-11-12 KST

**Status: NOT_RUN_PIT_GATE (BLOCKED).** The Regime190 PIT gate has zero eligible indicators. The DGS2/DGS10 date-level first-release snapshots and the 21-day Treasury comparison do not establish intraday source availability, historical revisions, Korean trading-calendar alignment, or an untouched independent holdout. The existing 2010–2026 rates are research inputs only.

No official strategy return, transaction-cost result, slippage estimate, walk-forward performance, or holdout metric was computed or approved for indicator 116. The independently checked arithmetic spread of 0.27 percentage points for 2020-01-06 is a **data calculation**, not a backtest result. A backtest may run only after the PIT and holdout requirements in [PIT_REPORT.md](PIT_REPORT.md) are met.

## Follow-up gate result

**BLOCKED; official backtest skipped.** The new row-level matrix has 4,204/4,204 strict PIT rows blocked. The existing `pit_eligibility()` returns zero eligible indicators, including 116. The seven-day-lag/Naver-session column is an exploratory as-of sensitivity only and was not passed to the official backtest. [The predeclared future target and holdout protocol](HOLDOUT_PROTOCOL.md) has no mature, sealed outcomes. No profitability, costs, slippage, walk-forward, or independent holdout performance is claimed.
