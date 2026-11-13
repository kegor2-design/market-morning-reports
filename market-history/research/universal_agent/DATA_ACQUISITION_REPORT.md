# Data acquisition evidence — 2026-11-14

Actual official source: [US Treasury 2010–2019 par yield archive](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives/par-yield-curve-rates-2010-2019.csv). A bounded network Worker fetched the CSV for the declared 2015-04-01/02 dates. Raw response SHA-256: `a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254`. The raw file and per-run checkpoints are private, ignored research artifacts and are not pushed.

| Case | Actual result | Independent check |
| --- | --- | --- |
| Missing 2015-04-02 UST 10Y | Downloaded; recovered `1.92` percent | Raw hash and parser recomputation passed |
| Research Job missing 2015-04-02 UST 2Y | Downloaded in one Worker attempt; recovered `0.55` percent | Supervisor artifact and `verify_recovery` passed |
| Existing `187` versus Treasury `1.87` on 2015-04-01 UST 10Y | `DATA_MISMATCH`; both values preserved; unit/date/revision review requested | Recomputed against the same actual downloaded CSV; no second network fetch |
| Indicator 116 PIT evidence | Existing FRED/ALFRED local source and matrix audit executed | 4,204 strict rows still `PIT_BLOCKED` |

The Treasury archive supplies a current historical value snapshot. It does not supply row-level original publication, first accessibility, or complete revisions. Those fields remain null with reasons. The recovered values are usable only as source evidence; no PIT or investment result was promoted. An initial in-sandbox DNS failure was recorded as `BLOCKED_ENV`; a new task ID was used for the approved network run, with no automatic replay of the uncertain first call.

Scope limits: the adapter covers only reviewed `UST_2Y` and `UST_10Y` US Treasury percentage series, explicit dates in one year, and a maximum three-request budget. It does not yet infer a trading calendar or collect from other listed agencies. Monetary provider billing was not observed; no paid endpoint or model call was used.

## Follow-up actual sources and discrepancy — 2026-11-14

The [New York Fed SOFR API](https://markets.newyorkfed.org/static/docs/markets-api.html) was called through the new registered adapter. For declared 2024-04-01/03 dates, 2024-04-02 `5.34%` and 2024-04-03 `5.32%` were recovered. Original JSON SHA-256: `7e302132b1cff25ae4b0a1cf69ae0aa8c893c8eb2a1573b1b662bd3a00ce015c`. The independent verifier recomputed both values. One network request was made. Publication and first-access clocks remain null, so PIT is blocked. NY Fed reference-rate conditions apply; raw JSON was not committed.

A real historical revision was found for 2014-01-14 UST 10Y. The hash-checked FRED/ALFRED initial-vintage file says `2.77%`; the official Treasury archive says `2.88%`. The [Federal Reserve H.15 correction notice](https://www.federalreserve.gov/feeds/h15.html) explicitly identifies `2.77` as the previous value and `2.88` as the correction. The bounded Research Job fetched the Treasury CSV and notice, recorded `OFFICIAL_REVISION`, preserved both values, and independently revalidated their hashes and text. Treasury SHA-256: `a9278f347b48b819d68f91961e3e1a18431514ae3763ef888cc9f1bdb064b254`; notice SHA-256: `8f367e879bfa15ba5618db2a0b8c37a740a797369e45f04d909efbcd4c6d6ae9`. Two requests were used. Result: `DATA_MISMATCH_RESOLVED_PIT_UNVERIFIED`.

The earlier `187` versus `1.87` case remains blocked without unit provenance. When `187` is claimed as a FRED initial vintage it fails the hash-checked source-value comparison before download. No value was silently divided by 100. A simulated 503 outage records `SOURCE_UNAVAILABLE` and an independent-task next action; no live outage was induced.
