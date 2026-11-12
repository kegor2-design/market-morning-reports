"""Read-only audit of indicator 116 first-vintage dates and Korean session proxy.

The seven-day lag is an exploratory sensitivity rule, never PIT evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from bisect import bisect_left
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree
from zoneinfo import ZoneInfo


SERIES = ("DGS2", "DGS10")
FIELDS = (
    "observation_date", "dgs2_first_vintage_date", "dgs10_first_vintage_date",
    "both_vintage_dates_completed_by_kst_0900_date", "us_eastern_offset_on_observation_date",
    "strict_pit_status", "strict_blocker", "exploratory_lag_days",
    "exploratory_first_proxy_session", "proxy_calendar_status",
    "differs_from_2026_10_27_snapshot",
)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def vintage_day_completed_by_kst_0900(vintage: date) -> date:
    """First KST 09:00 after the entire U.S. Eastern vintage day has ended.

    This proves only that the calendar day elapsed, not that FRED posted data.
    """
    close = datetime.combine(vintage + timedelta(days=1), time(),
                             ZoneInfo("America/New_York"))
    kst = close.astimezone(ZoneInfo("Asia/Seoul"))
    return kst.date() if kst.time() <= time(9) else kst.date() + timedelta(days=1)


def snapshot_differs(snapshot: dict, initial: dict, day: str) -> bool:
    return day in snapshot and snapshot[day] != initial[day]["value"]


def load_series(root: Path, series: str) -> tuple[dict, list]:
    rows = {}
    manifest_hashes = []
    for year in range(2010, 2027):
        file = root / series / f"{year}.json"
        manifest = json.loads(file.with_suffix(".manifest.json").read_text())
        raw = file.read_bytes()
        payload = json.loads(raw)
        observations = payload["observations"]
        assert manifest["series"] == series and manifest["year"] == year
        assert manifest["sha256"] == sha256(raw) and manifest["bytes"] == len(raw)
        assert manifest["rows"] == len(observations)
        assert payload["output_type"] == 4
        manifest_hashes.append(manifest["sha256"])
        for row in observations:
            assert row["date"] not in rows, (series, row["date"])
            assert date.fromisoformat(row["realtime_start"]) >= date.fromisoformat(row["date"])
            rows[row["date"]] = row
    return rows, manifest_hashes


def compare_treasury(data: dict, paths: list[Path]) -> dict:
    """Compare current Treasury archive values; archive has no historical PIT clocks."""
    counts = Counter()
    differences = []
    for path in paths:
        with path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                row = {key.lower(): value for key, value in row.items()}
                pattern = "%m/%d/%Y" if len(row["date"].split("/")[-1]) == 4 else "%m/%d/%y"
                day = datetime.strptime(row["date"], pattern).date().isoformat()
                for series, column in (("DGS2", "2 yr"), ("DGS10", "10 yr")):
                    if day not in data[series] or data[series][day]["value"] == "." or not row[column]:
                        continue
                    counts["overlap_" + series] += 1
                    if Decimal(data[series][day]["value"]) != Decimal(row[column]):
                        counts["different_" + series] += 1
                        differences.append((series, day))
    return {"counts": dict(counts), "difference_dates_first_20": differences[:20],
            "archive_sha256": {p.name: sha256(p.read_bytes()) for p in paths},
            "status": "CURRENT_ARCHIVE_COMPARISON_NOT_HISTORICAL_VINTAGE_OR_POSTING_TIME"}


def compare_treasury_xml(data: dict, paths: list[Path]) -> dict:
    """Check current official annual XML values; its updated tag is not row PIT time."""
    ns = {"a": "http://www.w3.org/2005/Atom",
          "d": "http://schemas.microsoft.com/ado/2007/08/dataservices"}
    counts = Counter()
    differences = []
    hashes = {}
    for path in paths:
        raw = path.read_bytes()
        hashes[path.name] = sha256(raw)
        root = ElementTree.fromstring(raw)
        seen = set()
        for entry in root.findall("a:entry", ns):
            day_node = entry.find(".//d:NEW_DATE", ns)
            if day_node is None or not day_node.text:
                raise ValueError("Treasury entry lacks observation date")
            day = day_node.text[:10]
            if day in seen:
                raise ValueError(f"Duplicate Treasury observation: {day}")
            seen.add(day)
            counts["treasury_rows"] += 1
            for series, field in (("DGS2", "BC_2YEAR"), ("DGS10", "BC_10YEAR")):
                node = entry.find(f".//d:{field}", ns)
                if day not in data[series] or data[series][day]["value"] == "." or node is None or not node.text:
                    continue
                counts["overlap_" + series] += 1
                if Decimal(data[series][day]["value"]) != Decimal(node.text):
                    counts["different_" + series] += 1
                    differences.append((series, day))
    return {"counts": dict(counts), "difference_dates": differences,
            "xml_sha256": hashes,
            "status": "CURRENT_XML_COMPARISON_NOT_HISTORICAL_VINTAGE_OR_POSTING_TIME"}


def build(raw_root: Path, latest_root: Path, kospi_csv: Path, kospi_hash: str,
          output: Path, treasury_archives: list[Path] | None = None,
          treasury_xml: list[Path] | None = None) -> dict:
    data = {}
    hashes = {}
    for series in SERIES:
        data[series], hashes[series] = load_series(raw_root, series)
    assert all(len(data[s]) == 4387 for s in SERIES)
    assert all(data["DGS2"][d]["value"] != "." for d in ("2015-04-01", "2015-04-02"))
    revision_comparison = {}
    latest_values = {}
    for series in SERIES:
        latest_file = latest_root / f"fred_{series}.json"
        latest = json.loads(latest_file.read_bytes())
        latest_rows = {r["date"]: r["value"] for r in latest["observations"]}
        latest_values[series] = latest_rows
        overlap = sorted(set(data[series]) & set(latest_rows))
        changed = [d for d in overlap if data[series][d]["value"] != latest_rows[d]]
        revision_comparison[series] = {
            "latest_snapshot_sha256": sha256(latest_file.read_bytes()),
            "latest_retrieved_at_utc": latest["retrieved_at_utc"],
            "overlap_rows": len(overlap), "changed_rows": len(changed),
            "changed_dates_first_20": changed[:20],
            "status": "TWO_SNAPSHOT_COMPARISON_NOT_FULL_REVISION_HISTORY",
        }

    assert sha256(kospi_csv.read_bytes()) == kospi_hash
    with kospi_csv.open(newline="") as stream:
        sessions = sorted(date.fromisoformat(r["date"]) for r in csv.DictReader(stream))
    assert len(sessions) == len(set(sessions)) == 7730

    counts = Counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for day in sorted(set(data["DGS2"]) & set(data["DGS10"])):
            r2, r10 = data["DGS2"][day], data["DGS10"][day]
            if "." in (r2["value"], r10["value"]):
                continue
            # The vintage is a calendar date, not a publication timestamp.
            vintages = [date.fromisoformat(r["realtime_start"]) for r in (r2, r10)]
            latest = max(vintages)
            threshold = latest + timedelta(days=7)
            pos = bisect_left(sessions, threshold)
            proxy = sessions[pos].isoformat() if pos < len(sessions) else ""
            eastern_noon = datetime.combine(date.fromisoformat(day), time(12), ZoneInfo("America/New_York"))
            # Date-only vintage may have appeared at any clock time on that date.
            row = {
                "observation_date": day,
                "dgs2_first_vintage_date": vintages[0].isoformat(),
                "dgs10_first_vintage_date": vintages[1].isoformat(),
                "both_vintage_dates_completed_by_kst_0900_date": vintage_day_completed_by_kst_0900(latest).isoformat(),
                "us_eastern_offset_on_observation_date": eastern_noon.strftime("%z"),
                "strict_pit_status": "BLOCKED",
                "strict_blocker": "NO_HISTORICAL_ACTUAL_POSTING_AND_INGEST_TIMESTAMPS",
                "exploratory_lag_days": 7,
                "exploratory_first_proxy_session": proxy,
                "proxy_calendar_status": "NAVER_SNAPSHOT_UNVERIFIED_KRX" if proxy else "OUTSIDE_PROXY_RANGE",
                "differs_from_2026_10_27_snapshot": str(any(
                    snapshot_differs(latest_values[s], data[s], day) for s in SERIES)).lower(),
            }
            writer.writerow(row)
            counts["paired_numeric"] += 1
            counts[row["proxy_calendar_status"]] += 1
            counts[row["us_eastern_offset_on_observation_date"]] += 1
            if day in ("2015-04-01", "2015-04-02"):
                counts["same_day_2015_exception"] += int(latest.isoformat() == day)
    assert counts["paired_numeric"] == 4204
    assert counts["same_day_2015_exception"] == 2
    return {"counts": dict(counts), "matrix_sha256": sha256(output.read_bytes()),
            "revision_comparison": revision_comparison,
            "treasury_comparison": compare_treasury(data, treasury_archives or []),
            "treasury_xml_comparison": compare_treasury_xml(data, treasury_xml or []),
            "input_manifest_sha256": hashes, "kospi_csv_sha256": kospi_hash}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--latest-root", type=Path, required=True)
    parser.add_argument("--kospi-csv", type=Path, required=True)
    parser.add_argument("--kospi-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--treasury-archive", type=Path, action="append", default=[])
    parser.add_argument("--treasury-xml", type=Path, action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(build(args.raw_root, args.latest_root, args.kospi_csv,
                           args.kospi_sha256, args.output, args.treasury_archive,
                           args.treasury_xml), indent=2))


if __name__ == "__main__":
    main()
