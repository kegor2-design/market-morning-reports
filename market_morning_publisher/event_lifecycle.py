from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Iterable
import re

UTC = timezone.utc

OFFICIAL_SOURCE_TYPES = {
    "OPENDART", "KRX", "BOK", "FED", "TREASURY", "GOV", "COMPANY_IR", "EXCHANGE_NOTICE",
    "KANSASCITYFED", "CONGRESS", "FEC", "BEA", "BLS", "ECB", "BOJ",
}
ATTRIBUTABLE_SOURCE_TYPES = {
    "REUTERS", "BLOOMBERG", "YONHAP", "YOUTUBE_EXPERT", "TELEGRAM_NAMED",
}
RUMOR_SOURCE_TYPES = {
    "YOUTUBE", "TELEGRAM", "TELEGRAM_ANON", "NEWS_TIP", "COMMUNITY", "RUMOR",
}

VALID_STATES = {
    "CANDIDATE",
    "UNVERIFIED",
    "CORROBORATED_UNVERIFIED",
    "VERIFIED",
    "ACTIVE",
    "RESOLVING",
    "RESOLVED",
    "REJECTED",
    "EXPIRED",
}


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9A-Za-z가-힣]+", " ", (text or "").lower())).strip()


def event_fingerprint(title: str, entities: Iterable[str] = (), event_type: str = "") -> str:
    payload = "|".join([_norm(event_type), _norm(title), *sorted({_norm(x) for x in entities if _norm(x)})])
    return sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass
class Evidence:
    source_type: str
    source_id: str
    claim: str
    published_at: str | None = None
    url: str | None = None
    source_name: str | None = None
    author: str | None = None
    official: bool = False
    attributable: bool = False
    stance: str = "SUPPORT"  # SUPPORT | DENY | NEUTRAL
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Evidence":
        source_type = str(raw.get("source_type") or "RUMOR").upper()
        return cls(
            source_type=source_type,
            source_id=str(raw.get("source_id") or raw.get("id") or ""),
            claim=str(raw.get("claim") or raw.get("text") or "").strip(),
            published_at=_iso(_parse_dt(raw.get("published_at"))),
            url=raw.get("url"),
            source_name=raw.get("source_name"),
            author=raw.get("author"),
            official=bool(raw.get("official")) or source_type in OFFICIAL_SOURCE_TYPES,
            attributable=bool(raw.get("attributable")) or source_type in ATTRIBUTABLE_SOURCE_TYPES,
            stance=str(raw.get("stance") or "SUPPORT").upper(),
            metadata=dict(raw.get("metadata") or {}),
        )

    def identity(self) -> str:
        return sha256(
            f"{self.source_type}|{self.source_id}|{self.url or ''}|{_norm(self.claim)}".encode("utf-8")
        ).hexdigest()[:24]


@dataclass
class EventRecord:
    event_id: str
    title: str
    event_type: str
    status: str = "CANDIDATE"
    truth_class: str = "UNVERIFIED"  # OFFICIAL_FACT | ATTRIBUTABLE_REPORT | UNVERIFIED
    entities: list[str] = field(default_factory=list)
    event_date: str | None = None
    result_expected_at: str | None = None
    estimated_end_date: str | None = None
    impact_until: str | None = None
    impact_summary: str | None = None
    resolution_condition: str | None = None
    linked_mi: list[str] = field(default_factory=list)
    expected_direction: dict[str, str] = field(default_factory=dict)
    actual_reaction: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    first_seen_at: str | None = None
    last_verified_at: str | None = None
    next_check_at: str | None = None
    confidence_band: str = "LOW"  # LOW | MEDIUM | HIGH; not a probability
    notes: list[str] = field(default_factory=list)
    decision_card: dict[str, Any] = field(default_factory=dict)
    post_event_result: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EventRecord":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: raw[k] for k in allowed if k in raw})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _source_independence_key(ev: Evidence) -> str:
    # Discovery-only aggregators/repost networks must never manufacture corroboration.
    if ev.metadata.get("corroboration_eligible") is False:
        return ""
    # Source Registry families collapse sister channels from the same organization/network.
    group = _norm(ev.metadata.get("independence_group") or ev.metadata.get("origin_group") or "")
    if group:
        return f"group:{group}"
    # Fallback: a channel/account is one source even when it posts repeatedly.
    named = _norm(ev.source_name or ev.author or ev.metadata.get("channel") or "")
    if named:
        return named
    # Without an attributable account identity, multiple message ids are NOT treated as independent sources.
    return f"unknown:{ev.source_type.lower()}"


