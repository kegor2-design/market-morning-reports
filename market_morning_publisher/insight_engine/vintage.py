from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _atomic_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def upsert_vintage(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    required = ("metric_id", "observation_date", "released_at", "value")
    missing = [key for key in required if record.get(key) is None]
    if missing:
        raise ValueError(f"missing vintage fields: {missing}")
    rows = _read_jsonl(path)
    key = (
        str(record["metric_id"]),
        str(record["observation_date"]),
        str(record["released_at"]),
        str(record.get("source", "")),
    )
    keyed = {
        (str(row["metric_id"]), str(row["observation_date"]), str(row["released_at"]), str(row.get("source", ""))): row
        for row in rows
    }
    keyed[key] = dict(record)
    ordered = sorted(keyed.values(), key=lambda x: (x["metric_id"], x["observation_date"], x["released_at"], str(x.get("source", ""))))
    _atomic_jsonl(path, ordered)
    return dict(record)


def available_as_of(rows: Iterable[dict[str, Any]], metric_id: str, as_of: str) -> list[dict[str, Any]]:
    cutoff = _parse_dt(as_of)
    eligible = [
        row for row in rows
        if row.get("metric_id") == metric_id and _parse_dt(str(row["released_at"])) <= cutoff
    ]
    # For each observation date retain the latest revision that was actually known by the cutoff.
    by_observation: dict[str, dict[str, Any]] = {}
    for row in eligible:
        observation = str(row["observation_date"])
        previous = by_observation.get(observation)
        if previous is None or _parse_dt(str(row["released_at"])) > _parse_dt(str(previous["released_at"])):
            by_observation[observation] = row
    return [by_observation[key] for key in sorted(by_observation)]


def latest_value_as_of(path: Path, metric_id: str, as_of: str) -> dict[str, Any] | None:
    rows = available_as_of(_read_jsonl(path), metric_id, as_of)
    if not rows:
        return None
    return max(rows, key=lambda row: str(row["observation_date"]))
