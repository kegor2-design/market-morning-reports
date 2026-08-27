from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from .primitives import map_expert_text

IMPORTANCE_SCORE = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
LIFECYCLE = ("DISCOVERED", "RESEARCH_CANDIDATE", "HISTORICALLY_SUPPORTED", "OUT_OF_SAMPLE_SUPPORTED", "OUR_CHART_PRINCIPLE", "REJECTED")


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalized_signature(parts: Iterable[str]) -> str:
    text = "|".join(re.sub(r"\s+", " ", str(part).strip()).casefold() for part in parts if str(part).strip())
    return hashlib.sha256(text.encode()).hexdigest()[:20].upper()


def _point_in_time_support(claim: dict[str, Any]) -> tuple[bool, list[str]]:
    records = (claim.get("chart_evidence") or {}).get("records") or []
    claim_id = str(claim.get("claim_id") or "")
    supported = []
    for row in records:
        if claim_id and str(row.get("source_claim_id") or "") not in {"", claim_id}:
            continue
        if str(row.get("primitive_mapping_status") or "") == "SUPPORTED_BY_POINT_IN_TIME_CHART":
            supported.append(str(row.get("source_claim_id") or claim_id))
    return bool(supported), supported


def _candidate_from_claim(claim: dict[str, Any], channel: dict[str, Any], primitive_registry: dict[str, Any]) -> dict[str, Any] | None:
    structured = claim.get("chart_strategy") if isinstance(claim.get("chart_strategy"), dict) else {}
    chart_dependent = bool(claim.get("chart_analysis_requested")) or bool(structured.get("is_strategy_candidate"))
    if not chart_dependent:
        return None
    source_text = " ".join([
        str(claim.get("claim_summary_ko") or ""),
        " ".join(_text_list(claim.get("causal_chain"))),
        " ".join(_text_list(claim.get("invalidation_conditions"))),
        " ".join(_text_list(structured.get("entry_conditions"))),
        " ".join(_text_list(structured.get("confirmation_conditions"))),
        " ".join(_text_list(structured.get("failure_pattern"))),
    ]).strip()
    mapped = map_expert_text(source_text, primitive_registry)
    allowed = {str(row.get("id")) for row in primitive_registry.get("primitives") or [] if row.get("id")}
    explicit = [item for item in _text_list(structured.get("primitive_candidates")) if item in allowed]
    primitive_ids = []
    for item in explicit + [str(row.get("primitive_id")) for row in mapped]:
        if item and item in allowed and item not in primitive_ids:
            primitive_ids.append(item)
    conditions = {
        "entry": _text_list(structured.get("entry_conditions")),
        "confirmation": _text_list(structured.get("confirmation_conditions")),
        "exit": _text_list(structured.get("exit_conditions")),
        "invalidation": _text_list(structured.get("invalidation_conditions")) or _text_list(claim.get("invalidation_conditions")),
        "risk_management": _text_list(structured.get("risk_management")),
        "failure_pattern": _text_list(structured.get("failure_pattern")),
        "explicit_numeric_rules": _text_list(structured.get("explicit_numeric_rules")),
    }
    if not primitive_ids and not any(conditions.values()):
        return None
    pit_supported, pit_records = _point_in_time_support(claim)
    timeframe = str(structured.get("timeframe_hint") or "UNKNOWN")
    method_family = str(structured.get("method_family") or channel.get("role") or "CHART_METHOD")
    signature_parts = [method_family, timeframe, *primitive_ids, *conditions["entry"], *conditions["confirmation"], *conditions["invalidation"]]
    strategy_id = "YCS-" + _normalized_signature(signature_parts or [str(claim.get("claim_id"))])
    lifecycle = "RESEARCH_CANDIDATE" if pit_supported else "DISCOVERED"
    candidate_types = []
    if primitive_ids: candidate_types.append("NEW_RULE")
    if conditions["failure_pattern"]: candidate_types.append("NEW_FAILURE_RULE")
    if conditions["invalidation"]: candidate_types.append("NEW_INVALIDATION")
    if conditions["risk_management"]: candidate_types.append("NEW_RISK_MANAGEMENT")
    if structured.get("existing_rule_challenge"): candidate_types.append("EXISTING_RULE_CHALLENGE")
    if _text_list(structured.get("new_method_terms")): candidate_types.append("NEW_PRIMITIVE_OR_METHOD_TERM")
    return {
        "schema_version": "1.0",
        "strategy_id": strategy_id,
        "lifecycle_status": lifecycle,
        "candidate_types": candidate_types or ["NEW_RULE"],
        "method_family": method_family,
        "primitive_ids": primitive_ids,
        "timeframe_hint": timeframe,
        "asset_hint": str(structured.get("asset_hint") or "UNKNOWN"),
        "conditions": conditions,
        "reasoning": _text_list(structured.get("reasoning")) or _text_list(claim.get("causal_chain")),
        "new_method_terms": _text_list(structured.get("new_method_terms")),
        "existing_rule_challenge": str(structured.get("existing_rule_challenge") or ""),
        "source_claim_ids": [str(claim.get("claim_id"))],
        "source_examples": [{
            "channel_id": claim.get("channel_id"), "channel_name": claim.get("channel_name"),
            "video_id": claim.get("video_id"), "video_url": claim.get("video_url"),
            "speech_start_ms": claim.get("speech_start_ms"), "speech_end_ms": claim.get("speech_end_ms"),
            "claim_summary_ko": claim.get("claim_summary_ko"), "importance": claim.get("importance"),
            "point_in_time_supported": pit_supported,
        }],
        "point_in_time_source_example_verified": pit_supported,
        "point_in_time_support_records": pit_records,
        "independently_verified_edge": False,
        "promotion_block_reason": "HISTORICAL_UNIVERSE_AND_OUT_OF_SAMPLE_VALIDATION_REQUIRED",
        "research_priority": "HIGH" if IMPORTANCE_SCORE.get(str(claim.get("importance") or "LOW"), 0) >= 3 or str(claim.get("classification")) == "ACTION_RULE" else "NORMAL",
    }


