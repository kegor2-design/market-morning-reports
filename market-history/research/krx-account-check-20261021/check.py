#!/usr/bin/env python3
"""One bounded KRX account check; never persist credentials, cookies, or raw responses."""
from __future__ import annotations

import contextlib
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
import os
from pathlib import Path

import requests

LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
LOGIN_JSP = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
HTTP = []

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "daily-index-validation-20261021"
URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
START, END = "20201005", "20201009"
INDICES = {"KOSPI": ("1", "001"), "KOSDAQ": ("2", "001")}


class ObservedSession(requests.Session):
    def get(self, url, *args, **kwargs):
        response = super().get(url, *args, **kwargs)
        if url in (LOGIN_PAGE, LOGIN_JSP):
            HTTP.append({"step": "login_warmup", "http_status": response.status_code})
        return response

    def post(self, url, *args, **kwargs):
        response = super().post(url, *args, **kwargs)
        if url == LOGIN_URL:
            code = None
            try:
                value = response.json()
                code = value.get("_error_code") if isinstance(value, dict) else None
            except ValueError:
                pass
            HTTP.append({"step": "login", "http_status": response.status_code,
                         "krx_error_code": code if isinstance(code, str) and len(code) <= 12 else None})
        return response


def prices(index: str, name: str) -> dict[str, Decimal]:
    path = PRIOR / name
    with path.open(newline="", encoding="utf-8") as stream:
        return {row["date"]: Decimal(row["close"]) for row in csv.DictReader(stream)
                if row["date"].startswith("2020-10-")}


def main() -> None:
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "method": "MMP PyKRX login_krx; KRX Data Marketplace MDCSTAT00301",
              "sample": {"start": START, "end": END}, "login_http": [],
              "login_success": False, "queries": [], "official_rows": 0,
              "comparisons": 0, "mismatches": 0}
    session = None
    original_session_class = requests.Session
    try:
        if not os.environ.get("KRX_ID") or not os.environ.get("KRX_PW"):
            report["result"] = "CREDENTIALS_MISSING"
            return
        # Importing PyKRX logs in automatically and prints the account ID.
        # Capture all output before import and observe its one normal login flow.
        requests.Session = ObservedSession
        with contextlib.redirect_stdout(io.StringIO()):
            from pykrx.website.comm import auth, webio
        session = webio._session.session if webio._session is not None else None
        report["login_success"] = session is not None
        if session is None:
            report["result"] = "LOGIN_FAILED"
            return
        for index, (group, ticker) in INDICES.items():
            payload = {"bld": "dbms/MDC/STAT/standard/MDCSTAT00301",
                       "locale": "ko_KR", "indIdx": group, "indIdx2": ticker,
                       "strtDd": START, "endDd": END}
            response = session.post(URL, data=payload, headers={
                "User-Agent": auth.USER_AGENT,
                "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
                "X-Requested-With": "XMLHttpRequest",
            }, timeout=25)
            query = {"index": index, "http_status": response.status_code}
            report["queries"].append(query)
            try:
                body = response.json()
            except ValueError:
                query["response_type"] = "non_json"
                query["logout_marker"] = response.text.strip() == "LOGOUT"
                continue
            if not isinstance(body, dict) or not isinstance(body.get("output"), list):
                query["response_type"] = "json_without_output"
                continue
            official = {}
            for row in body["output"]:
                if not isinstance(row, dict):
                    continue
                date = str(row.get("TRD_DD", "")).replace("/", "-")
                close = str(row.get("CLSPRC_IDX", "")).replace(",", "")
                if len(date) == 10 and close:
                    official[date] = Decimal(close)
            query["official_rows"] = len(official)
            report["official_rows"] += len(official)
            naver = prices(index, f"naver_{index.lower()}_daily.csv")
            yahoo = prices(index, f"{index.lower()}_daily.csv")
            for date, close in sorted(official.items()):
                for provider, series in (("Naver", naver), ("Yahoo", yahoo)):
                    if date not in series:
                        continue
                    difference = abs(close - series[date])
                    report["comparisons"] += 1
                    if difference > Decimal("0.0101"):
                        report["mismatches"] += 1
                    with (HERE / "comparison.local.csv").open("a", newline="", encoding="utf-8") as stream:
                        writer = csv.writer(stream)
                        writer.writerow((date, index, provider, str(close), str(series[date]),
                                         str(difference), "MATCH" if difference <= Decimal("0.0101") else "MISMATCH"))
        report["result"] = "OFFICIAL_ROWS_RECEIVED" if report["official_rows"] else "NO_OFFICIAL_ROWS"
    except Exception as exc:
        # Exception messages can include URLs or server content; never persist them.
        report["result"] = "EXCEPTION"
        report["exception_type"] = type(exc).__name__
    finally:
        requests.Session = original_session_class
        report["login_http"] = HTTP
        if session is not None:
            session.close()
        (HERE / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
