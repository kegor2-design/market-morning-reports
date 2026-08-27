# MarketMorningPublisher 1.6.5.2 — Expert Historical Corpus

## Purpose

Turn already-collected historical subtitles for Chesley/Park Seik and Park Jong-hoon/KPUNCH into a reusable, auditable reasoning corpus without treating expert speech as fact.

## Known archive baseline

- ChesleyTV: metadata 2,857; subtitles 2,848 (99.68%); 9 missing; period 2022-02-26 through 2026-08-04.
- Park Jong-hoon/KPUNCH: research archive 346/346 subtitles. The prior operating release deliberately excluded the 346-file research archive from the release ZIP and retained only 20 `.ko.vtt` files directly referenced by the existing ledger.

These numbers are guardrails, not hard-coded proof of current filesystem state. Deployment must locate and inventory the actual server archives before merge.

## Four-layer separation

1. `OFFICIAL_FACT`: DART, KRX, BOK, Fed, Treasury, company IR, etc.
2. `RUMOR/UNVERIFIED`: Telegram, anonymous tips, unconfirmed reports.
3. `EXPERT_HISTORICAL_CLAIM`: Chesley/Park Seik and Park Jong-hoon historical claims and reasoning.
4. `OUR_MI`: MarketMorningPublisher's independent conclusion after evidence and counter-evidence.

An expert claim can never promote an event to `OFFICIAL_FACT`.

## Initial backfill flow

`archive discovery -> inventory -> transcript normalization -> claim extraction -> attribution validation -> primitive consolidation -> historical validation queue -> Event Intelligence bridge`

### Attribution

Chesley content can include Park Seik, other Chesley staff, guests, news text and broker reports. The primary expert must be explicitly distinguished.

Park Jong-hoon content can include Fed/Treasury/government mechanics and official stated intent. Those must be separated from Park's own hypothesis.

## Claim model

Each reusable claim stores:

- expert / video / publication date
- exact source timestamp range
- speaker
- claim text and evidence summary
- causal chain
- premise metrics
- time horizon
- related assets/entities/topics
- expected direction
- invalidation conditions
- stable `primitive_key`
- stance and attribution confidence
- validation status

## New-video delta

After the historical backfill is stable, new videos compare against prior primitives:

- `NEW`
- `REINFORCED`
- `MODIFIED`
- `CONTRADICTED`
- `UNCHANGED`

Only meaningful delta is sent to Event Intelligence / Morning / Closing context.

## Historical validation

Validation must be point-in-time. A claim published on date T is evaluated only with data that becomes available after T under its declared horizon. Never rewrite the original claim using later knowledge.

Result states:

- `SUPPORTED`
- `PARTIAL`
- `CONTRADICTED`
- `INCONCLUSIVE`
- `NOT_TESTABLE`

## Calendar integration

Calendar event details may show related expert historical context, but it must be labeled `EXPERT_HISTORICAL_CLAIM`. Expert evidence does not change the official/unverified truth state of the event.
