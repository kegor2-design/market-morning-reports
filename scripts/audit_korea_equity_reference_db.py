#!/usr/bin/env python3
"""Produce a repeatable integrity and coverage audit for the Korean equity reference DB."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def scalar(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/private/reference/korea_equity_reference.sqlite3")
    parser.add_argument("--progress", default="data/private/reference/dart_batch_progress.json")
    parser.add_argument("--output", default="reports/korea_equity_reference_audit.json")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.database)
    conn.row_factory = sqlite3.Row
    counts = {name: scalar(conn, sql) for name, sql in {
        "companies":"SELECT COUNT(*) FROM company",
        "mapped":"SELECT COUNT(*) FROM company WHERE mapping_status='MAPPED'",
        "profiles":"SELECT COUNT(*) FROM company_profile",
        "reports":"SELECT COUNT(DISTINCT symbol) FROM dart_report",
        "coverage":"SELECT COUNT(*) FROM company_coverage",
        "exposures":"SELECT COUNT(*) FROM exposure",
        "verified":"SELECT COUNT(*) FROM exposure WHERE evidence_status='VERIFIED'",
        "candidate_eligible":"SELECT COUNT(*) FROM exposure WHERE candidate_eligible=1",
    }.items()}
    integrity = {
        "orphan_exposures": scalar(conn, "SELECT COUNT(*) FROM exposure e LEFT JOIN company c USING(symbol) WHERE c.symbol IS NULL"),
        "invalid_relations": scalar(conn, "SELECT COUNT(*) FROM exposure WHERE exposure_relation NOT IN ('PRODUCER_SERVICE','INPUT_DEPENDENCY','CUSTOMER_MARKET','AFFILIATE','INCIDENTAL_MENTION','UNKNOWN')"),
        "eligible_not_verified_producer": scalar(conn, "SELECT COUNT(*) FROM exposure WHERE candidate_eligible=1 AND (evidence_status!='VERIFIED' OR exposure_relation!='PRODUCER_SERVICE')"),
        "missing_evidence": scalar(conn, "SELECT COUNT(*) FROM exposure WHERE evidence_url='' OR evidence_date='' OR evidence_excerpt IS NULL"),
        "bad_revenue_pct": scalar(conn, "SELECT COUNT(*) FROM exposure WHERE revenue_exposure_pct IS NOT NULL AND (revenue_exposure_pct<0 OR revenue_exposure_pct>100)"),
    }
    relation_counts = dict(conn.execute("SELECT exposure_relation,COUNT(*) FROM exposure GROUP BY exposure_relation"))
    industry_counts = dict(conn.execute("SELECT industry,COUNT(*) FROM exposure GROUP BY industry ORDER BY COUNT(*) DESC"))
    coverage_status = dict(conn.execute("SELECT collection_status,COUNT(*) FROM company_coverage GROUP BY collection_status"))
    progress_path = Path(args.progress)
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.is_file() else {"symbols":{}}
    progress_status = Counter(item.get("status", "UNKNOWN") for item in progress.get("symbols", {}).values())
    complete = counts["companies"] == counts["mapped"] == len(progress.get("symbols", {})) and not any(integrity.values())
    payload = {
        "contract":"MMP_KR_EQUITY_REFERENCE_AUDIT_V1", "generated_at":datetime.now(timezone.utc).isoformat(),
        "complete":complete, "counts":counts, "coverage_pct":{
            "dart_mapping":round(100 * counts["mapped"] / max(1, counts["companies"]), 2),
            "batch_processed":round(100 * len(progress.get("symbols", {})) / max(1, counts["companies"]), 2),
            "document_profile":round(100 * counts["profiles"] / max(1, counts["companies"]), 2),
        }, "integrity":integrity, "coverage_status":coverage_status,
        "progress_status":dict(progress_status), "relation_counts":relation_counts, "industry_counts":industry_counts,
        "limitations":[
            "매출 노출 비중은 공시에서 제품별 수치가 명시되고 검증된 경우에만 채우며, 추정값은 기록하지 않는다.",
            "REVIEW_REQUIRED 발견 건은 장전 후보로 사용하지 않는다. VERIFIED+PRODUCER_SERVICE만 런타임에 반영한다.",
        ]
    }
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    conn.close()
    return 0 if (complete or not args.require_complete) and not any(integrity.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
