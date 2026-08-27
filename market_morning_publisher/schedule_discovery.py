from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from hashlib import sha256
from typing import Any, Iterable
import re


_DATE_RANGE_RE = re.compile(r"(?:(?P<year>20\d{2})\s*년\s*)?(?P<month>1[0-2]|0?[1-9])\s*월\s*(?P<day1>3[01]|[12]?\d)\s*(?:일)?\s*[~～\-–—]\s*(?P<day2>3[01]|[12]?\d)\s*일")
_DATE_ONE_RE = re.compile(r"(?:(?P<year>20\d{2})\s*년\s*)?(?P<month>1[0-2]|0?[1-9])\s*월\s*(?P<day>3[01]|[12]?\d)\s*일")
_ISO_RE = re.compile(r"\b(?P<year>20\d{2})[-/.](?P<month>1[0-2]|0?[1-9])[-/.](?P<day>3[01]|[12]?\d)\b")


@dataclass(frozen=True)
class DateMention:
    start_date: str
    end_date: str | None
    raw_text: str
    span_start: int
    span_end: int


@dataclass
class ScheduleCandidate:
    event_id: str
    source_type: str
    source_id: str
    title: str
    claim: str
    event_type: str
    event_date: str
    estimated_end_date: str | None = None
    published_at: str | None = None
    url: str | None = None
    source_name: str | None = None
    entities: list[str] | None = None
    attributable: bool = False
    official: bool = False
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["entities"] = raw["entities"] or []
        raw["metadata"] = raw["metadata"] or {}
        return raw


def _reference_year(published_at: str | None, default_year: int | None = None) -> int:
    if published_at:
        try:
            return datetime.fromisoformat(str(published_at).replace("Z", "+00:00")).year
        except ValueError:
            pass
        m = re.match(r"(20\d{2})", str(published_at))
        if m:
            return int(m.group(1))
    return default_year or datetime.now().year


def _valid_iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def find_date_mentions(text: str, published_at: str | None = None, default_year: int | None = None) -> list[DateMention]:
    text = str(text or "")
    year0 = _reference_year(published_at, default_year)
    found: list[DateMention] = []
    occupied: list[tuple[int, int]] = []

    def overlaps(a: int, b: int) -> bool:
        return any(not (b <= x or a >= y) for x, y in occupied)

    for m in _DATE_RANGE_RE.finditer(text):
        y = int(m.group("year") or year0)
        mo = int(m.group("month"))
        d1, d2 = int(m.group("day1")), int(m.group("day2"))
        s, e = _valid_iso(y, mo, d1), _valid_iso(y, mo, d2)
        if s and e:
            found.append(DateMention(s, e, m.group(0), m.start(), m.end()))
            occupied.append((m.start(), m.end()))

    for rx in (_DATE_ONE_RE, _ISO_RE):
        for m in rx.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            y = int(m.groupdict().get("year") or year0)
            mo = int(m.group("month"))
            d = int(m.group("day"))
            s = _valid_iso(y, mo, d)
            if s:
                found.append(DateMention(s, None, m.group(0), m.start(), m.end()))
                occupied.append((m.start(), m.end()))
    return sorted(found, key=lambda x: x.span_start)


def infer_event_type(context: str) -> str:
    t = str(context or "")
    u = t.upper()
    if "FOMC" in u or "연방공개시장위원회" in t:
        return "FOMC"
    if "잭슨홀" in t or "JACKSON HOLE" in u:
        return "JACKSON_HOLE"
    if "바이백" in t or "BUYBACK" in u or ("재무부" in t and "국채" in t):
        return "TREASURY_BUYBACK"
    if "금통위" in t or "금융통화위원회" in t or "한국은행" in t and "기준금리" in t:
        return "BOK"
    if "중간선거" in t or "대선" in t or "총선" in t or "ELECTION" in u:
        return "ELECTION"
    if "CLARITY" in u or "법안" in t or "표결" in t or "의회" in t or "상원" in t or "하원" in t:
        return "REGULATION"
    if any(k in u for k in ("CPI", "PCE", "GDP", "PMI")) or "고용보고서" in t:
        return "ECONOMIC_RELEASE"
    if "실적" in t or "EARNINGS" in u:
        return "EARNINGS"
    return "OTHER"


