#!/usr/bin/env python3
"""Create date-only historical timelines and descriptive stage outcomes."""
from __future__ import annotations
import csv
from pathlib import Path
import run

HERE = Path(__file__).resolve().parent


def main() -> None:
    timelines, stages = [], []
    for index, (dates, prices) in run.v2.load_input().items():
        events = run.v2.crash_events(index, dates, prices)
        masks, state = run.price_signals(prices)
        for model in run.MODELS:
            for period, limits in run.PERIODS.items():
                lo, hi = run.v2.bounds(dates, *limits)
                for e in events:
                    start = e["start_i"]
                    if not lo+20 <= start <= hi or e["left_censored"]:
                        continue
                    before = range(max(0,start-20), start)
                    risk = next((t for t in before if state[model][t] >= 1), None)
                    alert = next((t for t in before if masks[model][t]), None)
                    release = next((t for t in range(e["end_i"]+1, min(len(dates),e["end_i"]+61))
                                    if state[model][t] < 2), None)
                    timelines.append({"period":period,"index":index,"model":model,
                        "event_id":e["event_id"],"historical_context":run.v2.context(dates[start]),
                        "first_risk_change_date":dates[risk] if risk is not None else "",
                        "first_warning_date":dates[alert] if alert is not None else "",
                        "earliest_response_date":dates[alert+1] if alert is not None else "",
                        "peak_date":dates[e["peak_i"]],
                        "first_5pct_date":dates[e["first5_i"]] if e["first5_i"] is not None else "",
                        "first_10pct_date":dates[start],"low_date":dates[e["low_i"]],
                        "recovery_date":dates[e["recovery_i"]] if e["recovery_i"] is not None else "",
                        "warning_release_date":dates[release] if release is not None else "",
                        "warning_lead_sessions":start-alert if alert is not None else "",
                        "response_lead_sessions":start-alert-1 if alert is not None else ""})
                for level,name in enumerate(("NORMAL","WATCH","WARNING","CRITICAL")):
                    ts=[t for t in range(max(lo,19),hi-20+1) if state[model][t]==level]
                    for target in (5,7,10):
                        hits=sum(min(prices[t+1:t+21])/prices[t]-1 <= -target/100 for t in ts)
                        stages.append({"period":period,"index":index,"model":model,
                            "stage":name,"target_pct":target,"sessions":len(ts),
                            "future20_hits":hits,"empirical_rate":hits/len(ts) if ts else ""})
    run.csv_new("historical_event_timeline.csv",list(timelines[0]),timelines)
    run.csv_new("stage_outcomes.csv",list(stages[0]),stages)


if __name__ == "__main__":
    main()
