# MarketMorningPublisher 1.6.5 Rumor/Event Lifecycle Source Overlay

This overlay extends the already-created 1.6.5 Event Intelligence with persistent event lifecycle tracking and a separated unofficial-source layer.

It is deliberately additive because the exact generated 1.6.5 full source ZIP is not mounted in this ChatGPT runtime. Reconstructing existing 1.6.5 files from memory would risk dropping 1.6.4/1.6.4.1/1.6.5 functionality. The accompanying Codex prompt merges this overlay into the server's actual source and only then produces a final full replacement ZIP after regression checks.

Included source:

- `market_morning_publisher/event_lifecycle.py`
- `market_morning_publisher/rumor_intelligence.py`
- `market_morning_publisher/rumor_intelligence_cli.py`
- `market_morning_publisher/telegram_rumor_collector.py`
- `config/rumor_intelligence.json`
- `config/rumor_event_extraction.json`
- `config/telegram_rumor_sources.json`
- focused tests
- rumor/Telegram preflight and run scripts
- integration contract

Important design rule: Telegram/YouTube/news-tip claims remain unverified until authoritative evidence confirms them. Multiple rumor sources increase watch priority only; they do not create an official fact.

## 1.6.5.1 Source Registry extension

Adds `config/source_registry.json`, source-family independence, aggregator exclusion from corroboration, and lifecycle-derived source performance. Initial pool: 25 entries (18 Telegram, 3 YouTube, 4 official validators). Telegram collection remains disabled by default until credentials are configured.
