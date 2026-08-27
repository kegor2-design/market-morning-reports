#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/private/reference/korea_equity_reference.sqlite3")
    parser.add_argument("--env-file", default="/home/kegor2/mydream2000.env")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--progress", default="data/private/reference/dart_batch_progress.json")
    args = parser.parse_args()
    progress_path = Path(args.progress)
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.is_file() else {"contract":"MMP_DART_EXPOSURE_BATCH_V1", "symbols":{}}
    completed = {symbol for symbol, item in progress["symbols"].items() if item.get("status") in {"REVIEW_REQUIRED", "NO_BUSINESS_REPORT", "NO_AVAILABLE_DOCUMENT"}}
    conn = sqlite3.connect(args.database)
    rows = conn.execute("SELECT symbol FROM company WHERE mapping_status='MAPPED' ORDER BY symbol").fetchall()
    conn.close()
    symbols = [row[0] for row in rows if row[0] not in completed][:max(0, args.limit)]
    script = Path(__file__).with_name("enrich_dart_equity_exposures.py")
    ok = failed = 0
    for symbol in symbols:
        command = [sys.executable, str(script), "--env-file", args.env_file, "--database", args.database,
                   "--taxonomy", "config/korea_value_chain_taxonomy.json", "--exposure-export", "config/korea_equity_exposures.json",
                   "--cache-dir", "data/private/reference/dart_documents", "--symbols", symbol]
        result = subprocess.run(command, text=True, capture_output=True, timeout=240, check=False)
        item = {"updated_at":datetime.now(timezone.utc).isoformat(), "returncode":result.returncode}
        if result.returncode == 0:
            payload = json.loads(result.stdout)
            item.update(payload["results"][0])
            ok += 1
        else:
            item.update({"status":"FAILED", "error":" ".join((result.stderr or result.stdout).split())[-500:]})
            failed += 1
        progress["symbols"][symbol] = item
        progress["updated_at"] = datetime.now(timezone.utc).isoformat()
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"symbol":symbol, "status":item["status"], "ok":ok, "failed":failed}, ensure_ascii=False), flush=True)
    print(json.dumps({"selected":len(symbols), "ok":ok, "failed":failed, "completed_total":len(completed)+ok}, ensure_ascii=False))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
