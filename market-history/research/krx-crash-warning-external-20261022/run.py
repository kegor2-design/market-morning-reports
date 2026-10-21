#!/usr/bin/env python3
"""H.15 release-time join and exploratory incremental scores. No raw values published."""
from __future__ import annotations

from bisect import bisect_right
import csv
from datetime import datetime, date, time, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
V2_PATH = HERE.parent / "krx-crash-warning-v2-20261021" / "backtest.py"
H15 = HERE / "h15_rates.local.csv"
PRODUCTS = ("source_coverage.csv", "pit_join_audit.csv", "model_comparison.csv", "walkforward_results.csv", "metrics.json", "pit_join.local.csv")
US = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")
spec = importlib.util.spec_from_file_location("v2_external", V2_PATH)
v2 = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(v2)


def write_new(name, fields, rows):
    with (HERE / name).open("x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def load_h15():
    with H15.open(newline="", encoding="utf-8-sig") as f:
        raw = list(csv.reader(f))
    assert raw[5][0] == "Time Period"
    assert "RIFLGFCY02_N.B" in raw[5] and "RIFLGFCY10_N.B" in raw[5]
    rows = [dict(zip(raw[5], row)) for row in raw[6:] if row and len(row) == len(raw[5])]
    assert rows[-1]["Time Period"] <= "2026-10-20"
    return rows


def coverage(rows):
    window = [r for r in rows if "2010-01-01" <= r["Time Period"] <= "2026-10-20"]
    out = []
    for name, col in (("US2Y", "RIFLGFCY02_N.B"), ("US10Y", "RIFLGFCY10_N.B")):
        valid = [r for r in window if r[col] not in ("", ".", "ND")]
        out.append({"variable": name, "source": "Federal Reserve H.15 official DDP",
                    "first_observation": valid[0]["Time Period"], "last_observation": valid[-1]["Time Period"],
                    "weekday_rows": len(window), "observed_rows": len(valid), "missing_rows": len(window)-len(valid),
                    "missing_rate": (len(window)-len(valid))/len(window),
                    "publication_rule": "next H.15 release date 16:15 America/New_York",
                    "vintage_status": "UNVERIFIED_CURRENT_HISTORICAL_SNAPSHOT"})
    return out


def released_observations(rows):
    # A valid row d is first published on the next H.15 release date, not on d.
    # The next row with both Treasury rates is a conservative proxy for that
    # release date; holidays are skipped. Last row is intentionally unusable.
    good = [r for r in rows if r["RIFLGFCY02_N.B"] not in ("", ".", "ND")
            and r["RIFLGFCY10_N.B"] not in ("", ".", "ND")]
    observations = []
    for row, next_row in zip(good, good[1:]):
        obs = date.fromisoformat(row["Time Period"])
        release = datetime.combine(date.fromisoformat(next_row["Time Period"]), time(16, 15), US).astimezone(timezone.utc)
        observations.append((release, obs, Decimal(row["RIFLGFCY02_N.B"]), Decimal(row["RIFLGFCY10_N.B"])))
    assert all(a[0] < b[0] for a,b in zip(observations,observations[1:]))
    return observations


def join(dates, observations):
    times = [r[0] for r in observations]
    joined = []
    for day in dates:
        signal = datetime.combine(date.fromisoformat(day), time(18), KST).astimezone(timezone.utc)
        pos = bisect_right(times, signal)-1
        if pos < 5:
            joined.append(None)
            continue
        release, obs, y2, y10 = observations[pos]
        age = (date.fromisoformat(day)-obs).days
        if age > 7:
            joined.append(None)
            continue
        assert release <= signal and obs < date.fromisoformat(day)
        # Five distinct H.15 observations, avoiding multiple Korean sessions
        # counting one stale observation as a new change.
        prior2, prior10 = observations[pos-5][2:4]
        joined.append({"obs": obs.isoformat(), "release_utc": release.isoformat(),
                       "age_days": age, "y2": y2, "y10": y10,
                       "d2_5": y2-prior2, "d10_5": y10-prior10,
                       "signal_utc": signal.isoformat()})
    return joined


def models(prices, joined):
    dd = v2.signals(prices)["DD20_5"]
    shock = [r is not None and (abs(r["d2_5"]) >= Decimal("0.25") or abs(r["d10_5"]) >= Decimal("0.25"))
             for r in joined]
    return {"DD20_5": dd,
            "H15_SHOCK_25BP": shock,
            "DD20_5_AND_H15": [a and b for a,b in zip(dd,shock)],
            "DD20_5_OR_H15": [a or b for a,b in zip(dd,shock)]}


def main():
    if any((HERE / p).exists() for p in PRODUCTS):
        raise RuntimeError("OUTPUT_ALREADY_EXISTS")
    rows = load_h15()
    obs = released_observations(rows)
    data = v2.load_input()
    covers = coverage(rows)
    joins, audits, comparisons, folds = [], [], [], []
    metrics = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "h15_sha256": hashlib.sha256(H15.read_bytes()).hexdigest(),
               "krx_sha256": v2.digest(v2.INPUT),
               "backtest_status": "EXPLORATORY_PUBLICATION_TIME_ONLY_VINTAGE_UNVERIFIED",
               "signal_time": "18:00 Asia/Seoul after Korean close",
               "response_time": "next Korean trading session",
               "thresholds": "prespecified absolute 5-H15-observation change >= 0.25 percentage point; no fitting",
               "join_rule": "latest released H.15 observation at or before Korean 18:00, at most 7 calendar days old",
               "release_rule": "observation d first usable after next H.15 nonholiday release 16:15 America/New_York",
               "score_source": "unchanged v2 crash events, episode scoring and period boundaries",
               "models": {}, "v2_reproduced": {}}
    prior = json.loads((V2_PATH.parent / "metrics.json").read_text(encoding="utf-8"))
    for index,(dates,prices) in data.items():
        aligned = join(dates,obs)
        events = v2.crash_events(index,dates,prices)
        masks = models(prices,aligned)
        for day,r in zip(dates,aligned):
            joins.append({"index":index,"krx_date":day,"signal_time_utc":r["signal_utc"] if r else "",
                          "h15_observation_date":r["obs"] if r else "",
                          "h15_release_utc":r["release_utc"] if r else "",
                          "age_days":r["age_days"] if r else "",
                          "us2y":r["y2"] if r else "","us10y":r["y10"] if r else "",
                          "us2y_change_5obs":r["d2_5"] if r else "","us10y_change_5obs":r["d10_5"] if r else ""})
        for period, (first,last) in {k:v2.PERIODS[k] for k in ("development","validation","final")}.items():
            lo,hi = v2.bounds(dates,first,last)
            missing=sum(r is None for r in aligned[lo:hi+1])
            ages=[r["age_days"] for r in aligned[lo:hi+1] if r]
            audits.append({"index":index,"period":period,"krx_sessions":hi-lo+1,
                           "linked_sessions":hi-lo+1-missing,"missing_sessions":missing,
                           "max_age_days":max(ages) if ages else "", "median_age_days":median(ages) if ages else "",
                           "future_release_violations":0,"vintage_verified":0})
            for name,mask in masks.items():
                eps = v2.episodes(mask,index,name)
                early,_,_ = v2.early_score(dates,events,eps,lo,hi)
                further,_ = v2.further_score(prices,eps,mask,lo,hi,10)
                comparisons.append({"index":index,"period":period,"model":name,
                    "first":first,"last":last,"eligible_events":early["eligible_events"],
                    "hit_events":early["hit_events"],"event_recall":early["event_recall"],
                    "episodes":early["eligible_episodes"],"tp_episodes":early["tp_episodes"],
                    "fp_episodes":early["fp_episodes"],"episode_precision":early["episode_precision"],
                    "median_lead_sessions":early["median_first_warning_lead_sessions"],
                    "downside10_tp":further["tp"],"downside10_fp":further["fp"],
                    "downside10_fn":further["fn"],"downside10_tn":further["tn"]})
                metrics["models"].setdefault(period,{}).setdefault(index,{})[name] = {"early":early,"downside10":further}
                if name=="DD20_5":
                    assert early==prior["periods"][period][index]["DD20_5"]["early"]
                    metrics["v2_reproduced"].setdefault(index,[]).append(period)
        for fold,first,last in v2.FOLDS:
            lo,hi=v2.bounds(dates,first,last)
            for name,mask in masks.items():
                early,_,_=v2.early_score(dates,events,v2.episodes(mask,index,name),lo,hi)
                folds.append({"index":index,"fold":fold,"model":name,"first":first,"last":last,
                              "eligible_events":early["eligible_events"],"hit_events":early["hit_events"],
                              "fp_episodes":early["fp_episodes"],"episode_precision":early["episode_precision"]})
    write_new("source_coverage.csv",list(covers[0]),covers)
    write_new("pit_join.local.csv",list(joins[0]),joins)
    write_new("pit_join_audit.csv",list(audits[0]),audits)
    write_new("model_comparison.csv",list(comparisons[0]),comparisons)
    write_new("walkforward_results.csv",list(folds[0]),folds)
    with (HERE/"metrics.json").open("x",encoding="utf-8") as f:
        json.dump(metrics,f,ensure_ascii=False,indent=2)
        f.write("\n")


if __name__=="__main__":
    main()
