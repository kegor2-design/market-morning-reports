from __future__ import annotations

from typing import Any, Iterable
import re

from .expert_historical_corpus import ExpertClaim


def _tokens(values: Iterable[Any]) -> set[str]:
    out: set[str] = set()
    for value in values:
        text = re.sub(r"[^0-9A-Za-z가-힣]+", " ", str(value or "").lower())
        out.update(x for x in text.split() if len(x) >= 2)
    return out


def relevant_claims_for_event(event: Any, claims: Iterable[ExpertClaim], limit: int = 12) -> list[dict[str, Any]]:
    """Return historical expert context only. Never changes event truth/status/confidence."""
    if isinstance(event, dict):
        title = event.get("title")
        event_type = event.get("event_type")
        entities = event.get("entities") or []
        linked_mi = event.get("linked_mi") or []
    else:
        title = getattr(event, "title", "")
        event_type = getattr(event, "event_type", "")
        entities = getattr(event, "entities", []) or []
        linked_mi = getattr(event, "linked_mi", []) or []
    event_tokens = _tokens([title, event_type, *entities, *linked_mi])
    ranked: list[tuple[int, ExpertClaim]] = []
    for c in claims:
        if not c.reusable:
            continue
        claim_tokens = _tokens([c.primitive_key, c.claim_text, *c.topics, *c.related_entities, *c.related_assets, *c.premise_metrics])
        score = len(event_tokens & claim_tokens)
        if score:
            ranked.append((score, c))
    ranked.sort(key=lambda pair: (pair[0], pair[1].published_at or ""), reverse=True)
    out = []
    for score, c in ranked[: max(1, int(limit))]:
        out.append({
            "claim_id": c.claim_id,
            "expert_id": c.expert_id,
            "video_id": c.video_id,
            "published_at": c.published_at,
            "primitive_key": c.primitive_key,
            "claim_text": c.claim_text,
            "stance": c.stance,
            "validation_status": c.validation_status,
            "relevance_score": score,
            "truth_class": "EXPERT_HISTORICAL_CLAIM",
            "may_promote_event_truth": False,
        })
    return out
