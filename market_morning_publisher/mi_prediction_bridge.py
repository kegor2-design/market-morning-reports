from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .mi_prediction_scoreboard import PredictionRecord, append_jsonl_once


def prediction_from_mi_snapshot(
    mi: Mapping[str, Any],
    *,
    as_of: str,
    predictor_id: str = "OUR_MI_ENGINE",
    target_asset: str,
    target_metric: str,
    horizon: str,
    direction: str,
    confidence: float,
    baseline_value: float,
    flat_band_pct: float = 0.25,
    expected_range_low: float | None = None,
    expected_range_high: float | None = None,
    regime: str | None = None,
    event_ids: Sequence[str] = (),
    primitive_keys: Sequence[str] = (),
    expert_claim_ids: Sequence[str] = (),
    source_registry_ids: Sequence[str] = (),
) -> PredictionRecord:
    """Create an immutable prediction snapshot from a current MI.

    This bridge deliberately does not infer direction/confidence. The reasoning layer must
    explicitly commit them before the future outcome is known.
    """
    mi_id = str(mi.get("mi_id") or mi.get("id") or "").strip()
    if not mi_id:
        raise ValueError("MI snapshot requires mi_id/id")
    rationale = str(mi.get("summary") or mi.get("thesis") or mi.get("rationale") or "")
    invalidation = tuple(str(x) for x in (mi.get("invalidation_conditions") or mi.get("invalidation") or []) if str(x))
    context = {
        "mi": dict(mi),
        "event_ids": list(event_ids),
        "primitive_keys": list(primitive_keys),
        "expert_claim_ids": list(expert_claim_ids),
        "source_registry_ids": list(source_registry_ids),
    }
    return PredictionRecord.create(
        mi_id=mi_id,
        as_of=as_of,
        predictor_id=predictor_id,
        target_asset=target_asset,
        target_metric=target_metric,
        horizon=horizon,
        direction=direction,
        confidence=confidence,
        baseline_value=baseline_value,
        flat_band_pct=flat_band_pct,
        expected_range_low=expected_range_low,
        expected_range_high=expected_range_high,
        regime=regime,
        event_ids=event_ids,
        primitive_keys=primitive_keys,
        expert_claim_ids=expert_claim_ids,
        source_registry_ids=source_registry_ids,
        invalidation_conditions=invalidation,
        rationale_snapshot=rationale,
        context_snapshot=context,
    )


def capture_explicit_predictions(analysis: Mapping[str, Any], *, as_of: str, ledger: str | Path,
                                 predictor_id: str = "OUR_MI_ENGINE") -> dict[str, int]:
    """Commit only explicit, schema-bound MI predictions; never infer missing fields."""
    rows = analysis.get("mi_predictions") or []
    created = skipped = 0
    for raw in rows:
        if not isinstance(raw, Mapping):
            skipped += 1
            continue
        required = ("mi_id", "target_asset", "target_metric", "horizon", "direction", "confidence", "baseline_value")
        if any(raw.get(key) in (None, "") for key in required):
            skipped += 1
            continue
        record = prediction_from_mi_snapshot(
            raw, as_of=as_of, predictor_id=predictor_id,
            target_asset=str(raw["target_asset"]), target_metric=str(raw["target_metric"]),
            horizon=str(raw["horizon"]), direction=str(raw["direction"]),
            confidence=float(raw["confidence"]), baseline_value=float(raw["baseline_value"]),
            flat_band_pct=float(raw.get("flat_band_pct", 0.25)),
            expected_range_low=raw.get("expected_range_low"), expected_range_high=raw.get("expected_range_high"),
            regime=raw.get("regime"), event_ids=raw.get("event_ids") or (),
            primitive_keys=raw.get("primitive_keys") or (), expert_claim_ids=raw.get("expert_claim_ids") or (),
            source_registry_ids=raw.get("source_registry_ids") or (),
        )
        if append_jsonl_once(ledger, record.to_dict(), id_field="prediction_id"):
            created += 1
        else:
            skipped += 1
    return {"created": created, "skipped": skipped}
