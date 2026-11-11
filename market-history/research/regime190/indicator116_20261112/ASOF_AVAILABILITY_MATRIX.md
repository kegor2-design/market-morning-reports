# Indicator 116 as-of availability matrix — 2026-11-12 KST

The [4,204-row CSV](ASOF_AVAILABILITY_MATRIX.csv) contains date metadata only; source rates remain private. Matrix SHA-256: `0f871aa585f2aa73223c0b809621808e9e0b47fc3430375628eee11ee3fc3ceb`. Rebuild with `build_asof_matrix.py` and the manifest-checked private DGS2/DGS10 initial-release files, the two existing 2026-10-27 snapshots, and the hash-checked Naver KOSPI CSV. The script is read-only except for its explicit output file.

| Column | Meaning |
| --- | --- |
| `observation_date` | U.S. market rate observation date, **not** release date |
| `dgs*_first_vintage_date` | FRED/ALFRED date-granular `realtime_start` from `output_type=4` |
| `both_vintage_dates_completed_by_kst_0900_date` | First Korean 09:00 after the full U.S. Eastern date of the later vintage elapsed; **not** a verified posting time |
| `us_eastern_offset_on_observation_date` | `America/New_York` UTC offset at local noon, including DST |
| `strict_pit_status`, `strict_blocker` | BLOCKED unless historical actual release and ingest times are proved |
| `exploratory_lag_days`, `exploratory_first_proxy_session` | Explicit seven-calendar-day lag from later vintage, then next available Naver KOSPI date; research sensitivity only |
| `proxy_calendar_status` | Naver session proxy is not an official KRX calendar; blank beyond 2026-10-20 |
| `differs_from_2026_10_27_snapshot` | Initial-release value differs from the older current-vintage snapshot on that observation date |

All 4,204 rows are `BLOCKED` for strict PIT. DST offsets: 1,404 EST and 2,800 EDT. The exploratory proxy maps 4,194 rows and leaves the final 10 outside its range. Two same-observation-day vintages, 2015-04-01 and 2015-04-02, remain blocked. The [2015-04-06 H.15 PDF](https://www.federalreserve.gov/releases/h15/20150406/h15.pdf) gives a 14:30 ET **weekly** release clock, but neither proves the earlier daily posting time nor FRED ingestion time. The [FRED vintage-date definition](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html) provides dates when values changed, not intraday timestamps. Scheduled times, holiday changes, and Korean session dates cannot close that gap.

No official research engine consumes this matrix as PIT approval. It is an audit artifact and a candidate exploratory calendar map only.
