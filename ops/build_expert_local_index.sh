#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="${PROJECT:-/home/kegor2/MarketMorningPublisher}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
: "${EXPERT:?set EXPERT=chesley_park_seik or park_jonghoon_kpunch}"
cd "$PROJECT"
exec "$PYTHON_BIN" -m market_morning_publisher.expert_local_index --project-root "$PROJECT" --expert "$EXPERT" "$@"
