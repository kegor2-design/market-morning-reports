from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

UTC = timezone.utc

RESULT_STATES = {
    "NOT_DUE",
    "AWAITING_RESULT",
    "PROVISIONAL",
    "RESULT_CONFIRMED",
    "REACTION_TRACKING",
    "REVIEW_COMPLETE",
    "INCONCLUSIVE",
}
MI_REVIEW_STATES = {"PENDING", "SUPPORTED", "PARTIAL", "CONTRADICTED", "INCONCLUSIVE", "NOT_SCORED"}
VERIFICATION_CLASSES = {"UNVERIFIED", "ATTRIBUTABLE_REPORT", "OFFICIAL_FACT"}


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class MarketReaction:
    window: str
    asset: str
    metric: str = "PRICE"
    baseline_value: float | None = None
    observed_value: float | None = None
    change_pct: float | None = None
    observed_at: str | None = None
    interpretation: str | None = None
    source_id: str | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MarketReaction":
        return cls(
            window=str(raw.get("window") or "initial").strip(),
            asset=str(raw.get("asset") or "UNKNOWN").strip(),
            metric=str(raw.get("metric") or "PRICE").strip(),
            baseline_value=float(raw["baseline_value"]) if raw.get("baseline_value") is not None else None,
            observed_value=float(raw["observed_value"]) if raw.get("observed_value") is not None else None,
            change_pct=float(raw["change_pct"]) if raw.get("change_pct") is not None else None,
            observed_at=_clean(raw.get("observed_at")),
            interpretation=_clean(raw.get("interpretation")),
            source_id=_clean(raw.get("source_id")),
        )


@dataclass
class PostEventResult:
    result_state: str = "AWAITING_RESULT"
    verification_class: str = "UNVERIFIED"
    official_result_summary: str | None = None
    plain_result_summary: str | None = None
    expected_vs_actual: str | None = None
    surprise_summary: str | None = None
    matched_scenario_id: str | None = None
    scenario_review_summary: str | None = None
    result_verified_at: str | None = None
    official_source_ids: list[str] = field(default_factory=list)
    market_reactions: list[MarketReaction] = field(default_factory=list)
    mi_review_status: str = "PENDING"
    mi_review_summary: str | None = None
    what_changed: str | None = None
    next_watch: list[str] = field(default_factory=list)
    beginner_explanation: str | None = None

    def __post_init__(self) -> None:
        self.result_state = str(self.result_state or "AWAITING_RESULT").upper()
        self.verification_class = str(self.verification_class or "UNVERIFIED").upper()
        self.mi_review_status = str(self.mi_review_status or "PENDING").upper()
        if self.result_state not in RESULT_STATES:
            raise ValueError(f"invalid result_state: {self.result_state}")
        if self.verification_class not in VERIFICATION_CLASSES:
            raise ValueError(f"invalid verification_class: {self.verification_class}")
        if self.mi_review_status not in MI_REVIEW_STATES:
            raise ValueError(f"invalid mi_review_status: {self.mi_review_status}")
        if self.result_state in {"RESULT_CONFIRMED", "REACTION_TRACKING", "REVIEW_COMPLETE"}:
            if self.verification_class != "OFFICIAL_FACT":
                raise ValueError("confirmed post-event result requires OFFICIAL_FACT verification")
            if not self.official_result_summary:
                raise ValueError("confirmed post-event result requires official_result_summary")
            if not self.official_source_ids:
                raise ValueError("confirmed post-event result requires official_source_ids")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "PostEventResult":
        raw = dict(raw or {})
        reactions = [MarketReaction.from_dict(x) for x in raw.get("market_reactions") or [] if isinstance(x, Mapping)]
        return cls(
            result_state=str(raw.get("result_state") or "AWAITING_RESULT"),
            verification_class=str(raw.get("verification_class") or "UNVERIFIED"),
            official_result_summary=_clean(raw.get("official_result_summary")),
            plain_result_summary=_clean(raw.get("plain_result_summary")),
            expected_vs_actual=_clean(raw.get("expected_vs_actual")),
            surprise_summary=_clean(raw.get("surprise_summary")),
            matched_scenario_id=_clean(raw.get("matched_scenario_id")),
            scenario_review_summary=_clean(raw.get("scenario_review_summary")),
            result_verified_at=_clean(raw.get("result_verified_at")),
            official_source_ids=sorted({str(x).strip() for x in raw.get("official_source_ids") or [] if str(x).strip()}),
            market_reactions=reactions,
            mi_review_status=str(raw.get("mi_review_status") or "PENDING"),
            mi_review_summary=_clean(raw.get("mi_review_summary")),
            what_changed=_clean(raw.get("what_changed")),
            next_watch=[str(x).strip() for x in raw.get("next_watch") or [] if str(x).strip()],
            beginner_explanation=_clean(raw.get("beginner_explanation")),
        )

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["market_reactions"] = [asdict(x) for x in self.market_reactions]
        return raw


