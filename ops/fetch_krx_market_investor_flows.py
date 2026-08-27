#!/usr/bin/env python3
"""Fetch final full-market KOSPI/KOSDAQ investor flows from KRX statistics CSV."""
from __future__ import annotations

import argparse
import csv
import io
import json
import http.cookiejar
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://data.krx.co.kr"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def post(path: str, values: dict[str, str], accept: str) -> bytes:
    request = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(values).encode(), headers={
        "Accept": accept,
        "Origin": BASE, "Referer": BASE + "/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    return OPENER.open(request, timeout=25).read()


def fetch_market(day: str, market: str, market_id: str) -> dict:
    params = {"locale": "ko_KR", "inqTpCd": "1", "trdVolVal": "2", "askBid": "3",
              "mktId": market_id, "strtDd": day, "endDd": day, "share": "2", "money": "3",
              "csvxls_isNo": "false", "name": "fileDown", "url": "dbms/MDC/STAT/standard/MDCSTAT02201"}
    otp = post("/comm/fileDn/GenerateOTP/generate.cmd", params, "text/plain, */*; q=0.01").decode().strip()
    raw = post("/comm/fileDn/download_csv/download.cmd", {"code": otp}, "text/csv, text/plain, */*; q=0.01")
    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))[2:]
    aliases = {"institution": ("기관합계", "기관 합계"), "individual": ("개인",), "foreign": ("외국인", "외국인합계", "외국인 합계")}
    parsed = {}
    for key, names in aliases.items():
        row = next((r for r in rows if r and r[0].strip() in names), None)
        if not row or len(row) < 7:
            raise RuntimeError(f"KRX {market} missing {key} participant")
        parsed[key] = {"net_buy_quantity": int(row[3].replace(",", "")),
                       "net_buy_amount_krw": int(row[6].replace(",", "")) * 1_000_000}
    return {"market": market, "trade_date": f"{day[:4]}-{day[4:6]}-{day[6:]}", "unit": "KRW",
            "provider": "KRX Data Marketplace MDCSTAT02201", "quality": "FINAL_AFTER_18_KST", **parsed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    compact = args.date.replace("-", "")
    markets = [fetch_market(compact, "KOSPI", "STK"), fetch_market(compact, "KOSDAQ", "KSQ")]
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    payload["investor_flows"] = {"scope": "FULL_MARKET", "provider": "KRX Data Marketplace",
                                 "contract": "KRX_MDCSTAT02201_V1", "markets": markets}
    output = Path(args.output); output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "markets": markets}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
