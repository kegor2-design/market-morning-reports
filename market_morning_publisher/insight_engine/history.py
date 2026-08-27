from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

DEFAULT_WINDOWS = [1, 5, 20, 60, 250]


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    cases = list(cases or [])
    ids = [row.get("case_id") for row in cases]
    if any(not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("historical case_id must be non-empty and unique")
    return cases


def find_analog_cases(cases: Iterable[dict[str, Any]], tags: Iterable[str], *, limit: int = 5) -> list[dict[str, Any]]:
    wanted = {str(x).upper() for x in tags if x}
    scored = []
    for case in cases:
        case_tags = {str(x).upper() for x in case.get("tags", [])}
        intersection = len(wanted & case_tags)
        union = len(wanted | case_tags) or 1
        score = intersection / union
        if intersection:
            scored.append((score, intersection, str(case.get("start_date", "")), case))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return [{**row, "similarity_score": round(score, 4)} for score, _, _, row in scored[:limit]]


def _load_series(path: Path, column: str) -> list[tuple[date, float]]:
    if not path.exists():
        return []
    rows: list[tuple[date, float]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_date, raw_value = row.get("date"), row.get(column)
            if not raw_date or raw_value in {None, ""}:
                continue
            try:
                rows.append((date.fromisoformat(raw_date[:10]), float(raw_value)))
            except (ValueError, TypeError):
                continue
    return sorted(rows)


def _last_on_or_before(rows: list[tuple[date, float]], target: date) -> tuple[date, float] | None:
    candidates = [row for row in rows if row[0] <= target]
    return candidates[-1] if candidates else None


def _nearest_on_or_after_anchor(rows: list[tuple[date, float]], target: date, anchor: date) -> tuple[date, float] | None:
    candidates = [row for row in rows if row[0] >= anchor]
    return min(candidates, key=lambda row: abs((row[0] - target).days)) if candidates else None


def _delta(base: float, value: float) -> dict[str, float | None]:
    absolute = value - base
    percent = None if base == 0 else 100.0 * absolute / abs(base)
    return {"absolute_change": round(absolute, 6), "pct_change": round(percent, 4) if percent is not None else None}


def build_case_market_snapshot(root: Path, case: dict[str, Any], *, windows: list[int] | None = None) -> dict[str, Any]:
    windows = windows or list(DEFAULT_WINDOWS)
    anchor = date.fromisoformat(case.get("anchor_date") or case["start_date"])
    series_result: dict[str, Any] = {}
    for spec in case.get("series", []):
        series_id = spec["id"]
        rows = _load_series(root / spec["path"], spec["column"])
        baseline = _last_on_or_before(rows, anchor - timedelta(days=1)) or _last_on_or_before(rows, anchor)
        if not baseline:
            series_result[series_id] = {"status": "UNKNOWN", "reason": "baseline unavailable"}
            continue
        points = {}
        for days in windows:
            target = anchor + timedelta(days=days)
            observed = _nearest_on_or_after_anchor(rows, target, anchor)
            if not observed:
                points[f"D+{days}"] = {"status": "UNKNOWN"}
                continue
            points[f"D+{days}"] = {
                "status": "OBSERVED",
                "target_date": target.isoformat(),
                "observed_date": observed[0].isoformat(),
                "value": observed[1],
                **_delta(baseline[1], observed[1]),
            }
        series_result[series_id] = {
            "status": "OBSERVED",
            "baseline_date": baseline[0].isoformat(),
            "baseline_value": baseline[1],
            "points": points,
        }
    return {
        "case_id": case["case_id"],
        "title_ko": case.get("title_ko"),
        "anchor_date": anchor.isoformat(),
        "point_in_time_status": case.get("point_in_time_status", "BACKFILL_REQUIRED"),
        "series": series_result,
    }
