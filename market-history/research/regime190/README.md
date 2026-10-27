# Regime 190 historical data audit (2026-10-27)

Generated 2026-10-27T15:04:33.049087+00:00. Target 2010-01-01 to 2026-10-27, KOSPI and KOSDAQ separately. Exactly 190 indicators are listed in `inventory_190.csv`. Status counts: {'일부 확보': 16, '원천 확보·계산 미완료': 24, '미확보(미시도)': 150}.

The only verified raw files in this run are two Naver Finance index XML files and their normalized CSVs, locally retained from 2026-10-21. SHA-256 values match the prior manifest. Both end 2026-10-20. Sixteen price indicator definitions were calculated into private local CSVs, with hashes in `raw_manifest.csv`; these are partial acquisition because 2026-10-21 through 2026-10-27 and publication vintages are absent. Twenty-four other price indicators have raw inputs but unfinished calculations. The remaining 150 indicators were not individually collected. A KRX landing page HEAD request returned 200 but yielded no observations. DB connection failed.

Historical OHLC invalid rows: KOSPI 4 and KOSDAQ 1, all before 2010. Target-window OHLC invalid rows: 0 in each market. Calendar and provider comparisons were not repeated.

All index records remain `PIT_UNVERIFIED`: observation date exists, but row-level published/available timestamps and vintage do not. No predictive backtest was run because the prompt forbids unverified PIT data in final validation. `coverage_matrix.csv` reports raw weekday coverage as context, with 0% PIT eligibility; weekdays are not an official KRX calendar. Redistribution rights for Naver raw data were not confirmed, so no raw or derived series are committed. The private outputs remain in ignored `private/`.

Rebuild in the server snapshot: `python3 market-history/research/regime190/run.py`. Source files are required in the prior daily-index-validation directory. This command does not access the network or DB. Open risks: official provider reconciliation, exact publication times and revisions, exchange calendar, 150 source collections, 24 remaining calculations, and PIT-safe walk-forward backtesting.
