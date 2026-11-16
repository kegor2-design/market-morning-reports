# Session B real data E2E

Sources: official US Treasury archive (2Y and 10Y yields) and NY Fed reference rates (SOFR), 20 common weekdays from 2018-04-03 through 2018-04-30. Private recovery checkpoints retain content hashes and source records; raw source payloads are not committed.

The first 10Y minus 2Y spread was 0.51 percentage points and the last was 0.46. SOFR moved from 1.83% to 1.77%. The predeclared exploratory hypothesis was that a positive spread predicts a next day SOFR increase. Training accuracy was 3/12 (25%) versus a no increase baseline of 9/12 (75%). Validation accuracy was 3/7 (42.9%) versus a no increase baseline of 4/7 (57.1%). The hypothesis was **rejected in this exploratory window**.

An independent calculation read the three recovery source record sets directly and recomputed the seven validation pairs: three correct, three actual increases, matching the report. This is a calculation check over the same sources, not an independent market holdout. Historical row level PIT and a sealed market holdout are absent. The outcome is `EXPLORATORY_ONLY`; no predictive or investment performance is claimed.

Indicator 116 remained PIT blocked: historical actual publication and first access times and a full revision sequence remain unavailable. Its blocked result is separate from the US rates analysis.
