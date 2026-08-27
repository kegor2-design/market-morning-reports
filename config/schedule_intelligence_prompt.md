# MMP Schedule Intelligence V1

Use deterministic explicit-date discovery first, then semantic extraction/official verification for high-impact events.

## Required runtime path

```text
normalized News/YouTube/Telegram document
  -> explicit date/window discovery (schedule_discovery.py)
  -> semantic event cleanup / clustering
  -> official forward-calendar lookup and official-source verification
  -> lifecycle merge
  -> decision_card enrichment
  -> calendar projection
```

## Rules

- Preserve the date stated by the source as evidence, but an official primary source may correct `event_date` / `estimated_end_date`.
- Never silently replace the source claim. Keep both source claim and official correction in evidence/history.
- A YouTube expert is attributable evidence, not official evidence.
- Important official schedules should exist even if no news/YouTube item mentions them.
- Upcoming events must be collected proactively for at least the configured forward horizon.
- Calendar must display a WATCH item when a material date-bearing event is discovered but not yet officially verified.
- `decision_card.decision_question` must explain what the engine needs to judge; causal chain is secondary context.
