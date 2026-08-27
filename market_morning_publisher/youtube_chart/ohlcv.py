from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


SUPPORTED_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}


def parse_yahoo_chart(payload: dict[str, Any]) -> list[dict[str, Any]]:
    chart = payload.get("chart") or {}
    errors = chart.get("error")
    results = chart.get("result") or []
    if errors or not results:
        raise ValueError(f"Yahoo chart response has no result: {errors}")
    result = results[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = (indicators.get("quote") or [{}])[0]
    adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
    rows: list[dict[str, Any]] = []
    for index, stamp in enumerate(timestamps):
        def at(name: str) -> Any:
            values = quotes.get(name) or []
            return values[index] if index < len(values) else None

        values = {name: at(name) for name in ("open", "high", "low", "close", "volume")}
        if any(values[name] is None for name in ("open", "high", "low", "close")):
            continue
        numeric = [float(values[name]) for name in ("open", "high", "low", "close")]
        if not all(math.isfinite(value) for value in numeric):
            continue
        adjusted_close = adjusted[index] if index < len(adjusted) else None
        rows.append({
            "timestamp": datetime.fromtimestamp(int(stamp), timezone.utc).isoformat(),
            "open": numeric[0], "high": numeric[1], "low": numeric[2], "close": numeric[3],
            "volume": int(values["volume"]) if values["volume"] is not None else None,
            "adjusted_close": float(adjusted_close) if adjusted_close is not None else None,
            "price_basis": "RAW", "provider": "YAHOO_FINANCE",
        })
    return rows


class YahooOhlcvClient:
    def __init__(self, *, timeout: int = 30, user_agent: str = "MarketMorningPublisher/1.3") -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch(self, symbol: str, *, start: datetime, end: datetime, interval: str = "1d") -> list[dict[str, Any]]:
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(f"unsupported Yahoo interval: {interval}")
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("start/end must be aware datetimes with end after start")
        params = urllib.parse.urlencode({
            "period1": int(start.astimezone(timezone.utc).timestamp()),
            "period2": int((end.astimezone(timezone.utc) + timedelta(seconds=1)).timestamp()),
            "interval": interval, "events": "history", "includeAdjustedClose": "true",
        })
        encoded = urllib.parse.quote(symbol, safe="")
        request = urllib.request.Request(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?{params}",
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return parse_yahoo_chart(json.loads(response.read().decode("utf-8")))


def interval_for_timeframe(timeframe: str | None) -> str | None:
    mapping = {
        "MINUTE_1": "1m", "MINUTE_5": "5m", "MINUTE_15": "15m", "MINUTE_30": "30m",
        "HOUR_1": "60m", "DAILY": "1d", "WEEKLY": "1wk", "MONTHLY": "1mo",
    }
    return mapping.get(timeframe or "")


def completed_bars_as_of(bars: list[dict[str, Any]], actionable_at: str | None) -> list[dict[str, Any]]:
    """Return only bars known to be complete, using the next bar as cutoff.

    This is deliberately conservative.  Without exchange-calendar metadata we
    do not assume that a bar was complete merely because its start precedes the
    publication timestamp.
    """
    if not actionable_at:
        return []
    try:
        actionable = datetime.fromisoformat(actionable_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return []
    complete = []
    for index in range(len(bars) - 1):
        try:
            next_started = datetime.fromisoformat(str(bars[index + 1]["timestamp"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (KeyError, ValueError):
            continue
        if next_started <= actionable:
            complete.append(bars[index])
    return complete


def reconcile_screen_prices(screen_ticks: list[dict[str, Any]], bars: list[dict[str, Any]], *, tolerance_pct: float = 3.0) -> dict[str, Any]:
    if not screen_ticks or not bars:
        return {"status": "DATA_MISSING", "reason": "SCREEN_TICKS_OR_OHLCV_MISSING"}
    prices = [float(tick["value"]) for tick in screen_ticks]
    market_low = min(float(bar["low"]) for bar in bars)
    market_high = max(float(bar["high"]) for bar in bars)
    tolerance = max(abs(market_high), abs(market_low), 1.0) * tolerance_pct / 100
    inside = [price for price in prices if market_low - tolerance <= price <= market_high + tolerance]
    return {
        "status": "MATCHED" if inside else "MISMATCH",
        "screen_tick_count": len(prices), "matched_tick_count": len(inside),
        "ohlcv_low": market_low, "ohlcv_high": market_high, "tolerance_pct": tolerance_pct,
    }
