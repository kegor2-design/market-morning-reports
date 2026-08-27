# Source Registry 1.6.5.1

## Purpose

This registry makes rumor/event provenance explicit. It prevents repeated forwarding from being mistaken for independent confirmation and separates discovery, attributable research, and official validation.

## Tier meaning

- **A**: owner/provenance is strongly identifiable. It is **not** a truth/accuracy grade.
- **B**: attributable expert or near-primary mirror. Claims still require verification.
- **C**: news/research aggregator useful for early discovery. Trace the original source.
- **D**: rumor/speculative/auto-forward stream. High verification burden.

## Independence rules

1. `corroboration_eligible=false` sources never increase independent-source count.
2. Sources sharing `independence_group` count as one source family.
3. Telegram/YouTube repetition never creates `OFFICIAL_FACT`.
4. DART mirrors are not official by themselves; follow the linked DART/KRX original.
5. Market-price reaction is evidence about impact, not evidence that the underlying claim is true.

## Initial source pool

The registry starts with 25 entries: 18 public Telegram channels, 3 YouTube expert channels already used by this project, and 4 primary official validators (OpenDART, KRX KIND, Bank of Korea, Federal Reserve).

The Telegram collector remains globally disabled until runtime API credentials/session are configured. This release therefore changes provenance logic safely without silently starting a new external collector.

## Source performance

Historical accuracy is intentionally **not prefilled**. `source_performance.py` derives confirmed/denied/expired/open counts from resolved lifecycle events. This avoids assigning subjective accuracy scores before evidence exists.
