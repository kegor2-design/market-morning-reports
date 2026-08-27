from __future__ import annotations

from typing import Any, Iterable

from .time_model import first_bar_after


DEFAULT_WINDOWS = (1, 5, 20, 60)


def _valid_bar(bar: dict[str, Any]) -> bool:
    try:
        opening, high, low, close = (float(bar[name]) for name in ("open", "high", "low", "close"))
    except (KeyError, TypeError, ValueError):
        return False
    return low <= min(opening, close) <= max(opening, close) <= high and low > 0


def _excursions(direction: str, entry: float, bars: list[dict[str, Any]]) -> tuple[float, float]:
    if direction == "LONG":
        mfe = (max(float(bar["high"]) for bar in bars) / entry - 1) * 100
        mae = (min(float(bar["low"]) for bar in bars) / entry - 1) * 100
    else:
        mfe = (entry / min(float(bar["low"]) for bar in bars) - 1) * 100
        mae = (entry / max(float(bar["high"]) for bar in bars) - 1) * 100
    return mfe, mae


def _directional_return(direction: str, entry: float, close: float) -> float:
    return (close / entry - 1) * 100 if direction == "LONG" else (entry / close - 1) * 100


def _binary_status(direction: str, bars: list[dict[str, Any]], target: float, invalidation: float, *, horizon_complete: bool) -> tuple[str, int | None]:
    for offset, bar in enumerate(bars):
        high, low = float(bar["high"]), float(bar["low"])
        target_hit = high >= target if direction == "LONG" else low <= target
        invalidation_hit = low <= invalidation if direction == "LONG" else high >= invalidation
        if target_hit and invalidation_hit:
            return "AMBIGUOUS", offset
        if target_hit:
            return "SUCCESS", offset
        if invalidation_hit:
            return "FAILURE", offset
    return ("FAILURE" if horizon_complete else "OPEN"), None


def evaluate_claim(
    claim: dict[str, Any],
    bars: list[dict[str, Any]],
    *,
    windows: Iterable[int] = DEFAULT_WINDOWS,
    horizon_bars: int | None = None,
) -> dict[str, Any]:
    if not bars or any(not _valid_bar(bar) for bar in bars):
        return {"status": "DATA_MISSING", "reason": "OHLCV_MISSING_OR_INVALID"}
    direction = claim.get("direction")
    if direction not in {"LONG", "SHORT"}:
        return {"status": "UNSCORABLE", "reason": "DIRECTION_NOT_EXPLICIT", "forward_windows": []}
    entry_index = first_bar_after(bars, claim.get("publicly_actionable_at"))
    if entry_index is None or entry_index >= len(bars):
        return {"status": "DATA_MISSING", "reason": "NO_BAR_AFTER_ACTIONABLE_TIME"}
    evaluation = bars[entry_index:]
    entry = float(evaluation[0]["open"])
    if entry <= 0:
        return {"status": "DATA_MISSING", "reason": "ENTRY_PRICE_INVALID"}
    forward = []
    for window in sorted(set(int(value) for value in windows if int(value) > 0)):
        if len(evaluation) < window:
            forward.append({"bars": window, "status": "PENDING"})
            continue
        sample = evaluation[:window]
        mfe, mae = _excursions(direction, entry, sample)
        forward.append({
            "bars": window, "status": "COMPLETE",
            "return_pct": round(_directional_return(direction, entry, float(sample[-1]["close"])), 6),
            "mfe_pct": round(mfe, 6), "mae_pct": round(mae, 6),
        })
    target, invalidation = claim.get("target_price"), claim.get("invalidation_price")
    binary_status, hit_offset = "UNSCORABLE", None
    reason = "TARGET_AND_INVALIDATION_REQUIRED"
    if target is not None and invalidation is not None:
        target, invalidation = float(target), float(invalidation)
        valid_order = target > entry > invalidation if direction == "LONG" else target < entry < invalidation
        if not valid_order:
            overall_sample = evaluation[:horizon_bars] if horizon_bars else evaluation
            mfe, mae = _excursions(direction, entry, overall_sample)
            return {
                "status": "UNSCORABLE", "reason": "INVALID_TARGET_INVALIDATION_ORDER", "direction": direction,
                "entry_bar_index": entry_index, "entry_timestamp": evaluation[0]["timestamp"], "entry_price": entry,
                "target_price": target, "invalidation_price": invalidation, "hit_bar_offset": None,
                "mfe_pct": round(mfe, 6), "mae_pct": round(mae, 6), "forward_windows": forward,
                "evaluated_through": overall_sample[-1]["timestamp"], "price_basis": "RAW",
            }
        limit = horizon_bars or len(evaluation)
        sample = evaluation[:limit]
        binary_status, hit_offset = _binary_status(
            direction, sample, target, invalidation,
            horizon_complete=horizon_bars is not None and len(evaluation) >= horizon_bars,
        )
        reason = "EXPLICIT_LEVELS_EVALUATED"
    overall_sample = evaluation[:horizon_bars] if horizon_bars else evaluation
    mfe, mae = _excursions(direction, entry, overall_sample)
    return {
        "status": binary_status, "reason": reason, "direction": direction,
        "entry_bar_index": entry_index, "entry_timestamp": evaluation[0]["timestamp"], "entry_price": entry,
        "target_price": target, "invalidation_price": invalidation, "hit_bar_offset": hit_offset,
        "mfe_pct": round(mfe, 6), "mae_pct": round(mae, 6),
        "forward_windows": forward, "evaluated_through": overall_sample[-1]["timestamp"],
        "price_basis": "RAW",
    }
