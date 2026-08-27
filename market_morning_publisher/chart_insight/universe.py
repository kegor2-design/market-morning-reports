from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Iterable

from .primitives import detect_primitives


def _valid_price(row: dict[str, Any], key: str) -> float | None:
    try:
        value = float(row.get(key))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _outcome(bars: list[dict[str, Any]], event_index: int, windows: Iterable[int]) -> dict[str, Any]:
    entry_index = event_index + 1
    if entry_index >= len(bars):
        return {"status": "OPEN", "entry": None, "forward": []}
    entry = _valid_price(bars[entry_index], "open") or _valid_price(bars[entry_index], "close")
    if entry is None:
        return {"status": "DATA_MISSING", "entry": None, "forward": []}
    rows = []
    for window in sorted({int(value) for value in windows if int(value) > 0}):
        end_index = entry_index + window - 1
        if end_index >= len(bars):
            rows.append({"bars": window, "status": "OPEN", "return_pct": None, "mfe_pct": None, "mae_pct": None})
            continue
        segment = bars[entry_index:end_index + 1]
        close = _valid_price(segment[-1], "close")
        highs = [_valid_price(row, "high") for row in segment]
        lows = [_valid_price(row, "low") for row in segment]
        highs = [value for value in highs if value is not None]
        lows = [value for value in lows if value is not None]
        rows.append({
            "bars": window,
            "status": "COMPLETE" if close is not None else "DATA_MISSING",
            "return_pct": round((close / entry - 1) * 100, 6) if close is not None else None,
            "mfe_pct": round((max(highs) / entry - 1) * 100, 6) if highs else None,
            "mae_pct": round((min(lows) / entry - 1) * 100, 6) if lows else None,
        })
    return {"status": "EVALUATED", "entry": entry, "forward": rows}


def scan_symbol_bars(
    symbol: str,
    bars: list[dict[str, Any]],
    primitive_registry: dict[str, Any],
    required_primitive_ids: Iterable[str],
    *,
    windows: Iterable[int] = (1, 5, 20, 60),
    context_bars: int = 60,
    minimum_history: int = 20,
) -> list[dict[str, Any]]:
    """Scan one symbol without feature look-ahead.

    At event index i, primitive detection receives bars[:i+1] only. Future bars are
    passed exclusively to outcome calculation after the event has been frozen.
    """
    required = {str(value) for value in required_primitive_ids if str(value)}
    if not required:
        return []
    events = []
    start = max(2, int(minimum_history))
    for index in range(start, len(bars)):
        context = bars[max(0, index - int(context_bars) + 1):index + 1]
        detected = detect_primitives(context, primitive_registry)
        observed = {str(row.get("primitive_id")) for row in detected}
        if not required <= observed:
            continue
        event = {
            "symbol": symbol,
            "event_index": index,
            "event_timestamp": bars[index].get("timestamp"),
            "required_primitive_ids": sorted(required),
            "observed_primitives": [row for row in detected if str(row.get("primitive_id")) in required],
            "feature_bar_count": len(context),
            "future_bars_used_for_features": 0,
            "outcome": _outcome(bars, index, windows),
        }
        events.append(event)
    return events


def summarize_universe_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(events)
    by_window: dict[int, list[float]] = defaultdict(list)
    symbols = set()
    for row in rows:
        symbols.add(str(row.get("symbol")))
        for item in (row.get("outcome") or {}).get("forward") or []:
            if item.get("status") == "COMPLETE" and item.get("return_pct") is not None:
                by_window[int(item["bars"])].append(float(item["return_pct"]))
    forward = {}
    for window, returns in sorted(by_window.items()):
        forward[str(window)] = {
            "sample": len(returns),
            "positive_rate": round(sum(value > 0 for value in returns) / len(returns), 6) if returns else None,
            "average_return_pct": round(mean(returns), 6) if returns else None,
        }
    return {
        "event_sample": len(rows),
        "symbol_sample": len(symbols),
        "forward": forward,
        "warning": "Descriptive scan only. Costs, conditioning, survivor-bias controls and out-of-sample validation remain required.",
    }
