#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from build_korea_equity_reference_db import ensure_schema, export_verified_exposures, load_env


def api_json(endpoint: str, api_key: str, **params: str) -> dict:
    query = urllib.parse.urlencode({"crtfc_key": api_key, **params})
    with urllib.request.urlopen(f"https://opendart.fss.or.kr/api/{endpoint}?{query}", timeout=60) as response:
        payload = json.loads(response.read())
    if payload.get("status") not in ("000", "013"):
        raise RuntimeError(f"OpenDART {endpoint}: {payload.get('status')} {payload.get('message')}")
    return payload


def business_reports(api_key: str, corp_code: str) -> list[dict]:
    begin = f"{datetime.now(timezone.utc).year - 3}0101"
    payload = api_json(
        "list.json", api_key, corp_code=corp_code, pblntf_detail_ty="A001",
        bgn_de=begin, page_count="100",
    )
    reports = [row for row in payload.get("list", []) if "사업보고서" in row.get("report_nm", "") and "기재정정" not in row.get("report_nm", "")]
    return sorted(reports, key=lambda x: x.get("rcept_dt", ""), reverse=True)


def download_document(api_key: str, receipt_no: str) -> bytes:
    query = urllib.parse.urlencode({"crtfc_key": api_key, "rcept_no": receipt_no})
    with urllib.request.urlopen("https://opendart.fss.or.kr/api/document.xml?" + query, timeout=90) as response:
        raw = response.read()
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        status = re.search(rb"<status>(.*?)</status>", raw)
        message = re.search(rb"<message>(.*?)</message>", raw)
        raise RuntimeError(
            "OpenDART document unavailable: "
            + (status.group(1).decode(errors="replace") if status else "UNKNOWN") + " "
            + (message.group(1).decode("utf-8", errors="replace") if message else "invalid ZIP")
        )
    return raw


def document_text(raw_zip: bytes) -> str:
    chunks = []
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        for name in archive.namelist():
            if not name.lower().endswith((".xml", ".html", ".htm", ".txt")):
                continue
            raw = archive.read(name).decode("utf-8", errors="replace")
            raw = re.sub(r"<[^>]+>", " ", raw)
            chunks.append(html.unescape(re.sub(r"\s+", " ", raw)))
    return " ".join(chunks)


def discover_exposures(text: str, taxonomy: dict) -> list[dict]:
    result = []
    lowered = text.lower()
    for theme in taxonomy.get("themes", []):
        for role in theme.get("roles", []):
            occurrences = []
            for keyword in role.get("keywords", []):
                occurrences.extend((position, keyword) for position in _keyword_positions(lowered, keyword))
            hits = sorted({keyword for _, keyword in occurrences})
            if not hits:
                continue
            candidates = []
            for index, keyword in occurrences[:80]:
                excerpt = text[max(0, index - 180):index + len(keyword) + 300].strip()
                focused_context = text[max(0, index - 90):index + len(keyword) + 140].strip()
                relation, score, signals = classify_exposure_context(focused_context)
                candidates.append((_relation_rank(relation), score, -index, excerpt, relation, signals))
            _, score, _, excerpt, relation, signals = max(candidates)
            result.append({"industry":theme["industry"], "value_chain_role":role["role"], "match_keywords":hits, "excerpt":excerpt,
                           "exposure_relation":relation, "verification_score":score, "verification_signals":signals})
    return result


def iso_date(value: str) -> str:
    value = str(value or "")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}" if len(value) == 8 and value.isdigit() else value


def _keyword_position(lowered_text: str, keyword: str) -> int:
    positions = _keyword_positions(lowered_text, keyword)
    return positions[0] if positions else -1


def _keyword_positions(lowered_text: str, keyword: str) -> list[int]:
    lowered_keyword = keyword.lower()
    if re.fullmatch(r"[a-z0-9]+", lowered_keyword):
        return [match.start() for match in re.finditer(rf"(?<![a-z0-9]){re.escape(lowered_keyword)}(?![a-z0-9])", lowered_text)]
    return [match.start() for match in re.finditer(re.escape(lowered_keyword), lowered_text)]


