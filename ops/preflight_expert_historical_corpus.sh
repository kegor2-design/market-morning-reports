#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${1:-/home/kegor2/MarketMorningPublisher}"
MMP_ENV="${2:-$PROJECT/.env}"
MYDREAM_ENV="${3:-/home/kegor2/mydream2000.env}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

section(){ echo; echo "===== $* ====="; }
fail(){ echo "[FAIL] $*" >&2; exit 1; }
pass(){ echo "[PASS] $*"; }

cd "$PROJECT"

section "1. permissions / inputs"
[[ -f config/expert_historical_corpus.json ]] || fail "missing expert corpus config"
[[ -f market_morning_publisher/expert_historical_corpus.py ]] || fail "missing expert corpus module"
[[ -f market_morning_publisher/expert_event_bridge.py ]] || fail "missing expert event bridge"
[[ -f "$MMP_ENV" ]] && stat -c '%a %n' "$MMP_ENV" || true
[[ -f "$MYDREAM_ENV" ]] && stat -c '%a %n' "$MYDREAM_ENV" || true

section "2. compile / focused tests / json"
"$PYTHON_BIN" -m py_compile \
  market_morning_publisher/expert_historical_corpus.py \
  market_morning_publisher/expert_historical_corpus_cli.py \
  market_morning_publisher/expert_historical_backfill.py \
  market_morning_publisher/expert_event_bridge.py
"$PYTHON_BIN" -m unittest -v tests.test_expert_historical_corpus tests.test_expert_event_bridge
"$PYTHON_BIN" - <<'PY'
import json
for p in [
  'config/expert_historical_corpus.json',
  'config/expert_claim_output_schema.json',
]:
    json.load(open(p, encoding='utf-8'))
    print('[PASS] json', p)
PY

section "3. existing full regression"
"$PYTHON_BIN" -m unittest discover -s tests -v

section "4. DB schema read-only gate"
# This feature has no DB writes. Still require the current release's own DB schema contract checker
# before any operational merge, because Morning/Closing functions depend on the existing schema.
CHECKER=""
for c in \
  ops/check_mydream2000_db_schema.sh \
  ops/check_closing_db_schema.sh \
  ops/preflight_us_state_release.sh \
  ops/check_db_schema_contract.sh; do
  if [[ -x "$c" ]]; then CHECKER="$c"; break; fi
done
if [[ -z "$CHECKER" ]]; then
  fail "no existing DB schema contract checker found; derive/run current schema contract before deployment"
fi
set -a
[[ -f "$MMP_ENV" ]] && source "$MMP_ENV"
[[ -f "$MYDREAM_ENV" ]] && source "$MYDREAM_ENV"
set +a
if [[ "$CHECKER" == "ops/preflight_us_state_release.sh" ]]; then
  "$CHECKER" "$PROJECT" "$MMP_ENV" || fail "US State preflight/schema contract failed"
else
  "$CHECKER" || fail "DB schema contract failed: $CHECKER"
fi
pass "DB schema/read-only gate passed via $CHECKER"

section "5. subtitle archive inventory gate"
# Do not guess archive locations. The deployment merge must discover the actual server archive roots
# and then run these commands with --source-root. This preflight only blocks if no validated inventory exists.
for expert in chesley_park_seik park_jonghoon_kpunch; do
  SUM="data/state/expert_corpus/$expert/inventory_summary.json"
  [[ -f "$SUM" ]] || fail "missing validated inventory summary for $expert; run inventory with actual --source-root first"
  "$PYTHON_BIN" - "$SUM" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
print(obj)
if not obj.get('coverage_pass'):
    raise SystemExit(3)
if obj.get('expert_id') == 'chesley_park_seik' and obj.get('text_verified', 0) < 2848:
    raise SystemExit('chesley TEXT_VERIFIED coverage below 2848')
PY
  pass "inventory coverage: $expert"
done

echo "[RESULT] PASS_EXPERT_HISTORICAL_CORPUS_PREFLIGHT"
