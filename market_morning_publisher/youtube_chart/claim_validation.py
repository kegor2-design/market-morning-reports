from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .ohlcv import interval_for_timeframe


CLAIM_TYPES = {"DESCRIPTION", "FORECAST", "ACTION_RULE", "CONDITION", "MIXED", "UNKNOWN"}
REVIEW_STATUSES = {"PENDING", "CONFIRMED", "REJECTED"}
PREDICTIVE_TYPES = {"FORECAST", "ACTION_RULE"}


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _matched_markers(text: str, markers: Iterable[Any]) -> list[str]:
    matched: list[str] = []
    for raw in markers:
        marker = _normalized_text(raw)
        if marker and marker in text and str(raw) not in matched:
            matched.append(str(raw))
    return matched


def _collapse_adjacent_repetitions(tokens: list[str]) -> list[str]:
    """Collapse exact adjacent token blocks emitted by rolling captions."""
    result = list(tokens)
    index = 0
    collapsed = False
    while index < len(result):
        maximum = (len(result) - index) // 2
        duplicate_size = 0
        for size in range(maximum, 0, -1):
            left = [_normalized_text(item) for item in result[index:index + size]]
            right = [_normalized_text(item) for item in result[index + size:index + 2 * size]]
            if left == right:
                duplicate_size = size
                break
        if duplicate_size:
            del result[index + duplicate_size:index + 2 * duplicate_size]
            collapsed = True
            index = max(0, index - duplicate_size)
        else:
            index += 1
    if collapsed and len(result) >= 3:
        normalized = [_normalized_text(item) for item in result]
        for size in range(min(8, (len(result) - 1) // 2), 0, -1):
            if normalized[-size:] == normalized[:size]:
                del result[-size:]
                break
    return result


def merge_caption_texts(texts: Iterable[str]) -> str:
    """Merge rolling subtitle cues by word overlap without changing source rows."""
    merged: list[str] = []
    for raw in texts:
        current = _collapse_adjacent_repetitions(str(raw or "").split())
        if not current:
            continue
        normalized_current = [_normalized_text(item) for item in current]
        normalized_merged = [_normalized_text(item) for item in merged]
        if len(current) <= len(merged):
            lower = max(0, len(merged) - len(current) * 2)
            for start in range(lower, len(merged) - len(current) + 1):
                if normalized_merged[start:start + len(current)] == normalized_current:
                    current = []
                    break
        if not current:
            continue
        normalized_current = [_normalized_text(item) for item in current]
        normalized_merged = [_normalized_text(item) for item in merged]
        overlap = 0
        for size in range(min(len(merged), len(current)), 0, -1):
            if normalized_merged[-size:] == normalized_current[:size]:
                overlap = size
                break
        merged.extend(current[overlap:])
        merged = _collapse_adjacent_repetitions(merged)
    return " ".join(merged).strip()


def contextual_excerpt(
    cues: Iterable[Any],
    *,
    start_ms: int,
    end_ms: int,
    before_ms: int = 15_000,
    after_ms: int = 25_000,
) -> str:
    lower = max(0, int(start_ms) - max(0, int(before_ms)))
    upper = int(end_ms) + max(0, int(after_ms))
    selected = [
        str(cue.text)
        for cue in cues
        if int(cue.end_ms) >= lower and int(cue.start_ms) <= upper
    ]
    return merge_caption_texts(selected)


def classify_claim_nature(claim: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Return an explainable, conservative semantic suggestion.

    The result is never a human confirmation.  Multiple semantic signals are
    preserved because one subtitle span can combine history and a forecast.
    """
    text = _normalized_text(claim.get("validation_context_excerpt") or claim.get("speech_excerpt"))
    terms = config.get("classification_terms") or {}
    matches = {
        name: _matched_markers(text, terms.get(name, []))
        for name in ("ACTION_RULE", "FORECAST", "CONDITION", "DESCRIPTION")
    }
    detected = [name for name, values in matches.items() if values]
    has_action = bool(matches["ACTION_RULE"])
    has_forecast = bool(matches["FORECAST"])
    has_condition = bool(matches["CONDITION"])
    has_description = bool(matches["DESCRIPTION"])

    if has_action and has_description:
        primary = "MIXED"
    elif has_forecast and has_description:
        primary = "MIXED"
    elif has_action:
        primary = "ACTION_RULE"
    elif has_forecast:
        primary = "FORECAST"
    elif has_condition and has_description:
        primary = "MIXED"
    elif has_condition:
        primary = "CONDITION"
    elif has_description:
        primary = "DESCRIPTION"
    else:
        primary = "UNKNOWN"

    confidence = "LOW" if primary in {"MIXED", "UNKNOWN"} else "HIGH"
    if primary in {"FORECAST", "CONDITION"} and len(matches.get(primary, [])) == 1:
        confidence = "MEDIUM"
    return {
        "method": "RULE_BASED_CANDIDATE",
        "primary_type": primary,
        "detected_types": detected,
        "contains_condition": has_condition,
        "confidence": confidence,
        "matched_markers": matches,
        "requires_human_confirmation": True,
    }


def summarize_ocr(ocr: dict[str, Any] | None) -> dict[str, Any]:
    frames = list((ocr or {}).get("frames") or [])
    assets: set[str] = set()
    timeframes: set[str] = set()
    fitted_axis_frames = 0
    explicit_overlays = 0
    review_overlays = 0
    for frame in frames:
        fields = frame.get("screen_fields") or {}
        assets.update(str(item["symbol"]) for item in fields.get("asset_candidates", []) if item.get("symbol"))
        timeframes.update(
            str(item["normalized"])
            for item in fields.get("timeframe_candidates", [])
            if item.get("normalized")
        )
        axis_status = str((frame.get("price_axis_fit") or {}).get("status") or "UNKNOWN")
        if axis_status in {"FITTED", "HIGH"}:
            fitted_axis_frames += 1
        for overlay in frame.get("overlays") or []:
            if overlay.get("semantic_status") == "EXPLICIT":
                explicit_overlays += 1
            elif overlay.get("semantic_status") == "REVIEW_REQUIRED":
                review_overlays += 1
    return {
        "available": bool(frames),
        "frame_count": len(frames),
        "screen_asset_symbols": sorted(assets),
        "screen_timeframes": sorted(timeframes),
        "price_axis_fitted_frame_count": fitted_axis_frames,
        "explicit_overlay_count": explicit_overlays,
        "review_required_overlay_count": review_overlays,
    }


def _positive_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalize_review(review: dict[str, Any] | None) -> dict[str, Any]:
    raw = review or {}
    status = str(raw.get("review_status") or raw.get("status") or "PENDING").upper()
    claim_type = str(raw.get("claim_type") or "UNKNOWN").upper()
    direction = str(raw.get("direction") or "NEUTRAL").upper()
    pattern_ids = raw.get("pattern_ids") or []
    if isinstance(pattern_ids, str):
        pattern_ids = [item.strip() for item in re.split(r"[;,]", pattern_ids) if item.strip()]
    return {
        **raw,
        "review_version": str(raw.get("review_version") or "1.0"),
        "review_status": status if status in REVIEW_STATUSES else "PENDING",
        "claim_type": claim_type if claim_type in CLAIM_TYPES else "UNKNOWN",
        "direction": direction if direction in {"LONG", "SHORT", "NEUTRAL"} else "NEUTRAL",
        "asset_symbol": str(raw.get("asset_symbol") or "").strip() or None,
        "timeframe": str(raw.get("timeframe") or "").strip() or None,
        "target_price": _positive_float(raw.get("target_price")),
        "invalidation_price": _positive_float(raw.get("invalidation_price")),
        "pattern_ids": sorted(set(str(item) for item in pattern_ids)),
    }


def effective_claim(claim: dict[str, Any], review: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_review(review)
    result = dict(claim)
    if normalized["review_status"] != "CONFIRMED":
        return result
    if normalized["direction"] in {"LONG", "SHORT"}:
        result["direction"] = normalized["direction"]
    if normalized["timeframe"]:
        result["timeframe_spoken"] = normalized["timeframe"]
    if normalized["asset_symbol"]:
        result["asset_candidates"] = [{"symbol": normalized["asset_symbol"], "name": "HUMAN_CONFIRMED"}]
    result["target_price"] = normalized["target_price"]
    result["invalidation_price"] = normalized["invalidation_price"]
    result["human_review_status"] = "CONFIRMED"
    return result


def assess_claim(
    claim: dict[str, Any],
    *,
    config: dict[str, Any],
    review: dict[str, Any] | None = None,
    ocr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    automatic = classify_claim_nature(claim, config)
    normalized_review = normalize_review(review)
    review_status = normalized_review["review_status"]
    claim_type = normalized_review["claim_type"] if review_status == "CONFIRMED" else automatic["primary_type"]
    resolved = effective_claim(claim, normalized_review)
    ocr_summary = summarize_ocr(ocr)
    blockers: list[str] = []
    warnings: list[str] = []

    if review_status == "REJECTED":
        evaluation_mode = "EXCLUDED_REJECTED"
    elif review_status != "CONFIRMED":
        evaluation_mode = "PENDING_HUMAN_REVIEW"
        blockers.append("HUMAN_CONFIRMATION_REQUIRED")
        if automatic["primary_type"] == "MIXED":
            blockers.append("ATOMIC_CLAIM_SPLIT_REVIEW_REQUIRED")
        elif automatic["primary_type"] == "UNKNOWN":
            blockers.append("CLAIM_TYPE_UNKNOWN")
    elif claim_type == "DESCRIPTION":
        evaluation_mode = "EXCLUDED_RETROSPECTIVE_DESCRIPTION"
    elif claim_type == "CONDITION":
        evaluation_mode = "EXCLUDED_NON_DIRECTIONAL_CONDITION"
    elif claim_type == "MIXED":
        evaluation_mode = "NOT_SCOREABLE"
        blockers.append("ATOMIC_CLAIM_SPLIT_REQUIRED")
    elif claim_type == "UNKNOWN":
        evaluation_mode = "NOT_SCOREABLE"
        blockers.append("CLAIM_TYPE_UNKNOWN")
    else:
        assets = resolved.get("asset_candidates") or []
        if not normalized_review["asset_symbol"] or len(assets) != 1:
            blockers.append("HUMAN_CONFIRMED_ASSET_REQUIRED")
        if not normalized_review["timeframe"] or not interval_for_timeframe(resolved.get("timeframe_spoken")):
            blockers.append("SUPPORTED_HUMAN_CONFIRMED_TIMEFRAME_REQUIRED")
        if resolved.get("direction") not in {"LONG", "SHORT"}:
            blockers.append("EXPLICIT_DIRECTION_REQUIRED")
        if not resolved.get("publicly_actionable_at"):
            blockers.append("PUBLICLY_ACTIONABLE_TIME_REQUIRED")
        if blockers:
            evaluation_mode = "NOT_SCOREABLE"
        elif resolved.get("target_price") is not None and resolved.get("invalidation_price") is not None:
            evaluation_mode = "BINARY_SHADOW"
        else:
            evaluation_mode = "DIRECTIONAL_SHADOW"
            if (resolved.get("target_price") is None) != (resolved.get("invalidation_price") is None):
                warnings.append("TARGET_INVALIDATION_PAIR_INCOMPLETE")

    if not ocr_summary["available"]:
        warnings.append("OCR_NOT_AVAILABLE")
    elif not ocr_summary["price_axis_fitted_frame_count"]:
        warnings.append("PRICE_AXIS_NOT_FITTED")
    if ocr_summary["review_required_overlay_count"]:
        warnings.append("OVERLAY_SEMANTICS_REQUIRE_REVIEW")
    if len(ocr_summary["screen_asset_symbols"]) > 1:
        warnings.append("SCREEN_ASSET_AMBIGUOUS")
    if len(ocr_summary["screen_timeframes"]) > 1:
        warnings.append("SCREEN_TIMEFRAME_AMBIGUOUS")
    if claim.get("validation_context_source") != "RAW_VTT_WINDOW":
        warnings.append("RAW_VTT_CONTEXT_NOT_AVAILABLE")

    return {
        "schema_version": "1.0",
        "source_claim_id": claim["source_claim_id"],
        "channel_id": claim.get("channel_id"),
        "video_id": claim.get("video_id"),
        "timestamp_url": claim.get("timestamp_url"),
        "speech_excerpt": claim.get("speech_excerpt"),
        "validation_context_excerpt": claim.get("validation_context_excerpt") or claim.get("speech_excerpt"),
        "validation_context_source": claim.get("validation_context_source") or "CLAIM_EXCERPT",
        "publicly_actionable_at": claim.get("publicly_actionable_at"),
        "automatic_classification": automatic,
        "human_review": normalized_review,
        "effective_claim_type": claim_type,
        "evaluation_mode": evaluation_mode,
        "blocking_issues": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "ocr_summary": ocr_summary,
        "resolved_asset_symbol": normalized_review["asset_symbol"] if review_status == "CONFIRMED" else None,
        "resolved_timeframe": normalized_review["timeframe"] if review_status == "CONFIRMED" else None,
        "resolved_direction": resolved.get("direction") if review_status == "CONFIRMED" else None,
        "target_price": resolved.get("target_price") if review_status == "CONFIRMED" else None,
        "invalidation_price": resolved.get("invalidation_price") if review_status == "CONFIRMED" else None,
        "validation_state": "SHADOW_ONLY",
    }


def detect_pattern_candidates(
    claim: dict[str, Any],
    *,
    config: dict[str, Any],
    review: dict[str, Any] | None = None,
    evaluation_mode: str | None = None,
) -> list[dict[str, Any]]:
    text = _normalized_text(claim.get("validation_context_excerpt") or claim.get("speech_excerpt"))
    categories = set(str(item) for item in claim.get("claim_categories") or [])
    normalized_review = normalize_review(review)
    if normalized_review["review_status"] == "REJECTED":
        return []
    rows: list[dict[str, Any]] = []
    for candidate in config.get("pattern_candidates") or []:
        required_all = set(candidate.get("required_categories_all") or [])
        required_any = set(candidate.get("required_categories_any") or [])
        category_match = required_all.issubset(categories) and (not required_any or bool(required_any & categories))
        group_matches = []
        for group in candidate.get("text_marker_groups") or []:
            matched = _matched_markers(text, group)
            group_matches.append(matched)
        text_match = bool(group_matches) and all(group_matches)
        if not (category_match or text_match):
            continue
        pattern_id = str(candidate["pattern_id"])
        human_confirmed = (
            normalized_review["review_status"] == "CONFIRMED"
            and pattern_id in normalized_review["pattern_ids"]
        )
        rows.append({
            "schema_version": "1.0",
            "pattern_match_id": f"{claim['source_claim_id']}:{pattern_id}",
            "source_claim_id": claim["source_claim_id"],
            "pattern_id": pattern_id,
            "pattern_title": candidate.get("title"),
            "lifecycle_status": candidate.get("lifecycle_status", "UNDER_REVIEW"),
            "linked_principle_ids": candidate.get("linked_principle_ids") or [],
            "match_status": "HUMAN_CONFIRMED_SOURCE_MATCH" if human_confirmed else "AUTO_TEXT_CANDIDATE",
            "match_basis": {
                "category_match": category_match,
                "matched_categories": sorted(categories & (required_all | required_any)),
                "text_marker_group_matches": group_matches,
            },
            "evaluation_mode": evaluation_mode,
            "independently_verified": False,
            "validation_state": "SHADOW_ONLY",
        })
    return rows