def _relation_rank(relation: str) -> int:
    return {"PRODUCER_SERVICE":5, "INPUT_DEPENDENCY":4, "CUSTOMER_MARKET":3,
            "AFFILIATE":2, "UNKNOWN":1, "INCIDENTAL_MENTION":0}.get(relation, 0)


def classify_exposure_context(excerpt: str) -> tuple[str, float, list[str]]:
    text = excerpt.lower()
    rules = (
        ("PRODUCER_SERVICE", 0.92, ("주요 제품", "주요제품", "제품 등의 현황", "생산ㆍ판매", "생산·판매", "영업부문", "사업을 영위", "수주한 계약", "서비스를 제공", "매출 유형")),
        ("INPUT_DEPENDENCY", 0.82, ("주요 원재료", "원재료 매입", "매입액", "구매처", "투입되는", "원재료의 가격", "원재료 조달")),
        ("AFFILIATE", 0.72, ("종속기업", "관계기업", "최대주주", "지분율", "계열회사")),
        ("INCIDENTAL_MENTION", 0.70, ("손해배상", "소송", "공정가치", "시장 전망", "수요는", "전망됩니다")),
        ("CUSTOMER_MARKET", 0.58, ("전방산업", "주요 고객", "고객사", "수요 증가", "시장 성장")),
    )
    for relation, score, phrases in rules:
        hits = [phrase for phrase in phrases if phrase in text]
        if hits:
            return relation, score, hits
    return "UNKNOWN", 0.30, []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default="/home/kegor2/mydream2000.env")
    parser.add_argument("--database", default="data/private/reference/korea_equity_reference.sqlite3")
    parser.add_argument("--taxonomy", default="config/korea_value_chain_taxonomy.json")
    parser.add_argument("--exposure-export", default="config/korea_equity_exposures.json")
    parser.add_argument("--cache-dir", default="data/private/reference/dart_documents")
    parser.add_argument("--symbols", nargs="+", required=True)
    args = parser.parse_args()
    load_env(Path(args.env_file))
    api_key = os.getenv("OPENDART_API_KEY") or os.getenv("DART_API_KEY")
    if not api_key:
        raise RuntimeError("DART API key is required")
    taxonomy = json.loads(Path(args.taxonomy).read_text(encoding="utf-8"))
    taxonomy_version = taxonomy.get("contract", "UNKNOWN")
    conn = sqlite3.connect(args.database)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    summary = []
    for raw_symbol in args.symbols:
        symbol = raw_symbol.zfill(6)
        company = conn.execute("SELECT * FROM company WHERE symbol=?", (symbol,)).fetchone()
        if not company or not company["dart_corp_code"]:
            summary.append({"symbol":symbol, "status":"UNMAPPED"})
            continue
        profile = api_json("company.json", api_key, corp_code=company["dart_corp_code"])
        conn.execute("""INSERT INTO company_profile(symbol,dart_industry_code,homepage_url,ir_url,establishment_date,evidence_url,fetched_at)
          VALUES(?,?,?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET dart_industry_code=excluded.dart_industry_code,
          homepage_url=excluded.homepage_url,ir_url=excluded.ir_url,establishment_date=excluded.establishment_date,
          evidence_url=excluded.evidence_url,fetched_at=excluded.fetched_at""",
          (symbol, profile.get("induty_code"), profile.get("hm_url"), profile.get("ir_url"), profile.get("est_dt"),
           f"https://dart.fss.or.kr/dsae001/main.do?autoSearch=true&textCrpNm={company['dart_corp_code']}", now))
        reports = business_reports(api_key, company["dart_corp_code"])
        if not reports:
            summary.append({"symbol":symbol, "status":"NO_BUSINESS_REPORT"})
            conn.execute("INSERT OR REPLACE INTO company_coverage(symbol,collection_status,taxonomy_version,processed_at) VALUES(?,?,?,?)",
                         (symbol, "NO_BUSINESS_REPORT", taxonomy_version, now))
            conn.commit()
            continue
        report = None
        cache = None
        for candidate_report in reports:
            candidate_cache = cache_dir / f"{candidate_report['rcept_no']}.zip"
            if candidate_cache.is_file() and not zipfile.is_zipfile(candidate_cache):
                candidate_cache.unlink()
            try:
                if not candidate_cache.is_file():
                    candidate_cache.write_bytes(download_document(api_key, candidate_report["rcept_no"]))
            except RuntimeError:
                continue
            report, cache = candidate_report, candidate_cache
            break
        if report is None or cache is None:
            summary.append({"symbol":symbol, "status":"NO_AVAILABLE_DOCUMENT"})
            conn.execute("INSERT OR REPLACE INTO company_coverage(symbol,collection_status,taxonomy_version,last_error,processed_at) VALUES(?,?,?,?,?)",
                         (symbol, "NO_AVAILABLE_DOCUMENT", taxonomy_version, "No downloadable annual report in lookback window", now))
            conn.commit()
            continue
        receipt = report["rcept_no"]
        text = document_text(cache.read_bytes())
        discoveries = discover_exposures(text, taxonomy)
        report_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
        conn.execute("INSERT OR REPLACE INTO dart_report(receipt_no,symbol,report_name,receipt_date,report_url,document_cache_path,fetched_at) VALUES(?,?,?,?,?,?,?)",
                     (receipt, symbol, report["report_nm"], report["rcept_dt"], report_url, str(cache), now))
        for item in discoveries:
            conn.execute("""INSERT INTO exposure(symbol,industry,value_chain_role,match_keywords_json,revenue_exposure_pct,
              evidence_type,evidence_url,evidence_date,confidence,evidence_status,evidence_excerpt,created_at,updated_at,
              exposure_relation,candidate_eligible,verification_score,verification_signals_json)
              VALUES(?,?,?,?,NULL,'DART_BUSINESS_REPORT',?,?,'LOW','REVIEW_REQUIRED',?,?,?, ?,0,?,?)
              ON CONFLICT(symbol,industry,value_chain_role,evidence_url) DO UPDATE SET
              match_keywords_json=excluded.match_keywords_json,evidence_excerpt=excluded.evidence_excerpt,
              exposure_relation=CASE WHEN exposure.evidence_status='VERIFIED' THEN exposure.exposure_relation ELSE excluded.exposure_relation END,
              verification_score=excluded.verification_score,
              verification_signals_json=excluded.verification_signals_json,updated_at=excluded.updated_at""",
              (symbol, item["industry"], item["value_chain_role"], json.dumps(item["match_keywords"], ensure_ascii=False),
               report_url, iso_date(report["rcept_dt"]), item["excerpt"], now, now, item["exposure_relation"],
               item["verification_score"], json.dumps(item["verification_signals"], ensure_ascii=False)))
        counts = {relation: sum(item["exposure_relation"] == relation for item in discoveries)
                  for relation in ("PRODUCER_SERVICE", "INPUT_DEPENDENCY", "CUSTOMER_MARKET", "UNKNOWN")}
        conn.execute("""INSERT OR REPLACE INTO company_coverage(
          symbol,collection_status,latest_receipt_no,taxonomy_version,discovery_count,producer_count,input_count,
          customer_count,unknown_count,last_error,processed_at) VALUES(?,?,?,?,?,?,?,?,?,NULL,?)""",
          (symbol, "DOCUMENT_PARSED", receipt, taxonomy_version, len(discoveries), counts["PRODUCER_SERVICE"],
           counts["INPUT_DEPENDENCY"], counts["CUSTOMER_MARKET"], counts["UNKNOWN"], now))
        summary.append({"symbol":symbol, "status":"REVIEW_REQUIRED", "report":receipt, "discoveries":len(discoveries)})
        conn.commit()
    verified = export_verified_exposures(conn, Path(args.exposure_export))
    conn.close()
    print(json.dumps({"results":summary, "verified_runtime_exposures":verified}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
