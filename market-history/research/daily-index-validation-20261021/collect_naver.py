#!/usr/bin/env python3
"""Collect Naver index chart data as an independent auxiliary source."""
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent


def main():
    manifest = []
    for name in ("KOSPI", "KOSDAQ"):
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={name}&timeframe=day&requestType=1&startTime=19960101&endTime=20261020"
        response = requests.get(url, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        raw = HERE / f"naver_{name.lower()}_raw.xml"
        raw.write_bytes(response.content)
        root = ET.fromstring(response.content.decode("euc-kr"))
        chart = root.find(".//chartdata")
        rows = []
        for item in chart.findall("item"):
            parts = item.attrib["data"].split("|")
            if len(parts) != 6:
                continue
            date = f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:8]}"
            if not "1996-01-01" <= date <= "2026-10-20":
                continue
            rows.append(dict(zip(["date", "open", "high", "low", "close", "volume"],
                                 [date] + parts[1:])))
        rows.sort(key=lambda x: x["date"])
        path = HERE / f"naver_{name.lower()}_daily.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
            writer.writeheader()
            writer.writerows(rows)
        manifest.append({"index": name, "url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                         "raw_file": raw.name, "raw_sha256": hashlib.sha256(response.content).hexdigest(),
                         "raw_bytes": len(response.content), "csv_file": path.name,
                         "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(rows),
                         "first": rows[0]["date"] if rows else None,
                         "last": rows[-1]["date"] if rows else None,
                         "origin_time": chart.attrib.get("origintime")})
        print(name, manifest[-1])
    (HERE / "naver_source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
