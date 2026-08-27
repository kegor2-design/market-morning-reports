from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .history import find_analog_cases
from .registry import by_metric_id, registry_coverage
from .causal_flow import build_causal_flow_packet


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _text(event: dict[str, Any]) -> str:
    return " ".join(str(event.get(key) or "") for key in ("type", "category", "headline", "name", "summary")).upper()


def select_reasoning_playbooks(event: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    text = _text(event)
    selected = []
    for playbook in config.get("playbooks", []):
        triggers = [str(x).upper() for x in playbook.get("triggers", [])]
        if playbook.get("id") == "GENERAL_EVENT_REASONING" or any(trigger in text for trigger in triggers):
            selected.append(playbook)
    return selected


def _active_hypotheses(hypotheses: Iterable[dict[str, Any]], playbook_ids: set[str], tags: set[str]) -> list[dict[str, Any]]:
    out = []
    for row in hypotheses:
        if row.get("status") not in {None, "OPEN", "UNKNOWN", "PARTIAL"}:
            continue
        related_playbooks = set(row.get("playbook_ids") or [])
        related_tags = {str(x).upper() for x in row.get("tags") or []}
        if related_playbooks & playbook_ids or related_tags & tags:
            out.append(row)
    return out


def build_reasoning_packet(
    event: dict[str, Any],
    *,
    metric_registry: dict[str, Any],
    playbook_config: dict[str, Any],
    historical_cases: list[dict[str, Any]],
    observations: dict[str, Any] | None = None,
    hypotheses: list[dict[str, Any]] | None = None,
    source_lenses: dict[str, Any] | None = None,
    chart_insight: dict[str, Any] | None = None,
    nightly_youtube: dict[str, Any] | None = None,
    causal_flow_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observations = observations or {}
    hypotheses = hypotheses or []
    selected = select_reasoning_playbooks(event, playbook_config)
    playbook_ids = {row["id"] for row in selected}
    tags = {str(x).upper() for x in event.get("tags") or []}
    for playbook in selected:
        tags.update(str(x).upper() for x in playbook.get("tags") or [])
    required = list(dict.fromkeys(
        [mid for playbook in selected for mid in playbook.get("required_metrics", [])] + list(event.get("metric_ids") or [])
    ))
    registry = by_metric_id(metric_registry)
    metric_requirements = []
    missing = []
    for mid in required:
        decision = registry.get(mid)
        observation = observations.get(mid) or {}
        observed = observation.get("state") not in {None, "UNKNOWN", "STALE"} or observation.get("value") is not None
        if not observed: missing.append(mid)
        metric_requirements.append({
            "metric_id": mid,
            "registry": decision or {"decision": "UNREGISTERED"},
            "observation": observation or {"state": "UNKNOWN"},
        })
    analogs = find_analog_cases(historical_cases, tags, limit=5)
    active = _active_hypotheses(hypotheses, playbook_ids, tags)
    questions = list(dict.fromkeys(q for row in selected for q in row.get("questions", [])))
    steps = playbook_config.get("standard_reasoning_steps", [])
    lens_rules = source_lenses.get("lenses", []) if source_lenses else []
    packet = {
        "schema_version": "1.0",
        "event": event,
        "selected_playbooks": sorted(playbook_ids),
        "reasoning_steps": steps,
        "questions": questions,
        "required_metrics": metric_requirements,
        "missing_metrics": missing,
        "historical_analogs": analogs,
        "active_hypotheses": active,
        "source_lens_rules": lens_rules,
        "chart_insight_evidence": chart_insight or {"status": "UNKNOWN"},
        "nightly_youtube_evidence": nightly_youtube or {"status": "UNKNOWN"},
        "registry_coverage": registry_coverage(metric_registry, observations),
        "status": "NEEDS_DATA" if missing else "READY_FOR_REASONING",
        "guardrails": [
            "Do not treat official stated intent as realized effect.",
            "Do not treat high-weight expert hypotheses as facts.",
            "For historical comparisons, use only information released by that historical decision date whenever point-in-time data exists.",
            "Record at least two plausible alternative hypotheses before a final causal conclusion.",
            "Record explicit invalidation conditions and post-event verification windows.",
            "Do not let post-event price movement rewrite the pre-event hypothesis without logging the change.",
            "Chart Insight is an independent evidence layer; never let a chart primitive replace macro, earnings, flow, or causal evidence.",
            "Cross-channel YouTube agreement is source consensus, not factual confirmation.",
        ],
    }
    if causal_flow_config is not None:
        packet["global_causal_flow"] = build_causal_flow_packet(
            event, config=causal_flow_config, observations=observations
        )
    return packet


def build_engine_update_candidates(claims: Iterable[dict[str, Any]], metric_registry: dict[str, Any], playbook_config: dict[str, Any]) -> list[dict[str, Any]]:
    known_metrics = set(by_metric_id(metric_registry))
    known_playbooks = {row["id"] for row in playbook_config.get("playbooks", [])}
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for claim in claims:
        source_lens = str(claim.get("channel_id") or claim.get("source_lens") or "UNKNOWN")
        source_ref = str(claim.get("claim_id") or claim.get("video_id") or "")
        for metric in claim.get("metric_ids") or []:
            if metric not in known_metrics:
                candidates[("METRIC", str(metric))] = {
                    "candidate_type": "METRIC", "key": str(metric), "reason": claim.get("claim_summary_ko") or "YouTube claim references an unregistered metric",
                    "source_lens": source_lens, "source_ref": source_ref, "decision": "REVIEW_REQUIRED",
                }
        for item in claim.get("data_needed") or []:
            key = str(item).strip()
            if key:
                candidates[("DATA_NEED", key)] = {
                    "candidate_type": "DATA_NEED", "key": key, "reason": claim.get("claim_summary_ko") or "Expert claim requested additional evidence",
                    "source_lens": source_lens, "source_ref": source_ref, "decision": "REVIEW_REQUIRED",
                }
        for playbook in claim.get("playbook_ids") or []:
            if playbook not in known_playbooks:
                candidates[("PLAYBOOK", str(playbook))] = {
                    "candidate_type": "PLAYBOOK", "key": str(playbook), "reason": claim.get("claim_summary_ko") or "YouTube claim references an unknown playbook",
                    "source_lens": source_lens, "source_ref": source_ref, "decision": "REVIEW_REQUIRED",
                }
    return [candidates[key] for key in sorted(candidates)]
