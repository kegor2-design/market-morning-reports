# Release Notes 1.6.5.3 — MI Prediction Scoreboard

Base: 1.6.5.2 Expert Historical Corpus.

Added:
- immutable MI prediction snapshot contract
- point-in-time horizon scoring
- direction / range / MFE / MAE evaluation
- confidence calibration buckets
- asset/horizon/regime/primitive/expert/event/source attribution scoreboard
- JSONL idempotent ledgers
- CLI and preflight
- focused verification tests

Not added automatically:
- DB migrations
- cron changes
- automatic production prediction creation
- automatic market-data adapter selection

These must be integrated against the server's actual latest code and DB schema before release.
- prediction commit JSON schema/prompt
- matched `OUR_MI_ENGINE` vs `AI_BASELINE` shadow A/B comparison
