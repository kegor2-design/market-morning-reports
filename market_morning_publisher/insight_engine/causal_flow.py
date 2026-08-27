from __future__ import annotations

from typing import Any


UNKNOWN_STATES = {None, "", "UNKNOWN", "STALE"}


def _event_text(event: dict[str, Any]) -> str:
    fields = ("type", "category", "headline", "name", "summary")
    values = [str(event.get(key) or "") for key in fields]
    values.extend(str(value) for value in event.get("tags") or [])
    values.extend(str(value) for value in event.get("countries") or [])
    return " ".join(values).upper()


def select_causal_templates(event: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    text = _event_text(event)
    selected = []
    for template in config.get("templates", []):
        triggers = [str(value).upper() for value in template.get("triggers") or []]
        if triggers and any(trigger in text for trigger in triggers):
            selected.append(template)
    return selected


def _observed(observation: dict[str, Any]) -> bool:
    return observation.get("value") is not None or observation.get("state") not in UNKNOWN_STATES


def _clause_matches(clause: dict[str, Any], observation: dict[str, Any]) -> bool:
    state = observation.get("state")
    if "states" in clause:
        return str(state).upper() in {str(value).upper() for value in clause["states"]}
    value = observation.get("value")
    if value is None:
        return False
    if "gte" in clause and not value >= clause["gte"]:
        return False
    if "lte" in clause and not value <= clause["lte"]:
        return False
    return True


def _evaluate_path(path: dict[str, Any], observations: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    activation = path.get("activation") or {}
    all_clauses = activation.get("all") or []
    any_clauses = activation.get("any") or []
    clauses = [*all_clauses, *any_clauses]
    missing = sorted({c["metric_id"] for c in clauses if not _observed(observations.get(c["metric_id"]) or {})})
    observed_all = [c for c in all_clauses if _observed(observations.get(c["metric_id"]) or {})]
    observed_any = [c for c in any_clauses if _observed(observations.get(c["metric_id"]) or {})]
    all_ok = len(observed_all) == len(all_clauses) and all(
        _clause_matches(c, observations[c["metric_id"]]) for c in all_clauses
    )
    any_ok = not any_clauses or any(
        _clause_matches(c, observations[c["metric_id"]]) for c in observed_any
    )
    contradictions = [
        c["metric_id"] for c in observed_all
        if not _clause_matches(c, observations[c["metric_id"]])
    ]
    if all_ok and any_ok:
        return "ACTIVE", missing, contradictions
    if contradictions:
        return "INACTIVE", missing, contradictions
    if observed_all or observed_any:
        return "WATCH", missing, contradictions
    return "NEEDS_DATA", missing, contradictions


def build_causal_flow_packet(
    event: dict[str, Any],
    *,
    config: dict[str, Any],
    observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an evidence-gated cross-border causal map without inventing missing links."""
    observations = observations or {}
    templates = select_causal_templates(event, config)
    paths = []
    missing_metrics: set[str] = set()
    for template in templates:
        for path in template.get("paths") or []:
            status, missing, contradictions = _evaluate_path(path, observations)
            missing_metrics.update(missing)
            paths.append({
                "template_id": template["id"],
                "path_id": path["id"],
                "name_ko": path.get("name_ko"),
                "status": status,
                "horizon": path.get("horizon"),
                "chain": path.get("chain") or [],
                "actor_constraints": path.get("actor_constraints") or [],
                "policy_options": path.get("policy_options") or [],
                "cost_transfer": path.get("cost_transfer") or [],
                "us_impact": path.get("us_impact") or [],
                "global_impact": path.get("global_impact") or [],
                "korea_impact": path.get("korea_impact") or [],
                "evidence": {
                    "observations": {c["metric_id"]: observations.get(c["metric_id"], {"state": "UNKNOWN"})
                                     for group in (path.get("activation") or {}).values() for c in group},
                    "missing_metrics": missing,
                    "contradicting_metrics": contradictions,
                },
                "invalidation_conditions": path.get("invalidation_conditions") or [],
            })
    active = sum(path["status"] == "ACTIVE" for path in paths)
    status = "NO_TEMPLATE"
    if paths:
        status = "ACTIVE" if active else ("NEEDS_DATA" if all(p["status"] == "NEEDS_DATA" for p in paths) else "WATCH")
    return {
        "schema_version": "1.0",
        "root_event": event,
        "selected_templates": [template["id"] for template in templates],
        "paths": paths,
        "missing_metrics": sorted(missing_metrics),
        "status": status,
        "guardrails": [
            "A plausible narrative is not an active path until its configured evidence gate is met.",
            "Correlation or market co-movement alone does not establish the direction of causality.",
            "Separate the immediate market reaction from medium-term balance-sheet and real-economy effects.",
            "For every active path, retain explicit invalidation conditions and competing explanations.",
        ],
    }
