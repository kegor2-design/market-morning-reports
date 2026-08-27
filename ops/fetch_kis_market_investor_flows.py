#!/usr/bin/env python3
"""Fetch full-market KOSPI/KOSDAQ investor flows from the official KIS market API."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def number(value):
    text = str(value or "").strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def first(row: dict, *keys):
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--env-file", default="/home/kegor2/mydream2000.env")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    load_env(Path(args.env_file))
    sys.path.insert(0, "/home/kegor2/MyDream2000")
    from mydream2000.infrastructure import settings as config
    from mydream2000.infrastructure.broker.kis_auth import AUTH

    token = AUTH.get_access_token()
    url = str(config.REST_BASE_URL).rstrip("/") + "/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market"
    headers = {"authorization": f"Bearer {token}", "appkey": str(config.APP_KEY),
               "appsecret": str(config.APP_SECRET), "tr_id": "FHPTJ04040000", "custtype": "P"}
    date_compact = args.date.replace("-", "")
    markets = (("KOSPI", "KSP", "0001"), ("KOSDAQ", "KSQ", "1001"))
    results = []
    for name, market_code, industry_code in markets:
        params = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": industry_code,
                  "FID_INPUT_DATE_1": date_compact, "FID_INPUT_ISCD_1": market_code,
                  "FID_INPUT_DATE_2": date_compact, "FID_INPUT_ISCD_2": industry_code}
        response = requests.get(url, headers=headers, params=params, timeout=(5, 20))
        response.raise_for_status()
        body = response.json()
        if str(body.get("rt_cd")) != "0":
            raise RuntimeError(f"{name} KIS error {body.get('msg_cd')}: {body.get('msg1')}")
        rows = body.get("output") or []
        row = next((item for item in rows if str(first(item, "stck_bsop_date", "bsop_date") or "").replace("-", "") == date_compact), rows[0] if rows else None)
        if not row:
            raise RuntimeError(f"{name} returned no market investor row")
        results.append({
            "market": name, "market_code": market_code, "trade_date": args.date,
            "unit": "KRW_100M", "unit_label": "억원",
            "foreign_net_buy": number(first(row, "frgn_ntby_tr_pbmn", "frgn_ntby_amt", "frgn_ntby_val")),
            "institution_net_buy": number(first(row, "orgn_ntby_tr_pbmn", "istt_ntby_amt", "inst_ntby_amt")),
            "individual_net_buy": number(first(row, "prsn_ntby_tr_pbmn", "indv_ntby_amt", "personal_ntby_amt")),
            "raw_fields": {key: value for key, value in row.items() if "ntby" in key.lower() or "date" in key.lower()},
        })
    if any(item[key] is None for item in results for key in ("foreign_net_buy", "institution_net_buy", "individual_net_buy")):
        raise RuntimeError("KIS response fields did not match the verified market-flow contract")
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    payload["investor_flows"] = {"scope": "FULL_MARKET", "provider": "Korea Investment Open API",
                                 "contract": "KIS_MARKET_INVESTOR_DAILY_V1", "markets": results}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output, "markets": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