def build_strategy_candidates(claims: Iterable[dict[str, Any]], channels: Iterable[dict[str, Any]], primitive_registry: dict[str, Any]) -> list[dict[str, Any]]:
    channel_by_id = {str(row.get("id")): row for row in channels if row.get("id")}
    merged: dict[str, dict[str, Any]] = {}
    for claim in claims:
        channel = channel_by_id.get(str(claim.get("channel_id")), {})
        candidate = _candidate_from_claim(claim, channel, primitive_registry)
        if not candidate:
            continue
        key = candidate["strategy_id"]
        if key not in merged:
            merged[key] = candidate
            continue
        current = merged[key]
        for claim_id in candidate["source_claim_ids"]:
            if claim_id not in current["source_claim_ids"]:
                current["source_claim_ids"].append(claim_id)
        current["source_examples"].extend(candidate["source_examples"])
        current["candidate_types"] = sorted(set(current["candidate_types"]) | set(candidate["candidate_types"]))
        current["point_in_time_source_example_verified"] = current["point_in_time_source_example_verified"] or candidate["point_in_time_source_example_verified"]
        if current["point_in_time_source_example_verified"]:
            current["lifecycle_status"] = "RESEARCH_CANDIDATE"
        if candidate["research_priority"] == "HIGH": current["research_priority"] = "HIGH"
    return sorted(merged.values(), key=lambda row: (row["research_priority"] == "HIGH", len(row["source_claim_ids"])), reverse=True)


def build_historical_research_queue(candidates: Iterable[dict[str, Any]], research_policy: dict[str, Any], *, target_date: str) -> list[dict[str, Any]]:
    scan = research_policy.get("historical_scan") or {}
    rows = []
    for candidate in candidates:
        rows.append({
            "task_id": "YCRT-" + candidate["strategy_id"].split("-", 1)[-1],
            "strategy_id": candidate["strategy_id"],
            "target_date": target_date,
            "status": "WAITING_FOR_LIVE_DATA_ADAPTER" if scan.get("provider_status") != "READY" else "READY",
            "universe": scan.get("default_universe", "KR_ALL_LISTED"),
            "preferred_provider": scan.get("preferred_provider", "MYDREAM2000"),
            "provider_status": scan.get("provider_status", "UNKNOWN"),
            "point_in_time_required": bool(scan.get("point_in_time_required", True)),
            "primitive_ids": candidate.get("primitive_ids") or [],
            "timeframe_hint": candidate.get("timeframe_hint"),
            "conditions": candidate.get("conditions") or {},
            "conditioning_dimensions": scan.get("conditioning_dimensions") or [],
            "forward_windows": scan.get("forward_windows") or [1, 5, 20, 60],
            "minimum_research_sample": scan.get("minimum_research_sample", 100),
            "compare_success_and_failure": bool(scan.get("compare_success_and_failure", True)),
            "out_of_sample_required": bool(scan.get("out_of_sample_required", True)),
            "note": "Do not execute against MyDream2000 until live DB/table/column schema is verified read-only.",
        })
    return rows


def build_nightly_chart_research(target_date: str, claims: list[dict[str, Any]], channels: list[dict[str, Any]], primitive_registry: dict[str, Any], research_policy: dict[str, Any]) -> dict[str, Any]:
    candidates = build_strategy_candidates(claims, channels, primitive_registry)
    queue = build_historical_research_queue(candidates, research_policy, target_date=target_date)
    type_counts: dict[str, int] = defaultdict(int)
    for row in candidates:
        for item in row.get("candidate_types") or []: type_counts[item] += 1
    return {
        "schema_version": "1.0", "mode": "SHADOW_ONLY", "target_date": target_date,
        "candidate_count": len(candidates),
        "research_candidate_count": sum(row.get("lifecycle_status") == "RESEARCH_CANDIDATE" for row in candidates),
        "discovered_count": sum(row.get("lifecycle_status") == "DISCOVERED" for row in candidates),
        "candidate_type_counts": dict(sorted(type_counts.items())),
        "candidates": candidates,
        "historical_research_queue": queue,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "warning": "Content creates research hypotheses only. Historical and out-of-sample evidence are required before OUR_CHART_PRINCIPLE promotion.",
    }


def render_chart_research_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "## Nightly Chart Strategy Research", "",
        f"- 신규/갱신 전략 후보: {payload.get('candidate_count', 0)}",
        f"- Point-in-Time 사례 확인 후 연구후보: {payload.get('research_candidate_count', 0)}",
        f"- 아직 원천 사례 검증 전: {payload.get('discovered_count', 0)}", "",
    ]
    for idx, row in enumerate((payload.get("candidates") or [])[:12], 1):
        lines += [
            f"### C{idx}. {row.get('strategy_id')} · {row.get('lifecycle_status')}", "",
            f"- Primitive: {', '.join(row.get('primitive_ids') or []) or 'UNKNOWN'}",
            f"- Timeframe: {row.get('timeframe_hint') or 'UNKNOWN'} / 방법군: {row.get('method_family')}",
            f"- 출처 claim 수: {len(row.get('source_claim_ids') or [])}",
            f"- 승격 차단: {row.get('promotion_block_reason')}", "",
        ]
    return "\n".join(lines)
