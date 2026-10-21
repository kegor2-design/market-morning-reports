#!/usr/bin/env python3
"""One-off, reproducible index collection; writes only in this research folder."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

HERE = Path(__file__).resolve().parent
START = int(datetime(1996, 1, 1, tzinfo=timezone.utc).timestamp())
END = int(datetime(2026, 10, 21, tzinfo=timezone.utc).timestamp())
UA = {"User-Agent": "Mozilla/5.0"}


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    manifest = []
    for name, symbol in (("KOSPI", "^KS11"), ("KOSDAQ", "^KQ11")):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?period1={START}&period2={END}&interval=1d&events=history"
        response = requests.get(url, headers=UA, timeout=90)
        response.raise_for_status()
        raw_path = HERE / f"yahoo_{name.lower()}_raw.json"
        raw_path.write_bytes(response.content)
        payload = response.json()["chart"]["result"][0]
        timestamps = payload.get("timestamp") or []
        quote_rows = payload["indicators"]["quote"][0]
        rows = []
        for i, stamp in enumerate(timestamps):
            day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
            if not "1996-01-01" <= day <= "2026-10-20":
                continue
            def value(key):
                vals = quote_rows.get(key) or []
                return vals[i] if i < len(vals) else None
            rows.append({"date": day, "index": name, "open": value("open"), "high": value("high"),
                         "low": value("low"), "close": value("close"), "volume": value("volume"),
                         "trading_value": "", "source": "Yahoo Finance chart API"})
        fields = ["date", "index", "open", "high", "low", "close", "volume", "trading_value", "source"]
        csv_path = HERE / f"{name.lower()}_daily.csv"
        write_csv(csv_path, rows, fields)
        manifest.append({"index": name, "url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                         "raw_file": raw_path.name, "raw_sha256": hashlib.sha256(response.content).hexdigest(),
                         "raw_bytes": len(response.content), "csv_file": csv_path.name,
                         "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                         "rows": len(rows), "first": rows[0]["date"] if rows else None,
                         "last": rows[-1]["date"] if rows else None,
                         "meta_first_trade_date": payload.get("meta", {}).get("firstTradeDate")})
        print(name, manifest[-1])
    (HERE / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
