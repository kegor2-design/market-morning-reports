# Release Notes — 1.6.5.1 Source Registry / Corroboration Guard

- Added 25-entry source registry (18 Telegram / 3 YouTube / 4 official validators).
- Added `independence_group` and `origin_group` to collapse sister/repost channels.
- Added `corroboration_eligible=false` for aggregators/mirrors that must not manufacture confirmation.
- Added source-registry enrichment to rumor ingestion.
- Added lifecycle-derived source performance output; no fabricated initial hit-rate.
- Telegram collector writes registry metadata into normalized JSONL.
- Existing rule remains: unofficial repetition and price reaction can never create `OFFICIAL_FACT`.
- Telegram runtime remains opt-in (`enabled=false`) to avoid unexpected collection or credential requirements.
