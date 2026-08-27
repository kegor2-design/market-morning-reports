from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass
class WatchItem:
    label: str
    what_to_check: str
    positive_interpretation: str | None = None
    negative_interpretation: str | None = None
    beginner_note: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WatchItem":
        return cls(
            label=str(raw.get("label") or "확인 지표").strip(),
            what_to_check=str(raw.get("what_to_check") or raw.get("signal") or "").strip(),
            positive_interpretation=_clean_optional(raw.get("positive_interpretation")),
            negative_interpretation=_clean_optional(raw.get("negative_interpretation")),
            beginner_note=_clean_optional(raw.get("beginner_note")),
        )


@dataclass
class DecisionCard:
    decision_question: str
    plain_summary: str
    why_it_matters: str
    current_view: str | None = None
    current_view_confidence: str | None = None
    transmission_path: list[str] = field(default_factory=list)
    watch_items: list[WatchItem] = field(default_factory=list)
    scenario_up: str | None = None
    scenario_down: str | None = None
    invalidation_conditions: list[str] = field(default_factory=list)
    beginner_glossary: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DecisionCard":
        return cls(
            decision_question=str(raw.get("decision_question") or "이 일정에서 무엇을 판단해야 할까?").strip(),
            plain_summary=str(raw.get("plain_summary") or "일정 결과가 시장의 예상과 얼마나 다른지 확인합니다.").strip(),
            why_it_matters=str(raw.get("why_it_matters") or "예상과 다른 결과는 금리·환율·수급을 통해 국내 시장에 영향을 줄 수 있습니다.").strip(),
            current_view=_clean_optional(raw.get("current_view")),
            current_view_confidence=_clean_optional(raw.get("current_view_confidence")),
            transmission_path=[str(x).strip() for x in raw.get("transmission_path") or [] if str(x).strip()],
            watch_items=[WatchItem.from_dict(x) for x in raw.get("watch_items") or [] if isinstance(x, dict)],
            scenario_up=_clean_optional(raw.get("scenario_up")),
            scenario_down=_clean_optional(raw.get("scenario_down")),
            invalidation_conditions=[str(x).strip() for x in raw.get("invalidation_conditions") or [] if str(x).strip()],
            beginner_glossary={str(k).strip(): str(v).strip() for k, v in dict(raw.get("beginner_glossary") or {}).items() if str(k).strip() and str(v).strip()},
        )

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["watch_items"] = [asdict(x) for x in self.watch_items]
        return raw


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _event_type(event: Any) -> str:
    if isinstance(event, dict):
        return _safe_text(event.get("event_type")).upper()
    return _safe_text(getattr(event, "event_type", "")).upper()


def _event_title(event: Any) -> str:
    if isinstance(event, dict):
        return _safe_text(event.get("title") or event.get("name"))
    return _safe_text(getattr(event, "title", ""))


def _impact_summary(event: Any) -> str:
    if isinstance(event, dict):
        return _safe_text(event.get("impact_summary") or event.get("why_it_matters") or event.get("korea_transmission"))
    return _safe_text(getattr(event, "impact_summary", ""))


def _expected_direction(event: Any) -> dict[str, str]:
    if isinstance(event, dict):
        return dict(event.get("expected_direction") or {})
    return dict(getattr(event, "expected_direction", {}) or {})


