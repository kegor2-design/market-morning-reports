from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
import hashlib
import json


def build_morning_report_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create the public factual/report view without re-running MI inference."""
    return {
        "view_id": "MORNING_REPORT",
        "as_of": payload.get("as_of"),
        "overnight_market": deepcopy(payload.get("overnight_market", {})),
        "major_news": deepcopy(payload.get("major_news", [])),
        "macro_and_policy": deepcopy(payload.get("macro_and_policy", [])),
        "official_calendar": deepcopy(payload.get("official_calendar", [])),
        "short_term_market_map_summary": deepcopy(payload.get("short_term_market_map_summary", {})),
        "brief_mi_context": deepcopy(payload.get("brief_mi_context", [])),
        "sources": deepcopy(payload.get("sources", [])),
        "guardrail": "REPORT_VIEW_DOES_NOT_REGENERATE_MI",
    }


def build_premarket_mi_view(frozen_scenario: Mapping[str, Any], *, short_term_map: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Expose the same frozen MI scenario object used by the app.

    No scenario probabilities or stock predictions may be recomputed here; this is a
    renderer boundary, not another inference stage.
    """
    if not frozen_scenario.get("scenario_id"):
        raise ValueError("scenario_id is required")
    if not frozen_scenario.get("as_of"):
        raise ValueError("as_of is required")
    view = deepcopy(dict(frozen_scenario))
    view["view_id"] = "PREMARKET_MI_SCENARIO"
    if short_term_map is not None:
        view["short_term_market_map"] = deepcopy(dict(short_term_map))
    view["publication_guardrail"] = "FROZEN_SCENARIO_ONLY"
    return view


def build_closing_review_view(original_prediction: Mapping[str, Any], evaluation: Mapping[str, Any]) -> dict[str, Any]:
    if not original_prediction.get("prediction_id"):
        raise ValueError("prediction_id is required")
    return {
        "view_id": "CLOSING_MI_REVIEW",
        "original_prediction": deepcopy(dict(original_prediction)),
        "evaluation": deepcopy(dict(evaluation)),
        "publication_guardrail": "ORIGINAL_PREDICTION_IMMUTABLE",
    }


def freeze_mi_scenario(analysis: Mapping[str, Any], *, report_date: str, as_of: str, prediction_ids: list[str] | None = None) -> dict[str, Any]:
    source = json.dumps({"date": report_date, "as_of": as_of, "analysis": analysis}, ensure_ascii=False, sort_keys=True)
    return {"scenario_id": "MI-S-" + hashlib.sha256(source.encode()).hexdigest()[:16], "as_of": as_of, "report_date": report_date, "core_market_judgement": analysis.get("one_line_diagnosis"), "confidence": analysis.get("overall_confidence"), "scenarios": deepcopy(analysis.get("scenarios", [])), "critical_events": deepcopy(analysis.get("critical_upcoming_events", [])), "watch_indicators": deepcopy(analysis.get("watch_items", [])), "sector_bias": deepcopy(analysis.get("sector_views", [])), "stock_predictions": deepcopy(analysis.get("mi_predictions", [])), "invalidation_conditions": deepcopy(analysis.get("invalidation_conditions", [])), "prediction_ids": list(prediction_ids or []), "freeze_guardrail": "IMMUTABLE_POINT_IN_TIME_SNAPSHOT"}


def render_premarket_mi_markdown(view: Mapping[str, Any]) -> str:
    def bullets(values: Any) -> str:
        return "\n".join("- " + (json.dumps(x, ensure_ascii=False) if isinstance(x, Mapping) else str(x)) for x in (values or [])) or "- 없음"
    market_map = view.get("short_term_market_map") or {}
    return f"""# 장전 MI 시나리오 | {view.get('report_date')}

기준 시각: **{view.get('as_of')}**  
scenario_id: **{view.get('scenario_id')}**  
확신도: **{view.get('confidence') or 'UNKNOWN'}**

## 오늘의 핵심 판단
{view.get('core_market_judgement') or '판단 가능한 MI 결과가 없습니다.'}

## 단기 시장지도 (1D~20D)
- 현재 상태: **{market_map.get('overall_state', 'NO_DATA')}**
- 압력 점수: **{market_map.get('overall_score')}**
- 해석: {market_map.get('interpretation', '데이터 부족')}

## Base / Upside / Risk
{bullets(view.get('scenarios'))}

## CRITICAL/HIGH 일정
{bullets(view.get('critical_events'))}

## 오늘 확인할 지표
{bullets(view.get('watch_indicators'))}

## 섹터 편향
{bullets(view.get('sector_bias'))}

## 명시적으로 확정된 종목·자산 예측
{bullets(view.get('stock_predictions'))}

## prediction_id
{bullets(view.get('prediction_ids'))}

## 판단 무효화 조건
{bullets(view.get('invalidation_conditions'))}

> 단기지도 점수는 수익률 확률이 아니라 현재 환경의 압력지표입니다. 이 글은 투자 권유가 아닙니다.
"""
