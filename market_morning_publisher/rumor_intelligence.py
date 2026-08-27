from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json
import re

from .event_lifecycle import EventRecord, merge_candidate, expire_or_resolve, project_calendar_item, event_fingerprint

UTC = timezone.utc

RUMOR_SOURCE_TYPES = {"YOUTUBE", "YOUTUBE_EXPERT", "TELEGRAM", "TELEGRAM_NAMED", "TELEGRAM_ANON", "NEWS_TIP", "COMMUNITY", "RUMOR"}


@dataclass
class RumorCandidate:
    title: str
    claim: str
    source_type: str
    source_id: str
    published_at: str | None = None
    url: str | None = None
    source_name: str | None = None
    author: str | None = None
    event_type: str = "OTHER"
    entities: list[str] | None = None
    event_date: str | None = None
    estimated_end_date: str | None = None
    impact_until: str | None = None
    impact_summary: str | None = None
    resolution_condition: str | None = None
    linked_mi: list[str] | None = None
    expected_direction: dict[str, str] | None = None
    decision_card: dict[str, Any] | None = None
    stance: str = "SUPPORT"
    attributable: bool = False
    metadata: dict[str, Any] | None = None

    def to_event_candidate(self) -> dict[str, Any]:
        evidence = asdict(self)
        evidence["official"] = False
        return {
            "title": self.title,
            "claim": self.claim,
            "event_type": self.event_type,
            "entities": self.entities or [],
            "event_date": self.event_date,
            "estimated_end_date": self.estimated_end_date,
            "impact_until": self.impact_until,
            "impact_summary": self.impact_summary,
            "resolution_condition": self.resolution_condition,
            "linked_mi": self.linked_mi or [],
            "expected_direction": self.expected_direction or {},
            "decision_card": self.decision_card or {},
            "evidence": [evidence],
            # Rumors are never activated merely on ingest.
            "activate": False,
        }


def _safe_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_candidate(raw: dict[str, Any]) -> RumorCandidate:
    source_type = _safe_text(raw.get("source_type") or raw.get("platform") or "RUMOR").upper()
    if source_type not in RUMOR_SOURCE_TYPES:
        source_type = "RUMOR"
    claim = _safe_text(raw.get("claim") or raw.get("text") or raw.get("summary"))
    title = _safe_text(raw.get("title")) or claim[:120] or "Untitled rumor"
    source_id = _safe_text(raw.get("source_id") or raw.get("video_id") or raw.get("message_id") or raw.get("id"))
    if not source_id:
        raise ValueError("rumor candidate requires source_id/video_id/message_id/id")
    if not claim:
        raise ValueError("rumor candidate requires claim/text/summary")

    if "attributable" in raw:
        attributable = bool(raw.get("attributable"))
    else:
        attributable = source_type in {"YOUTUBE_EXPERT", "TELEGRAM_NAMED"} and bool(raw.get("author") or raw.get("source_name"))

    return RumorCandidate(
        title=title,
        claim=claim,
        source_type=source_type,
        source_id=source_id,
        published_at=raw.get("published_at"),
        url=raw.get("url"),
        source_name=raw.get("source_name") or raw.get("channel"),
        author=raw.get("author"),
        event_type=_safe_text(raw.get("event_type") or "OTHER").upper(),
        entities=[_safe_text(x) for x in raw.get("entities") or [] if _safe_text(x)],
        event_date=raw.get("event_date"),
        estimated_end_date=raw.get("estimated_end_date"),
        impact_until=raw.get("impact_until"),
        impact_summary=raw.get("impact_summary"),
        resolution_condition=raw.get("resolution_condition"),
        linked_mi=[_safe_text(x) for x in raw.get("linked_mi") or [] if _safe_text(x)],
        expected_direction=dict(raw.get("expected_direction") or {}),
        decision_card=dict(raw.get("decision_card") or {}),
        stance=_safe_text(raw.get("stance") or "SUPPORT").upper(),
        attributable=attributable,
        metadata=dict(raw.get("metadata") or {}),
    )


def load_jsonl(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in paths:
        path = Path(value)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSONL {path}:{line_no}: {exc}") from exc
                if isinstance(obj, dict):
                    rows.append(obj)
    return rows


def read_ledger(path: str | Path) -> dict[str, EventRecord]:
    p = Path(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    events = raw.get("events", raw if isinstance(raw, list) else [])
    return {x["event_id"]: EventRecord.from_dict(x) for x in events if isinstance(x, dict) and x.get("event_id")}


def write_ledger(path: str | Path, records: Iterable[EventRecord], generated_at: datetime | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    generated_at = (generated_at or datetime.now(UTC)).astimezone(UTC)
    payload = {
        "contract": "MMP_EVENT_LIFECYCLE_V1",
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "events": [r.to_dict() for r in sorted(records, key=lambda x: (x.event_date or "9999", x.event_id))],
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def ingest_rows(
    rows: Iterable[dict[str, Any]],
    ledger: dict[str, EventRecord] | None = None,
    now: datetime | None = None,
    default_recheck_hours: int = 6,
    source_registry: Any | None = None,
) -> dict[str, EventRecord]:
    now = now or datetime.now(UTC)
    ledger = dict(ledger or {})
    for raw in rows:
        if source_registry is not None:
            raw = source_registry.enrich(raw)
        candidate = normalize_candidate(raw).to_event_candidate()
        # Event id can be supplied by upstream entity/event clustering. If absent, merge_candidate creates a fingerprint.
        requested_id = raw.get("event_id")
        if requested_id:
            candidate["event_id"] = str(requested_id)
            lookup_id = str(requested_id)
        else:
            lookup_id = f"EVT-{event_fingerprint(candidate["title"], candidate.get("entities") or [], candidate.get("event_type") or "OTHER")}"
            candidate["event_id"] = lookup_id
        current = ledger.get(lookup_id)
        merged = merge_candidate(current, candidate, now=now, default_recheck_hours=default_recheck_hours)
        ledger[merged.event_id] = merged
    return {k: expire_or_resolve(v, now=now) for k, v in ledger.items()}


def build_rumor_watch(records: Iterable[EventRecord]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        if record.truth_class == "OFFICIAL_FACT" or record.status in {"REJECTED", "EXPIRED", "RESOLVED"}:
            continue
        rows.append(project_calendar_item(record))
    return sorted(rows, key=lambda x: (x.get("event_date") or "9999", x["title"]))


def build_calendar_overlay(records: Iterable[EventRecord]) -> list[dict[str, Any]]:
    return [
        project_calendar_item(record)
        for record in records
        if record.status not in {"REJECTED", "EXPIRED"}
    ]
