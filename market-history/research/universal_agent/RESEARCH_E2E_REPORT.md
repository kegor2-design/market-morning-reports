# Session B real data E2E

## Session C continuation: original May Goal and autonomous reproductions

Original May 2018 Goal `research_21ae71a8bd77` resumed under its original Goal ID after an evidence-backed calendar DAG revision. The reviewed 22 observation dates exclude the full closure on 2018-05-28. Three revalidation jobs used the identical sealed Treasury/NY Fed source hashes with zero additional network calls. The predeclared positive-spread hypothesis had validation accuracy 3/9 (33.3%) versus the no-increase baseline 6/9 (66.7%): `REJECTED_EXPLORATORY`. The result was independently recomputed from the revised source jobs and matched exactly.

Independent May 2019 and July 2018 Goals reproduced holiday gaps and were automatically repaired by the Problem Solver on their second queue runs. May 2019 validation accuracy was 2/9 (22.2%) versus 7/9 (77.8%) baseline; July 2018 was 3/8 (37.5%) versus 5/8 (62.5%). Both hypotheses were rejected exploratorily. Each retained its original Goal ID, source hashes, and three-request budget. None of these new goals has a sealed independent holdout or historical row-level first-access evidence; official investment claims remain blocked.

Sources: official US Treasury archive (2Y and 10Y yields) and NY Fed reference rates (SOFR), 20 common weekdays from 2018-04-03 through 2018-04-30. Private recovery checkpoints retain content hashes and source records; raw source payloads are not committed.

The first 10Y minus 2Y spread was 0.51 percentage points and the last was 0.46. SOFR moved from 1.83% to 1.77%. The predeclared exploratory hypothesis was that a positive spread predicts a next day SOFR increase. Training accuracy was 3/12 (25%) versus a no increase baseline of 9/12 (75%). Validation accuracy was 3/7 (42.9%) versus a no increase baseline of 4/7 (57.1%). The hypothesis was **rejected in this exploratory window**.

An independent calculation read the three recovery source record sets directly and recomputed the seven validation pairs: three correct, three actual increases, matching the report. This is a calculation check over the same sources, not an independent market holdout. Historical row level PIT and a sealed market holdout are absent. The outcome is `EXPLORATORY_ONLY`; no predictive or investment performance is claimed.

Indicator 116 remained PIT blocked: historical actual publication and first access times and a full revision sequence remain unavailable. Its blocked result is separate from the US rates analysis.

## 2026-11-17 independent holdout and new research type

Before fetching new evaluation data, a private manifest fixed the positive 10Y minus 2Y spread rule, next-day SOFR direction target, 2018-05-01 to 2018-05-25 period, accuracy and always-no-increase baseline, no tuning, and the prior April report hash. Its SHA-256 is `e750f4b45aa7d4522deb1878472fab80b51c0019b0a8eec4dbca791e7fc75912`. The May program collected official Treasury and NY Fed records for 19 common weekdays. Independent holdout evaluation found 6/18 correct (33.3%) versus 12/18 (66.7%) for the baseline; the rule was rejected. The Wilson 95% interval for rule accuracy was approximately 16.3% to 56.3%. This is a distinct temporal market holdout, with PIT still unverified; no investment prediction claim follows.

The separate Korean crash goal used the existing Regime190 hash-checked Naver Finance KOSPI/KOSDAQ snapshot, restricted to 2010-01-01 through 2025-12-31. Six KOSPI days met a prespecified close-to-close decline of at least 5%; 3,872 non-crash windows were controls. Median volatility over the 20 preceding returns was 2.073% for crash days versus 0.840% for controls. A separate raw-CSV recomputation matched the event count and medians. The source has unresolved provider mismatches, no official KRX validation, no PIT evidence, and only six events. This is descriptive exploratory evidence, not a validated warning signal or backtest.

Indicator 116 alone remained `RESEARCH_BLOCKED`. Under an explicitly approved independent research request, its blocked parent kept a separate Goal ID while the US rates child completed exploratory work under its own Goal Contract. The unsupported Bitcoin options goal persisted `RESEARCH_UNSUPPORTED` with zero data or model calls.
