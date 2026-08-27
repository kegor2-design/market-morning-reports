#!/usr/bin/env python3
"""Rebuild review-required exposures from locally cached DART annual reports."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from build_korea_equity_reference_db import ensure_schema, export_verified_exposures
from enrich_dart_equity_exposures import discover_exposures, document_text, iso_date


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/private/reference/korea_equity_reference.sqlite3")
    parser.add_argument("--taxonomy", default="config/korea_value_chain_taxonomy.json")
    parser.add_argument("--exposure-export", default="config/korea_equity_exposures.json")
    args = parser.parse_args()
    taxonomy = json.loads(Path(args.taxonomy).read_text(encoding="utf-8"))
    taxonomy_version = taxonomy.get("contract", "UNKNOWN")
    conn = sqlite3.connect(args.database)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    reports = conn.execute("""SELECT r.* FROM dart_report r JOIN (
      SELECT symbol,MAX(receipt_date) receipt_date FROM dart_report GROUP BY symbol
    ) latest ON latest.symbol=r.symbol AND latest.receipt_date=r.receipt_date ORDER BY r.symbol""").fetchall()
    now = datetime.now(timezone.utc).isoformat()
    parsed = skipped = discoveries_total = 0
    for report in reports:
        cache = Path(report["document_cache_path"] or "")
        if not cache.is_file():
            skipped += 1
            continue
        discoveries = discover_exposures(document_text(cache.read_bytes()), taxonomy)
        conn.execute("DELETE FROM exposure WHERE symbol=? AND evidence_url=? AND evidence_status='REVIEW_REQUIRED'",
                     (report["symbol"], report["report_url"]))
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
              (report["symbol"], item["industry"], item["value_chain_role"], json.dumps(item["match_keywords"], ensure_ascii=False),
               report["report_url"], iso_date(report["receipt_date"]), item["excerpt"], now, now, item["exposure_relation"],
               item["verification_score"], json.dumps(item["verification_signals"], ensure_ascii=False)))
        counts = {relation: sum(item["exposure_relation"] == relation for item in discoveries)
                  for relation in ("PRODUCER_SERVICE", "INPUT_DEPENDENCY", "CUSTOMER_MARKET", "UNKNOWN")}
        conn.execute("""INSERT OR REPLACE INTO company_coverage(symbol,collection_status,latest_receipt_no,taxonomy_version,
          discovery_count,producer_count,input_count,customer_count,unknown_count,last_error,processed_at)
          VALUES(?,?,?,?,?,?,?,?,?,NULL,?)""", (report["symbol"], "DOCUMENT_PARSED", report["receipt_no"], taxonomy_version,
          len(discoveries), counts["PRODUCER_SERVICE"], counts["INPUT_DEPENDENCY"], counts["CUSTOMER_MARKET"],
          counts["UNKNOWN"], now))
        parsed += 1
        discoveries_total += len(discoveries)
        if parsed % 100 == 0:
            conn.commit()
            print(json.dumps({"parsed":parsed,"discoveries":discoveries_total}, ensure_ascii=False), flush=True)
    conn.commit()
    verified = export_verified_exposures(conn, Path(args.exposure_export))
    conn.close()
    print(json.dumps({"reports":len(reports),"parsed":parsed,"skipped":skipped,
                      "discoveries":discoveries_total,"verified_runtime_exposures":verified}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
