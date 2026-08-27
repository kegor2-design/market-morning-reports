# Release notes — 1.6.5.4 Calendar Decision Card

- Adds beginner-first `decision_card` projection to Event Lifecycle calendar items.
- Makes `decision_question` the primary detail-card headline.
- Moves causal chain to `transmission_path` under the explanation.
- Adds `plain_summary`, `why_it_matters`, `watch_items`, scenarios, invalidation conditions and beginner glossary.
- Preserves OUR_MI provenance: expert/rumor claims never become `current_view` automatically.
- Adds safe fallbacks for FOMC, BOK, Treasury buyback, election, regulation and generic events.
- Backward compatible with old EventRecord JSON; missing `decision_card` is filled at projection time.
