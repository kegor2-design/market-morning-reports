from __future__ import annotations

from typing import Any


def _row(observations: dict[str, dict[str, Any]], metric_id: str) -> dict[str, Any]:
    return observations.get(metric_id) or {"metric_id": metric_id, "state": "UNKNOWN"}


def _change(row: dict[str, Any], label: str = "20p") -> float | None:
    value = (row.get("changes") or {}).get(label)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _value(row: dict[str, Any]) -> float | None:
    try:
        return float(row.get("value")) if row.get("value") is not None else None
    except (TypeError, ValueError):
        return None


def _coverage(observations: dict[str, dict[str, Any]], ids: list[str]) -> dict[str, Any]:
    observed = [mid for mid in ids if _row(observations, mid).get("state") not in {None, "UNKNOWN", "STALE"} or _row(observations, mid).get("value") is not None]
    return {"required": ids, "observed": observed, "missing": [mid for mid in ids if mid not in observed]}


def earnings_state(observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = ["forward_eps_kospi_12m", "earnings_revision_breadth_kospi", "earnings_surprise_breadth_sp500"]
    cov = _coverage(observations, ids)
    eps_change = _change(_row(observations, "forward_eps_kospi_12m"))
    revision = _value(_row(observations, "earnings_revision_breadth_kospi"))
    if eps_change is None or revision is None:
        state = "UNKNOWN"
    elif eps_change > 0 and revision > 0:
        state = "IMPROVING"
    elif eps_change < 0 and revision < 0:
        state = "DETERIORATING"
    else:
        state = "MIXED"
    return {"state": state, **cov, "reason": {"forward_eps_20p_change": eps_change, "revision_breadth": revision}}


def valuation_state(observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = ["forward_per_kospi", "forward_pbr_kospi"]
    cov = _coverage(observations, ids)
    percentiles = []
    for mid in ids:
        row = _row(observations, mid)
        pct = row.get("percentile_5y") if row.get("percentile_5y") is not None else row.get("percentile_1y")
        try:
            if pct is not None: percentiles.append(float(pct))
        except (TypeError, ValueError):
            pass
    if not percentiles:
        state = "UNKNOWN"
    elif sum(percentiles) / len(percentiles) >= 85:
        state = "EXPENSIVE"
    elif sum(percentiles) / len(percentiles) <= 15:
        state = "CHEAP"
    else:
        state = "NEUTRAL"
    return {"state": state, **cov, "valuation_percentiles": percentiles}


def flow_positioning_state(observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = ["foreign_cash_flow_kospi", "foreign_kospi200_futures_net", "program_net_flow", "forced_liquidation_kr"]
    cov = _coverage(observations, ids)
    cash = _value(_row(observations, ids[0])); futures = _value(_row(observations, ids[1]))
    if cash is None or futures is None:
        state = "UNKNOWN"
    elif cash > 0 and futures > 0:
        state = "POSITIVE"
    elif cash < 0 and futures < 0:
        state = "NEGATIVE"
    else:
        state = "DIVERGENT"
    forced = _change(_row(observations, "forced_liquidation_kr"))
    return {"state": state, **cov, "reason": {"foreign_cash": cash, "foreign_futures": futures, "forced_liquidation_change": forced}}


def breadth_state(observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = ["breadth_advance_pct_kr", "breadth_above_60dma_kr", "breadth_new_high_low_kr"]
    cov = _coverage(observations, ids)
    advance = _value(_row(observations, ids[0])); above60 = _value(_row(observations, ids[1]))
    if advance is None or above60 is None:
        state = "UNKNOWN"
    elif advance >= 55 and above60 >= 55:
        state = "HEALTHY"
    elif advance <= 45 and above60 <= 45:
        state = "WEAK"
    else:
        state = "MIXED"
    return {"state": state, **cov, "reason": {"advance_pct": advance, "above_60dma_pct": above60}}


def industry_cycle_state(observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = ["semiconductor_inventory_sales", "dram_asp", "semiconductor_export_10day", "semiconductor_utilization"]
    cov = _coverage(observations, ids)
    inventory = _change(_row(observations, ids[0])); asp = _change(_row(observations, ids[1])); exports = _change(_row(observations, ids[2]))
    if inventory is None or asp is None or exports is None:
        state = "UNKNOWN"
    elif inventory < 0 and asp > 0 and exports > 0:
        state = "UPTURN"
    elif inventory > 0 and asp < 0 and exports < 0:
        state = "DOWNTURN"
    else:
        state = "TRANSITION"
    return {"state": state, **cov, "reason": {"inventory_20p": inventory, "asp_20p": asp, "export_20p": exports}}


def build_market_states(observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "EARNINGS_STATE": earnings_state(observations),
        "VALUATION_STATE": valuation_state(observations),
        "FLOW_POSITIONING_STATE": flow_positioning_state(observations),
        "MARKET_BREADTH_STATE": breadth_state(observations),
        "INDUSTRY_CYCLE_STATE": industry_cycle_state(observations),
        "guardrail": "States remain UNKNOWN when required point-in-time data is unavailable; no present-day revised value is backfilled into historical decisions.",
    }
