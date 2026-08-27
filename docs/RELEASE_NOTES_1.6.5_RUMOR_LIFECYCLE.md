# MarketMorningPublisher 1.6.5 Final Extension — Rumor/Event Lifecycle

Date: 2026-08-25

## Why this extension exists

The first 1.6.5 Event Intelligence scope covered official schedules and OpenDART evidence, but it did not yet provide a dedicated lifecycle for unofficial, time-bearing claims discovered in news, YouTube, Telegram or tips. This extension adds that missing layer without changing the rule that unofficial claims are not facts.

## Added behavior

- Persistent event lifecycle: `CANDIDATE`, `UNVERIFIED`, `CORROBORATED_UNVERIFIED`, `VERIFIED`, `ACTIVE`, `RESOLVING`, `RESOLVED`, `REJECTED`, `EXPIRED`.
- Separate `event_date`, `estimated_end_date`, `impact_until`.
- Evidence history and source identity tracking.
- Calendar projection with explicit `공식 / 보도·주장 / 미확인` distinction.
- Optional Telegram public-channel collector using an allowlist and a separate MTProto/Telethon runtime.
- Raw Telegram messages are separated from event candidates: `messages.jsonl → event extraction/clustering → events.jsonl → lifecycle`.
- A source-count guardrail ensures that repeated or multiple rumors never automatically become an official fact.

## Focused validation in the artifact build environment

- 13 focused unit tests: PASS.
- Python compile: PASS.
- JSON config parsing: PASS.
- Shell syntax: PASS.

These focused tests validate only the new additive modules. Full MarketMorningPublisher regression, current DB schema checks, Morning dry-run, Research Portal XML/live verification and final full replacement ZIP must be run against the server's actual 1.6.5 tree using the accompanying Codex apply prompt.
