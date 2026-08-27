from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping

VALID_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


@dataclass(frozen=True)
class ImpactProfile:
    level: str
    score: int
    badge: str
    plain_label: str
    reason: str
    impacted_assets: list[str]
    methodology: str = "RULE_BASED_MARKET_REACH_V1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


BASE_IMPACT: dict[str, tuple[int, str, list[str]]] = {
    "FOMC": (95, "미국 금리·달러·글로벌 위험자산에 동시에 영향을 줄 수 있는 핵심 통화정책 일정입니다.", ["US2Y", "US10Y", "DXY", "USD/KRW", "NASDAQ", "KOSPI"]),
    "BOK": (90, "한국 금리·원화·외국인 수급에 직접 영향을 줄 수 있는 핵심 국내 통화정책 일정입니다.", ["KR3Y", "USD/KRW", "KOSPI", "KOSDAQ", "외국인수급"]),
    "CPI": (90, "미국 물가 결과가 Fed 기대와 국채금리·달러를 빠르게 바꿀 수 있습니다.", ["US2Y", "US10Y", "DXY", "USD/KRW", "NASDAQ"]),
    "PCE": (85, "Fed가 중요하게 보는 물가지표여서 금리 기대와 달러 방향을 바꿀 수 있습니다.", ["US2Y", "US10Y", "DXY", "USD/KRW"]),
    "NFP": (88, "미국 고용 강도가 Fed 정책 기대와 경기 판단을 동시에 바꿀 수 있습니다.", ["US2Y", "US10Y", "DXY", "NASDAQ", "USD/KRW"]),
    "EMPLOYMENT": (88, "미국 고용 강도가 Fed 정책 기대와 경기 판단을 동시에 바꿀 수 있습니다.", ["US2Y", "US10Y", "DXY", "NASDAQ", "USD/KRW"]),
    "TREASURY_REFUNDING": (88, "미 국채 발행·수급 변화가 장기금리와 글로벌 자금흐름에 영향을 줄 수 있습니다.", ["US10Y", "US30Y", "DXY", "NASDAQ", "USD/KRW"]),
    "TREASURY_BUYBACK": (82, "미 재무부의 국채 수급 조치가 장기금리와 위험선호를 바꿀 수 있습니다.", ["US10Y", "US30Y", "DXY", "NASDAQ", "USD/KRW"]),
    "ECB": (80, "유로존 통화정책 변화가 달러와 글로벌 금리·위험선호에 영향을 줄 수 있습니다.", ["EUR/USD", "DXY", "US10Y", "USD/KRW"]),
    "BOJ": (82, "일본 금리·엔화 변화가 글로벌 캐리트레이드와 아시아 자금흐름에 영향을 줄 수 있습니다.", ["USD/JPY", "JGB10Y", "DXY", "KOSPI"]),
    "ELECTION": (90, "선거 결과와 정책 기대가 재정·규제·무역정책을 바꾸며 여러 시장에 영향을 줄 수 있습니다.", ["US10Y", "DXY", "S&P500", "USD/KRW", "KOSPI"]),
    "REGULATION": (70, "법안·규제 진전 여부가 관련 산업의 기대와 밸류에이션을 바꿀 수 있습니다.", ["관련산업", "관련종목"]),
    "GDP": (68, "경기 강도 판단을 바꾸지만 통화정책 핵심 이벤트보다 직접적인 파급력은 보통 낮습니다.", ["US10Y", "DXY", "S&P500"]),
    "JACKSON_HOLE": (86, "중앙은행의 향후 정책 방향을 미리 가늠할 수 있어 금리·달러 기대가 크게 변할 수 있습니다.", ["US2Y", "US10Y", "DXY", "USD/KRW", "NASDAQ"]),
}