def calendar_phase(event_date: str | None, result: PostEventResult | None, *, now: str | datetime | None = None,
                   result_expected_at: str | None = None, estimated_end_date: str | None = None) -> str:
    """Return a UI phase without altering the event lifecycle state.

    PRE_EVENT: decision card is primary.
    RESULT_PENDING: event time passed but official result is not verified.
    RESULT_AVAILABLE: official result is known; reaction may still be tracked.
    REVIEW_COMPLETE: result and MI review are complete.
    """
    current = _parse_dt(now) or datetime.now(UTC)
    def _end_of_date(value: str | None) -> datetime | None:
        dt = _parse_dt(value)
        if dt is not None and value and len(str(value).strip()) == 10:
            return dt.replace(hour=23, minute=59, second=59)
        return dt
    event_dt = _parse_dt(result_expected_at) or _end_of_date(estimated_end_date) or _end_of_date(event_date)
    if event_dt is None or current < event_dt:
        return "PRE_EVENT"
    if result is None or result.result_state in {"NOT_DUE", "AWAITING_RESULT", "PROVISIONAL", "INCONCLUSIVE"}:
        return "RESULT_PENDING"
    if result.result_state == "REVIEW_COMPLETE":
        return "REVIEW_COMPLETE"
    return "RESULT_AVAILABLE"


def beginner_result_headline(result: PostEventResult) -> str:
    if result.result_state == "PROVISIONAL":
        return "결과 보도는 나왔지만 아직 공식 확인 전입니다."
    if result.result_state in {"AWAITING_RESULT", "NOT_DUE"}:
        return "일정은 끝났지만 공식 결과를 아직 확인 중입니다."
    if result.result_state == "INCONCLUSIVE":
        return "결과는 확인했지만 시장 의미를 아직 한 방향으로 판단하기 어렵습니다."
    if result.plain_result_summary:
        return result.plain_result_summary
    if result.official_result_summary:
        return result.official_result_summary
    return "공식 결과가 확인됐습니다."


def compact_result_summary(result: PostEventResult | Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    obj = result if isinstance(result, PostEventResult) else PostEventResult.from_dict(result)
    return {
        "result_state": obj.result_state,
        "verification_class": obj.verification_class,
        "headline": beginner_result_headline(obj),
        "official_result_summary": obj.official_result_summary,
        "expected_vs_actual": obj.expected_vs_actual,
        "surprise_summary": obj.surprise_summary,
        "matched_scenario_id": obj.matched_scenario_id,
        "scenario_review_summary": obj.scenario_review_summary,
        "result_verified_at": obj.result_verified_at,
        "official_source_ids": list(obj.official_source_ids),
        "market_reactions": [asdict(x) for x in obj.market_reactions],
        "mi_review_status": obj.mi_review_status,
        "mi_review_summary": obj.mi_review_summary,
        "what_changed": obj.what_changed,
        "next_watch": list(obj.next_watch),
        "beginner_explanation": obj.beginner_explanation,
    }


def merge_result_payload(current: Mapping[str, Any] | None, update: Mapping[str, Any]) -> dict[str, Any]:
    """Merge an immutable-ish result snapshot while protecting official-result semantics.

    Non-official reports may be stored as PROVISIONAL but cannot overwrite a previously
    confirmed official result. A confirmed result must carry an official summary and
    at least one official source id.
    """
    base = dict(current or {})
    candidate = dict(update or {})
    existing = PostEventResult.from_dict(base) if base else None

    candidate_class = str(candidate.get("verification_class") or "UNVERIFIED").upper()
    candidate_state = str(candidate.get("result_state") or "AWAITING_RESULT").upper()

    if existing and existing.verification_class == "OFFICIAL_FACT" and candidate_class != "OFFICIAL_FACT":
        return existing.to_dict()

    if candidate_state in {"RESULT_CONFIRMED", "REACTION_TRACKING", "REVIEW_COMPLETE"} and candidate_class != "OFFICIAL_FACT":
        candidate["result_state"] = "PROVISIONAL"

    merged = dict(base)
    for key, value in candidate.items():
        if value not in (None, "", [], {}):
            merged[key] = value

    # De-duplicate source ids and keep prior market reaction windows unless updated.
    merged["official_source_ids"] = sorted({str(x) for x in (base.get("official_source_ids") or []) + (candidate.get("official_source_ids") or []) if str(x)})
    reaction_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in list(base.get("market_reactions") or []) + list(candidate.get("market_reactions") or []):
        if not isinstance(raw, Mapping):
            continue
        key = (str(raw.get("window") or "initial"), str(raw.get("asset") or "UNKNOWN"), str(raw.get("metric") or "PRICE"))
        reaction_index[key] = dict(raw)
    merged["market_reactions"] = list(reaction_index.values())
    return PostEventResult.from_dict(merged).to_dict()
