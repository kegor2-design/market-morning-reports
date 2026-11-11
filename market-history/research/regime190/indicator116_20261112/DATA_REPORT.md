# Indicator 116 DATA_REPORT — 2026-11-12 KST

Base: `research/universal-agent-e2e-20261112`, SHA `21f3bf65fa216ad323b3a4aa0d3b9f021a3554b5`. This work used the isolated `research/regime190-indicator116-pit-20261112` worktree. No agent or operating code was changed. Raw data and keys remain in ignored private directories.

## Definition and provenance

Regime190 indicator 116 is the U.S. nominal 2-year and 10-year Treasury constant-maturity yield pair, with a candidate spread `DGS10 − DGS2` in percentage points. The existing mapping in `worker.py` uses FRED `DGS2` and `DGS10`. Both FRED series identify the Federal Reserve Board's [H.15 release](https://www.federalreserve.gov/releases/h15/) as their source and are labeled [Public Domain: Citation Requested](https://fred.stlouisfed.org/series/DGS2), [DGS10](https://fred.stlouisfed.org/series/DGS10). Raw responses are not redistributed here.

## Actual source audit

| Check | DGS2 | DGS10 | Verdict |
| --- | ---: | ---: | --- |
| Existing annual `output_type=4` windows, 2010–2026 | 17 | 17 | PASS: all file byte lengths, row counts, SHA-256, series IDs, and years match private manifests |
| Rows / distinct observation dates | 4,387 / 4,387 | 4,387 / 4,387 | PASS: no duplicate observation dates |
| Numeric / missing `.` / invalid numeric | 4,204 / 183 / 0 | 4,205 / 182 / 0 | PASS for parsing; missing values retained as missing |
| Vintage date before observation date | 0 | 0 | PASS for date ordering, not publication-hour proof |

There are **4,204** dates with both numeric yields, from 2010-01-04 to 2026-10-26. One asymmetric missing observation is 2013-01-31: DGS2 is missing while DGS10 is present. No value was imputed. Independent `Decimal` subtraction over paired dates gave a candidate spread range of −1.08 to 2.91 percentage points; for 2020-01-06 it was 1.81 − 1.54 = 0.27. This arithmetic validates the calculation only, not PIT eligibility or predictive performance. Full audit metadata: ignored `.universal_private/indicator116_audit.json`.

The annual snapshots were originally retrieved on 2026-11-10; a fresh bounded FRED API probe made **two** requests for 2020-01-01 through 2020-01-31 using the documented [`output_type=4` initial-release format](https://fred.stlouisfed.org/docs/api/fred/series_observations.html). Both returned HTTP 200, 23 rows, 21 numeric paired observations and two missing dates. New private raw SHA-256: DGS2 `331c9226620b4820e80f591653daa263e6c6649d09642bad2d0eb419749ac9a0`; DGS10 `323dcb811acc045d8180bbd271043957d93e4098a66a177aa68d7d332069535a`. The 23 `date/value/realtime_start` triples for each series match the earlier independent 2026-11-01 sample and the 2020 annual files. Other response metadata differ because query windows differ.

An independently fetched [U.S. Treasury January 2020 daily par-yield table](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value=202001&type=daily_treasury_yield_curve) returned 21 rows. On all 21 matching dates, its `2 Yr` and `10 Yr` numeric values equal the corresponding FRED sample; mismatches: **0**. Private Treasury CSV SHA-256: `7309a0c4d2f13d870cf0381f1f819f026acbe608e79cf0420c735dfc78b49ce1`. This is a bounded source cross-check, not a full-period revision or timing audit. Treasury notes a yield-curve methodology change on 2021-12-06, so its full-history use also needs definition review.

The earlier broad `output_type=4` request recorded HTTP 400 for both series in the existing research checkpoint. Its exact provider rejection reason was not retained; no root cause is claimed. The bounded monthly request returned 200, and annual private windows already exist. The initial sandboxed live request failed with `ConnectionError`; the authorized network retry succeeded. Neither failure was silently counted as an acquired source.

**DATA_STATUS=ACQUIRED_FOR_RESEARCH; PIT_STATUS=BLOCKED.** The period-wide numeric audit and one-month independent comparison are complete. Historical intraday availability, source revisions, and Korean exchange-day alignment remain open.
