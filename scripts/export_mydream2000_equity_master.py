#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.removeprefix("export ").split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default="/home/kegor2/mydream2000_backtest_ro.env")
    parser.add_argument("--output", default="data/private/reference/korea_equity_master.json")
    args = parser.parse_args()
    load_env(Path(args.env_file))
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "trading"), user=os.environ["DB_USER"], password=os.getenv("DB_PASSWORD", ""),
        options="-c default_transaction_read_only=on -c statement_timeout=120000",
    )
    columns = ["symbol", "isin", "name", "market", "industry_larg_code", "industry_medm_code", "industry_smal_code", "kospi200_sector_name"]
    with conn, conn.cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        if cur.fetchone()[0] != "on":
            raise RuntimeError("database session is not read-only")
        cur.execute("SELECT " + ",".join(columns) + " FROM public.symbol_master_trade_eligible_v ORDER BY symbol")
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    conn.close()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"contract":"MMP_KR_EQUITY_MASTER_V1", "generated_at":datetime.now(timezone.utc).isoformat(), "source":"MYDREAM2000_SYMBOL_MASTER_READ_ONLY", "rows":rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output":str(output), "rows":len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