def fallback_decision_card(event: Any) -> DecisionCard:
    """Build beginner-friendly fallback copy without inventing a directional forecast.

    Rich cards should normally come from Schedule Intelligence / MI reasoning. This
    fallback only explains what should be judged when an older event record lacks
    explicit decision-card metadata.
    """
    kind = _event_type(event)
    title = _event_title(event) or "주요 일정"
    impact = _impact_summary(event)
    expected = _expected_direction(event)

    templates: dict[str, dict[str, Any]] = {
        "FOMC": {
            "q": "Fed가 시장 예상보다 매파적으로 나올까, 완화적으로 나올까?",
            "summary": "금리 결정 숫자만 보지 말고 성명서와 기자회견에서 앞으로 금리를 얼마나 오래 높게 유지할지 확인하는 일정입니다.",
            "why": "Fed의 태도가 미국 국채금리와 달러를 움직이면 원/달러 환율과 외국인의 한국 주식 수급까지 영향을 받을 수 있습니다.",
            "path": ["Fed 정책 기대", "미국 국채금리·달러", "원/달러 환율", "외국인 수급", "국내 증시"],
            "watch": [
                {"label": "정책금리", "what_to_check": "시장 예상과 실제 금리 결정의 차이", "beginner_note": "예상과 같아도 앞으로의 발언이 더 중요할 수 있습니다."},
                {"label": "점도표/성명", "what_to_check": "추가 인상·동결 장기화·인하 가능성 변화"},
                {"label": "미국 2년·10년 금리", "what_to_check": "발표 직후 금리가 오르는지 내리는지"},
                {"label": "DXY·USD/KRW", "what_to_check": "달러 강세와 원화 약세가 함께 나타나는지"},
            ],
            "glossary": {"매파적": "물가를 잡기 위해 높은 금리를 더 오래 유지하거나 금리 인상을 선호하는 태도", "완화적": "경기 부담을 더 고려해 금리 인하나 긴축 완화를 선호하는 태도"},
        },
        "BOK": {
            "q": "한국은행이 환율·물가를 더 걱정할까, 경기 둔화를 더 걱정할까?",
            "summary": "기준금리 결정과 총재 발언을 통해 한국의 다음 금리 방향과 환율 방어 의지를 확인하는 일정입니다.",
            "why": "한국 금리 기대는 원화 가치, 외국인 채권·주식 수급, 은행·성장주 등 금리 민감 업종에 영향을 줍니다.",
            "path": ["한국은행 판단", "한국 금리 기대", "원화", "외국인 수급", "국내 자산가격"],
            "watch": [
                {"label": "기준금리", "what_to_check": "동결/인상/인하 여부와 소수의견"},
                {"label": "총재 발언", "what_to_check": "환율·부동산·가계부채·경기 중 무엇을 가장 강조하는지"},
                {"label": "USD/KRW", "what_to_check": "발표 후 원화가 강해지는지 약해지는지"},
            ],
            "glossary": {"소수의견": "위원 다수와 다른 금리 의견. 다음 회의 방향을 가늠하는 단서가 될 수 있습니다."},
        },
        "TREASURY_BUYBACK": {
            "q": "미 재무부 조치가 장기국채 금리 상승 압력을 실제로 낮출까?",
            "summary": "재무부가 장기국채의 유동성을 개선하거나 바이백을 확대해 채권시장의 부담을 얼마나 줄이는지 확인합니다.",
            "why": "미국 장기금리가 안정되면 성장주와 위험자산 부담이 줄 수 있고, 반대로 금리가 계속 오르면 달러·원화·외국인 수급에 부담이 될 수 있습니다.",
            "path": ["미 재무부 국채 수급", "미국 장기금리", "달러·위험선호", "원화·외국인 수급", "국내 성장주"],
            "watch": [
                {"label": "10년·30년 금리", "what_to_check": "바이백 전후 장기금리가 안정되는지"},
                {"label": "입찰 수요", "what_to_check": "국채 입찰 수요가 약한지 강한지"},
                {"label": "DXY·NASDAQ", "what_to_check": "금리 변화가 달러와 성장주에 어떻게 전달되는지"},
            ],
            "glossary": {"바이백": "재무부가 이미 발행된 국채를 다시 사들이는 것. 시장 유동성과 특정 만기 수급에 영향을 줄 수 있습니다."},
        },
        "ELECTION": {
            "q": "선거를 앞둔 정책 선택이 금리·재정·시장에 어떤 방향의 압력을 만들까?",
            "summary": "선거 결과 자체뿐 아니라 선거 전후 재정정책·규제·통화정책 기대가 어떻게 바뀌는지 확인합니다.",
            "why": "정책 기대 변화는 미국 국채금리와 달러, 글로벌 위험선호를 통해 한국 시장에도 전달될 수 있습니다.",
            "path": ["선거·정책 기대", "재정·규제 기대", "미국 금리·달러", "글로벌 위험선호", "한국 시장"],
            "watch": [
                {"label": "정책 공약", "what_to_check": "재정지출·세금·무역·규제 방향"},
                {"label": "미국 장기금리", "what_to_check": "재정 확대 기대가 금리를 밀어 올리는지"},
                {"label": "DXY·외국인 수급", "what_to_check": "달러 강세와 한국 자금 유출이 동반되는지"},
            ],
        },
        "REGULATION": {
            "q": "이번 규제·법안이 실제 시행 단계로 가까워질까, 지연될까?",
            "summary": "표결이나 심사 일정의 의미를 구분하고, 실제 법률·규정으로 이어질 가능성이 얼마나 높아졌는지 판단합니다.",
            "why": "정책 기대가 먼저 가격에 반영되므로 최종 통과 여부뿐 아니라 절차가 한 단계 진전됐는지가 관련 산업과 자산 가격을 움직일 수 있습니다.",
            "path": ["법안·규제 절차", "통과 가능성", "관련 산업 기대", "자산가격"],
            "watch": [
                {"label": "절차 단계", "what_to_check": "최종 표결인지, 토론종결·위원회 심사 같은 중간 절차인지"},
                {"label": "찬반 구도", "what_to_check": "통과에 필요한 표가 실제로 확보되는지"},
                {"label": "관련 자산", "what_to_check": "기대가 이미 가격에 선반영됐는지"},
            ],
        },
    }
    key = kind
    if key not in templates:
        if "FOMC" in title.upper() or "FED" in title.upper():
            key = "FOMC"
        elif "금통" in title or "한국은행" in title:
            key = "BOK"
        elif "바이백" in title or "BUYBACK" in title.upper():
            key = "TREASURY_BUYBACK"
        elif "선거" in title or "ELECTION" in title.upper():
            key = "ELECTION"
        elif "법안" in title or "표결" in title or "CLARITY" in title.upper():
            key = "REGULATION"

    t = templates.get(key)
    if t:
        card = DecisionCard(
            decision_question=t["q"],
            plain_summary=t["summary"],
            why_it_matters=t["why"],
            transmission_path=list(t.get("path") or []),
            watch_items=[WatchItem.from_dict(x) for x in t.get("watch") or []],
            beginner_glossary=dict(t.get("glossary") or {}),
        )
    else:
        card = DecisionCard(
            decision_question=f"'{title}' 일정에서 시장 예상과 실제 결과가 얼마나 다를까?",
            plain_summary="이 일정의 결과가 예상보다 강한지 약한지, 그리고 시장 가격이 실제로 반응하는지를 확인합니다.",
            why_it_matters=impact or "결과가 금리·환율·수급 또는 관련 업종의 기대를 바꿀 수 있기 때문입니다.",
            transmission_path=["일정 결과", "시장 기대 변화", "금리·환율·수급", "관련 자산"],
        )

    if impact and impact not in card.why_it_matters:
        card.plain_summary = f"{card.plain_summary} 현재 추적 중인 영향은 '{impact}'입니다."
    # expected_direction is shared by rumor/expert/event records, so it is evidence,
    # not proof that the view came from OUR_MI. Never promote it to current_view here.
    return card


