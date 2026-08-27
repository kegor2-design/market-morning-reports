# MarketMorningPublisher 1.6.5.4 — Schedule Intelligence

## Why this patch exists

The 1.6.5.x contracts described time-bearing extraction, but the overlay did not contain a runtime extractor that transformed existing normalized YouTube/news text into schedule candidates. This could leave important dates absent from the calendar even when a transcript explicitly mentioned them.

## Runtime addition

`schedule_discovery.py` performs a conservative first-pass extraction of explicit Korean/ISO dates and date ranges from normalized source text. It does **not** make the source official. Its output is an event candidate that must go through existing source registry, lifecycle and official validation.

The semantic/official pipeline on the production server must be:

```text
existing normalized source -> schedule_discovery -> semantic cleanup/cluster
-> official validator / forward calendar -> lifecycle -> decision_card -> calendar
```

## Regression fixture

Video id `cUAwb9CTMHo` is used as a regression fixture for schedule discovery semantics. The fixture verifies detection of Jackson Hole, Treasury buyback, CLARITY/legislation, FOMC and U.S. midterm election date mentions. It does not assert that the YouTube dates are official; official evidence may correct them.

## Official validators added

- U.S. Treasury
- Federal Reserve Bank of Kansas City
- U.S. Congress / Congress.gov / GovInfo
- Federal Election Commission

These extend the prior Fed/BOK/OpenDART/KRX official validator registry. A registry entry alone is not a collector: production integration must proactively fetch/normalize future official schedules for the configured forward horizon.
