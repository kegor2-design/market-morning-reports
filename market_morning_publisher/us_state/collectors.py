from __future__ import annotations

import csv
import concurrent.futures
import io
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from market_morning_publisher.core import atomic_json, fetch, now_iso


def _fred_points(series_id: str, fetcher: Callable = fetch) -> list[dict]:
    # The state engine only needs recent history for trend/percentile checks. Limiting
    # the window avoids downloading decades of observations for every daily run.
    cosd = (datetime.now(timezone.utc).date() - timedelta(days=365 * 6)).isoformat()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={urllib.parse.quote(series_id)}&cosd={cosd}"
    rows = csv.DictReader(io.StringIO(fetcher(url).decode("utf-8-sig")))
    out = []
    for row in rows:
        raw = row.get(series_id)
        date = row.get("DATE") or row.get("observation_date")
        if not date or not raw or raw == ".":
            continue
        try:
            out.append({"date": date, "value": float(raw)})
        except ValueError:
            continue
    return out



def _yahoo_points(symbol: str, fetcher: Callable = fetch) -> list[dict]:
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=2y&interval=1d&includePrePost=false&events=div%2Csplits"
    payload = json.loads(fetcher(url).decode("utf-8"))
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError("Yahoo chart returned no result")
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    closes = quote.get("close") or []
    out = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        try:
            d = datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat()
            out.append({"date": d, "value": float(close)})
        except (TypeError, ValueError, OSError):
            continue
    return out


def _metric_record(metric: dict, points: list[dict], *, collected_at: str, history_limit: int) -> dict:
    points = points[-history_limit:]
    if not points:
        return {**metric, "ok": False, "status": "UNKNOWN", "error": "no observations", "collected_at": collected_at}
    return {
        **metric,
        "ok": True,
        "status": "OBSERVED",
        "as_of": points[-1]["date"],
        "value": points[-1]["value"],
        "history": points,
        "collected_at": collected_at,
    }


def collect_us_state_metrics(root: Path, config: dict, *, fetcher: Callable = fetch) -> dict:
    """Collect supported US-state metrics and explicitly preserve unsupported metrics as UNKNOWN.

    The collector never substitutes a proxy for a named P0 metric. This is intentional: e.g.
    term premium and MOVE remain UNKNOWN until a verified source adapter is configured.
    """
    collected_at = now_iso()
    history_limit = int(config.get("history_limit", 900))
    metrics: dict[str, dict] = {}
    configured = list(config.get("metrics", []))
    network_metrics = [m for m in configured if m.get("provider") in {"fred", "yahoo"}]

    def fetch_one(metric: dict) -> tuple[str, dict]:
        try:
            if metric.get("provider") == "fred":
                points = _fred_points(metric["series_id"], fetcher)
            else:
                points = _yahoo_points(metric["symbol"], fetcher)
            record = _metric_record(metric, points, collected_at=collected_at, history_limit=history_limit)
        except Exception as exc:
            record = {**metric, "ok": False, "status": "UNKNOWN", "error": str(exc)[:300], "collected_at": collected_at}
        return metric["id"], record

    workers = max(1, min(8, len(network_metrics)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for mid, record in pool.map(fetch_one, network_metrics):
            metrics[mid] = record

    # Exact derived metrics are allowed only when every named input is observed.
    # This is arithmetic, not a semantic proxy.
    for metric in configured:
        if metric.get("provider") != "derived":
            continue
        mid = metric["id"]
        inputs = list(metric.get("inputs") or [])
        formula = metric.get("formula")
        source_rows = [metrics.get(x) for x in inputs]
        if formula != "subtract" or len(inputs) != 2 or not all(x and x.get("ok") for x in source_rows):
            metrics[mid] = {**metric, "ok": False, "status": "UNKNOWN", "error": "derived inputs unavailable", "collected_at": collected_at}
            continue
        left, right = source_rows
        right_by_date = {x["date"]: float(x["value"]) for x in right.get("history", [])}
        points = []
        for row in left.get("history", []):
            if row["date"] in right_by_date:
                points.append({"date": row["date"], "value": round(float(row["value"]) - right_by_date[row["date"]], 8)})
        metrics[mid] = _metric_record(metric, points, collected_at=collected_at, history_limit=history_limit)

    for metric in configured:
        if metric.get("provider") in {"fred", "yahoo", "derived"}:
            continue
        mid = metric["id"]
        metrics[mid] = {
            **metric,
            "ok": False,
            "status": "UNKNOWN",
            "error": f"provider not active: {metric.get('provider')}",
            "collected_at": collected_at,
        }

    result = {
        "schema_version": 1,
        "collected_at": collected_at,
        "metrics": metrics,
        "quality": {
            "p0_total": sum(1 for x in config.get("metrics", []) if x.get("importance") == "P0"),
            "p0_observed": sum(1 for x in metrics.values() if x.get("importance") == "P0" and x.get("ok")),
            "unknown": sorted(k for k, v in metrics.items() if not v.get("ok")),
        },
    }
    atomic_json(root / "data" / "state" / "us_state" / "raw_metrics_latest.json", result)
    return result
