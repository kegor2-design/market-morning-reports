# MarketMorningPublisher 1.6.5 — Rumor/Event Lifecycle Integration Contract

## Goal

Extend Event Intelligence so news, YouTube, Telegram and other unofficial claims can become tracked market events without ever being confused with official facts.

## Mandatory data path

```text
Existing news / YouTube collectors
Telegram collector or normalized import
        ↓
RumorCandidate normalization
        ↓
Event lifecycle ledger
        ↓
CANDIDATE / UNVERIFIED / CORROBORATED_UNVERIFIED
        ↓                       ↓
official confirmation       official denial / TTL
        ↓                       ↓
VERIFIED → ACTIVE          REJECTED / EXPIRED
        ↓
RESOLVING → RESOLVED
        ↓
Morning/Closing inference + Calendar
```

## Hard rules

1. Two or more Telegram/YouTube claims **must not** automatically become `OFFICIAL_FACT`.
2. `actual`, official dates and confirmed amounts must come from official/attributable evidence, not rumor text.
3. `estimated_end_date` and `impact_until` are different fields. Passing an estimated end date changes an active event to `RESOLVING`, not `RESOLVED`.
4. Keep every source/evidence item so the history of an event is auditable.
5. A public calendar must visibly distinguish `공식`, `보도/주장`, and `미확인`.
6. Rumor items can influence scenario attention/monitoring but must never be rendered as confirmed facts.
7. Telegram credentials/session data are runtime secrets and must never be packaged in release ZIPs.

## Telegram ingestion

The core module intentionally consumes normalized JSONL rather than owning user credentials. Use one of these collectors outside the core:

- Bot API collector for channels where the bot actually receives `channel_post` updates.
- MTProto/TDLib collector using user authorization and `api_id/api_hash` where this is legitimately configured.
- Manual/export JSONL import for channels that cannot be collected automatically.

Normalize all of them into the same JSONL contract. Example:

```json
{"event_id":"EVT-FX-SKHYNIX-ADR","source_type":"TELEGRAM_NAMED","message_id":"12345","channel":"example","author":"analyst-name","published_at":"2026-08-25T03:00:00Z","title":"SK하이닉스 ADR 환전 9월 지속 주장","text":"...","event_type":"FX_FLOW","entities":["SK하이닉스","USD/KRW"],"estimated_end_date":"2026-09-30","impact_summary":"USD 공급 증가 가능성","expected_direction":{"USD/KRW":"DOWN_PRESSURE"},"resolution_condition":"회사/은행/공식자료로 환전 종료 또는 지속 확인"}
```

## Integration points in existing 1.6.5

Codex must locate existing functions rather than assume filenames/line numbers.

- `event_intelligence.py`: merge rumor lifecycle records into event state and calendar projection.
- `event_intelligence_cli.py` / `run_event_intelligence.sh`: run rumor ingest after existing official calendar/OpenDART collection and before final state serialization.
- Codex input builder: include `event_lifecycle`, `rumor_watch`, and `active_events`; add an explicit instruction that rumor rows are hypotheses/watch items only.
- Morning Brief: add a compact `미확인·추적 이벤트` section only when rows exist.
- Closing Review: update active event reaction and resolution checks.
- Research Portal calendar: render official and unverified items together but with unmistakable badges and filters. Do not hide rumor items merely because there is no exact date; use impact window/agenda/watch list.
- Existing 1.6.4.1 homepage full-post/share suppression must remain intact.

## State files

Recommended files under the existing `data/state/event_intelligence/` directory:

```text
event_lifecycle.json
rumor_watch.json
calendar_overlay.json
```

These are runtime state, not release-package files.

## Suggested normalized input locations

Codex must first discover current YouTube/news normalized artifacts and reuse them. Do not create duplicate collectors when an existing source already exists.

For Telegram, use a configured path such as:

```text
data/private/telegram/normalized/events.jsonl
```

The path can be changed by config/env, but runtime data must not be packaged.

## Raw-source extraction stage

Telegram collector output is **source material**, not yet an event ledger input:

```text
data/private/telegram/normalized/messages.jsonl
        ↓
MMP_RUMOR_EVENT_EXTRACTION_V1 extraction/clustering
        ↓
data/private/telegram/normalized/events.jsonl
        ↓
rumor_intelligence.py
```

Apply the same principle to existing YouTube/news source artifacts: reuse their normalized content, run only event extraction/clustering, then pass event candidates to the lifecycle engine. Avoid duplicating the existing collectors.

For an initial deployment, scan recent source history broadly enough to catch still-active events. A practical default is recent 90 days for news/YouTube event extraction and 7 days for the first Telegram backfill, followed by incremental collection. This is a deployment default, not a truth rule; an older event with an explicit still-active window must remain tracked when discovered.

## Source Registry / repost-independence extension (1.6.5.1)

`config/source_registry.json` is the provenance contract for Telegram/YouTube discovery and official validators.
Before `normalize_candidate()`, enrich each row with `SourceRegistry.enrich()` so evidence retains:

- `source_registry_id`
- `source_tier`
- `source_role`
- `independence_group`
- `origin_group`
- `corroboration_eligible`
- `source_owner`

Corroboration rules:

1. `corroboration_eligible=false` contributes zero independent corroboration.
2. Multiple channels with the same `independence_group` count as one family.
3. A/B/C/D is provenance quality, never a truth or investment-grade score.
4. Official mirrors must dereference the primary DART/KRX/central-bank release before `OFFICIAL_FACT` promotion.
5. Source accuracy is learned from lifecycle outcomes using `source_performance.py`; do not pre-seed subjective hit rates.
