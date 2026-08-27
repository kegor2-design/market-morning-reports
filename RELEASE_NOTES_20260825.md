# MarketMorningPublisher 1.6.5 — Event Intelligence / Disclosure Intelligence

Release date: 2026-08-25  
Baseline: **1.6.4 + Research Portal 1.6.4 → 1.6.4.1 HOTFIX**  
Target runtime root: `/home/kegor2/MarketMorningPublisher`

## 1. Release purpose

1.6.5 closes a pre-market information gap found during the 2026-08-25 Morning Brief review.
The existing Insight Engine could interpret collected news, but it did not have a persistent first-class input for:

- important events that are known **before** they happen;
- official Korean corporate disclosures that can matter to the next session.

This release makes those inputs part of the Morning judgment path before Codex produces the final prose.

## 2. Baseline preservation / regression rule

The release was reconstructed in this order before editing:

1. `MarketMorningPublisher_InsightEngine_1.6.4_20260825.zip`
2. `MarketMorningPublisher_ResearchPortal_1.6.4_to_1.6.4.1_HOTFIX_20260825.zip` overlaid on top

No baseline file was deleted. The 1.6.4.1 Blogger share/full-post suppression hotfix is intentionally preserved.
Existing Morning, Closing, Insight Engine, US State, Nightly YouTube Intelligence, Chart Insight,
Historical/Point-in-Time, Hypothesis Ledger, Responsive Publishing, and Research Portal code remains in the bundle.

Baseline test count before 1.6.5 work: **169 PASS**.  
Final 1.6.5 test count: **184 PASS**.

## 3. New Event Intelligence architecture

New contract: `MMP_EVENT_INTELLIGENCE_V1`

Main files:

- `config/event_intelligence.json`
- `market_morning_publisher/event_intelligence.py`
- `market_morning_publisher/event_intelligence_cli.py`
- `ops/run_event_intelligence.sh`
- `ops/check_event_intelligence_preflight.sh`

Persistent state is written at runtime to:

- `data/state/event_intelligence/calendar.json`
- `data/state/event_intelligence/disclosures.json`

Runtime state is not bundled as release data.

### Official schedule sources

The collector refreshes official schedules and keeps the previous ledger if a remote source fails.
It currently supports:

- U.S. BLS official ICS calendar: CPI, Employment Situation, PPI, JOLTS, ECI
- U.S. BEA official release schedule: PCE/Personal Income and Outlays, GDP, trade/external releases
- Federal Reserve official FOMC meeting calendar
- Bank of Korea monthly official event calendar, refreshed across the next six months
- Bank of Japan official Monetary Policy Meeting calendar
- ECB official Governing Council monetary-policy meeting calendar

Near-term events whose official pages do not expose a stable general-purpose calendar feed are retained as
verified seed events, including the current NVIDIA earnings/call and Jackson Hole items. Seeds do not replace
official-source refresh; where an automated official parser exists, the parser uses the same stable event ID and
updates the persistent ledger.

### Schedule-change tracking

Each persisted event can retain:

- `first_seen_at`
- `last_verified_at`
- `previous_scheduled_at_kst`
- `changed_at`
- `status=SCHEDULE_CHANGED`

A temporary official-site/network failure does not erase a previously known event.

### Dynamic importance

Events retain a base importance and receive a dynamic importance based on:

- base event importance;
- Korea relevance;
- time remaining to the event.

This allows an A/S event to be promoted as it enters the critical pre-event window.

## 4. OpenDART Disclosure Intelligence decision

### Primary source decision

**OpenDART is the primary disclosure source. MyDream2000 DB is not the source of truth for Morning disclosures.**

Reason:

- MarketMorningPublisher must be able to operate independently of the MyDream2000 DB runtime state;
- the official filing source should be checked directly;
- MyDream2000 remains suitable for later read-only price/flow reaction validation and strategy research.

No new MyDream2000/PostgreSQL table is introduced by 1.6.5.

### Important disclosure classification

The collector identifies material disclosures such as:

- distress/trading risk: embezzlement, breach of trust, rehabilitation/bankruptcy, delisting, shutdown;
- financing/dilution: rights offering, capital reduction, CB/BW/EB;
- M&A/control changes;
- large sales/supply contracts and contract termination;
- preliminary earnings / material earnings structure changes;
- treasury shares/dividend/bonus issue;
- major investment/facility investment;
- legal/regulatory events.

Only KOSPI/KOSDAQ classes are retained by default.

### Official original-document enrichment

For the highest-ranked disclosures, 1.6.5 can call OpenDART's official original-document endpoint and parse the
returned ZIP/XML/HTML with the Python standard library. No OCR is used.

It extracts evidence windows around labels such as:

- 계약금액
- 최근매출액
- 매출액 대비
- 계약기간
- 계약상대
- 영업이익 / 당기순이익
- 증자방식 / 자금조달 / 발행가액
- 시설투자 / 투자금액
- 생산중단 / 영업정지
- 배당금 / 배당성향

