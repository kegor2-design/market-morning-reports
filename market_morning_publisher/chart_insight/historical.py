from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable

from market_morning_publisher.youtube_chart.ohlcv import completed_bars_as_of
from market_morning_publisher.youtube_chart.outcomes import evaluate_claim
from market_morning_publisher.youtube_chart.time_model import first_bar_after

from .primitives import detect_primitives, key_levels, map_expert_text


def _normalize_claim(claim: dict[str, Any]) -> dict[str, Any]:
    value = dict(claim)
    if value.get("resolved_direction") and not value.get("direction"):
        value["direction"] = value.get("resolved_direction")
    if value.get("resolved_asset_symbol") and not value.get("asset_symbol"):
        value["asset_symbol"] = value.get("resolved_asset_symbol")
    if value.get("resolved_timeframe") and not value.get("timeframe"):
        value["timeframe"] = value.get("resolved_timeframe")
    if value.get("validation_context_excerpt") and not value.get("speech_excerpt"):
        value["speech_excerpt"] = value.get("validation_context_excerpt")
    return value


def validate_historical_claim(
    claim: dict[str, Any],
    bars: list[dict[str, Any]],
    primitive_registry: dict[str, Any],
    *,
    windows: Iterable[int] = (1, 5, 20, 60),
    context_bars: int = 60,
    regime: str | None = None,
    horizon_bars: int | None = 60,
) -> dict[str, Any]:
    value = _normalize_claim(claim)
    entry_index = first_bar_after(bars, value.get("publicly_actionable_at"))
    if entry_index is None:
        return {
            "schema_version": "1.0", "source_claim_id": value.get("source_claim_id"),
            "status": "DATA_MISSING", "reason": "NO_BAR_AFTER_ACTIONABLE_TIME", "validation_state": "SHADOW_ONLY",
        }
    completed = completed_bars_as_of(bars, value.get("publicly_actionable_at"))
    context = completed[-max(3, int(context_bars)):]
    if len(context) < 3:
        return {
            "schema_version": "1.0", "source_claim_id": value.get("source_claim_id"),
            "status": "DATA_MISSING", "reason": "INSUFFICIENT_POINT_IN_TIME_CONTEXT", "validation_state": "SHADOW_ONLY",
        }
    mapped = map_expert_text(str(value.get("speech_excerpt") or ""), primitive_registry)
    mapped_ids = {row["primitive_id"] for row in mapped}
    observed = detect_primitives(context, primitive_registry)
    observed_ids = {row["primitive_id"] for row in observed}
    if not mapped_ids:
        mapping_status = "NO_EXPERT_PRIMITIVE_MAPPING"
    elif mapped_ids & observed_ids:
        mapping_status = "SUPPORTED_BY_POINT_IN_TIME_CHART"
    else:
        mapping_status = "NOT_OBSERVED_IN_POINT_IN_TIME_CHART"
    outcome = evaluate_claim(value, bars, windows=windows, horizon_bars=horizon_bars)
    return {
        "schema_version": "1.0",
        "source_claim_id": value.get("source_claim_id"),
        "channel_id": value.get("channel_id"),
        "video_id": value.get("video_id"),
        "asset_symbol": value.get("asset_symbol") or value.get("resolved_asset_symbol"),
        "timeframe": value.get("timeframe") or value.get("resolved_timeframe"),
        "publicly_actionable_at": value.get("publicly_actionable_at"),
        "point_in_time_context": {
            "bar_count": len(context),
            "first_timestamp": context[0].get("timestamp"),
            "last_timestamp": context[-1].get("timestamp"),
            "future_bars_used_for_context": 0,
            "key_levels": key_levels(context),
            "observed_primitives": observed,
        },
        "expert_primitive_candidates": mapped,
        "primitive_mapping_status": mapping_status,
        "market_regime": regime or "UNKNOWN",
        "outcome": outcome,
        "status": "EVALUATED" if outcome.get("status") not in {"DATA_MISSING"} else "DATA_MISSING",
        "validation_state": "SHADOW_ONLY",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_edge_summary(validations: Iterable[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in validations:
        timeframe = str(row.get("timeframe") or "UNKNOWN")
        regime = str(row.get("market_regime") or "UNKNOWN")
        candidates = row.get("expert_primitive_candidates") or []
        mapping_status = str(row.get("primitive_mapping_status") or "")
        # Only a primitive that was actually visible in the point-in-time chart may contribute
        # to OUR primitive edge statistics. A source-language match alone is not enough.
        if mapping_status and mapping_status != "SUPPORTED_BY_POINT_IN_TIME_CHART":
            candidates = []
        if mapping_status == "SUPPORTED_BY_POINT_IN_TIME_CHART":
            observed_ids = {str(item.get("primitive_id")) for item in (row.get("point_in_time_context", {}).get("observed_primitives") or [])}
            candidates = [item for item in candidates if str(item.get("primitive_id")) in observed_ids]
        for primitive in candidates:
            primitive_id = str(primitive.get("primitive_id") or "")
            if primitive_id:
                buckets[(primitive_id, timeframe, regime)].append(row)
    summaries = []
    for (primitive_id, timeframe, regime), rows in sorted(buckets.items()):
        forward_by_window: dict[int, list[float]] = defaultdict(list)
        binary = []
        for row in rows:
            outcome = row.get("outcome") or {}
            if outcome.get("status") in {"SUCCESS", "FAILURE", "AMBIGUOUS"}:
                binary.append(outcome.get("status"))
            for item in outcome.get("forward_windows") or []:
                if item.get("status") == "COMPLETE" and item.get("return_pct") is not None:
                    forward_by_window[int(item["bars"])].append(float(item["return_pct"]))
        forward = {}
        for window, returns in sorted(forward_by_window.items()):
            forward[str(window)] = {
                "sample": len(returns),
                "positive_rate": round(sum(value > 0 for value in returns) / len(returns), 6) if returns else None,
                "average_return_pct": round(mean(returns), 6) if returns else None,
            }
        summaries.append({
            "primitive_id": primitive_id,
            "timeframe": timeframe,
            "market_regime": regime,
            "claim_sample": len(rows),
            "binary_success": binary.count("SUCCESS"),
            "binary_failure": binary.count("FAILURE"),
            "binary_ambiguous": binary.count("AMBIGUOUS"),
            "forward": forward,
            "promotion_status": "RESEARCH_ONLY",
        })
    return {
        "schema_version": "1.0", "mode": "SHADOW_ONLY", "groups": summaries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "warning": "These are descriptive historical outcomes, not causal proof or an automatic trading rule.",
    }
