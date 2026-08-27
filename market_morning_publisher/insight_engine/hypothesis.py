from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

VALID_STATUS = {"OPEN", "SUPPORTED", "PARTIAL", "REJECTED", "UNKNOWN"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(row: dict[str, Any]) -> str:
    seed = "|".join([str(row.get("source_lens", "")), str(row.get("hypothesis", "")), str(row.get("event_id", ""))])
    return "HYP-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16].upper()


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush(); os.fsync(handle.fileno()); temp = Path(handle.name)
    os.replace(temp, path)


def upsert_hypothesis(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    record = dict(row)
    record.setdefault("hypothesis_id", _stable_id(record))
    record.setdefault("status", "OPEN")
    if record["status"] not in VALID_STATUS:
        raise ValueError(f"invalid hypothesis status: {record['status']}")
    record.setdefault("created_at", _now())
    record.setdefault("assessments", [])
    rows = {item["hypothesis_id"]: item for item in _read(path)}
    if record["hypothesis_id"] in rows:
        created = rows[record["hypothesis_id"]].get("created_at")
        assessments = rows[record["hypothesis_id"]].get("assessments", [])
        rows[record["hypothesis_id"]] = {**rows[record["hypothesis_id"]], **record, "created_at": created, "assessments": assessments}
    else:
        rows[record["hypothesis_id"]] = record
    _write(path, [rows[key] for key in sorted(rows)])
    return rows[record["hypothesis_id"]]


def assess_hypothesis(path: Path, hypothesis_id: str, *, status: str, evidence: list[str] | None = None, counterevidence: list[str] | None = None, note: str = "") -> dict[str, Any]:
    if status not in VALID_STATUS - {"OPEN"}:
        raise ValueError(f"invalid assessment status: {status}")
    rows = {item["hypothesis_id"]: item for item in _read(path)}
    if hypothesis_id not in rows:
        raise KeyError(hypothesis_id)
    row = rows[hypothesis_id]
    assessment = {
        "assessed_at": _now(), "status": status, "evidence": evidence or [], "counterevidence": counterevidence or [], "note": note,
    }
    row.setdefault("assessments", []).append(assessment)
    row["status"] = status
    row["last_assessed_at"] = assessment["assessed_at"]
    rows[hypothesis_id] = row
    _write(path, [rows[key] for key in sorted(rows)])
    return row


def source_performance(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        source = str(row.get("source_lens") or "UNKNOWN")
        bucket = by_source.setdefault(source, {"total": 0, "closed": 0, "SUPPORTED": 0, "PARTIAL": 0, "REJECTED": 0, "UNKNOWN": 0, "OPEN": 0})
        status = str(row.get("status") or "UNKNOWN")
        bucket["total"] += 1
        bucket[status] = bucket.get(status, 0) + 1
        if status in {"SUPPORTED", "PARTIAL", "REJECTED"}:
            bucket["closed"] += 1
    for bucket in by_source.values():
        closed = bucket["closed"]
        bucket["support_rate"] = round((bucket["SUPPORTED"] + 0.5 * bucket["PARTIAL"]) / closed, 4) if closed else None
        bucket["calibration_status"] = "INSUFFICIENT_SAMPLE" if closed < 10 else "OBSERVED"
    return by_source
