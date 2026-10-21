#!/usr/bin/env python3
"""Two distinct close-time warning backtests on the local KRX-verified series."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / "krx-crash-warning-20261021"
INPUT = V1 / "validated_closes.local.csv"
WINDOW, HORIZON, MERGE_GAP = 60, 20, 20
TARGETS = (5, 7, 10)
MODELS = ("DD20_5", "TREND20", "TREND60", "VOL20_RISE", "MAXDD20_EXPAND", "NO_ALERT")
PERIODS = {"development": ("2010-01-04", "2017-12-28"),
           "validation": ("2018-01-02", "2021-12-30"),
           "final": ("2022-01-03", "2026-10-20"),
           "v1_test_reproduction": ("2018-01-02", "2026-10-20")}
FOLDS = [("WF1", "2018-01-02", "2019-12-30"),
         ("WF2", "2020-01-02", "2021-12-30"),
         ("WF3", "2022-01-03", "2023-12-28"),
         ("WF4", "2024-01-02", "2026-10-20")]
CONTEXTS = [
    ("2011 European debt crisis", "2011-07-01", "2011-12-31"),
    ("2015-2016 China market shock", "2015-06-01", "2016-03-31"),
    ("2018 market decline", "2018-01-01", "2018-12-31"),
    ("2020 COVID crash", "2020-02-01", "2020-05-31"),
    ("2022 tightening", "2022-01-01", "2022-12-31"),
    ("2024-2026 market declines", "2024-01-01", "2026-10-20"),
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_input() -> dict[str, tuple[list[str], list[Decimal]]]:
    v1 = json.loads((V1 / "metrics.json").read_text(encoding="utf-8"))
    assert v1["scope"]["status"] == "KRX_OFFICIAL_CLOSE_AND_TRADING_DAY_VERIFIED"
    assert digest(INPUT) == v1["input_lineage"]["isolated_local_sha256"]
    by_index: dict[str, list[tuple[str, Decimal]]] = {"KOSPI": [], "KOSDAQ": []}
    with INPUT.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            by_index[row["index"]].append((row["date"], Decimal(row["official_close"])))
    out = {}
    for index, rows in by_index.items():
        assert len(rows) == 4133 and rows == sorted(rows)
        dates = [day for day, _ in rows]
        assert len(set(dates)) == 4133 and dates[0] == "2010-01-04" and dates[-1] == "2026-10-20"
        out[index] = (dates, [price for _, price in rows])
    return out


def max_drawdown(values: list[float]) -> float:
    peak, worst = values[0], 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def signals(prices: list[Decimal]) -> dict[str, list[bool]]:
    n = len(prices)
    out = {name: [False] * n for name in MODELS}
    floats = [float(p) for p in prices]
    returns = [0.0] + [floats[t] / floats[t-1] - 1.0 for t in range(1, n)]
    for t in range(n):
        if t >= 19:
            last20 = prices[t-19:t+1]
            out["DD20_5"][t] = prices[t] / max(last20) - 1 <= Decimal("-0.05")
            out["TREND20"][t] = prices[t] < sum(last20) / 20
        if t >= 59:
            out["TREND60"][t] = prices[t] < sum(prices[t-59:t+1]) / 60
        if t >= 60:
            vol20 = statistics.pstdev(returns[t-19:t+1])
            vol60 = statistics.pstdev(returns[t-59:t+1])
            out["VOL20_RISE"][t] = vol60 > 0 and vol20 >= 1.5 * vol60
        if t >= 39:
            current = max_drawdown(floats[t-19:t+1])
            prior = max_drawdown(floats[t-39:t-19])
            out["MAXDD20_EXPAND"][t] = current <= -0.05 and current <= prior - 0.02
    return out


def runs(mask: list[bool]) -> list[tuple[int, int]]:
    out = []
    start = None
    for t, active in enumerate(mask):
        if active and start is None:
            start = t
        elif not active and start is not None:
            out.append((start, t - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def crash_events(index: str, dates: list[str], prices: list[Decimal]) -> list[dict]:
    mask = [False] * len(prices)
    for t in range(WINDOW - 1, len(prices)):
        mask[t] = prices[t] / max(prices[t-WINDOW+1:t+1]) - 1 <= Decimal("-0.10")
    merged: list[list[int]] = []
    for start, end in runs(mask):
        if merged and start - merged[-1][1] - 1 <= MERGE_GAP:
            merged[-1][1] = end
            merged[-1][2] += 1
        else:
            merged.append([start, end, 1])
    events = []
    for number, (start, end, merged_runs) in enumerate(merged, 1):
        peak = max(range(start-WINDOW+1, start+1), key=lambda j: (prices[j], -j))
        first5 = next((j for j in range(peak+1, start+1)
                       if prices[j] / prices[peak] - 1 <= Decimal("-0.05")), None)
        low = min(range(start, end+1), key=lambda j: prices[j])
        next_start = merged[number][0] if number < len(merged) else len(prices)
        recovery = next((j for j in range(end+1, next_start)
                         if prices[j] >= prices[peak]), None)
        events.append({"event_id": f"{index}-{dates[start].replace('-', '')}-{number:02d}",
                       "index": index, "peak_i": peak, "first5_i": first5,
                       "start_i": start, "end_i": end, "low_i": low,
                       "recovery_i": recovery, "merged_runs": merged_runs,
                       "left_censored": start == WINDOW-1,
                       "right_censored_low": end == len(prices)-1})
    return events


def episodes(mask: list[bool], index: str, model: str) -> list[dict]:
    return [{"episode_id": f"{index}-{model}-{number:04d}", "index": index,
             "model": model, "start_i": start, "end_i": end}
            for number, (start, end) in enumerate(runs(mask), 1)]


def bounds(dates: list[str], first: str, last: str) -> tuple[int, int]:
    candidates = [i for i, day in enumerate(dates) if first <= day <= last]
    return candidates[0], candidates[-1]


def context(day: str) -> str:
    names = [name for name, first, last in CONTEXTS if first <= day <= last]
    return "; ".join(names)


def early_score(dates: list[str], events: list[dict], eps: list[dict], lo: int, hi: int) -> tuple[dict, dict, dict]:
    eligible = [e for e in events if not e["left_censored"] and lo + HORIZON <= e["start_i"] <= hi]
    eligible_eps = [ep for ep in eps if lo <= ep["start_i"] <= hi-HORIZON]
    event_matches: dict[str, list[dict]] = {}
    episode_matches: dict[str, dict | None] = {}
    for ep in eligible_eps:
        future = [e for e in eligible if 1 <= e["start_i"] - ep["start_i"] <= HORIZON]
        matched = min(future, key=lambda e: e["start_i"], default=None)
        episode_matches[ep["episode_id"]] = matched
        if matched:
            event_matches.setdefault(matched["event_id"], []).append(ep)
    leads = {}
    for e in eligible:
        match = event_matches.get(e["event_id"], [])
        leads[e["event_id"]] = e["start_i"] - min(ep["start_i"] for ep in match) if match else None
    tp_ep = sum(match is not None for match in episode_matches.values())
    fp_ep = len(eligible_eps) - tp_ep
    hit_events = sum(lead is not None for lead in leads.values())
    lead_values = [lead for lead in leads.values() if lead is not None]
    result = {"eligible_events": len(eligible), "hit_events": hit_events,
              "event_recall": hit_events / len(eligible) if eligible else None,
              "eligible_episodes": len(eligible_eps), "tp_episodes": tp_ep,
              "fp_episodes": fp_ep,
              "episode_precision": tp_ep / len(eligible_eps) if eligible_eps else None,
              "false_episodes_per_1000_sessions": fp_ep / (hi-lo+1) * 1000,
              "median_first_warning_lead_sessions": statistics.median(lead_values) if lead_values else None,
              "events_with_at_least_lead": {str(k): sum(lead >= k for lead in lead_values) for k in (1, 3, 5, 10, 20)}}
    return result, leads, episode_matches


def further_score(prices: list[Decimal], eps: list[dict], mask: list[bool], lo: int, hi: int,
                  target_pct: int) -> tuple[dict, dict[str, bool]]:
    eligible_end = hi - HORIZON
    eligible_start = max(lo, 19)
    target = Decimal(target_pct) / 100
    labels = {t: min(prices[t+1:t+HORIZON+1]) / prices[t] - 1 <= -target
              for t in range(eligible_start, eligible_end+1)}
    tp = sum(mask[t] and labels[t] for t in labels)
    fp = sum(mask[t] and not labels[t] for t in labels)
    fn = sum(not mask[t] and labels[t] for t in labels)
    tn = sum(not mask[t] and not labels[t] for t in labels)
    eligible_eps = [ep for ep in eps if eligible_start <= ep["start_i"] <= eligible_end]
    ep_hit = {ep["episode_id"]: any(labels.get(t, False) for t in range(ep["start_i"], min(ep["end_i"], eligible_end)+1))
              for ep in eligible_eps}
    base_rate = (tp+fn)/len(labels) if labels else None
    precision = tp/(tp+fp) if tp+fp else None
    result = {"evaluated_days": len(labels), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
              "event_days": tp+fn, "alert_days": tp+fp,
              "event_rate": base_rate,
              "precision": precision, "recall": tp/(tp+fn) if tp+fn else None,
              "false_positive_rate": fp/(fp+tn) if fp+tn else None,
              "precision_lift": precision/base_rate if precision is not None and base_rate else None,
              "eligible_episodes": len(eligible_eps),
              "tp_episodes": sum(ep_hit.values()), "fp_episodes": len(eligible_eps)-sum(ep_hit.values()),
              "episode_precision": sum(ep_hit.values())/len(eligible_eps) if eligible_eps else None}
    return result, ep_hit


def write_csv(name: str, fields: list[str], rows: list[dict]) -> None:
    with (HERE / name).open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    products = ("metrics.json", "crash_events.csv", "warning_episode_summary.csv",
                "event_detection_scorecard.csv", "walkforward_results.csv", "failure_cases.csv",
                "daily_signals.local.csv")
    if any((HERE / name).exists() for name in products):
        raise RuntimeError("V2_OUTPUT_ALREADY_EXISTS")
    data = load_input()
    v1 = json.loads((V1 / "metrics.json").read_text(encoding="utf-8"))
    metrics = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "input_sha256": digest(INPUT), "v1_commit": "66ed022",
               "input_scope": "KRX-verified closes and trading dates 2010-01-04..2026-10-20, 4133 per index",
               "signal_time": "after confirmed close t", "earliest_response": "next trading session t+1",
               "definitions": {"crash": "first close <= 90% of trailing 60-session maximum",
                               "event_merge_gap_sessions": MERGE_GAP,
                               "early_lead_window_sessions": HORIZON,
                               "further_horizon_sessions": HORIZON,
                               "threshold_optimization": "none; all candidate rules fixed before evaluation"},
               "periods": {}, "v1_reproduction": {}, "models": {},
               "operation_decision": "RESEARCH_ONLY"}
    crash_rows, episode_rows, score_rows, fold_rows, failure_rows, daily_rows = [], [], [], [], [], []
    for index, (dates, prices) in data.items():
        all_signals = signals(prices)
        events = crash_events(index, dates, prices)
        all_episodes = {model: episodes(all_signals[model], index, model) for model in MODELS}
        for e in events:
            crash_rows.append({"event_id": e["event_id"], "index": index,
                               "peak_date": dates[e["peak_i"]],
                               "first_5pct_date": dates[e["first5_i"]] if e["first5_i"] is not None else "",
                               "first_10pct_date": dates[e["start_i"]], "last_10pct_zone_date": dates[e["end_i"]],
                               "low_date": dates[e["low_i"]],
                               "recovery_to_peak_date": dates[e["recovery_i"]] if e["recovery_i"] is not None else "",
                               "merged_10pct_runs": e["merged_runs"], "left_censored": int(e["left_censored"]),
                               "right_censored_low": int(e["right_censored_low"]),
                               "historical_context": context(dates[e["start_i"]])})
        for model in MODELS:
            for ep in all_episodes[model]:
                episode_rows.append({"episode_id": ep["episode_id"], "index": index, "model": model,
                                     "first_alert_date": dates[ep["start_i"]], "last_alert_date": dates[ep["end_i"]],
                                     "alert_sessions": ep["end_i"]-ep["start_i"]+1,
                                     "earliest_response_date": dates[ep["start_i"]+1] if ep["start_i"]+1<len(dates) else "",
                                     "starts_in_10pct_zone": int(any(e["start_i"] <= ep["start_i"] <= e["end_i"] for e in events))})
        for period, (first, last) in PERIODS.items():
            lo, hi = bounds(dates, first, last)
            metrics["periods"].setdefault(period, {})[index] = {}
            for model in MODELS:
                early, leads, ep_matches = early_score(dates, events, all_episodes[model], lo, hi)
                further = {}
                further_episode_hits = {}
                for target in TARGETS:
                    further[str(target)], further_episode_hits[str(target)] = further_score(
                        prices, all_episodes[model], all_signals[model], lo, hi, target)
                metrics["periods"][period][index][model] = {"early": early, "further": further}
                if period == "v1_test_reproduction" and model == "DD20_5":
                    old = v1["results"][index]["test"]
                    now = further["10"]
                    assert all(now[key] == old[key] for key in ("tp", "fp", "fn", "tn")), (index, now, old)
                    metrics["v1_reproduction"][index] = {key: now[key] for key in ("tp", "fp", "fn", "tn")}
                if period in ("development", "validation", "final"):
                    for event in events:
                        if not (lo + HORIZON <= event["start_i"] <= hi) or event["left_censored"]:
                            continue
                        lead = leads[event["event_id"]]
                        score_rows.append({"period": period, "index": index, "model": model,
                                           "event_id": event["event_id"], "first_10pct_date": dates[event["start_i"]],
                                           "hit_before_10pct": int(lead is not None),
                                           "first_warning_lead_sessions": lead if lead is not None else "",
                                           "earliest_response_lead_sessions": lead-1 if lead is not None else "",
                                           "first_warning_date": dates[event["start_i"]-lead] if lead is not None else "",
                                           "historical_context": context(dates[event["start_i"]])})
                    if model == "DD20_5":
                        for ep in all_episodes[model]:
                            if ep["episode_id"] not in further_episode_hits["10"] or further_episode_hits["10"][ep["episode_id"]]:
                                continue
                            t = ep["start_i"]
                            in_zone = any(e["start_i"] <= t <= e["end_i"] for e in events)
                            future20 = prices[t+1:t+HORIZON+1]
                            rebound = bool(future20 and max(future20) >= prices[t])
                            reason = "already_in_price_defined_crash" if in_zone else (
                                "rebound_within_20_sessions" if rebound else "decline_below_10pct_target")
                            failure_rows.append({"task": "FURTHER_DOWNSIDE_RISK", "period": period,
                                                 "index": index, "model": model, "case_type": "FALSE_ALERT_EPISODE",
                                                 "date": dates[t], "event_id": "", "reason": reason})
                        for event in events:
                            if not (lo + HORIZON <= event["start_i"] <= hi) or event["left_censored"]:
                                continue
                            if leads[event["event_id"]] is None:
                                failure_rows.append({"task": "EARLY_CRASH_WARNING", "period": period,
                                                     "index": index, "model": model, "case_type": "MISSED_EVENT",
                                                     "date": dates[event["start_i"]], "event_id": event["event_id"],
                                                     "reason": "no_new_alert_episode_in_prior_20_sessions"})
                        for ep in all_episodes[model]:
                            if ep["episode_id"] not in ep_matches or ep_matches[ep["episode_id"]] is not None:
                                continue
                            t = ep["start_i"]
                            in_zone = any(e["start_i"] <= t <= e["end_i"] for e in events)
                            future20 = prices[t+1:t+HORIZON+1]
                            rebound = bool(future20 and max(future20) >= prices[t])
                            reason = "after_10pct_or_within_crash_zone" if in_zone else (
                                "rebound_without_new_crash" if rebound else "slow_or_shallow_decline")
                            failure_rows.append({"task": "EARLY_CRASH_WARNING", "period": period,
                                                 "index": index, "model": model, "case_type": "FALSE_ALERT_EPISODE",
                                                 "date": dates[t], "event_id": "", "reason": reason})
            if period != "v1_test_reproduction":
                for model in MODELS:
                    row = metrics["periods"][period][index][model]
                    for task, target, stats in [("EARLY_CRASH_WARNING", "", row["early"])] + [
                        ("FURTHER_DOWNSIDE_RISK", str(p), row["further"][str(p)]) for p in TARGETS]:
                        fold_rows.append({"fold": period, "index": index, "model": model,
                                          "task": task, "target_pct": target,
                                          "start": dates[lo], "end": dates[hi],
                                          "event_recall": stats.get("event_recall", stats.get("recall")),
                                          "episode_precision": stats.get("episode_precision"),
                                          "day_precision": stats.get("precision", ""),
                                          "false_positive_rate": stats.get("false_positive_rate", ""),
                                          "alert_episodes": stats.get("eligible_episodes"),
                                          "false_alert_episodes": stats.get("fp_episodes"),
                                          "events_or_event_days": stats.get("eligible_events", stats.get("event_days")),
                                          "hits_or_tp_days": stats.get("hit_events", stats.get("tp"))})
        for fold, first, last in FOLDS:
            lo, hi = bounds(dates, first, last)
            for model in MODELS:
                early, _, _ = early_score(dates, events, all_episodes[model], lo, hi)
                further, _ = further_score(prices, all_episodes[model], all_signals[model], lo, hi, 10)
                for task, stats in (("EARLY_CRASH_WARNING", early), ("FURTHER_DOWNSIDE_RISK", further)):
                    fold_rows.append({"fold": fold, "index": index, "model": model, "task": task,
                                      "target_pct": "" if task.startswith("EARLY") else 10,
                                      "start": dates[lo], "end": dates[hi],
                                      "event_recall": stats.get("event_recall", stats.get("recall")),
                                      "episode_precision": stats["episode_precision"],
                                      "day_precision": stats.get("precision", ""),
                                      "false_positive_rate": stats.get("false_positive_rate", ""),
                                      "alert_episodes": stats["eligible_episodes"],
                                      "false_alert_episodes": stats["fp_episodes"],
                                      "events_or_event_days": stats.get("eligible_events", stats.get("event_days")),
                                      "hits_or_tp_days": stats.get("hit_events", stats.get("tp"))})
        for t, day in enumerate(dates):
            daily_rows.append({"date": day, "index": index,
                               **{model: int(all_signals[model][t]) for model in MODELS}})
        metrics["models"][index] = {"price_defined_crash_events": len(events),
                                     "event_dates": [dates[e["start_i"]] for e in events],
                                     "warning_episode_counts": {model: len(all_episodes[model]) for model in MODELS}}
    write_csv("crash_events.csv", ["event_id", "index", "peak_date", "first_5pct_date", "first_10pct_date",
                                   "last_10pct_zone_date", "low_date", "recovery_to_peak_date", "merged_10pct_runs",
                                   "left_censored", "right_censored_low", "historical_context"], crash_rows)
    write_csv("warning_episode_summary.csv", ["episode_id", "index", "model", "first_alert_date", "last_alert_date",
                                               "alert_sessions", "earliest_response_date", "starts_in_10pct_zone"], episode_rows)
    write_csv("event_detection_scorecard.csv", ["period", "index", "model", "event_id", "first_10pct_date",
                                                "hit_before_10pct", "first_warning_lead_sessions",
                                                "earliest_response_lead_sessions", "first_warning_date", "historical_context"], score_rows)
    write_csv("walkforward_results.csv", ["fold", "index", "model", "task", "target_pct", "start", "end",
                                          "event_recall", "episode_precision", "day_precision", "false_positive_rate",
                                          "alert_episodes", "false_alert_episodes", "events_or_event_days", "hits_or_tp_days"], fold_rows)
    failure_rows.sort(key=lambda row: (row["task"], row["period"], row["index"],
                                       row["case_type"], row["date"], row["event_id"], row["reason"]))
    write_csv("failure_cases.csv", ["task", "period", "index", "model", "case_type", "date", "event_id", "reason"], failure_rows)
    write_csv("daily_signals.local.csv", ["date", "index", *MODELS], daily_rows)
    (HERE / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "events": len(crash_rows), "episodes": len(episode_rows),
                      "v1_reproduction": metrics["v1_reproduction"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
