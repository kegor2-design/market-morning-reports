import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from market_morning_publisher.us_state.collectors import collect_us_state_metrics
from market_morning_publisher.us_state.event_engine import analyze_event, upcoming_events
from market_morning_publisher.us_state.state_engine import build_state, summarize_metric


class USStateTest(unittest.TestCase):
    def test_collector_keeps_pending_metric_unknown_instead_of_proxying(self):
        cfg = {
            "history_limit": 20,
            "metrics": [
                {"id":"us_10y","provider":"fred","series_id":"DGS10","name":"10Y","group":"rates","frequency":"daily","unit":"%","importance":"P0","stale_days":5},
                {"id":"term_premium_10y","provider":"external_pending","name":"TP","group":"rates","frequency":"daily","unit":"%","importance":"P0","stale_days":5},
            ],
        }
        csv = b"observation_date,DGS10\n2026-08-20,4.7\n2026-08-21,4.8\n"
        with tempfile.TemporaryDirectory() as td:
            out = collect_us_state_metrics(Path(td), cfg, fetcher=lambda url: csv)
        self.assertTrue(out["metrics"]["us_10y"]["ok"])
        self.assertFalse(out["metrics"]["term_premium_10y"]["ok"])
        self.assertEqual(out["metrics"]["term_premium_10y"]["status"], "UNKNOWN")
        self.assertIn("term_premium_10y", out["quality"]["unknown"])

    def test_yahoo_metric_provider_parses_daily_close(self):
        cfg = {
            "history_limit": 20,
            "metrics": [
                {"id":"btc_market","provider":"yahoo","symbol":"BTC-USD","name":"BTC","group":"market","frequency":"daily","unit":"USD","importance":"P0","stale_days":5}
            ],
        }
        payload = json.dumps({"chart":{"result":[{"timestamp":[1787184000,1787270400],"indicators":{"quote":[{"close":[100.0,105.0]}]}}]}}).encode()
        with tempfile.TemporaryDirectory() as td:
            out = collect_us_state_metrics(Path(td), cfg, fetcher=lambda url: payload)
        self.assertTrue(out["metrics"]["btc_market"]["ok"])
        self.assertEqual(out["metrics"]["btc_market"]["value"], 105.0)


    def test_exact_derived_spread_uses_observed_inputs_only(self):
        cfg = {
            "history_limit": 20,
            "metrics": [
                {"id":"sofr","provider":"fred","series_id":"SOFR","name":"SOFR","group":"money","frequency":"daily","unit":"%","importance":"P0","stale_days":5},
                {"id":"iorb","provider":"fred","series_id":"IORB","name":"IORB","group":"money","frequency":"daily","unit":"%","importance":"P0","stale_days":5},
                {"id":"sofr_iorb_spread","provider":"derived","formula":"subtract","inputs":["sofr","iorb"],"name":"spread","group":"money","frequency":"daily","unit":"pp","importance":"P0","stale_days":5},
            ],
        }
        payloads = {
            "SOFR": b"observation_date,SOFR\n2026-08-20,5.10\n2026-08-21,5.15\n",
            "IORB": b"observation_date,IORB\n2026-08-20,5.00\n2026-08-21,5.00\n",
        }
        def fetcher(url):
            return payloads["SOFR" if "SOFR" in url else "IORB"]
        with tempfile.TemporaryDirectory() as td:
            out = collect_us_state_metrics(Path(td), cfg, fetcher=fetcher)
        self.assertTrue(out["metrics"]["sofr_iorb_spread"]["ok"])
        self.assertAlmostEqual(out["metrics"]["sofr_iorb_spread"]["value"], 0.15, places=6)

    def test_metric_summary_uses_change_and_staleness(self):
        metric = {
            "id":"us_30y", "name":"30Y", "group":"rates", "importance":"P0", "frequency":"daily", "unit":"%", "stale_days":5,
            "ok":True, "as_of":"2026-08-21", "history":[{"date":f"2026-07-{i:02d}","value":4.0+i/100} for i in range(1,29)] + [
                {"date":"2026-08-20","value":5.0},{"date":"2026-08-21","value":5.2}
            ]
        }
        result = summarize_metric(metric, now=date(2026,8,24))
        self.assertEqual(result["state"], "RISING")
        self.assertGreater(result["changes"]["20p"], 0)

    def test_state_preserves_missing_p0(self):
        raw = {"metrics": {
            "us_10y":{"id":"us_10y","name":"10Y","group":"rates","importance":"P0","frequency":"daily","unit":"%","stale_days":5,"ok":False,"error":"missing"},
            "us_20y":{"id":"us_20y","name":"20Y","group":"rates","importance":"P0","frequency":"daily","unit":"%","stale_days":5,"ok":False,"error":"missing"},
            "us_30y":{"id":"us_30y","name":"30Y","group":"rates","importance":"P0","frequency":"daily","unit":"%","stale_days":5,"ok":False,"error":"missing"},
            "us_real_10y":{"id":"us_real_10y","name":"real10","group":"rates","importance":"P0","frequency":"daily","unit":"%","stale_days":5,"ok":False,"error":"missing"},
        }, "quality": {"unknown":["us_10y"]}}
        state = build_state(raw, now=date(2026,8,24))
        self.assertEqual(state["states"]["US_LONG_END_STRESS"]["state"], "UNKNOWN")

    def test_buyback_event_selects_park_hypothesis_and_missing_evidence(self):
        playbooks = {
            "playbooks":[
                {"id":"US_TREASURY_STRESS","required_metrics":["us_30y"]},
                {"id":"TREASURY_BUYBACK","required_metrics":["treasury_buyback","term_premium_10y"],"park_hypothesis":"political timing / long-end suppression"},
            ]
        }
        state = {"metrics": {
            "us_30y":{"id":"us_30y","state":"RISING"},
            "treasury_buyback":{"id":"treasury_buyback","state":"UNKNOWN"},
            "term_premium_10y":{"id":"term_premium_10y","state":"UNKNOWN"},
        }}
        result = analyze_event({"id":"x","type":"TREASURY_BUYBACK","name":"Treasury expands buyback"}, state, playbooks)
        self.assertIn("TREASURY_BUYBACK", result["playbooks"])
        self.assertEqual(result["our_status"], "UNKNOWN")
        self.assertIn("political timing", result["park_primary_hypotheses"][0])
        self.assertIn("term_premium_10y", result["missing_or_stale"])

    def test_event_calendar_returns_upcoming_in_order(self):
        calendar = {"events":[
            {"id":"b","date":"2026-11-04","name":"QRA"},
            {"id":"a","date":"2026-11-03","name":"Midterm"},
            {"id":"old","date":"2026-08-01","name":"Old"},
        ]}
        out = upcoming_events(calendar, as_of=date(2026,8,24), horizon_days=90)
        self.assertEqual([x["id"] for x in out], ["a","b"])

    def test_release_configs_have_unique_metric_and_playbook_ids(self):
        root = Path(__file__).resolve().parents[1]
        metrics = json.loads((root / "config/us_state_metrics.json").read_text(encoding="utf-8"))
        playbooks = json.loads((root / "config/us_issue_playbooks.json").read_text(encoding="utf-8"))
        mids = [x["id"] for x in metrics["metrics"]]
        pids = [x["id"] for x in playbooks["playbooks"]]
        self.assertEqual(len(mids), len(set(mids)))
        self.assertEqual(len(pids), len(set(pids)))
        self.assertIn("fima_usage", mids)
        self.assertIn("srf_usage", mids)
        self.assertIn("eslr_regime", mids)
        self.assertIn("mmf_tbill", mids)
        self.assertIn("sofr_iorb_spread", mids)
        knowledge = json.loads((root / "config/us_background_knowledge.json").read_text(encoding="utf-8"))
        kids = [x["id"] for x in knowledge["modules"]]
        self.assertEqual(len(kids), len(set(kids)))
        self.assertIn("FED_IMPLEMENTATION", kids)
        self.assertIn("REALIZED_EFFECT_VALIDATION", kids)


if __name__ == "__main__":
    unittest.main()
