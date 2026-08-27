#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${PROJECT:-/home/kegor2/MarketMorningPublisher}"
EXPERT="${EXPERT:?set EXPERT=chesley_park_seik or park_jonghoon_kpunch}"
SOURCE_ROOT="${SOURCE_ROOT:?set SOURCE_ROOT to the verified subtitle archive directory}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT"
exec "$PYTHON_BIN" -m market_morning_publisher.expert_historical_corpus_cli \
  --project-root "$PROJECT" \
  inventory \
  --expert "$EXPERT" \
  --source-root "$SOURCE_ROOT" \
  --require-known-coverage
