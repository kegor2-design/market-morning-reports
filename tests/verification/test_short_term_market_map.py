import json
import unittest
from pathlib import Path

from datetime import datetime, timezone
from market_morning_publisher.short_term_market_map import build_short_term_market_map, observations_from_market_history, observations_from_us_state

ROOT = Path(__file__).resolve().parents[2]


class ShortTermMarketMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / "config/short_term_market_map.json").read_text(encoding="utf-8"))

    def test_korea_friendly_mix_is_risk_on(self):
        obs = {
            "DXY": {"change_1d_pct": -0.8, "change_5d_pct": -1.4},
            "USDKRW": {"change_1d_pct": -1.0, "change_5d_pct": -2.0},
            "US2Y": {"change_1d_pct": -0.6, "change_5d_pct": -1.0},
            "US10Y": {"change_1d_pct": -0.5, "change_5d_pct": -0.8},
            "US_HY_OAS": {"change_1d_pct": -1.0, "change_5d_pct": -2.0},
            "VIX": {"change_1d_pct": -8.0, "change_5d_pct": -10.0},
            "BTC": {"change_1d_pct": 3.0, "change_5d_pct": 7.0},
            "NASDAQ": {"change_1d_pct": 1.5, "change_5d_pct": 4.0},
            "SOX": {"change_1d_pct": 2.0, "change_5d_pct": 5.0},
            "KOSPI_FOREIGN_NET": {"signal_value": 1.0, "signal_scale": 0.5},
        }
        out = build_short_term_market_map(self.cfg, obs, as_of="2026-08-27T08:00:00+09:00")
        self.assertIn(out["overall_state"], {"RISK_ON", "STRONG_RISK_ON"})

    def test_stale_is_excluded_not_zeroed(self):
        obs = {"USDKRW": {"change_1d_pct": 5.0, "stale": True}}
        out = build_short_term_market_map(self.cfg, obs)
        fx = next(g for g in out["groups"] if g["group_id"] == "FX_DOLLAR")
        usdkrw = next(i for i in fx["indicators"] if i["indicator_id"] == "USDKRW")
        self.assertTrue(usdkrw["stale"])
        self.assertIsNone(usdkrw["score"])

    def test_gold_is_contextual(self):
        obs = {
            "GOLD": {"change_1d_pct": 2.0},
            "DXY": {"change_1d_pct": -1.0},
            "US10Y": {"change_1d_pct": -1.0},
        }
        out = build_short_term_market_map(self.cfg, obs)
        grp = next(g for g in out["groups"] if g["group_id"] == "INFLATION_COMMODITY")
        gold = next(i for i in grp["indicators"] if i["indicator_id"] == "GOLD")
        self.assertGreater(gold["score"], 0)
        self.assertIn("동반", gold["explanation"])

    def test_cpi_event_metric_supported(self):
        obs = {"US_CPI_SURPRISE": {"signal_value": 0.4, "signal_scale": 0.2}}
        out = build_short_term_market_map(self.cfg, obs)
        grp = next(g for g in out["groups"] if g["group_id"] == "INFLATION_COMMODITY")
        cpi = next(i for i in grp["indicators"] if i["indicator_id"] == "US_CPI_SURPRISE")
        self.assertLess(cpi["score"], 0)

    def test_missing_data_does_not_fail(self):
        out = build_short_term_market_map(self.cfg, {})
        self.assertEqual(out["overall_state"], "NO_DATA")

    def test_existing_market_history_adapter_does_not_invent_sources(self):
        markets = [{"symbol": "^IXIC", "ok": True, "value": 110, "change_pct": 1.0, "age_minutes": 10}]
        history = [{"markets": [{"symbol": "^IXIC", "ok": True, "value": value}]} for value in range(80, 105)]
        out = observations_from_market_history(markets, history)
        self.assertIn("NASDAQ", out)
        self.assertNotIn("BTC", out)
        self.assertIsNotNone(out["NASDAQ"]["change_20d_pct"])

    def test_stale_us_state_history_is_visible_but_excluded(self):
        snapshot = {"metrics": {"us_2y": {"as_of": "2026-08-20", "history": [{"date": "2026-08-19", "value": 4.0}, {"date": "2026-08-20", "value": 4.1}]}}}
        out = observations_from_us_state(snapshot, as_of=datetime(2026, 8, 27, tzinfo=timezone.utc))
        self.assertTrue(out["US2Y"]["stale"])


if __name__ == "__main__":
    unittest.main()
