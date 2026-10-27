## Scope and result

Target date: 2026-10-27. The audit contains exactly 190 indicators: 23 partly acquired, 24 with index raw inputs but unfinished calculations, and 143 not individually collected. No indicator is classified as fully acquired.

KOSPI and KOSDAQ are separate. Four local Naver Finance files were verified by SHA-256 against the prior manifest: raw XML and normalized CSV for each market. KOSPI has 7,730 rows from 1996-01-03 to 2026-10-20; KOSDAQ has 7,574 rows from 1996-07-02 to 2026-10-20. Each has 4,133 rows from 2010 onward. Sixteen defined price transforms were calculated into ignored private files. Four existing monthly repository CSVs supply partial components for seven additional indicators; they are incomplete and lack release vintages.

PIT eligibility is **0%** in both markets because row-level publication/available timestamps and vintages are unavailable. Predictive walk-forward backtesting was **not run** under the PIT gate. Historical OHLC invalid rows: KOSPI 4 and KOSDAQ 1, all before 2010. The 2010+ target window had no OHLC invalid rows. The official KRX landing page returned HTTP 200 to HEAD, but no KRX observations were collected. PostgreSQL connection failed before schema inspection.

The 190-row master, 1,140-row market/period coverage matrix, PIT and quality audits, source attempt log, raw file hashes, and explicit backtest status are under `market-history/research/regime190/`. Verification passed for 190 unique consecutive IDs, all coverage keys, XLSX row count, and all ten manifest file hashes. Rebuild command on the server snapshot: `python3 market-history/research/regime190/run.py`.

Only the new research directory changed. MyDream2000 and MarketMorningPublisher code, settings, services, DB schema, and tables were not changed. Private Naver raw files and computed series are ignored. Remaining work: 143 individual source collections, 24 index calculations, seven monthly indicators' missing components, source rights, official comparison, as-of vintages, and PIT-safe backtesting. This is a partial checkpoint, not completion of the collection goal.
