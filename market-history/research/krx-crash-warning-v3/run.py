#!/usr/bin/env python3
"""Causal, close-time v3 research on the existing local KRX-verified series.

Writes aggregate scores and dates only. Never exports index levels or source rows.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
V2_PATH = HERE.parent / "krx-crash-warning-v2-20261021" / "backtest.py"
spec = importlib.util.spec_from_file_location("v2_backtest", V2_PATH)
v2 = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(v2)

PERIODS = {k: v2.PERIODS[k] for k in ("development", "validation", "final")}
FOLDS = v2.FOLDS
MODELS = ("PRICE_ONLY", "PRICE_VOLATILITY")
PRODUCTS = ("data_inventory.csv", "pit_audit.csv", "feature_catalog.csv",
            "model_comparison.csv", "walkforward_results.csv",
            "event_detection_scorecard.csv", "false_alert_analysis.csv", "metrics.json")


def csv_new(name: str, fields: list[str], rows: list[dict]) -> None:
    with (HERE / name).open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def inventory() -> list[dict]:
    base = {"first_date": "", "last_date": "", "rows": "", "missing_rate": "not measured",
            "publication_time_kst": "unverified", "usable_time_kst": "unverified",
            "revision": "unverified", "license": "raw redistribution unconfirmed",
            "pit": "FAIL", "reason": "No 2010-2026 local timestamped observations audited"}
    rows = []
    def add(name: str, category: str, source: str, **kw) -> None:
        rows.append({"variable": name, "category": category, "source": source, **(base | kw)})
    add("KOSPI/KOSDAQ close and trading day", "price", "local KRX-verified v1 series",
        first_date="2010-01-04", last_date="2026-10-20", rows="4133/index",
        missing_rate="0 within official trading-day series", publication_time_kst="close confirmed; exact timestamp unverified",
        usable_time_kst="next Korean trading session", revision="historical corrections not independently audited",
        pit="PASS_NEXT_SESSION", reason="Signals are formed after close; next session is earliest response")
    for name in ("returns_5_20_60_120", "realized_vol20", "max_drawdown20", "ma20_60_slope", "trend_and_vol_expansion"):
        add(name, "derived_price", "causal transform of verified close", first_date="2010-01-04 + lookback",
            last_date="2026-10-20", rows="up to 4133/index", missing_rate="lookback only",
            publication_time_kst="after close confirmation", usable_time_kst="next Korean trading session",
            revision="inherits source corrections", pit="PASS_NEXT_SESSION",
            reason="Uses observations no later than signal date")
    for name in ("advance_decline_ratio", "market_breadth", "equal_vs_cap_weight_return", "sector_breadth", "large_cap_concentration"):
        add(name, "market_internal", "MyDream2000 market_breadth_summary / sector shadow; historical archive unverified",
            reason="Collector stores snapshot_time but accessible 2010-2026 history and as-of integrity not verified")
    for name in ("foreign_kospi_cash", "foreign_kospi200_futures", "institutional_flow", "retail_flow", "flow_5_20", "program_trading"):
        add(name, "flow", "MMP configuration or MyDream2000 investor_flow_snapshot; index-level history unverified",
            reason="Instrument/scope, final release time and 2010-2026 observations unverified")
    for name in ("USD/KRW", "US2Y", "US10Y", "US10Y-US2Y", "VIX", "S&P500", "NASDAQ", "SOX", "credit_spread", "dollar_strength"):
        add(name, "macro_overseas", "MMP configuration / public provider candidate; no audited local daily vintage",
            reason="KST availability and vintage/revision history unverified; no aligned local observations")
    return rows


def price_signals(prices: list) -> tuple[dict[str, list[bool]], dict[str, list[int]]]:
    old = v2.signals(prices)
    # Prespecified, interpretable filter. The 60-day trend and volatility are
    # calculated from closes <= t. No threshold is selected on validation/final.
    only = old["DD20_5"]
    filtered = [only[t] and (old["TREND60"][t] or old["VOL20_RISE"][t])
                for t in range(len(prices))]
    masks = {"PRICE_ONLY": only, "PRICE_VOLATILITY": filtered}
    stages = {}
    for name, mask in masks.items():
        state, clear = 0, 0
        out = []
        for t, active in enumerate(mask):
            dd20 = (float(prices[t] / max(prices[max(0,t-19):t+1]) - 1)
                    if t >= 19 else 0.0)
            raw = 3 if dd20 <= -.10 else (2 if active else (1 if dd20 <= -.03 else 0))
            if raw >= state:
                state, clear = raw, 0
            else:
                clear += 1
                if clear >= 3:
                    state, clear = raw, 0
            out.append(state)
        stages[name] = out
    return masks, stages


def episode_diagnostics(dates, prices, events, eps, matches, lo, hi, model, index, period):
    rows = []
    for ep in eps:
        t = ep["start_i"]
        if t < lo or t > hi - 20:
            continue
        match = matches.get(ep["episode_id"])
        future = prices[t+1:t+21]
        mdd = float(min(future) / prices[t] - 1) if future else None
        mfe = float(max(future) / prices[t] - 1) if future else None
        in_crash = any(e["start_i"] <= t <= e["end_i"] for e in events)
        reason = "hit" if match else ("late_inside_crash" if in_crash else
                 "rebound_or_no_new_crash_within_20_sessions")
        rows.append({"index": index, "period": period, "model": model,
                     "first_alert_date": dates[t], "earliest_response_date": dates[t+1],
                     "last_alert_date": dates[ep["end_i"]], "event_id": match["event_id"] if match else "",
                     "classification": reason, "next20_max_adverse_pct": round(mdd*100, 3),
                     "next20_max_favorable_pct": round(mfe*100, 3)})
    return rows


def main() -> None:
    if any((HERE / p).exists() for p in PRODUCTS):
        raise RuntimeError("V3_OUTPUT_ALREADY_EXISTS")
    data = v2.load_input()  # verifies local input hash and trading-day count
    prior = json.loads((V2_PATH.parent / "metrics.json").read_text(encoding="utf-8"))
    inv = inventory()
    comparison, wf, scorecard, false_rows = [], [], [], []
    metrics = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "source_sha256": v2.digest(v2.INPUT), "source_v2_commit": "045bd0d",
               "signal_time": "after confirmed Korean close t", "response_time": "session t+1",
               "selection": "prespecified DD20_5 and DD20_5 AND (TREND60 OR VOL20_RISE); no optimization",
               "stage_rule": "NORMAL=0, WATCH=DD20<=-3%, WARNING=model alert, CRITICAL=DD20<=-10%; downgrade after 3 consecutive lower raw states",
               "reproduction": {}, "periods": {}, "model_status": {
                   "PRICE_ONLY": "EVALUATED", "PRICE_VOLATILITY": "EVALUATED",
                   "MARKET_INTERNAL": "NOT_EVALUATED_PIT_AND_HISTORY", "FLOW_MACRO": "NOT_EVALUATED_PIT_AND_HISTORY",
                   "REGIME_TRANSITION_SHADOW": "DESCRIPTIVE_ONLY_NOT_VALIDATED"},
               "operation_decision": "RESEARCH_ONLY"}
    for index, (dates, prices) in data.items():
        events = v2.crash_events(index, dates, prices)
        masks, stages = price_signals(prices)
        all_eps = {m: v2.episodes(mask, index, m) for m, mask in masks.items()}
        # Exact v2 score reproduction before new comparisons.
        lo, hi = v2.bounds(dates, *PERIODS["final"])
        original_mask = v2.signals(prices)["DD20_5"]
        original_eps = v2.episodes(original_mask, index, "DD20_5")
        reproduce, _, _ = v2.early_score(dates, events, original_eps, lo, hi)
        expected = prior["periods"]["final"][index]["DD20_5"]["early"]
        assert reproduce == expected, f"v2 early reproduction failed: {index}"
        lo1, hi1 = v2.bounds(dates, *v2.PERIODS["v1_test_reproduction"])
        downside, _ = v2.further_score(prices, original_eps, original_mask, lo1, hi1, 10)
        assert {k: downside[k] for k in ("tp", "fp", "fn", "tn")} == prior["v1_reproduction"][index]
        metrics["reproduction"][index] = {"v2_early_exact": True, "v1_confusion_exact": True,
                                          "final_v2_early": expected,
                                          "v1_confusion": prior["v1_reproduction"][index]}
        for period, limits in PERIODS.items():
            lo, hi = v2.bounds(dates, *limits)
            for model in MODELS:
                eps = all_eps[model]
                early, leads, matches = v2.early_score(dates, events, eps, lo, hi)
                further = {str(target): v2.further_score(prices, eps, masks[model], lo, hi, target)[0]
                           for target in (5, 7, 10)}
                metrics["periods"].setdefault(period, {}).setdefault(index, {})[model] = {
                    "early": early, "further": further,
                    "stage_sessions": {name: sum(stages[model][t] == val for t in range(lo,hi+1))
                                       for val,name in enumerate(("NORMAL","WATCH","WARNING","CRITICAL"))}}
                comparison.append({"period": period, "index": index, "model": model,
                    "same_period": f"{limits[0]}..{limits[1]}", "events": early["eligible_events"],
                    "event_hits": early["hit_events"], "event_recall": early["event_recall"],
                    "episodes": early["eligible_episodes"], "true_episodes": early["tp_episodes"],
                    "false_episodes": early["fp_episodes"], "episode_precision": early["episode_precision"],
                    "median_lead_sessions": early["median_first_warning_lead_sessions"],
                    "alerts_per_month": round(early["eligible_episodes"] / ((hi-lo+1)/21), 3),
                    "further10_tp": further["10"]["tp"], "further10_fp": further["10"]["fp"],
                    "further10_fn": further["10"]["fn"], "further10_tn": further["10"]["tn"]})
                if period == "final":
                    false_rows += episode_diagnostics(dates, prices, events, eps, matches, lo, hi, model,index,period)
                    for e in events:
                        if not lo+20 <= e["start_i"] <= hi or e["left_censored"]:
                            continue
                        lead = leads.get(e["event_id"])
                        scorecard.append({"index": index, "model": model, "event_id": e["event_id"],
                            "context": v2.context(dates[e["start_i"]]), "peak_date": dates[e["peak_i"]],
                            "first_5pct_date": dates[e["first5_i"]] if e["first5_i"] is not None else "",
                            "first_10pct_date": dates[e["start_i"]], "low_date": dates[e["low_i"]],
                            "recovery_date": dates[e["recovery_i"]] if e["recovery_i"] is not None else "",
                            "first_warning_date": dates[e["start_i"]-lead] if lead is not None else "",
                            "earliest_response_date": dates[e["start_i"]-lead+1] if lead is not None else "",
                            "warning_lead_sessions": lead if lead is not None else "",
                            "response_lead_sessions": lead-1 if lead is not None else "",
                            "hit": int(lead is not None)})
        for fold, first, last in FOLDS:
            lo, hi = v2.bounds(dates, first, last)
            for model in MODELS:
                early, _, _ = v2.early_score(dates, events, all_eps[model], lo, hi)
                wf.append({"fold": fold, "index": index, "model": model, "first": first,
                    "last": last, "events": early["eligible_events"], "hits": early["hit_events"],
                    "episodes": early["eligible_episodes"], "false_episodes": early["fp_episodes"],
                    "episode_precision": early["episode_precision"], "median_lead_sessions": early["median_first_warning_lead_sessions"]})
    for model in ("MARKET_INTERNAL", "FLOW_MACRO"):
        comparison.append({"period": "not_evaluated", "index": "both", "model": model,
                           "same_period": "unavailable", "events": "", "event_hits": "",
                           "event_recall": "", "episodes": "", "true_episodes": "", "false_episodes": "",
                           "episode_precision": "", "median_lead_sessions": "", "alerts_per_month": "",
                           "further10_tp": "", "further10_fp": "", "further10_fn": "", "further10_tn": ""})
    csv_new("data_inventory.csv", list(inv[0]), inv)
    csv_new("pit_audit.csv", ["variable","pit","usable_time_kst","reason"], inv)
    features = [{"feature": r["variable"], "category": r["category"], "source": r["source"],
                 "pit": r["pit"], "experiment": "PRICE_ONLY/PRICE_VOLATILITY" if r["pit"].startswith("PASS") else "EXCLUDED",
                 "lookback_or_lag": "up to 120 sessions; t close to t+1 response" if r["pit"].startswith("PASS") else "undefined"}
                for r in inv]
    csv_new("feature_catalog.csv", list(features[0]), features)
    csv_new("model_comparison.csv", list(comparison[0]), comparison)
    csv_new("walkforward_results.csv", list(wf[0]), wf)
    csv_new("event_detection_scorecard.csv", list(scorecard[0]), scorecard)
    csv_new("false_alert_analysis.csv", list(false_rows[0]), false_rows)
    with (HERE / "metrics.json").open("x", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
