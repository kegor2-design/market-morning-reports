#!/usr/bin/env bash
set -Eeuo pipefail
ENV_FILE="${1:-/home/kegor2/mydream2000.env}"
MODE="${2:-optional}"
required=0
[[ "$MODE" == "--required" ]] && required=1

if [[ ! -f "$ENV_FILE" ]]; then
  if (( required )); then
    echo "[FAIL] MyDream2000 env required but not found: $ENV_FILE"
    exit 2
  fi
  echo "[SKIP] MyDream2000 env not found: $ENV_FILE"
  exit 0
fi
if ! command -v psql >/dev/null 2>&1; then
  if (( required )); then
    echo "[FAIL] psql is required for DB schema preflight"
    exit 2
  fi
  echo "[SKIP] psql not installed"
  exit 0
fi

set -a
source "$ENV_FILE"
set +a
export PGPASSWORD="${DB_PASSWORD:-}"
for key in DB_HOST DB_PORT DB_USER DB_NAME; do
  [[ -n "${!key:-}" ]] || { echo "[FAIL] missing $key in $ENV_FILE"; exit 2; }
done

REQUIRED=$(cat <<'EOF'
market_breadth_summary:snapshot_time
investor_flow_snapshot:id
investor_flow_snapshot:symbol
investor_flow_snapshot:name
investor_flow_snapshot:trade_date
investor_flow_snapshot:data_date
investor_flow_snapshot:foreign_net_value
investor_flow_snapshot:institution_net_value
investor_flow_snapshot:personal_net_value
investor_flow_snapshot:program_net_value
investor_flow_snapshot:collected_at
investor_flow_snapshot:status
market_sector_breadth_snapshot:snapshot_time
market_sector_breadth_snapshot:sector_level
market_sector_breadth_snapshot:market
market_sector_breadth_snapshot:industry_code
market_sector_breadth_snapshot:quote_count
market_sector_breadth_snapshot:coverage_ratio
market_sector_breadth_snapshot:advance_count
market_sector_breadth_snapshot:decline_count
market_sector_breadth_snapshot:breadth_ratio
market_sector_breadth_snapshot:avg_change_pct
market_sector_breadth_snapshot:total_trade_value
market_sector_breadth_snapshot:top_symbol
market_sector_breadth_snapshot:top_symbol_name
market_sector_breadth_snapshot:top_symbol_change_pct
market_breadth_snapshot:snapshot_time
market_breadth_snapshot:symbol
market_breadth_snapshot:name
market_breadth_snapshot:market
market_breadth_snapshot:price
market_breadth_snapshot:change_pct
market_breadth_snapshot:volume
market_breadth_snapshot:trade_value
EOF
)
ACTUAL="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -X -At -F: <<'SQL'
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('market_breadth_summary','investor_flow_snapshot','market_sector_breadth_snapshot','market_breadth_snapshot')
ORDER BY table_name,column_name;
SQL
)"
missing=0
while IFS= read -r req; do
  [[ -z "$req" ]] && continue
  if ! grep -Fxq "$req" <<<"$ACTUAL"; then
    echo "[FAIL] DB schema missing: $req"
    missing=1
  fi
done <<<"$REQUIRED"
if (( missing )); then
  exit 3
fi
echo "[PASS] closing DB schema contract satisfied"
