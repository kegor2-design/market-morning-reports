from __future__ import annotations

import math
import re
from statistics import mean
from typing import Any, Iterable


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _valid_bars(bars: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in bars:
        values = {key: _number(row.get(key)) for key in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            continue
        if values["low"] <= 0 or not (values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]):
            continue
        out.append(dict(row))
    return out


def _true_range(row: dict[str, Any], previous_close: float | None) -> float:
    high, low = float(row["high"]), float(row["low"])
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def _volume_ratio(bars: list[dict[str, Any]], window: int = 20) -> float | None:
    if len(bars) < 2:
        return None
    current = _number(bars[-1].get("volume"))
    prior = [_number(row.get("volume")) for row in bars[max(0, len(bars) - window - 1):-1]]
    prior = [value for value in prior if value is not None and value > 0]
    if current is None or current < 0 or not prior:
        return None
    baseline = mean(prior)
    return current / baseline if baseline > 0 else None


def key_levels(bars: Iterable[dict[str, Any]], *, short_window: int = 20, annual_window: int = 252) -> dict[str, Any]:
    rows = _valid_bars(bars)
    if not rows:
        return {"status": "DATA_MISSING", "levels": {}}
    latest = rows[-1]
    prior = rows[:-1]
    prior_short = prior[-short_window:] if prior else []
    prior_annual = prior[-annual_window:] if prior else []
    levels: dict[str, float] = {"LAST_CLOSE": float(latest["close"]), "LAST_OPEN": float(latest["open"])}
    if prior:
        levels["PREVIOUS_CLOSE"] = float(prior[-1]["close"])
        levels["PREVIOUS_HIGH"] = float(prior[-1]["high"])
        levels["PREVIOUS_LOW"] = float(prior[-1]["low"])
    if prior_short:
        levels[f"PRIOR_{short_window}_HIGH"] = max(float(row["high"]) for row in prior_short)
        levels[f"PRIOR_{short_window}_LOW"] = min(float(row["low"]) for row in prior_short)
    if prior_annual:
        levels[f"PRIOR_{annual_window}_HIGH"] = max(float(row["high"]) for row in prior_annual)
        levels[f"PRIOR_{annual_window}_LOW"] = min(float(row["low"]) for row in prior_annual)
    return {"status": "OK", "levels": levels}


def map_expert_text(text: str, registry: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = " ".join(str(text or "").casefold().split())
    if not normalized:
        return []
    matches = []
    for primitive in registry.get("primitives") or []:
        aliases = [str(alias).casefold().strip() for alias in primitive.get("aliases") or [] if str(alias).strip()]
        matched = [alias for alias in aliases if alias and re.search(re.escape(alias), normalized)]
        if matched:
            matches.append({
                "primitive_id": primitive["id"],
                "family": primitive.get("family"),
                "match_status": "EXPERT_LANGUAGE_CANDIDATE",
                "matched_aliases": matched,
                "independently_verified": False,
            })
    return matches


def detect_primitives(bars: Iterable[dict[str, Any]], registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _valid_bars(bars)
    if len(rows) < 3:
        return []
    thresholds = registry.get("default_thresholds") or {}
    breakout_buffer = float(thresholds.get("breakout_buffer_pct", 0.1)) / 100
    rel_vol_high = float(thresholds.get("relative_volume_expansion", 1.5))
    rel_vol_low = float(thresholds.get("relative_volume_dryup", 0.6))
    gap_pct = float(thresholds.get("gap_pct", 1.0)) / 100
    reaction_buffer = float(thresholds.get("reaction_buffer_pct", 0.5)) / 100
    compression_ratio = float(thresholds.get("range_compression_ratio", 0.65))
    expansion_ratio = float(thresholds.get("volatility_expansion_ratio", 1.5))

    latest = rows[-1]
    prior = rows[:-1]
    prior20 = prior[-20:]
    prior_high = max(float(row["high"]) for row in prior20)
    prior_low = min(float(row["low"]) for row in prior20)
    close, high, low, opening = (float(latest[key]) for key in ("close", "high", "low", "open"))
    detected: list[dict[str, Any]] = []

    def add(primitive_id: str, strength: float | None = None, **evidence: Any) -> None:
        detected.append({
            "primitive_id": primitive_id,
            "status": "DETECTED",
            "strength": round(float(strength), 6) if strength is not None and math.isfinite(float(strength)) else None,
            "evidence": evidence,
        })

    if close > prior_high * (1 + breakout_buffer):
        add("BREAKOUT", close / prior_high - 1, reference=prior_high, close=close)
    if close < prior_low * (1 - breakout_buffer):
        add("BREAKDOWN", prior_low / close - 1, reference=prior_low, close=close)
    if high > prior_high * (1 + breakout_buffer) and close <= prior_high:
        add("FAILED_BREAKOUT", high / prior_high - 1, reference=prior_high, high=high, close=close)
    if low < prior_low * (1 - breakout_buffer) and close >= prior_low:
        add("FAILED_BREAKDOWN", prior_low / low - 1, reference=prior_low, low=low, close=close)

    last_three = rows[-3:]
    lows = [float(row["low"]) for row in last_three]
    highs = [float(row["high"]) for row in last_three]
    if lows[0] < lows[1] < lows[2]:
        add("HIGHER_LOW", (lows[2] / lows[0] - 1), lows=lows)
    if highs[0] > highs[1] > highs[2]:
        add("LOWER_HIGH", (highs[0] / highs[2] - 1), highs=highs)

    volume_ratio = _volume_ratio(rows)
    if volume_ratio is not None and volume_ratio >= rel_vol_high:
        add("VOLUME_EXPANSION", volume_ratio, relative_volume=volume_ratio)
    if volume_ratio is not None and volume_ratio <= rel_vol_low:
        add("VOLUME_DRYUP", 1 - volume_ratio, relative_volume=volume_ratio)

    if len(rows) >= 11:
        trs = []
        prev_close = None
        for row in rows[-31:]:
            trs.append(_true_range(row, prev_close))
            prev_close = float(row["close"])
        recent = mean(trs[-5:])
        baseline_slice = trs[:-5][-20:]
        if baseline_slice:
            baseline = mean(baseline_slice)
            if baseline > 0 and recent / baseline <= compression_ratio:
                add("RANGE_COMPRESSION", 1 - recent / baseline, recent_true_range=recent, baseline_true_range=baseline)
            if baseline > 0 and recent / baseline >= expansion_ratio:
                add("VOLATILITY_EXPANSION", recent / baseline, recent_true_range=recent, baseline_true_range=baseline)

    previous_close = float(prior[-1]["close"])
    if opening > previous_close * (1 + gap_pct) and close >= opening:
        add("GAP_AND_HOLD", opening / previous_close - 1, previous_close=previous_close, open=opening, close=close)
    prior_open = float(prior[-1]["open"])
    prior_gap_up = prior_open > float(prior[-2]["close"]) * (1 + gap_pct) if len(prior) >= 2 else False
    if prior_gap_up and low <= float(prior[-2]["close"]):
        add("GAP_FILL", abs(low / float(prior[-2]["close"]) - 1), prior_gap_reference=float(prior[-2]["close"]), low=low)

    if low <= prior_low * (1 + reaction_buffer) and close > opening and close > prior_low:
        add("SUPPORT_REACTION", (close / max(low, 1e-12) - 1), reference=prior_low, low=low, close=close)
    if high >= prior_high * (1 - reaction_buffer) and close < opening and close < prior_high:
        add("RESISTANCE_REACTION", (high / max(close, 1e-12) - 1), reference=prior_high, high=high, close=close)

    annual = prior[-252:]
    if annual and high >= max(float(row["high"]) for row in annual):
        add("NEW_HIGH", high / max(float(row["high"]) for row in annual) - 1 if max(float(row["high"]) for row in annual) else 0, high=high)
    if annual and low <= min(float(row["low"]) for row in annual):
        add("NEW_LOW", min(float(row["low"]) for row in annual) / low - 1 if low else 0, low=low)

    # Deduplicate if a primitive was triggered through more than one relationship.
    best: dict[str, dict[str, Any]] = {}
    for row in detected:
        current = best.get(row["primitive_id"])
        if current is None or (row.get("strength") or 0) > (current.get("strength") or 0):
            best[row["primitive_id"]] = row
    return [best[key] for key in sorted(best)]