These excerpts are passed to the Insight Engine as official filing evidence. The engine is instructed not to infer
amounts, ratios, valuation impact, or earnings impact unless the supplied original-document evidence supports them.

### Critical timing guard

The OpenDART list response used here does not supply a reliable receipt clock time. Therefore 1.6.5 **does not**
label every DART filing as an "after-close disclosure". It records the receipt date and keeps the session relation as
time-unknown unless another supplied source proves the release time.

This prevents a previous-day or pre-open filing from being falsely described as an after-close disclosure.

## 5. Morning Insight Engine integration

The Morning pipeline now performs, before `build_codex_input()`:

1. news collection/clustering;
2. official event-calendar refresh;
3. OpenDART important-disclosure collection and original-document enrichment;
4. disclosure event normalization/reservation;
5. `event_intelligence` context construction;
6. Codex Insight Engine analysis;
7. deterministic calendar/disclosure rendering plus the existing analytical report.

New input fields include:

- `event_intelligence_contract`
- `event_intelligence.calendar.upcoming_events`
- `event_intelligence.calendar.critical_upcoming_events`
- `event_intelligence.disclosures.rows`
- `official_disclosure_event_ids`

The prompt explicitly requires critical upcoming events and DART official facts to be inspected before the one-line
diagnosis, regime, drivers, scenarios, watch items, and invalidation conditions are finalized.

## 6. Morning report output

New deterministic sections:

### `주요 일정 캘린더`

Shows in KST:

- schedule time/date;
- T-minus / D-minus;
- dynamic importance;
- event name;
- Korea transmission path;
- schedule status.

A-grade and above are prioritized and displayed chronologically.

### `최근 중요 공시 · OpenDART 공식`

Shows:

- receipt date;
- importance;
- company / symbol;
- filing title;
- category;
- correction status;
- automated verification scope.

The report also states that the receipt clock time is not fabricated.

## 7. Blogger Research Portal 1.6.5

The existing 1.6.4.1 homepage share/full-post suppression is preserved.

New `Market Calendar` presentation:

- desktop/tablet: real two-month calendar grid populated from the latest Morning Brief event table;
- mobile: horizontally scrollable agenda cards;
- S/S+ and A events are visually distinguished;
- KST is explicit.

Theme marker:

`data-rp-theme='1.6.5'`

Blogger Theme write is still not performed through the Blogger post API. Apply the XML theme manually after backup,
then run the included static/live validators.

## 8. Refresh schedule

`ops/install_cron.sh` preserves the existing 08:10 Morning pipeline and adds Event Intelligence refreshes:

- 00:20 daily
- 06:30 daily
- 07:50 daily — final pre-Morning refresh
- 15:40 weekdays
- 18:30 weekdays
- 21:30 daily

All event-refresh entries use one `flock` lock to avoid overlap.

## 9. Environment

OpenDART requires one of:

- `OPENDART_API_KEY`
- `DART_API_KEY`

Optional:

- `MMP_EVENT_INTELLIGENCE_REFRESH=1` (Morning defaults to refresh enabled)
- `MMP_PYTHON=/path/to/python`

No secret is included in the release ZIP.

## 10. DB schema / dependency contract

1.6.5 creates **no new PostgreSQL schema and no migration**.

Before production activation, the server must still run the existing read-only Closing/MyDream2000 schema contract:

```bash
cd /home/kegor2/MarketMorningPublisher
chmod +x ops/check_closing_db_schema.sh ops/check_event_intelligence_preflight.sh
./ops/check_closing_db_schema.sh /home/kegor2/mydream2000.env --required
./ops/check_event_intelligence_preflight.sh /home/kegor2/MarketMorningPublisher /home/kegor2/MarketMorningPublisher/.env
```

If the MyDream2000 schema contract fails, do not install/update cron and do not enable production publishing until the
existing integration is reconciled.

## 11. Verification completed on release workspace

Completed:

- reconstructed 1.6.4 + 1.6.4.1 baseline;
- no baseline file deletion in the 1.6.5 diff;
- full unit regression: **184 tests PASS**;
- Python `compileall`: PASS;
- all config JSON parse: PASS;
- all `ops/*.sh` `bash -n`: PASS;
- Blogger XML parse: PASS;
- Event Intelligence offline preflight: PASS;
- Research Portal theme contract + preview: PASS;
- schema-change review: no new DB table/migration required.

The release workspace cannot access the user's production PostgreSQL instance, so the actual production schema check is
a mandatory deployment gate in the apply prompt rather than a claimed local PASS.

## 12. Rollback

The deployment prompt requires a timestamped project backup before overlay. Rollback consists of restoring that
backup and restoring the previous Blogger theme backup, then restoring the previous cron if it was changed.

Do not delete `.env`, `data/private`, `data/state`, `logs`, `reports`, OAuth credentials, or existing runtime data during
an overlay deployment.