def _derive_truth_and_status(evidence: list[Evidence], previous: str) -> tuple[str, str, str]:
    supporting = [e for e in evidence if e.stance == "SUPPORT"]
    denials = [e for e in evidence if e.stance == "DENY"]
    official_support = [e for e in supporting if e.official]
    official_deny = [e for e in denials if e.official]

    if official_deny:
        return "OFFICIAL_FACT", "REJECTED", "HIGH"
    if official_support:
        return "OFFICIAL_FACT", "VERIFIED", "HIGH"

    attributable_support = [e for e in supporting if e.attributable]
    independent_keys = {_source_independence_key(e) for e in supporting if _source_independence_key(e)}

    # Crucial guardrail: multiple rumors never become OFFICIAL_FACT.
    if attributable_support:
        band = "MEDIUM" if len({_source_independence_key(e) for e in attributable_support}) >= 1 else "LOW"
        return "ATTRIBUTABLE_REPORT", "CORROBORATED_UNVERIFIED", band
    if len(independent_keys) >= 2:
        return "UNVERIFIED", "CORROBORATED_UNVERIFIED", "MEDIUM"
    if supporting:
        return "UNVERIFIED", "UNVERIFIED", "LOW"
    return "UNVERIFIED", previous if previous in VALID_STATES else "CANDIDATE", "LOW"


def merge_candidate(
    current: EventRecord | None,
    candidate: dict[str, Any],
    now: datetime | None = None,
    default_recheck_hours: int = 6,
) -> EventRecord:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    title = str(candidate.get("title") or candidate.get("claim") or "Untitled event").strip()
    event_type = str(candidate.get("event_type") or "OTHER").upper()
    entities = [str(x) for x in candidate.get("entities") or []]

    if current is None:
        event_id = str(candidate.get("event_id") or f"EVT-{event_fingerprint(title, entities, event_type)}")
        current = EventRecord(
            event_id=event_id,
            title=title,
            event_type=event_type,
            status="CANDIDATE",
            entities=entities,
            first_seen_at=_iso(now),
        )

    # Candidate may add lifecycle metadata, but unverified candidates must not write actual market facts.
    for name in ("event_date", "result_expected_at", "estimated_end_date", "impact_until", "impact_summary", "resolution_condition"):
        value = candidate.get(name)
        if value not in (None, ""):
            setattr(current, name, value)
    current.linked_mi = sorted(set(current.linked_mi).union(str(x) for x in candidate.get("linked_mi") or []))
    current.expected_direction.update(dict(candidate.get("expected_direction") or {}))
    if isinstance(candidate.get("decision_card"), dict):
        current.decision_card.update(dict(candidate.get("decision_card") or {}))
    if isinstance(candidate.get("post_event_result"), dict):
        from .post_event_result import merge_result_payload
        current.post_event_result = merge_result_payload(current.post_event_result, candidate.get("post_event_result") or {})
    current.entities = sorted(set(current.entities).union(entities))

    old = {Evidence.from_dict(x).identity(): Evidence.from_dict(x) for x in current.evidence}
    incoming = candidate.get("evidence") or []
    if not incoming and candidate.get("claim"):
        incoming = [candidate]
    for raw in incoming:
        ev = Evidence.from_dict(raw)
        if ev.claim:
            old[ev.identity()] = ev

    evidence = list(old.values())
    truth_class, status, band = _derive_truth_and_status(evidence, current.status)
    current.truth_class = truth_class
    current.status = status
    current.confidence_band = band
    current.evidence = [asdict(x) for x in sorted(evidence, key=lambda x: x.published_at or "")]
    current.last_verified_at = _iso(now)
    current.next_check_at = _iso(now + timedelta(hours=max(1, int(default_recheck_hours))))

    if current.status == "VERIFIED" and candidate.get("activate", True):
        current.status = "ACTIVE"

    return current


