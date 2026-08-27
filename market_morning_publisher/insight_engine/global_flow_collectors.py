from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from market_morning_publisher.core import atomic_json, fetch, now_iso
from market_morning_publisher.us_state.collectors import _fred_points
from market_morning_publisher.us_state.state_engine import summarize_metric


def _number(value: str) -> float:
    return float(value.replace(",", "").strip())


def parse_mof_weekly_foreign_bond_flow(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("cp932")
    rows = list(csv.reader(io.StringIO(text)))
    points = []
    for row in rows:
        if len(row) < 7:
            continue
        period = unicodedata.normalize("NFKC", row[0]).replace(" ", "")
        match = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})[~～](?:(\d{4})\.)?(\d{1,2})\.(\d{1,2})", period)
        if not match:
            continue
        year, start_month, _start_day, end_year, end_month, end_day = match.groups()
        resolved_year = int(end_year or year)
        if not end_year and int(end_month) < int(start_month):
            resolved_year += 1
        try:
            as_of = date(resolved_year, int(end_month), int(end_day)).isoformat()
            value = _number(row[6])  # outward long-term debt securities, net
        except (ValueError, IndexError):
            continue
        points.append({"date": as_of, "value": value})
    return points


def parse_tic_japan_holdings(raw: bytes, country: str = "Japan") -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t"))
    header = next((row for row in rows if row and row[0].strip() == "Country"), None)
    target = next((row for row in rows if row and row[0].strip() == country), None)
    if not header or not target:
        return []
    points = []
    for month, value in zip(header[1:], target[1:]):
        try:
            points.append({"date": f"{month.strip()}-01", "value": _number(value)})
        except ValueError:
            continue
    return sorted(points, key=lambda row: row["date"])


def _semantic_record(metric: dict[str, Any], points: list[dict[str, Any]], collected_at: str) -> dict[str, Any]:
    if not points:
        return {"state": "UNKNOWN", "reason": "no observations", "provider": metric["provider"], "collected_at": collected_at}
    latest = points[-1]
    age = (datetime.now(timezone.utc).date() - date.fromisoformat(latest["date"])).days
    if age > int(metric.get("stale_days", 7)):
        state = "STALE"
    elif metric["id"] == "japan_foreign_bond_flow":
        state = "REPATRIATING" if latest["value"] < 0 else ("NET_BUYING" if latest["value"] > 0 else "FLAT")
    else:
        previous = points[-2]["value"] if len(points) > 1 else latest["value"]
        state = "RISING" if latest["value"] > previous else ("FALLING" if latest["value"] < previous else "FLAT")
    return {
        "id": metric["id"], "name": metric["name"], "provider": metric["provider"],
        "state": state, "value": latest["value"], "as_of": latest["date"], "age_days": age,
        "unit": metric.get("unit"), "history": points, "collected_at": collected_at,
    }


def _realized_vol(points: list[dict[str, Any]], window: int = 20) -> list[dict[str, Any]]:
    out = []
    for index in range(window, len(points)):
        returns = [math.log(points[i]["value"] / points[i - 1]["value"]) for i in range(index - window + 1, index + 1)]
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / max(1, len(returns) - 1)
        out.append({"date": points[index]["date"], "value": round(math.sqrt(variance * 252) * 100, 4)})
    return out


def collect_global_flow_metrics(root: Path, config: dict[str, Any], *, fetcher: Callable = fetch) -> dict[str, Any]:
    collected_at = now_iso()
    history_limit = int(config.get("history_limit", 900))
    metrics: dict[str, dict[str, Any]] = {}
    raw_points: dict[str, list[dict[str, Any]]] = {}
    for metric in config.get("metrics") or []:
        provider = metric.get("provider")
        try:
            if provider == "fred":
                points = _fred_points(metric["series_id"], fetcher)[-history_limit:]
                raw_points[metric["id"]] = points
                record = summarize_metric({**metric, "ok": bool(points), "history": points, "as_of": points[-1]["date"] if points else None})
                record.update({"provider": "FRED", "collected_at": collected_at})
            elif provider == "derived_realized_vol":
                points = _realized_vol(raw_points.get(metric["input"], []))[-history_limit:]
                record = _semantic_record(metric, points, collected_at)
                record["proxy_disclosure"] = metric.get("proxy_disclosure")
            elif provider == "mof_weekly":
                points = parse_mof_weekly_foreign_bond_flow(fetcher(metric["url"]))[-history_limit:]
                record = _semantic_record(metric, points, collected_at)
            elif provider == "tic_table5":
                points = parse_tic_japan_holdings(fetcher(metric["url"]), metric.get("country", "Japan"))[-history_limit:]
                record = _semantic_record(metric, points, collected_at)
            else:
                record = {"state": "UNKNOWN", "reason": f"unsupported provider: {provider}", "collected_at": collected_at}
        except Exception as exc:
            record = {"state": "UNKNOWN", "reason": str(exc)[:300], "provider": provider, "collected_at": collected_at}
        metrics[metric["id"]] = record
    result = {
        "schema_version": 1, "collected_at": collected_at, "metrics": metrics,
        "quality": {"total": len(metrics), "observed": sum(v.get("state") not in {"UNKNOWN", "STALE"} for v in metrics.values()),
                    "unknown": sorted(k for k, v in metrics.items() if v.get("state") in {"UNKNOWN", "STALE"})},
    }
    atomic_json(root / "data/state/insight_engine/metrics_latest.json", result)
    return result
