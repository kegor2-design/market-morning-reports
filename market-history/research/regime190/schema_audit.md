# Read-only database schema audit

Checked on 2026-10-28 KST using the existing read-only DB environment file. Connection parameters and values were not logged. Every inspection transaction used `BEGIN READ ONLY` and `SET LOCAL statement_timeout`. No operating DB row or schema was changed.

The earlier `CONNECT_FAILED` checkpoint used the wrong environment file and is superseded by this successful inspection. The read-only file supplied all five needed `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` keys. A sandboxed connection failed; the approved outside-sandbox read-only connection succeeded.

| Table | Actual rows | Date span | Key finding |
|---|---:|---|---|
| `domestic_daily_price` | 4,605,876 | 2011-09-16 to 2026-10-27 | OHLCV, turnover, `available_at`; historical `market` is mostly null, so market membership needs reconstruction. |
| `domestic_index_daily` | 828 | 2025-06-27 to 2026-10-27 | KIS index codes 0001, 1001, 2001; `market_division` is `U`, requiring index identity verification. |
| `domestic_investor_daily` | 108,684 | 2025-04-16 to 2026-10-20 | Per-symbol foreign/institution/retail quantities and amounts; futures coverage not established. |
| `domestic_short_sale_daily` | 165,502 | 2025-05-30 to 2026-10-27 | Per-symbol short quantities and amounts. |
| `domestic_credit_daily` | 149,800 | 2025-05-30 to 2026-10-22 | Per-symbol credit fields. |
| `market_rates_snapshot` | 5,205 | 2025-07-01 to 2026-10-27 | `released_at`, `available_at`, `vintage_date`, `revision_no` columns exist; row-level completeness and meaning are not yet audited. |
| `market_fx_snapshot` | 9,405 | 2026-07-07 to 2026-10-27 | Short recent FX snapshot period. |
| `us_market_daily` | 803 | 2026-03-26 to 2026-10-26 | Mixed symbols and sources; instrument-level mapping required. |
| `orderbook_depth_snapshot` | 1,669,153 at inspection | 2026-10-26 to 2026-10-27 | Ten bid/ask price and quantity levels, quote and receive timestamps; very short period and no cancellation or trade stream verified. |
| `event_shadow_snapshot` | 29,790 | 2026-05-26 to 2026-10-27 | News, disclosure, and notice events; event/publication time semantics require verification. |

`market_breadth_summary` contained 1,269 rows between 2026-10-14 and 2026-10-27; `market_index_snapshot` contained 24,905 rows between 2026-07-13 and 2026-10-27. Counts are inspection-time observations and may grow. The independent worker saves only bounded component query summaries in its private research directory; a successful generic DB field query is not treated as confirmation of an indicator definition or PIT eligibility.
