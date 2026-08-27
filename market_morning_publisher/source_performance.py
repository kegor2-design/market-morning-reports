from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .event_lifecycle import EventRecord, Evidence


def build_source_performance(records: Iterable[EventRecord]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "source_registry_id": None,
        "supported_claims": 0,
        "confirmed": 0,
        "denied": 0,
        "expired": 0,
        "open": 0,
    })
    for record in records:
        for raw in record.evidence:
            ev = Evidence.from_dict(raw)
            sid = str(ev.metadata.get("source_registry_id") or "").strip()
            if not sid:
                continue
            row = stats[sid]
            row["source_registry_id"] = sid
            if ev.stance != "SUPPORT":
                continue
            row["supported_claims"] += 1
            if record.status == "REJECTED":
                row["denied"] += 1
            elif record.status == "EXPIRED":
                row["expired"] += 1
            elif record.truth_class == "OFFICIAL_FACT" and record.status in {"VERIFIED", "ACTIVE", "RESOLVING", "RESOLVED"}:
                row["confirmed"] += 1
            else:
                row["open"] += 1
    out = []
    for sid, row in stats.items():
        decided = row["confirmed"] + row["denied"]
        row["verification_hit_rate"] = (row["confirmed"] / decided) if decided else None
        out.append(row)
    return sorted(out, key=lambda x: x["source_registry_id"] or "")