def _sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    # Keep one compact line/sentence around the date mention. Transcript input often has line breaks.
    left = max(text.rfind("\n", 0, pos), text.rfind(".", 0, pos), text.rfind("?", 0, pos), text.rfind("!", 0, pos))
    candidates = [x for x in (text.find("\n", pos), text.find(".", pos), text.find("?", pos), text.find("!", pos)) if x >= 0]
    right = min(candidates) + 1 if candidates else len(text)
    return max(0, left + 1), min(len(text), right)


def _compact_title(context: str, mention: DateMention, max_len: int = 120) -> str:
    text = re.sub(r"\s+", " ", context).strip(" -–—:;,")
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text or mention.raw_text


def _candidate_id(source_id: str, event_type: str, event_date: str, title: str) -> str:
    norm = re.sub(r"\s+", " ", title.lower()).strip()
    h = sha256(f"{source_id}|{event_type}|{event_date}|{norm}".encode("utf-8")).hexdigest()[:20]
    return f"EVT-SCHED-{h}"


def extract_schedule_candidates(document: dict[str, Any], default_year: int | None = None) -> list[dict[str, Any]]:
    source_id = str(document.get("source_id") or document.get("video_id") or document.get("id") or "").strip()
    if not source_id:
        raise ValueError("source_id is required")
    source_type = str(document.get("source_type") or "YOUTUBE").upper()
    text = str(document.get("text") or document.get("transcript") or document.get("caption") or "")
    published_at = document.get("published_at")
    if not text.strip():
        return []

    out: list[ScheduleCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for mention in find_date_mentions(text, published_at=published_at, default_year=default_year):
        a, b = _sentence_bounds(text, mention.span_start)
        context = text[a:b].strip()
        event_type = infer_event_type(context)
        # Do not create a calendar item from a bare date with no market/event semantics.
        if event_type == "OTHER" and len(context) < 18:
            continue
        title = _compact_title(context, mention)
        key = (mention.start_date, mention.end_date or "", title)
        if key in seen:
            continue
        seen.add(key)
        out.append(ScheduleCandidate(
            event_id=_candidate_id(source_id, event_type, mention.start_date, title),
            source_type=source_type,
            source_id=source_id,
            title=title,
            claim=context,
            event_type=event_type,
            event_date=mention.start_date,
            estimated_end_date=mention.end_date,
            published_at=published_at,
            url=document.get("url"),
            source_name=document.get("source_name") or document.get("channel"),
            entities=[str(x) for x in document.get("entities") or []],
            attributable=bool(document.get("attributable")) or source_type == "YOUTUBE_EXPERT",
            official=bool(document.get("official")),
            metadata={
                "extraction_contract": "MMP_SCHEDULE_DISCOVERY_V1",
                "date_text": mention.raw_text,
                "requires_official_verification": not bool(document.get("official")),
                "source_registry_id": document.get("source_registry_id"),
                "independence_group": document.get("independence_group"),
                "origin_group": document.get("origin_group"),
                "corroboration_eligible": document.get("corroboration_eligible", True),
            },
        ))
    return [x.to_dict() for x in out]


def candidate_date_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Loose matcher used before official evidence is merged into a discovered event."""
    try:
        a0 = date.fromisoformat(str(a.get("event_date")))
        a1 = date.fromisoformat(str(a.get("estimated_end_date") or a.get("event_date")))
        b0 = date.fromisoformat(str(b.get("event_date")))
        b1 = date.fromisoformat(str(b.get("estimated_end_date") or b.get("event_date")))
    except (TypeError, ValueError):
        return False
    return max(a0, b0) <= min(a1, b1)


def match_official_candidate(discovered: dict[str, Any], official_rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    et = str(discovered.get("event_type") or "OTHER").upper()
    best = None
    for row in official_rows:
        if str(row.get("event_type") or "OTHER").upper() != et:
            continue
        if candidate_date_overlap(discovered, row):
            best = row
            break
    return best
