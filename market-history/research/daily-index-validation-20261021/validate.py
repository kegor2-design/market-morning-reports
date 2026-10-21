#!/usr/bin/env python3
"""Validate retained index snapshots without modifying operational data."""
import csv
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOL = 0.0101  # 0.01 index point plus float32 representation slack


def read(name):
    with (HERE / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(name, fields, rows):
    with (HERE / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def number(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def issue(index, source, kind, day="", count=1, detail="", severity="REVIEW"):
    return {"index": index, "source": source, "issue_type": kind, "date": day,
            "count": count, "detail": detail, "severity": severity}


def main():
    inventory, comparisons, quality, peer = [], [], [], []
    windows = [("FX_CRISIS", "1997-01-01", "1998-12-31"),
               ("DOTCOM_BUST", "2000-01-01", "2001-12-31"),
               ("GFC", "2008-01-01", "2009-12-31"),
               ("COVID", "2020-01-01", "2020-12-31"),
               ("RATE_HIKES", "2022-01-01", "2022-12-31"),
               ("RECENT", "2025-01-01", "2026-10-20")]
    window_rows = []
    for index in ("KOSPI", "KOSDAQ"):
        key = index.lower()
        yahoo_all = read(f"{key}_daily.csv")
        yahoo = [r for r in yahoo_all if number(r["close"]) is not None]
        naver = read(f"naver_{key}_daily.csv")
        sources = (("Naver Finance chart", naver), ("Yahoo Finance chart API", yahoo))
        for source, rows in sources:
            dates = [r["date"] for r in rows]
            duplicate = sum(c - 1 for c in Counter(dates).values() if c > 1)
            quality.append(issue(index, source, "DUPLICATE_TRADE_DATE", count=duplicate, severity="FAIL" if duplicate else "OK"))
            invalid = 0
            extreme = 0
            prev = None
            for r in rows:
                nums = {k: number(r[k]) for k in ("open", "high", "low", "close", "volume")}
                o, h, l, c, v = (nums[k] for k in ("open", "high", "low", "close", "volume"))
                if any(x is None or x <= 0 for x in (o, h, l, c)) or v is None or v < 0 or (h is not None and l is not None and h < l) or (c is not None and h is not None and c > h + TOL) or (c is not None and l is not None and c < l - TOL) or (o is not None and h is not None and o > h + TOL) or (o is not None and l is not None and o < l - TOL):
                    invalid += 1
                    quality.append(issue(index, source, "INVALID_OHLCV", r["date"], detail=str(nums), severity="FAIL"))
                if prev and c and prev[1] and abs(c / prev[1] - 1) > .15:
                    extreme += 1
                    quality.append(issue(index, source, "ABS_RETURN_GT_15PCT", r["date"],
                                         detail=f"prev={prev[0]}:{prev[1]:.2f}; close={c:.2f}; return={(c/prev[1]-1)*100:.2f}%"))
                prev = (r["date"], c)
            quality.append(issue(index, source, "INVALID_OHLCV_TOTAL", count=invalid, severity="FAIL" if invalid else "OK"))
            quality.append(issue(index, source, "ABS_RETURN_GT_15PCT_TOTAL", count=extreme))
            quality.append(issue(index, source, "TRADING_VALUE_UNAVAILABLE", count=len(rows),
                                 detail="Neither source response contains index trading value", severity="UNVERIFIED"))
            inventory.append({"index": index, "start_date": min(dates), "end_date": max(dates), "row_count": len(rows),
                              "source": source, "verification_status": "OFFICIAL_UNVERIFIED",
                              "raw_file": f"{'naver_' if source.startswith('Naver') else 'yahoo_'}{key}_raw.{'xml' if source.startswith('Naver') else 'json'}"})
        a = {r["date"]: r for r in yahoo}
        b = {r["date"]: r for r in naver}
        both = sorted(a.keys() & b.keys())
        mismatch = 0
        for day in both:
            ya, nb = number(a[day]["close"]), number(b[day]["close"])
            delta = abs(ya - nb)
            verdict = "MATCH" if delta <= TOL else "MISMATCH"
            mismatch += verdict == "MISMATCH"
            peer.append({"date": day, "index": index, "yahoo_close": f"{ya:.6f}", "naver_close": f"{nb:.2f}",
                         "absolute_error": f"{delta:.6f}", "relative_error_pct": f"{delta / nb * 100:.6f}",
                         "verdict": verdict})
            if verdict == "MISMATCH":
                quality.append(issue(index, "Yahoo vs Naver", "CLOSE_MISMATCH", day,
                                     detail=f"Yahoo={ya:.6f}; Naver={nb:.2f}; delta={delta:.6f}", severity="FAIL"))
        quality.append(issue(index, "Yahoo vs Naver", "CLOSE_MISMATCH_TOTAL", count=mismatch, severity="FAIL" if mismatch else "OK"))
        for day in sorted(b.keys() - a.keys()):
            kind = "YAHOO_PRE_COVERAGE" if day < min(a) else "YAHOO_MISSING_NAVER_SESSION"
            quality.append(issue(index, "Yahoo Finance chart API", kind, day,
                                 severity="GAP"))
        for label, start, end in windows:
            nr = [d for d in b if start <= d <= end]
            overlap = [r for r in peer if r["index"] == index and start <= r["date"] <= end]
            window_rows.append({"index": index, "period": label, "start_date": start, "end_date": end,
                                "naver_rows": len(nr), "yahoo_overlap": len(overlap),
                                "peer_match": sum(r["verdict"] == "MATCH" for r in overlap),
                                "peer_mismatch": sum(r["verdict"] == "MISMATCH" for r in overlap),
                                "naver_only": len([d for d in nr if d not in a]), "krx_official_compared": 0})
        quality.append(issue(index, "Yahoo Finance chart API", "YAHOO_NULL_PRICE_ROW_TOTAL",
                             count=sum(not r["close"] for r in yahoo_all), severity="GAP"))
        # This is a candidate list, not an official trading calendar. Naver itself
        # cannot certify dates missing from both providers.
        calendar = sorted(b)
        long_gaps = 0
        for x, y in zip(calendar, calendar[1:]):
            missing_weekdays = sum((date.fromisoformat(x) + timedelta(days=i)).weekday() < 5
                                   for i in range(1, (date.fromisoformat(y)-date.fromisoformat(x)).days))
            if missing_weekdays >= 3:
                long_gaps += 1
                quality.append(issue(index, "Naver Finance chart", "UNCONFIRMED_CALENDAR_GAP", x,
                                     detail=f"next={y}; missing_weekdays={missing_weekdays}"))
        quality.append(issue(index, "Naver Finance chart", "UNCONFIRMED_CALENDAR_GAP_TOTAL", count=long_gaps))
        quality.append(issue(index, "KRX official", "OFFICIAL_COMPARISON_UNAVAILABLE", count=0,
                             detail="KRX MDCSTAT00301 HTTP 400 LOGOUT; no account/API key available", severity="UNVERIFIED"))
        print(index, "Naver", len(naver), "Yahoo valid", len(yahoo), "overlap", len(both),
              "peer mismatches", mismatch, "Yahoo missing within coverage", sum(x >= min(a) for x in b.keys()-a.keys()),
              "KRX comparisons", 0)
    write("daily_index_data_inventory.csv", ["index", "start_date", "end_date", "row_count", "source", "verification_status", "raw_file"], inventory)
    write("krx_daily_comparison.csv", ["date", "index", "collected_close", "krx_official_close", "absolute_error", "relative_error_pct", "verdict"], comparisons)
    write("provider_daily_comparison.csv", ["date", "index", "yahoo_close", "naver_close", "absolute_error", "relative_error_pct", "verdict"], peer)
    write("provider_mismatches.csv", ["date", "index", "yahoo_close", "naver_close", "absolute_error", "relative_error_pct", "verdict"],
          [row for row in peer if row["verdict"] == "MISMATCH"])
    write("daily_data_quality_report.csv", ["index", "source", "issue_type", "date", "count", "detail", "severity"], quality)
    write("historical_window_summary.csv", ["index", "period", "start_date", "end_date", "naver_rows", "yahoo_overlap", "peer_match", "peer_mismatch", "naver_only", "krx_official_compared"], window_rows)


if __name__ == "__main__":
    main()
