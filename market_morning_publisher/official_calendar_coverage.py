from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

UTC = timezone.utc


def _parse(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.fromisoformat(text + "T00:00:00+00:00")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@dataclass(frozen=True)
class SourceCoverage:
    source_id: str
    required: bool
    future_events: int
    latest_observed_at: str | None
    status: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_coverage(events: Iterable[Mapping[str, Any]], source_specs: Iterable[Mapping[str, Any]], *, now: str | datetime | None = None) -> dict[str, Any]:
    current = _parse(now) if now is not None else datetime.now(UTC)
    current = current or datetime.now(UTC)
    rows = [dict(x) for x in events]
    results: list[SourceCoverage] = []
    for spec in source_specs:
        sid = str(spec.get("source_id") or "").strip()
        required = bool(spec.get("required"))
        relevant = [x for x in rows if str(x.get("source_id") or "") == sid]
        future = [x for x in relevant if (_parse(x.get("result_expected_at") or x.get("estimated_end_date") or x.get("event_date")) or current) >= current]
        observed_times = [_parse(x.get("observed_at") or x.get("last_verified_at") or x.get("fetched_at")) for x in relevant]
        observed_times = [x for x in observed_times if x]
        latest = max(observed_times) if observed_times else None
        freshness_hours = int(spec.get("freshness_hours") or 168)
        stale = bool(latest and (current - latest).total_seconds() > freshness_hours * 3600)
        if required and len(future) == 0:
            status, reason = "FAIL", "required official source has zero future events"
        elif stale:
            status, reason = "WARN", f"source observation is older than {freshness_hours}h"
        elif len(future) == 0:
            status, reason = "WARN", "no future events observed"
        else:
            status, reason = "OK", f"{len(future)} future event(s)"
        results.append(SourceCoverage(sid, required, len(future), latest.isoformat() if latest else None, status, reason))
    overall = "FAIL" if any(x.status == "FAIL" for x in results) else ("WARN" if any(x.status == "WARN" for x in results) else "OK")
    return {"overall": overall, "sources": [x.to_dict() for x in results]}
