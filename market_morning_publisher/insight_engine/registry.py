from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VALID_DECISIONS = {"ACCEPT_P0", "ACCEPT_P1", "EVENT_ONLY", "RESEARCH_ONLY", "REJECT"}


def load_metric_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_metric_registry(payload)
    return payload


def validate_metric_registry(payload: dict[str, Any]) -> None:
    metrics = payload.get("metrics") or []
    ids = [str(row.get("metric_id") or "") for row in metrics]
    if any(not item for item in ids):
        raise ValueError("metric_id is required")
    if len(ids) != len(set(ids)):
        raise ValueError("metric_id must be unique")
    for row in metrics:
        decision = row.get("decision")
        if decision not in VALID_DECISIONS:
            raise ValueError(f"invalid metric decision: {row.get('metric_id')}={decision}")
        if decision in {"ACCEPT_P0", "ACCEPT_P1"} and not row.get("why_collect"):
            raise ValueError(f"why_collect required: {row.get('metric_id')}")
        if row.get("point_in_time_required") and not row.get("vintage_policy"):
            raise ValueError(f"vintage_policy required: {row.get('metric_id')}")


def by_metric_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["metric_id"]): row for row in payload.get("metrics", [])}


def accepted_metric_ids(payload: dict[str, Any], *, include_p1: bool = True) -> list[str]:
    decisions = {"ACCEPT_P0", "ACCEPT_P1"} if include_p1 else {"ACCEPT_P0"}
    return [row["metric_id"] for row in payload.get("metrics", []) if row.get("decision") in decisions]


def registry_coverage(payload: dict[str, Any], observations: dict[str, Any]) -> dict[str, Any]:
    accepted = accepted_metric_ids(payload)
    observed = []
    unknown = []
    for metric_id in accepted:
        row = observations.get(metric_id) or {}
        if row.get("state") not in {None, "UNKNOWN", "STALE"} or row.get("value") is not None:
            observed.append(metric_id)
        else:
            unknown.append(metric_id)
    return {
        "accepted_total": len(accepted),
        "observed": len(observed),
        "unknown": len(unknown),
        "coverage_pct": round(100.0 * len(observed) / len(accepted), 1) if accepted else 100.0,
        "unknown_metric_ids": unknown,
    }


def make_update_candidate(
    *,
    candidate_type: str,
    key: str,
    reason: str,
    source_lens: str,
    source_ref: str | None = None,
    related_hypothesis: str | None = None,
) -> dict[str, Any]:
    return {
        "candidate_type": candidate_type,
        "key": key,
        "reason": reason,
        "source_lens": source_lens,
        "source_ref": source_ref,
        "related_hypothesis": related_hypothesis,
        "decision": "REVIEW_REQUIRED",
    }


def collection_plan(payload: dict[str, Any]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "ACTIVE_P0": [], "PENDING_P0": [], "EVENT_P0": [], "P1": [], "RESEARCH": [], "REJECTED": []
    }
    for row in payload.get("metrics", []):
        decision = row.get("decision")
        adapter = row.get("adapter_status", "PENDING")
        compact = {
            "metric_id": row.get("metric_id"), "label_ko": row.get("label_ko"), "why_collect": row.get("why_collect"),
            "candidate_sources": row.get("candidate_sources") or [], "point_in_time_required": bool(row.get("point_in_time_required")),
            "adapter_status": adapter,
        }
        if decision == "ACCEPT_P0" and adapter == "ACTIVE": buckets["ACTIVE_P0"].append(compact)
        elif decision == "ACCEPT_P0" and adapter == "EVENT_MANAGED": buckets["EVENT_P0"].append(compact)
        elif decision == "ACCEPT_P0": buckets["PENDING_P0"].append(compact)
        elif decision == "ACCEPT_P1": buckets["P1"].append(compact)
        elif decision == "RESEARCH_ONLY": buckets["RESEARCH"].append(compact)
        elif decision == "REJECT": buckets["REJECTED"].append(compact)
    return {key: sorted(value, key=lambda row: str(row.get("metric_id"))) for key, value in buckets.items()}
