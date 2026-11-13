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
