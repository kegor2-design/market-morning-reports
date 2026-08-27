#!/usr/bin/env python3
"""Export a read-only MyDream2000 EOD snapshot into MMP_KOREA_CLOSE_V1 JSON."""
from __future__ import annotations

import argparse
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def native(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--env-file", default="/home/kegor2/mydream2000.env")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    load_env(Path(args.env_file))
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "mydream"), password=os.getenv("DB_PASSWORD", ""),
        dbname=os.getenv("DB_NAME", "trading"), cursor_factory=psycopg2.extras.RealDictCursor,
        options="-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=2000",
        application_name="mmp_closing_file_export_v1",
    )
    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM market_breadth_summary
            WHERE snapshot_time >= %s::date AND snapshot_time < %s::date + interval '1 day'
            ORDER BY snapshot_time DESC LIMIT 1
        """, (args.date, args.date))
        breadth = dict(cur.fetchone() or {})
        cur.execute("""
            WITH latest AS (
              SELECT DISTINCT ON (symbol) symbol, name, data_date, foreign_net_value,
                     institution_net_value, personal_net_value, program_net_value, collected_at, status
              FROM investor_flow_snapshot
              WHERE trade_date=%s::date AND data_date<=%s::date AND status='OK'
              ORDER BY symbol, data_date DESC, collected_at DESC, id DESC
            )
            SELECT COUNT(*) AS symbols, MAX(data_date) AS data_date, MAX(collected_at) AS collected_at,
                   SUM(foreign_net_value) AS foreign_net_value,
                   SUM(institution_net_value) AS institution_net_value,
                   SUM(personal_net_value) AS personal_net_value,
                   SUM(program_net_value) AS program_net_value
            FROM latest
        """, (args.date, args.date))
        flows = dict(cur.fetchone() or {})
        cur.execute("""
            WITH cutoff AS (
              SELECT MAX(snapshot_time) AS ts FROM market_sector_breadth_snapshot
              WHERE snapshot_time >= %s::date AND snapshot_time < %s::date + interval '1 day'
                AND sector_level='LARG'
            )
            SELECT market, industry_code, quote_count, coverage_ratio, advance_count, decline_count,
                   breadth_ratio, avg_change_pct, total_trade_value, top_symbol, top_symbol_name,
                   top_symbol_change_pct, snapshot_time
            FROM market_sector_breadth_snapshot, cutoff
            WHERE snapshot_time=cutoff.ts AND sector_level='LARG'
            ORDER BY avg_change_pct DESC NULLS LAST LIMIT 20
        """, (args.date, args.date))
        sectors = [dict(row) for row in cur.fetchall()]
        cur.execute("""
            WITH cutoff AS (
              SELECT MAX(snapshot_time) AS ts FROM market_breadth_snapshot
              WHERE snapshot_time >= %s::date AND snapshot_time < %s::date + interval '1 day'
            )
            SELECT symbol, name, market, price, change_pct, volume, trade_value, snapshot_time
            FROM market_breadth_snapshot, cutoff WHERE snapshot_time=cutoff.ts
            ORDER BY trade_value DESC NULLS LAST LIMIT 20
        """, (args.date, args.date))
        leaders = [dict(row) for row in cur.fetchall()]
    result = {
        "contract": "MMP_KOREA_CLOSE_V1", "report_date": args.date,
        "breadth": breadth or None,
        "investor_flows": {k: v for k, v in flows.items() if k != "program_net_value"} if flows else None,
        "program_flows": {"program_net_value": flows.get("program_net_value"), "data_date": flows.get("data_date")} if flows else None,
        "sectors": sectors, "leaders": leaders,
        "turnover": {"total_trade_value": sum(float(x.get("trade_value") or 0) for x in leaders), "scope": "top_20_by_trade_value"},
        "source": {"system": "MyDream2000", "mode": "read_only_file_export", "as_of": breadth.get("snapshot_time") if breadth else None},
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=native) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "breadth": bool(breadth), "flow_symbols": flows.get("symbols", 0), "sectors": len(sectors), "leaders": len(leaders)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