def decision_card_from_event(event: Any) -> DecisionCard:
    if isinstance(event, dict):
        raw = event.get("decision_card") or {}
    else:
        raw = getattr(event, "decision_card", {}) or {}
    if raw:
        base = fallback_decision_card(event).to_dict()
        # Explicit inference output wins, fallback only fills omissions.
        for k, v in dict(raw).items():
            if v not in (None, "", [], {}):
                base[k] = v
        source = str(raw.get("current_view_source") or "").upper()
        view = str(raw.get("current_view") or "")
        if source != "OUR_MI" and "OUR_MI" not in view.upper():
            base["current_view"] = None
            base["current_view_confidence"] = None
        return DecisionCard.from_dict(base)
    return fallback_decision_card(event)


def compact_card_summary(card: DecisionCard, max_watch_items: int = 3) -> dict[str, Any]:
    """Stable public JSON for calendar/detail card UI."""
    return {
        "decision_question": card.decision_question,
        "plain_summary": card.plain_summary,
        "why_it_matters": card.why_it_matters,
        "current_view": card.current_view,
        "current_view_confidence": card.current_view_confidence,
        "transmission_path": list(card.transmission_path),
        "watch_items": [asdict(x) for x in card.watch_items[:max(0, int(max_watch_items))]],
        "scenario_up": card.scenario_up,
        "scenario_down": card.scenario_down,
        "invalidation_conditions": list(card.invalidation_conditions),
        "beginner_glossary": dict(card.beginner_glossary),
    }
