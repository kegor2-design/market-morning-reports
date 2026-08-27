from __future__ import annotations

import math
from datetime import date, datetime, timezone
from pathlib import Path

from market_morning_publisher.core import atomic_json, now_iso

LOOKBACKS = {
    "daily": {"1p": 1, "5p": 5, "20p": 20, "60p": 60, "1y": 252},
    "weekly": {"1p": 1, "5p": 4, "20p": 13, "60p": 26, "1y": 52},
    "monthly": {"1p": 1, "5p": 2, "20p": 6, "60p": 12, "1y": 12},
    "quarterly": {"1p": 1, "5p": 1, "20p": 2, "60p": 4, "1y": 4},
}


def _days_old(date_text: str | None, now: date) -> int | None:
    if not date_text:
        return None
    try:
        return (now - date.fromisoformat(date_text[:10])).days
    except ValueError:
        return None


def _percentile(values: list[float], x: float) -> float | None:
    if len(values) < 3:
        return None
    return round(100 * sum(v <= x for v in values) / len(values), 1)


def _zscore(values: list[float], x: float) -> float | None:
    if len(values) < 10:
        return None
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    if var <= 0:
        return 0.0
    return round((x - mean) / math.sqrt(var), 3)


def summarize_metric(metric: dict, *, now: date | None = None) -> dict:
    now = now or datetime.now(timezone.utc).date()
    if not metric.get("ok"):
        return {
            "id": metric.get("id"), "name": metric.get("name"), "group": metric.get("group"),
            "importance": metric.get("importance"), "state": "UNKNOWN", "reason": metric.get("error", "unavailable"),
        }
    hist = metric.get("history") or []
    vals = [float(p["value"]) for p in hist]
    current = vals[-1]
    frequency = metric.get("frequency", "daily")
    indices = LOOKBACKS.get(frequency, LOOKBACKS["daily"])
    changes = {}
    for label, lag in indices.items():
        changes[label] = round(current - vals[-1-lag], 4) if len(vals) > lag else None
    age = _days_old(metric.get("as_of"), now)
    stale = age is None or age > int(metric.get("stale_days", 7))
    one_year = vals[-max(3, indices.get("1y", len(vals))):]
    trend_change = changes.get("20p")
    if stale:
        state = "STALE"
    elif trend_change is None:
        state = "OBSERVED"
    elif trend_change > 0:
        state = "RISING"
    elif trend_change < 0:
        state = "FALLING"
    else:
        state = "FLAT"
    return {
        "id": metric.get("id"), "name": metric.get("name"), "group": metric.get("group"),
        "importance": metric.get("importance"), "unit": metric.get("unit"), "as_of": metric.get("as_of"),
        "stress_when": metric.get("stress_when", "context"),
        "age_days": age, "state": state, "value": current, "changes": changes,
        "percentile_1y": _percentile(one_year, current), "zscore_1y": _zscore(one_year, current),
    }


def _stress_composite(states: dict[str, dict], ids: list[str]) -> dict:
    observed = [states[x] for x in ids if x in states and states[x].get("state") not in {"UNKNOWN", "STALE"}]
    if len(observed) < max(1, (len(ids) + 1) // 2):
        return {"state": "UNKNOWN", "evidence": [x.get("id") for x in observed], "reason": "insufficient observed inputs"}
    stress = 0
    relief = 0
    evidence = []
    for item in observed:
        direction = item.get("stress_when", "context")
        st = item.get("state")
        pct = item.get("percentile_1y")
        if direction == "higher":
            stress += int(st == "RISING") + int(pct is not None and pct >= 90)
            relief += int(st == "FALLING") + int(pct is not None and pct <= 10)
        elif direction == "lower":
            stress += int(st == "FALLING") + int(pct is not None and pct <= 10)
            relief += int(st == "RISING") + int(pct is not None and pct >= 90)
        evidence.append(item["id"])
    score = stress - relief
    if score >= 4:
        state = "EXTREME"
    elif score >= 2:
        state = "STRESS"
    elif score <= -2:
        state = "EASING"
    else:
        state = "WATCH"
    return {"state": state, "stress_signals": stress, "relief_signals": relief, "evidence": evidence}


def build_state(raw: dict, root: Path | None = None, *, now: date | None = None) -> dict:
    metrics = {mid: summarize_metric(m, now=now) for mid, m in (raw.get("metrics") or {}).items()}
    composites = {
        "US_LONG_END_STRESS": _stress_composite(metrics, ["us_10y", "us_20y", "us_30y", "us_real_10y"]),
        "US_INFLATION_EXPECTATION": _stress_composite(metrics, ["us_be_5y", "us_be_10y"]),
        "US_FED_LIQUIDITY": _stress_composite(metrics, ["fed_total_assets", "reserve_balances"]),
        "US_MONEY_MARKET_BUFFER": _stress_composite(metrics, ["on_rrp", "mmf_total_assets", "mmf_tbill", "sofr_iorb_spread"]),
        "US_FISCAL_BURDEN": _stress_composite(metrics, ["federal_debt", "federal_interest_expense", "federal_deficit_monthly", "federal_outlays_monthly"]),
    }
    result = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "metrics": metrics,
        "states": composites,
        "quality": raw.get("quality", {}),
        "guardrail": "UNKNOWN is preserved when a required source is unavailable; no proxy is silently substituted.",
    }
    if root is not None:
        atomic_json(root / "data" / "state" / "us_state" / "latest.json", result)
    return result
