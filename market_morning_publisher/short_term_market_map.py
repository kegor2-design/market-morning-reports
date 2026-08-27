from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import math

MARKET_ALIASES = {"DX-Y.NYB": "DXY", "KRW=X": "USDKRW", "^TNX": "US10Y", "GC=F": "GOLD", "CL=F": "WTI", "^VIX": "VIX", "^IXIC": "NASDAQ", "^SOX": "SOX"}


@dataclass(frozen=True)
class IndicatorAssessment:
    indicator_id: str
    label: str
    available: bool
    stale: bool
    score: float | None
    signal: str
    explanation: str
    current: float | None = None
    change_1d_pct: float | None = None
    change_5d_pct: float | None = None
    change_20d_pct: float | None = None
    zscore_60d: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GroupAssessment:
    group_id: str
    label: str
    beginner_question: str
    score: float | None
    state: str
    coverage: float
    indicators: list[dict[str, Any]]
    beginner_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _bounded(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _raw_momentum(row: Mapping[str, Any]) -> float | None:
    """Convert multi-window movement to a bounded -100..100 impulse.

    It is intentionally scale-light. Production may replace upstream change/z-score
    adapters, but point-in-time semantics and orientation must remain unchanged.
    """
    c1 = _num(row.get("change_1d_pct"))
    c5 = _num(row.get("change_5d_pct"))
    c20 = _num(row.get("change_20d_pct"))
    z = _num(row.get("zscore_60d"))
    parts: list[tuple[float, float]] = []
    if c1 is not None:
        parts.append((math.tanh(c1 / 1.25) * 100.0, 0.45))
    if c5 is not None:
        parts.append((math.tanh(c5 / 3.0) * 100.0, 0.35))
    if c20 is not None:
        parts.append((math.tanh(c20 / 7.0) * 100.0, 0.15))
    if z is not None:
        parts.append((math.tanh(z / 2.0) * 100.0, 0.05))
    if not parts:
        # Event-style metrics such as CPI surprise can be passed as `signal_value`.
        sig = _num(row.get("signal_value"))
        if sig is None:
            return None
        scale = _num(row.get("signal_scale")) or 1.0
        return _bounded(math.tanh(sig / scale) * 100.0)
    total_w = sum(w for _, w in parts)
    return _bounded(sum(v * w for v, w in parts) / total_w)


def _context_orientation(indicator_id: str, raw: float, all_rows: Mapping[str, Mapping[str, Any]]) -> tuple[float, str]:
    """Handle assets whose direction is context dependent rather than monotonic."""
    if indicator_id == "GOLD":
        dxy = _raw_momentum(all_rows.get("DXY", {}))
        us10 = _raw_momentum(all_rows.get("US10Y", {}))
        # Gold up with dollar/yields down is often easing/liquidity friendly; gold up
        # with dollar/yields up is more consistent with stress/inflation hedging.
        if raw > 0 and (dxy or 0) < 0 and (us10 or 0) < 0:
            return abs(raw) * 0.45, "금 상승이 달러·금리 하락과 동반돼 완화/유동성 신호로 해석됩니다."
        if raw > 0 and ((dxy or 0) > 0 or (us10 or 0) > 0):
            return -abs(raw) * 0.35, "금 상승이 달러 또는 금리 상승과 동반돼 안전자산/인플레이션 경계 신호일 수 있습니다."
        return raw * 0.1, "금 단독 움직임은 방향성이 모호해 낮은 가중치로 반영합니다."
    if indicator_id == "WTI":
        # Oil down is not automatically risk-on: a collapse can signal demand stress.
        if raw > 45:
            return -abs(raw) * 0.5, "유가 급등은 단기 물가·금리 부담을 키울 수 있습니다."
        if raw < -60:
            return -abs(raw) * 0.15, "유가 급락은 물가에는 우호적이지만 경기수요 둔화 신호일 수 있어 중립에 가깝게 봅니다."
        return -raw * 0.2, "완만한 유가 하락은 물가 부담 완화, 상승은 물가 부담 확대 방향으로 약하게 반영합니다."
    if indicator_id == "COPPER":
        return raw * 0.25, "구리는 단기 경기 기대 보조지표로 낮은 가중치로 반영합니다."
    return 0.0, "상황 의존 지표라 단독 방향 신호로 사용하지 않습니다."


def _assess_indicator(spec: Mapping[str, Any], row: Mapping[str, Any], all_rows: Mapping[str, Mapping[str, Any]]) -> IndicatorAssessment:
    iid = str(spec.get("id", ""))
    label = str(spec.get("label", iid))
    stale = bool(row.get("stale", False))
    raw = _raw_momentum(row)
    if raw is None:
        return IndicatorAssessment(iid, label, False, stale, None, "NO_DATA", "데이터가 없어 점수에서 제외합니다.")
    if stale:
        return IndicatorAssessment(iid, label, True, True, None, "STALE", "데이터가 오래되어 현재 점수에서 제외합니다.", _num(row.get("current")), _num(row.get("change_1d_pct")), _num(row.get("change_5d_pct")), _num(row.get("change_20d_pct")), _num(row.get("zscore_60d")))

    orientation = str(spec.get("risk_on_when", "CONTEXT")).upper()
    if orientation == "UP":
        score = raw
        explanation = "상승할수록 단기 위험선호에 우호적인 방향으로 반영합니다."
    elif orientation == "DOWN":
        score = -raw
        explanation = "하락할수록 단기 위험선호에 우호적인 방향으로 반영합니다."
    else:
        score, explanation = _context_orientation(iid, raw, all_rows)
    score = _bounded(score)
    if score >= 35:
        signal = "RISK_ON"
    elif score <= -35:
        signal = "RISK_OFF"
    else:
        signal = "NEUTRAL"
    return IndicatorAssessment(iid, label, True, False, round(score, 2), signal, explanation, _num(row.get("current")), _num(row.get("change_1d_pct")), _num(row.get("change_5d_pct")), _num(row.get("change_20d_pct")), _num(row.get("zscore_60d")))


def _state(score: float | None) -> str:
    if score is None:
        return "NO_DATA"
    if score >= 35:
        return "STRONG_RISK_ON"
    if score >= 15:
        return "RISK_ON"
    if score <= -35:
        return "STRONG_RISK_OFF"
    if score <= -15:
        return "RISK_OFF"
    return "NEUTRAL"


def _summary(label: str, score: float | None, coverage: float) -> str:
    state = _state(score)
    if state == "NO_DATA":
        return f"{label} 데이터가 부족해 현재 방향을 판단하지 않습니다."
    phrase = {
        "STRONG_RISK_ON": "위험선호에 강하게 우호적",
        "RISK_ON": "위험선호에 다소 우호적",
        "NEUTRAL": "뚜렷한 한쪽 방향이 없는 중립",
        "RISK_OFF": "위험자산에 다소 부담",
        "STRONG_RISK_OFF": "위험자산에 강한 부담",
    }[state]
    suffix = "" if coverage >= 0.75 else " 다만 일부 데이터가 빠져 신뢰도를 낮춰 봐야 합니다."
    return f"{label} 축은 현재 {phrase}인 상태입니다.{suffix}"


def build_short_term_market_map(config: Mapping[str, Any], observations: Mapping[str, Mapping[str, Any]], *, as_of: str | None = None) -> dict[str, Any]:
    groups_out: list[GroupAssessment] = []
    composite_parts: list[tuple[float, float]] = []
    for group in config.get("groups", []):
        assessed: list[tuple[IndicatorAssessment, float]] = []
        for spec in group.get("indicators", []):
            item = _assess_indicator(spec, observations.get(str(spec.get("id")), {}), observations)
            assessed.append((item, float(spec.get("weight", 1.0))))
        usable = [(a, w) for a, w in assessed if a.score is not None]
        total_defined = max(1, len(assessed))
        coverage = len(usable) / total_defined
        if usable:
            denom = sum(w for _, w in usable)
            score = sum(float(a.score) * w for a, w in usable) / denom
            # Coverage reduces conviction without changing directional sign.
            score *= 0.5 + 0.5 * coverage
            score = round(_bounded(score), 2)
            composite_parts.append((score, float(group.get("weight", 1.0))))
        else:
            score = None
        groups_out.append(GroupAssessment(
            group_id=str(group.get("group_id")),
            label=str(group.get("label")),
            beginner_question=str(group.get("beginner_question", "")),
            score=score,
            state=_state(score),
            coverage=round(coverage, 4),
            indicators=[a.to_dict() for a, _ in assessed],
            beginner_summary=_summary(str(group.get("label")), score, coverage),
        ))

    if composite_parts:
        denom = sum(w for _, w in composite_parts)
        composite = round(_bounded(sum(s * w for s, w in composite_parts) / denom), 2)
    else:
        composite = None
    overall = _state(composite)
    generated = as_of or datetime.now(timezone.utc).isoformat()
    return {
        "version": str(config.get("version", "1.6.5.7")),
        "as_of": generated,
        "horizon": "SHORT_TERM_1D_TO_20D",
        "overall_score": composite,
        "overall_state": overall,
        "interpretation": _summary("단기 시장지도", composite, 1.0 if composite_parts else 0.0),
        "groups": [g.to_dict() for g in groups_out],
        "guardrails": [
            "점수는 수익률 예측확률이 아니라 현재 단기 환경의 압력 방향입니다.",
            "금·유가·비트코인은 단독 신호로 사용하지 않습니다.",
            "stale/미수집 데이터는 0점이 아니라 점수 계산에서 제외합니다.",
            "CPI 등 저빈도 지표는 최신 발표 surprise와 추세를 사용하고 발표 전후 이벤트와 함께 해석합니다."
        ]
    }


def observations_from_market_history(markets: list[Mapping[str, Any]], historical_reports: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Adapt existing Morning snapshots; unavailable series remain NO_DATA."""
    history: dict[str, list[float]] = {}
    for report in historical_reports:
        for row in report.get("markets", []):
            iid, value = MARKET_ALIASES.get(str(row.get("symbol"))), _num(row.get("value"))
            if iid and row.get("ok") and value is not None:
                history.setdefault(iid, []).append(value)
    out: dict[str, dict[str, Any]] = {}
    for row in markets:
        iid, value = MARKET_ALIASES.get(str(row.get("symbol"))), _num(row.get("value"))
        if not iid or not row.get("ok") or value is None:
            continue
        values = history.get(iid, [])
        def change(days: int) -> float | None:
            return (value / values[-days] - 1.0) * 100.0 if len(values) >= days and values[-days] else None
        age = _num(row.get("age_minutes"))
        out[iid] = {"current": value, "change_1d_pct": _num(row.get("change_pct")), "change_5d_pct": change(5), "change_20d_pct": change(20), "stale": age is None or age > 1440, "source_symbol": row.get("symbol"), "as_of": row.get("as_of_kst") or row.get("as_of_utc")}
    return out


def observations_from_us_state(snapshot: Mapping[str, Any], *, as_of: datetime) -> dict[str, dict[str, Any]]:
    """Reuse existing US-state histories while enforcing daily freshness."""
    key_map = {"us_2y": "US2Y", "us_30y": "US30Y", "btc_market": "BTC"}
    out: dict[str, dict[str, Any]] = {}
    for key, iid in key_map.items():
        metric = (snapshot.get("metrics") or {}).get(key) or {}
        history = [row for row in metric.get("history", []) if _num(row.get("value")) is not None]
        if not history:
            continue
        current = float(history[-1]["value"])
        release_date = str(metric.get("as_of") or history[-1].get("date") or "")
        try:
            age_days = (as_of.date() - datetime.fromisoformat(release_date).date()).days
        except ValueError:
            age_days = 999999
        def change(days: int) -> float | None:
            return (current / float(history[-days]["value"]) - 1.0) * 100.0 if len(history) >= days and history[-days].get("value") else None
        out[iid] = {"current": current, "change_1d_pct": change(2), "change_5d_pct": change(6), "change_20d_pct": change(21), "stale": age_days > 1, "as_of": release_date, "source_metric": key}
    return out
