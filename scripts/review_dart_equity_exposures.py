#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from build_korea_equity_reference_db import ensure_schema, export_verified_exposures


def parse_verify(values: list[str]) -> list[tuple[int, str]]:
    result = []
    for value in values:
        raw_id, confidence = value.split(":", 1)
        confidence = confidence.upper()
        if confidence not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError(f"invalid confidence: {confidence}")
        result.append((int(raw_id), confidence))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/private/reference/korea_equity_reference.sqlite3")
    parser.add_argument("--exposure-export", default="config/korea_equity_exposures.json")
    parser.add_argument("--verify", nargs="*", default=[], metavar="ID:CONFIDENCE")
    parser.add_argument("--reject", nargs="*", default=[], type=int, metavar="ID")
    args = parser.parse_args()
    conn = sqlite3.connect(args.database)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    now = datetime.now(timezone.utc).isoformat()
    for exposure_id, confidence in parse_verify(args.verify):
        changed = conn.execute("UPDATE exposure SET evidence_status='VERIFIED',confidence=?,exposure_relation='PRODUCER_SERVICE',candidate_eligible=1,updated_at=? WHERE id=? AND evidence_status='REVIEW_REQUIRED'", (confidence, now, exposure_id)).rowcount
        if changed != 1:
            raise RuntimeError(f"exposure {exposure_id} is missing or not REVIEW_REQUIRED")
    for exposure_id in args.reject:
        changed = conn.execute("UPDATE exposure SET evidence_status='REJECTED',updated_at=? WHERE id=? AND evidence_status='REVIEW_REQUIRED'", (now, exposure_id)).rowcount
        if changed != 1:
            raise RuntimeError(f"exposure {exposure_id} is missing or not REVIEW_REQUIRED")
    conn.commit()
    count = export_verified_exposures(conn, Path(args.exposure_export))
    conn.close()
    print(f"verified_runtime_exposures={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