def _get(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(name, default)
    return getattr(event, name, default)


def _kind(event: Any) -> str:
    kind = str(_get(event, "event_type", "") or "").upper().strip()
    title = str(_get(event, "title", "") or "").upper()
    if kind in BASE_IMPACT:
        return kind
    if "FOMC" in title or "FED" in title:
        return "FOMC"
    if "금통" in title or "한국은행" in title:
        return "BOK"
    if "CPI" in title:
        return "CPI"
    if "PCE" in title:
        return "PCE"
    if "고용" in title or "PAYROLL" in title or "NFP" in title:
        return "NFP"
    if "JACKSON" in title or "잭슨홀" in title:
        return "JACKSON_HOLE"
    if "REFUND" in title or "리펀딩" in title:
        return "TREASURY_REFUNDING"
    if "바이백" in title or "BUYBACK" in title:
        return "TREASURY_BUYBACK"
    if "선거" in title or "ELECTION" in title:
        return "ELECTION"
    if "법안" in title or "표결" in title or "REGULATION" in title or "CLARITY" in title:
        return "REGULATION"
    return kind or "OTHER"


def _level(score: int) -> str:
    if score >= 90:
        return "CRITICAL"
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "LOW"


def impact_profile(event: Any) -> ImpactProfile:
    kind = _kind(event)
    base_score, reason, assets = BASE_IMPACT.get(
        kind,
        (50, "관련 자산의 기대와 수급을 바꿀 수 있어 일정 결과를 확인할 필요가 있습니다.", ["관련자산"]),
    )
    score = base_score
    linked_mi = list(_get(event, "linked_mi", []) or [])
    expected_direction = dict(_get(event, "expected_direction", {}) or {})
    # Small, bounded boosts reflect current engine relevance, not truth/accuracy.
    if linked_mi:
        score += 3
    if len(expected_direction) >= 2:
        score += 2
    score = max(0, min(100, int(score)))
    level = _level(score)
    badge = {"CRITICAL": "🔥 매우 중요", "HIGH": "▲ 중요", "MEDIUM": "● 보통", "LOW": "· 참고"}[level]
    plain = {
        "CRITICAL": "시장 전체 방향이 바뀔 수 있는 일정",
        "HIGH": "여러 핵심 자산에 큰 영향을 줄 수 있는 일정",
        "MEDIUM": "관련 시장에 의미 있는 영향을 줄 수 있는 일정",
        "LOW": "참고할 가치가 있는 보조 일정",
    }[level]
    return ImpactProfile(level=level, score=score, badge=badge, plain_label=plain, reason=reason, impacted_assets=list(assets))


def _changes(*items: tuple[str, str, str]) -> list[dict[str, str]]:
    return [{"asset": a, "direction": d, "why": w} for a, d, w in items]


def _scenario(sid: str, name: str, condition: str, summary: str, changes: list[dict[str, str]], checks: list[str]) -> dict[str, Any]:
    return {
        "scenario_id": sid,
        "name": name,
        "if_result": condition,
        "beginner_summary": summary,
        "expected_changes": changes,
        "confirmation_signals": checks,
        "probability": None,
        "probability_source": None,
    }


def outcome_scenarios(event: Any) -> list[dict[str, Any]]:
    """Conditional branches, not unconditional forecasts.

    Probabilities intentionally remain null unless an upstream OUR_MI inference supplies
    an explicit point-in-time probability. This prevents fallback UI copy from inventing
    conviction.
    """
    kind = _kind(event)
    if kind == "FOMC":
        return [
            _scenario("HAWKISH", "예상보다 매파적", "금리·점도표·기자회견이 시장 예상보다 긴축적일 때", "미국 금리와 달러가 오르고 원화·성장주에는 부담이 커질 가능성을 먼저 봅니다.", _changes(("US2Y/US10Y", "UP", "더 높은 금리를 오래 유지할 기대"), ("DXY", "UP", "미국 금리 매력 상승"), ("USD/KRW", "UP", "달러 강세와 원화 부담"), ("NASDAQ/KOSPI 성장주", "DOWN_PRESSURE", "할인율 상승")), ["미국 2년·10년 금리 동반 상승", "DXY 상승", "USD/KRW 상승"]),
            _scenario("INLINE", "대체로 예상 부합", "결정과 향후 신호가 시장 컨센서스와 비슷할 때", "첫 반응보다 이후 물가·고용 데이터와 장기금리 흐름이 더 중요해질 수 있습니다.", _changes(("US2Y/US10Y", "MIXED", "새로운 정책 충격이 제한적"), ("DXY", "MIXED", "기존 기대 유지"), ("KOSPI", "MIXED", "수급·실적 변수 영향 확대")), ["발표 직후 변동 후 원위치", "금리곡선 큰 변화 없음"]),
            _scenario("DOVISH", "예상보다 완화적", "인하 가능성 확대·긴축 종료 신호가 예상보다 강할 때", "미국 금리와 달러가 약해지면 원화와 위험자산에 우호적인 환경이 될 수 있습니다.", _changes(("US2Y/US10Y", "DOWN", "정책금리 기대 하락"), ("DXY", "DOWN_PRESSURE", "금리 메리트 약화"), ("USD/KRW", "DOWN_PRESSURE", "원화 강세 압력"), ("NASDAQ/KOSPI 성장주", "UP_PRESSURE", "할인율 하락")), ["미국 2년물 하락", "DXY 하락", "외국인 한국주식 순매수 개선"]),
        ]
    if kind == "BOK":
        return [
            _scenario("HAWKISH", "환율·물가 우려 강화", "인상·장기 동결 또는 매파 발언이 예상보다 강할 때", "원화에는 지지 요인이지만 국내 금리민감 업종에는 부담이 될 수 있습니다.", _changes(("KR 금리", "UP", "긴축 기대 강화"), ("USD/KRW", "DOWN_PRESSURE", "원화 금리 메리트 개선"), ("성장주/부동산 민감", "DOWN_PRESSURE", "자금조달비용 부담")), ["국고채 금리 상승", "USD/KRW 하락 여부", "외국인 채권수급"]),
            _scenario("INLINE", "예상 부합", "동결과 발언이 시장 예상 범위일 때", "환율·외국인 수급과 다음 물가·가계부채 지표가 더 중요해집니다.", _changes(("KR 금리", "MIXED", "정책 기대 변화 제한"), ("USD/KRW", "MIXED", "대외 달러 변수 영향 확대")), ["금리·환율 변동 축소", "다음 지표 대기"]),
            _scenario("DOVISH", "경기 우려 강화", "인하 또는 완화 신호가 예상보다 강할 때", "국내 금리는 내려갈 수 있지만 원화 약세가 동반되는지 확인해야 합니다.", _changes(("KR 금리", "DOWN", "완화 기대"), ("USD/KRW", "UP_PRESSURE", "금리차 부담 가능성"), ("금리민감 성장주", "UP_PRESSURE", "할인율 하락")), ["국고채 금리 하락", "USD/KRW 상승 여부", "외국인 주식·채권 수급"]),
        ]
    if kind in {"CPI", "PCE", "NFP", "EMPLOYMENT"}:
        metric = "물가" if kind in {"CPI", "PCE"} else "고용"
        return [
            _scenario("HOT", f"{metric}가 예상보다 강함", f"발표치가 시장 예상보다 강하고 Fed 긴축 기대를 높일 때", f"미국 금리와 달러 상승 압력이 커져 원화와 성장주에 부담이 될 수 있습니다.", _changes(("US2Y", "UP", "Fed 긴축 기대 강화"), ("DXY", "UP_PRESSURE", "미국 금리 상승"), ("USD/KRW", "UP_PRESSURE", "원화 약세 압력"), ("성장주", "DOWN_PRESSURE", "할인율 상승")), ["US2Y 상승", "DXY 상승", "나스닥 약세"]),
            _scenario("INLINE", "예상 부합", "발표치가 컨센서스 범위일 때", "정책 기대 변화가 작으면 다른 이벤트와 기존 추세가 더 중요합니다.", _changes(("US2Y", "MIXED", "정책 기대 변화 제한"), ("DXY", "MIXED", "새 충격 제한")), ["초기 변동 후 되돌림"]),
            _scenario("COOL", f"{metric}가 예상보다 약함", "발표치가 예상보다 약해 Fed 완화 기대를 높일 때", "미국 금리와 달러가 내려가면 원화·성장주에 우호적일 수 있지만 경기침체 우려가 커지는지도 같이 봐야 합니다.", _changes(("US2Y", "DOWN", "Fed 완화 기대"), ("DXY", "DOWN_PRESSURE", "금리 메리트 약화"), ("USD/KRW", "DOWN_PRESSURE", "원화 강세 압력"), ("성장주", "UP_PRESSURE", "할인율 하락")), ["US2Y 하락", "DXY 하락", "경기민감주와 성장주의 상대반응"]),
        ]
    if kind in {"TREASURY_BUYBACK", "TREASURY_REFUNDING"}:
        return [
            _scenario("RELIEF", "채권 수급 부담 완화", "바이백·발행계획이 시장 예상보다 장기채 수급 부담을 줄일 때", "장기금리가 안정되면 성장주·원화 등 위험자산에 우호적일 수 있습니다.", _changes(("US10Y/US30Y", "DOWN_PRESSURE", "장기채 수급 부담 완화"), ("NASDAQ", "UP_PRESSURE", "할인율 부담 완화"), ("USD/KRW", "DOWN_PRESSURE", "risk-off 압력 완화 가능성")), ["10년·30년 금리 하락", "입찰 수요 개선", "NASDAQ 상대강세"]),
            _scenario("INLINE", "예상 범위", "발행·바이백 계획이 예상과 비슷할 때", "시장 방향은 인플레이션·Fed·재정전망 같은 다른 변수가 더 좌우할 수 있습니다.", _changes(("US10Y/US30Y", "MIXED", "새 수급 충격 제한"), ("DXY", "MIXED", "다른 변수 영향 확대")), ["장기금리 제한적 반응"]),
            _scenario("STRESS", "채권 수급 부담 확대", "장기물 발행 부담이나 수요 부진이 예상보다 클 때", "장기금리가 급등하면 달러·위험회피가 강해지고 원화·성장주에 부담이 될 수 있습니다.", _changes(("US10Y/US30Y", "UP", "공급/수요 불균형"), ("NASDAQ", "DOWN_PRESSURE", "할인율 상승"), ("USD/KRW", "UP_PRESSURE", "risk-off와 달러 수요")), ["장기금리 급등", "입찰 tail 확대", "USD/KRW 상승"]),
        ]
    if kind == "ELECTION":
        return [
            _scenario("FISCAL_EXPANSION", "재정확대 기대 강화", "선거 결과가 감세·지출 확대 가능성을 높일 때", "미 장기금리 상승과 업종별 정책 수혜/피해가 동시에 나타날 수 있습니다.", _changes(("US10Y/US30Y", "UP_PRESSURE", "재정적자·국채공급 기대"), ("DXY", "MIXED", "금리 상승과 재정우려가 충돌"), ("정책수혜업종", "UP_PRESSURE", "정책 기대 선반영")), ["장기금리 반응", "정책 세부안", "업종별 상대수익률"]),
            _scenario("GRIDLOCK", "정책 추진력 약화", "분점정부 등으로 큰 정책변화 가능성이 낮아질 때", "대규모 정책 변화 기대가 줄면서 기존 경기·Fed 요인이 다시 중요해질 수 있습니다.", _changes(("US10Y", "MIXED", "재정 기대 완화 가능성"), ("주식시장", "MIXED", "정책 불확실성 완화와 성장 기대 충돌")), ["재정정책 기대 변화", "변동성 하락 여부"]),
        ]
    if kind == "REGULATION":
        return [
            _scenario("ADVANCE", "법안·규제 진전", "표결·심사를 통과해 실제 시행 가능성이 높아질 때", "관련 산업의 수혜·비용 구조가 바뀔 가능성이 커져 관련 종목 재평가가 나타날 수 있습니다.", _changes(("관련산업", "REPRICE", "정책 시행 확률 상승"),), ["다음 입법 단계", "기업 가이던스", "관련 종목 거래량"]),
            _scenario("DELAY", "지연·부결", "절차가 지연되거나 필요한 표를 확보하지 못할 때", "정책 기대가 되돌려지며 선반영된 관련 종목이 반대로 움직일 수 있습니다.", _changes(("관련산업", "REVERSE_EXPECTATION", "정책 시행 확률 하락"),), ["재상정 일정", "대체 법안", "선반영 가격 되돌림"]),
        ]
    return [
        _scenario("POSITIVE_SURPRISE", "예상보다 긍정적", "결과가 현재 시장 기대보다 관련 자산에 우호적일 때", "관련 금리·환율·수급이 실제로 같은 방향으로 움직이는지 확인합니다.", _changes(("관련자산", "FAVORABLE", "예상 대비 긍정적 결과"),), ["관련 가격·수급 확인"]),
        _scenario("NEGATIVE_SURPRISE", "예상보다 부정적", "결과가 현재 시장 기대보다 관련 자산에 불리할 때", "예상되는 부정적 전달경로가 실제 시장 가격으로 확인되는지 봅니다.", _changes(("관련자산", "UNFAVORABLE", "예상 대비 부정적 결과"),), ["관련 가격·수급 확인"]),
    ]


def project_impact_and_scenarios(event: Any) -> dict[str, Any]:
    profile = impact_profile(event)
    explicit = _get(event, "decision_card", {}) or {}
    scenarios = outcome_scenarios(event)
    # Only accept explicit probability overlays when explicitly attributed to OUR_MI.
    probability_overrides = dict(explicit.get("scenario_probabilities") or {}) if isinstance(explicit, Mapping) else {}
    if str(explicit.get("scenario_probability_source") or "").upper() == "OUR_MI":
        for scenario in scenarios:
            value = probability_overrides.get(scenario["scenario_id"])
            if value is not None:
                try:
                    p = float(value)
                except (TypeError, ValueError):
                    continue
                if 0.0 <= p <= 1.0:
                    scenario["probability"] = p
                    scenario["probability_source"] = "OUR_MI"
    return {"impact_profile": profile.to_dict(), "outcome_scenarios": scenarios}
