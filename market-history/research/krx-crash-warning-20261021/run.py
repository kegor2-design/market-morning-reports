#!/usr/bin/env python3
"""Isolate KRX-validated closes and run a fixed, price-only warning baseline."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
KRX = RESEARCH / "krx-full-validation-20261021"
PREVIOUS = RESEARCH / "daily-index-validation-20261021"
START, END = "2010-01-01", "2026-10-20"
WINDOW = 20
HORIZON = 20
SIGNAL_DRAWDOWN = Decimal("-0.05")
EVENT_FALL = Decimal("-0.10")
TOLERANCE = Decimal("0.0101")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_verified() -> dict[str, list[tuple[str, Decimal]]]:
    audit = json.loads((KRX / "result.json").read_text(encoding="utf-8"))
    assert audit["status"] == "COMPLETE" and len(audit["queries"]) == 49
    assert all(q["http_status"] == 200 for q in audit["queries"])
    out: dict[str, list[tuple[str, Decimal]]] = {"KOSPI": [], "KOSDAQ": []}
    with (KRX / "official.local.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if START <= row["date"] <= END:
                out[row["index"]].append((row["date"], Decimal(row["krx_close"])))
    for index, series in out.items():
        series.sort()
        assert len(series) == 4133 == len({day for day, _ in series})
        assert series[0][0] == "2010-01-04" and series[-1][0] == END
        with (PREVIOUS / f"naver_{index.lower()}_daily.csv").open(newline="", encoding="utf-8") as stream:
            naver = {r["date"]: Decimal(r["close"]) for r in csv.DictReader(stream) if START <= r["date"] <= END}
        assert set(naver) == {day for day, _ in series}
        assert all(abs(close - naver[day]) <= TOLERANCE for day, close in series)
    return out


def classify(series: list[tuple[str, Decimal]]) -> list[dict]:
    rows = []
    for t in range(WINDOW - 1, len(series) - HORIZON):
        day, close = series[t]
        prior_peak = max(value for _, value in series[t-WINDOW+1:t+1])
        drawdown = close / prior_peak - 1
        alert = drawdown <= SIGNAL_DRAWDOWN
        future = [value for _, value in series[t+1:t+HORIZON+1]]
        event = min(future) / close - 1 <= EVENT_FALL
        lead = next((i for i, value in enumerate(future, 1) if value / close - 1 <= EVENT_FALL), None)
        rows.append({"date": day, "close": close, "drawdown": drawdown,
                     "alert": alert, "event": event, "lead": lead})
    return rows


def metrics(rows: list[dict]) -> dict:
    tp = sum(r["alert"] and r["event"] for r in rows)
    fp = sum(r["alert"] and not r["event"] for r in rows)
    fn = sum(not r["alert"] and r["event"] for r in rows)
    tn = sum(not r["alert"] and not r["event"] for r in rows)
    n = len(rows)
    episodes = sum(r["alert"] and (i == 0 or not rows[i-1]["alert"])
                   for i, r in enumerate(rows))
    precision = tp / (tp + fp) if tp + fp else None
    base_rate = (tp + fn) / n if n else None
    leads = [r["lead"] for r in rows if r["alert"] and r["event"]]
    return {"dates": n, "first_date": rows[0]["date"] if rows else None,
            "last_date": rows[-1]["date"] if rows else None,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "alert_days": tp + fp, "alert_episodes": episodes,
            "event_days": tp + fn, "event_rate": base_rate,
            "precision": precision, "recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
            "precision_lift": precision / base_rate if precision is not None and base_rate else None,
            "median_lead_sessions_for_true_alerts": statistics.median(leads) if leads else None}


def main() -> None:
    for name in ("validated_closes.local.csv", "signals.local.csv", "metrics.json"):
        if (HERE / name).exists():
            raise RuntimeError(f"OUTPUT_ALREADY_EXISTS:{name}")
    series_by_index = load_verified()
    with (HERE / "validated_closes.local.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("date", "index", "official_close"))
        for index, series in series_by_index.items():
            writer.writerows((day, index, str(close)) for day, close in series)
    outcome = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {"start": "2010-01-04", "end": END, "indices": ["KOSPI", "KOSDAQ"],
                  "rows_per_index": 4133, "status": "KRX_OFFICIAL_CLOSE_AND_TRADING_DAY_VERIFIED"},
        "input_lineage": {"krx_local_sha256": sha256(KRX / "official.local.csv"),
                          "validation_result_sha256": sha256(KRX / "result.json"),
                          "isolated_local_sha256": sha256(HERE / "validated_closes.local.csv")},
        "baseline": {"name": "20-session drawdown alert", "signal": "At close t, close / max(closes t-19..t) - 1 <= -5%",
                     "target": "Any close t+1..t+20 <= 90% of close t",
                     "fixed_thresholds": True, "training_or_tuning": False,
                     "test_period": "2018-01-01 to 2026-10-20", "development_period": "2010-01-04 to 2017-12-31"},
        "results": {},
        "long_horizon_30y_reevaluation": "PENDING_1996_2009_FULL_OFFICIAL_VERIFICATION",
    }
    with (HERE / "signals.local.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("date", "index", "close", "drawdown", "alert", "future_20d_10pct_event", "lead_sessions"))
        for index, series in series_by_index.items():
            classified = classify(series)
            for row in classified:
                writer.writerow((row["date"], index, str(row["close"]), str(row["drawdown"]),
                                 int(row["alert"]), int(row["event"]), row["lead"] or ""))
            outcome["results"][index] = {
                "development": metrics([r for r in classified if r["date"] < "2018-01-01"]),
                "test": metrics([r for r in classified if r["date"] >= "2018-01-01"]),
            }
    (HERE / "metrics.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "test": {i: x["test"] for i, x in outcome["results"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
