#!/usr/bin/env python3
"""Read-only coverage and outcome audit for MyDream2000 AP research data."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import psycopg2
from psycopg2 import sql


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def connect() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "trading"),
        user=os.environ["DB_USER"],
        password=os.environ.get("DB_PASSWORD", ""),
        connect_timeout=5,
        application_name="mydream2000_ap_outcome_readonly_audit",
        options="-c timezone=Asia/Seoul -c default_transaction_read_only=on -c statement_timeout=120000",
    )
    conn.autocommit = True
    return conn


def fetch_dicts(cur, query: str, params: tuple = ()) -> list[dict]:
    cur.execute(query, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default="/home/kegor2/mydream2000_backtest_ro.env")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    load_env(Path(args.env_file))

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        if cur.fetchone()[0] != "on":
            raise RuntimeError("database session is not read-only")
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema='public' AND table_name='ai_candidate_outcome'
               ORDER BY ordinal_position"""
        )
        columns = [row[0] for row in cur.fetchall()]
        if not columns:
            raise RuntimeError("public.ai_candidate_outcome not found")

        wanted = [
            "actual_net_ret_est", "future_ret_60s", "future_ret_120s", "future_ret_180s",
            "max_ret_60s", "min_ret_60s", "max_ret_120s", "min_ret_120s",
            "max_ret_180s", "min_ret_180s", "target_first", "stop_first",
            "net_profit_score", "stop_risk_score", "clean_momentum_score",
            "signal_score", "rest_score", "ai_rank_score", "ai_rank_score_v2",
        ]
        present = [c for c in wanted if c in columns]
        missing = [c for c in wanted if c not in columns]

        coverage_exprs = [
            sql.SQL("count({}) AS {}").format(sql.Identifier(c), sql.Identifier(f"{c}_n"))
            for c in present
        ]
        query = sql.SQL(
            "SELECT count(*) AS rows, count(DISTINCT trade_date) AS trade_days, "
            "min(trade_date) AS min_date, max(trade_date) AS max_date, {} "
            "FROM public.ai_candidate_outcome WHERE trade_date BETWEEN %s AND %s"
        ).format(sql.SQL(", ").join(coverage_exprs))
        cur.execute("SELECT min(trade_date), max(trade_date) FROM public.ai_candidate_outcome")
        min_date, max_date = cur.fetchone()
        if min_date is None:
            raise RuntimeError("ai_candidate_outcome has no rows")
        cur.execute(query, (min_date, max_date))
        names = [d.name for d in cur.description]
        coverage = dict(zip(names, cur.fetchone()))

        daily = fetch_dicts(
            cur,
            """SELECT trade_date, count(*) AS rows,
                      count(*) FILTER (WHERE target_first IS NOT NULL OR stop_first IS NOT NULL) AS labeled_rows,
                      count(*) FILTER (WHERE target_first) AS target_first_n,
                      count(*) FILTER (WHERE stop_first) AS stop_first_n,
                      round(100.0 * count(*) FILTER (WHERE target_first) / nullif(count(*),0), 2) AS target_first_pct,
                      round(100.0 * count(*) FILTER (WHERE stop_first) / nullif(count(*),0), 2) AS stop_first_pct,
                      round(avg(actual_net_ret_est)::numeric, 6) AS avg_net_ret_est,
                      round(avg(max_ret_60s)::numeric, 6) AS avg_max_ret_60s,
                      round(avg(min_ret_60s)::numeric, 6) AS avg_min_ret_60s,
                      round(avg(max_ret_120s)::numeric, 6) AS avg_max_ret_120s,
                      round(avg(min_ret_120s)::numeric, 6) AS avg_min_ret_120s
               FROM public.ai_candidate_outcome
               WHERE trade_date BETWEEN %s AND %s
               GROUP BY trade_date ORDER BY trade_date""",
            (min_date, max_date),
        )
        overall = fetch_dicts(
            cur,
            """SELECT count(*) AS rows,
                      count(*) FILTER (WHERE target_first IS NOT NULL OR stop_first IS NOT NULL) AS labeled_rows,
                      count(*) FILTER (WHERE target_first) AS target_first_n,
                      count(*) FILTER (WHERE stop_first) AS stop_first_n,
                      round(100.0 * count(*) FILTER (WHERE target_first) / nullif(count(*),0), 2) AS target_first_pct,
                      round(100.0 * count(*) FILTER (WHERE stop_first) / nullif(count(*),0), 2) AS stop_first_pct,
                      round(avg(actual_net_ret_est)::numeric, 6) AS avg_net_ret_est,
                      round(avg(max_ret_60s)::numeric, 6) AS avg_max_ret_60s,
                      round(avg(min_ret_60s)::numeric, 6) AS avg_min_ret_60s,
                      round(avg(max_ret_120s)::numeric, 6) AS avg_max_ret_120s,
                      round(avg(min_ret_120s)::numeric, 6) AS avg_min_ret_120s
               FROM public.ai_candidate_outcome
               WHERE trade_date BETWEEN %s AND %s""",
            (min_date, max_date),
        )[0]
        versions = fetch_dicts(
            cur,
            """SELECT score_version, label_version, source, count(*) AS rows,
                      count(DISTINCT (trade_date, source, source_id)) AS distinct_events,
                      min(trade_date) AS min_date, max(trade_date) AS max_date
               FROM public.ai_candidate_outcome
               WHERE trade_date BETWEEN %s AND %s
               GROUP BY score_version, label_version, source
               ORDER BY rows DESC LIMIT 100""",
            (min_date, max_date),
        )
        dedup = fetch_dicts(
            cur,
            """SELECT count(*) AS rows,
                      count(DISTINCT (trade_date, source, source_id)) AS distinct_events,
                      count(DISTINCT (trade_date, symbol, coalesce(ref_time, signal_time, entry_time))) AS distinct_symbol_times
               FROM public.ai_candidate_outcome
               WHERE trade_date BETWEEN %s AND %s""",
            (min_date, max_date),
        )[0]

    write_csv(out / "daily_outcomes.csv", daily)
    write_csv(out / "version_source_counts.csv", versions)
    result = {
        "read_only": True,
        "table": "public.ai_candidate_outcome",
        "coverage": {k: str(v) if v is not None else None for k, v in coverage.items()},
        "overall": {k: str(v) if v is not None else None for k, v in overall.items()},
        "deduplication": {k: str(v) if v is not None else None for k, v in dedup.items()},
        "present_requested_columns": present,
        "missing_requested_columns": missing,
        "daily_rows": len(daily),
    }
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
