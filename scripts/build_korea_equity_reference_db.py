#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.removeprefix("export ").split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def parse_corp_code_zip(raw: bytes) -> dict[str, dict]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        xml_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
        root = ElementTree.fromstring(archive.read(xml_name))
    result = {}
    for node in root.findall(".//list"):
        stock_code = (node.findtext("stock_code") or "").strip()
        if not stock_code:
            continue
        result[stock_code.zfill(6)] = {
            "corp_code": (node.findtext("corp_code") or "").strip(),
            "corp_name": (node.findtext("corp_name") or "").strip(),
            "modify_date": (node.findtext("modify_date") or "").strip(),
        }
    return result


def download_corp_codes(api_key: str) -> bytes:
    url = CORP_CODE_URL + "?" + urllib.parse.urlencode({"crtfc_key": api_key})
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS company (
      symbol TEXT PRIMARY KEY, isin TEXT, name TEXT NOT NULL, market TEXT NOT NULL,
      industry_larg_code TEXT, industry_medm_code TEXT, industry_smal_code TEXT,
      kospi200_sector_name TEXT, dart_corp_code TEXT, dart_corp_name TEXT,
      dart_modify_date TEXT, mapping_status TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_company_dart_corp_code ON company(dart_corp_code) WHERE dart_corp_code IS NOT NULL;
    CREATE TABLE IF NOT EXISTS company_profile (
      symbol TEXT PRIMARY KEY REFERENCES company(symbol), dart_industry_code TEXT,
      homepage_url TEXT, ir_url TEXT, establishment_date TEXT,
      evidence_url TEXT NOT NULL, fetched_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS exposure (
      id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL REFERENCES company(symbol),
      industry TEXT NOT NULL, value_chain_role TEXT NOT NULL, match_keywords_json TEXT NOT NULL,
      revenue_exposure_pct REAL, evidence_type TEXT NOT NULL, evidence_url TEXT NOT NULL,
      evidence_date TEXT NOT NULL, confidence TEXT NOT NULL, evidence_status TEXT NOT NULL,
      evidence_excerpt TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(symbol, industry, value_chain_role, evidence_url)
    );
    CREATE TABLE IF NOT EXISTS dart_report (
      receipt_no TEXT PRIMARY KEY, symbol TEXT NOT NULL REFERENCES company(symbol), report_name TEXT NOT NULL,
      receipt_date TEXT NOT NULL, report_url TEXT NOT NULL, document_cache_path TEXT,
      fetched_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS company_coverage (
      symbol TEXT PRIMARY KEY REFERENCES company(symbol), collection_status TEXT NOT NULL,
      latest_receipt_no TEXT, taxonomy_version TEXT,
      discovery_count INTEGER NOT NULL DEFAULT 0, producer_count INTEGER NOT NULL DEFAULT 0,
      input_count INTEGER NOT NULL DEFAULT 0, customer_count INTEGER NOT NULL DEFAULT 0,
      unknown_count INTEGER NOT NULL DEFAULT 0, last_error TEXT, processed_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    exposure_columns = {row[1] for row in conn.execute("PRAGMA table_info(exposure)")}
    if "exposure_relation" not in exposure_columns:
        conn.execute("ALTER TABLE exposure ADD COLUMN exposure_relation TEXT NOT NULL DEFAULT 'UNKNOWN'")
    if "candidate_eligible" not in exposure_columns:
        conn.execute("ALTER TABLE exposure ADD COLUMN candidate_eligible INTEGER NOT NULL DEFAULT 0")
    if "verification_score" not in exposure_columns:
        conn.execute("ALTER TABLE exposure ADD COLUMN verification_score REAL")
    if "verification_signals_json" not in exposure_columns:
        conn.execute("ALTER TABLE exposure ADD COLUMN verification_signals_json TEXT NOT NULL DEFAULT '[]'")
    conn.execute("""UPDATE exposure SET exposure_relation='PRODUCER_SERVICE'
                    WHERE evidence_status='VERIFIED' AND candidate_eligible=1
                      AND exposure_relation!='PRODUCER_SERVICE'""")


def upsert_companies(conn: sqlite3.Connection, master_rows: list[dict], dart_map: dict[str, dict]) -> tuple[int, int]:
    now = datetime.now(timezone.utc).isoformat()
    mapped = 0
    for row in master_rows:
        symbol = str(row.get("symbol", "")).zfill(6)
        dart = dart_map.get(symbol)
        mapped += bool(dart)
        conn.execute("""
          INSERT INTO company(symbol,isin,name,market,industry_larg_code,industry_medm_code,industry_smal_code,
            kospi200_sector_name,dart_corp_code,dart_corp_name,dart_modify_date,mapping_status,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(symbol) DO UPDATE SET
            isin=excluded.isin,name=excluded.name,market=excluded.market,
            industry_larg_code=excluded.industry_larg_code,industry_medm_code=excluded.industry_medm_code,
            industry_smal_code=excluded.industry_smal_code,kospi200_sector_name=excluded.kospi200_sector_name,
            dart_corp_code=excluded.dart_corp_code,dart_corp_name=excluded.dart_corp_name,
            dart_modify_date=excluded.dart_modify_date,mapping_status=excluded.mapping_status,updated_at=excluded.updated_at
        """, (
            symbol, row.get("isin"), row.get("name"), row.get("market"), row.get("industry_larg_code"),
            row.get("industry_medm_code"), row.get("industry_smal_code"), row.get("kospi200_sector_name"),
            dart.get("corp_code") if dart else None, dart.get("corp_name") if dart else None,
            dart.get("modify_date") if dart else None, "MAPPED" if dart else "UNMAPPED", now,
        ))
    conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('contract','MMP_KR_EQUITY_REFERENCE_DB_V1')")
    conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('updated_at',?)", (now,))
    return len(master_rows), mapped


def export_verified_exposures(conn: sqlite3.Connection, output: Path) -> int:
    rows = conn.execute("""
      SELECT symbol,industry,value_chain_role,exposure_relation,candidate_eligible,match_keywords_json,
             revenue_exposure_pct,evidence_type,evidence_url,evidence_date,confidence,evidence_status
      FROM exposure WHERE evidence_status='VERIFIED' ORDER BY symbol,industry,value_chain_role
    """).fetchall()
    payload = []
    for row in rows:
        item = dict(row)
        item["candidate_eligible"] = bool(item["candidate_eligible"])
        item["match_keywords"] = json.loads(item.pop("match_keywords_json"))
        raw_date = str(item.get("evidence_date") or "")
        if len(raw_date) == 8 and raw_date.isdigit():
            item["evidence_date"] = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        payload.append(item)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"contract":"MMP_KR_EQUITY_EXPOSURE_V1", "description":"Evidence-backed runtime export from the private reference DB.", "rows":payload}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default="/home/kegor2/mydream2000.env")
    parser.add_argument("--master", default="data/private/reference/korea_equity_master.json")
    parser.add_argument("--database", default="data/private/reference/korea_equity_reference.sqlite3")
    parser.add_argument("--exposure-export", default="config/korea_equity_exposures.json")
    parser.add_argument("--corp-code-cache", default="data/private/reference/dart_corp_codes.zip")
    parser.add_argument("--refresh-corp-codes", action="store_true")
    args = parser.parse_args()
    load_env(Path(args.env_file))
    api_key = os.getenv("OPENDART_API_KEY") or os.getenv("DART_API_KEY")
    if not api_key:
        raise RuntimeError("OPENDART_API_KEY or DART_API_KEY is required")
    master = json.loads(Path(args.master).read_text(encoding="utf-8"))["rows"]
    cache = Path(args.corp_code_cache)
    if args.refresh_corp_codes or not cache.is_file():
        raw = download_corp_codes(api_key)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
    else:
        raw = cache.read_bytes()
    dart_map = parse_corp_code_zip(raw)
    database = Path(args.database)
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    total, mapped = upsert_companies(conn, master, dart_map)
    conn.commit()
    exposures = export_verified_exposures(conn, Path(args.exposure_export))
    conn.close()
    print(json.dumps({"database":str(database), "companies":total, "dart_mapped":mapped, "unmapped":total-mapped, "verified_exposures":exposures}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
