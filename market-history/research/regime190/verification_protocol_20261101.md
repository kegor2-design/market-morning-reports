# Regime190 evidence and evaluation protocol

Status: **PREPARED**, not PIT approved or historically backtested.

## Calculation verification queue

The existing `derive_more.py` and private series are retained. A calculation
task may run only against a checksum-recorded, dated source series with a fixed
market and definition. Each task must save input hash, parameters, code commit,
output hash, row count, first valid date and an independent reference comparison.
Warm-up rows remain missing. A calculated value from day *t* can first be used
at the next verified decision timestamp after publication, never by assumption.

| Indicator IDs | Calculation | Independent check still needed |
| --- | --- | --- |
| 1 | SMA 5/10/20/60/120/200 | Rolling mean versus independent implementation; split-adjustment convention |
| 2 | EMA | Seed and `adjust` convention versus a published reference |
| 13 | MACD, signal, histogram | EMA windows, seed, histogram sign |
| 14 | RSI and divergence | Wilder smoothing, zero-loss cases, divergence definition |
| 29 | ATR and NATR | True range, smoothing and denominator convention |
| 36 | Realized volatility 5/20/60 | Return type, annualization and missing sessions |
| 40 | Drawdown speed and recovery | Peak convention, rolling window and recovery event definition |
| 28 | Bollinger %B and bandwidth | Standard deviation convention and zero-width bands |

No item in this queue inherits PIT approval from calculation success.

## PIT gate and backtest design

Per observation, require a source identifier, observation date, publication
timestamp with timezone, decision timestamp, available revision or vintage,
as-of market membership including delisted securities, corporate-action policy
for security prices, source rights, and reproducible calculation lineage. A
missing field blocks the affected indicator. The 2026-11-01 inventory has zero
approved indicators, so historical evaluation remains `BACKTEST_BLOCKED`.

Once every feature and outcome used by a specific test passes its own gate,
freeze the eligible feature list and chronological train/validation/test dates.
Fit thresholds only on past windows. Use expanding or rolling walk-forward
splits with an embargo at least as long as the outcome horizon. Record crash
warning and recovery precision/recall, false rebound frequency, regime
transition delay, forward-return distributions and maximum drawdown, including
event definitions, sample counts and confidence intervals. Compare against a
no-signal baseline. Do not infer performance from an empty or blocked run.

## Resume

The development queue is separate from the existing 02:15 worker. Run from
`market-history/research` with `/home/kegor2/stock_env/bin/python -m universal_agent.offline_worker`
and `--state-dir ~/MyDream2000/research/universal_agent/regime190-evidence-discovery-final`
plus `--repo ~/market-morning-reports`. Use `status` to inspect, `run --max-tasks 5
--max-seconds 120` to resume. A new plan needs a new state directory; the
existing queue deliberately rejects plan replacement.