def expire_or_resolve(record: EventRecord, now: datetime | None = None, unverified_ttl_hours: int = 72) -> EventRecord:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if record.status in {"RESOLVED", "REJECTED", "EXPIRED"}:
        return record

    impact_until = _parse_dt(record.impact_until)
    estimated_end = _parse_dt(record.estimated_end_date)
    first_seen = _parse_dt(record.first_seen_at)

    if impact_until and now > impact_until and record.status in {"ACTIVE", "VERIFIED", "RESOLVING"}:
        record.status = "RESOLVED"
        record.last_verified_at = _iso(now)
        record.notes.append("impact_until elapsed; resolved by lifecycle policy")
        return record
    if estimated_end and now > estimated_end and record.status == "ACTIVE":
        record.status = "RESOLVING"
        record.notes.append("estimated_end_date elapsed; requires explicit resolution check")
    if record.truth_class == "UNVERIFIED" and first_seen and now - first_seen > timedelta(hours=unverified_ttl_hours):
        record.status = "EXPIRED"
        record.last_verified_at = _iso(now)
        record.notes.append("unverified TTL elapsed without confirmation")
    return record


def project_calendar_item(record: EventRecord, now: str | datetime | None = None) -> dict[str, Any]:
    from .calendar_decision_card import compact_card_summary, decision_card_from_event
    from .calendar_event_impact import project_impact_and_scenarios
    from .post_event_result import PostEventResult, calendar_phase, compact_result_summary
    uncertain = record.truth_class != "OFFICIAL_FACT"
    if record.status in {"REJECTED", "EXPIRED", "RESOLVED"}:
        visibility = "HISTORY"
    elif record.status in {"ACTIVE", "VERIFIED", "RESOLVING"}:
        visibility = "ACTIVE"
    else:
        visibility = "WATCH"
    result_obj = PostEventResult.from_dict(record.post_event_result) if record.post_event_result else None
    phase = calendar_phase(record.event_date, result_obj, now=now, result_expected_at=record.result_expected_at, estimated_end_date=record.estimated_end_date)
    if phase in {"RESULT_PENDING", "RESULT_AVAILABLE", "REVIEW_COMPLETE"}:
        visibility = "HISTORY"
    badge = {
        "OFFICIAL_FACT": "공식",
        "ATTRIBUTABLE_REPORT": "보도/주장",
        "UNVERIFIED": "미확인",
    }.get(record.truth_class, "미확인")
    return {
        "event_id": record.event_id,
        "title": record.title,
        "event_type": record.event_type,
        "event_date": record.event_date,
        "result_expected_at": record.result_expected_at,
        "estimated_end_date": record.estimated_end_date,
        "impact_until": record.impact_until,
        "status": record.status,
        "truth_class": record.truth_class,
        "confidence_band": record.confidence_band,
        "uncertain": uncertain,
        "badge": badge,
        "visibility": visibility,
        "impact_summary": record.impact_summary,
        "next_check_at": record.next_check_at,
        "linked_mi": record.linked_mi,
        "expected_direction": record.expected_direction,
        "decision_card": {**compact_card_summary(decision_card_from_event(record)), **project_impact_and_scenarios(record)},
        "calendar_phase": phase,
        "post_event_result": compact_result_summary(result_obj),
    }
