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

## Follow-up audit on `research/regime190-ind116-asof-20261112`

Base remote SHA: `4242f72347ed08bc0c3e54cc437c0be8e2e4c093`. The read-only `build_asof_matrix.py` rechecked every manifest, byte count, SHA-256, series ID, year, `output_type=4`, date uniqueness, and date ordering. All **34** annual inputs passed; the **4,204** paired numeric dates are unchanged. No missing value was filled. The raw annual files remain outside Git.

An additional comparison with the existing 2026-10-27 FRED snapshots (4,386 overlapping rows per series) found **2** differing DGS2 dates (`2013-01-31`, `2020-08-19`) and **4** differing DGS10 dates (`2014-01-14`, `2020-08-19`, `2022-04-01`, `2022-05-18`). Initial-release DGS2 is missing on the first two dates, while the snapshot has numbers; DGS10 is missing initially on `2020-08-19`. The other three DGS10 differences are numeric changes. In particular, the official [H.15 correction feed](https://www.federalreserve.gov/feeds/H15.html) explicitly identifies the `2014-01-14` 10-year correction from 2.77 to 2.88. This two-snapshot comparison is evidence of changed values, **not** a complete dated revision sequence. Snapshot SHA-256: DGS2 `38f4369b18ee9cdc6238e36b65425331b3a9cd11a151913cf12063ab8126ae6e`, DGS10 `ae841b61fa8a018b79f55f1b9a96dba6acaadadadb1313187164a9e19889d0aa`.

The new `ASOF_AVAILABILITY_MATRIX.csv` records dates and evidence status only. It does not redistribute raw yields. Its SHA-256 is `0f871aa585f2aa73223c0b809621808e9e0b47fc3430375628eee11ee3fc3ceb`. The existing Naver KOSPI snapshot used only as a **calendar proxy** matched tracked SHA-256 `b243b958aae4ac360527f8d85e38c2696b8be4379bd77a0833ef977ec2595ae3`; it is not an official KRX session calendar or timestamped PIT source.

Two newly downloaded official [U.S. Treasury daily par-yield archives](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives) were retained privately: 2010–2019 SHA-256 `a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254`, 2020–2023 SHA-256 `25877e5541442e8c8c642a3cf9709d8c20eb2c1603556e3ebd84545f1f0acfe2`. Independent `Decimal` comparison with the initial-release FRED files found **3,500/3,500** matching DGS2 numeric overlaps and **3,498/3,501** matching DGS10 overlaps. The three DGS10 differences are `2014-01-14`, `2022-04-01`, and `2022-05-18`; they match the three numeric changes seen in the 2026-10-27 FRED snapshot. This strengthens value reconciliation across 2010–2023 but does not backdate when the Treasury archive, H.15, or FRED first published each row. The 2024–2026 Treasury full-period archive comparison remains **SKIPPED**; no full-period source equivalence is claimed.
