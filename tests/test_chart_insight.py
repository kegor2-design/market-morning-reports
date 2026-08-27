import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_morning_publisher.chart_insight.historical import build_edge_summary, validate_historical_claim
from market_morning_publisher.chart_insight.primitives import detect_primitives, key_levels, map_expert_text


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "config/chart_insight_primitives.json").read_text(encoding="utf-8"))


def bar(day, o, h, l, c, v=100):
    return {"timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc).replace(day=1).isoformat() if False else day, "open": o, "high": h, "low": l, "close": c, "volume": v}


class ChartInsightTest(unittest.TestCase):
    def test_expert_language_maps_to_primitive_candidate_not_fact(self):
        rows = map_expert_text("전고점 돌파 뒤 거래량이 증가했습니다", REGISTRY)
        ids = {row["primitive_id"] for row in rows}
        self.assertIn("BREAKOUT", ids)
        self.assertIn("VOLUME_EXPANSION", ids)
        self.assertTrue(all(not row["independently_verified"] for row in rows))

    def test_detects_breakout_and_relative_volume(self):
        bars = []
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(25):
            base = 100 + i * 0.1
            bars.append({"timestamp": (start + timedelta(days=i)).isoformat(), "open": base, "high": base + 1, "low": base - 1, "close": base + 0.2, "volume": 100})
        prior_high = max(row["high"] for row in bars)
        bars.append({"timestamp": (start + timedelta(days=25)).isoformat(), "open": prior_high, "high": prior_high + 4, "low": prior_high - 0.2, "close": prior_high + 3, "volume": 220})
        found = {row["primitive_id"] for row in detect_primitives(bars, REGISTRY)}
        self.assertIn("BREAKOUT", found)
        self.assertIn("VOLUME_EXPANSION", found)

    def test_key_levels_are_numeric_and_do_not_invent_vwap(self):
        bars = [
            {"timestamp": "2026-01-01T00:00:00+00:00", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 10},
            {"timestamp": "2026-01-02T00:00:00+00:00", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 10},
        ]
        levels = key_levels(bars)["levels"]
        self.assertEqual(levels["PREVIOUS_CLOSE"], 11.0)
        self.assertNotIn("VWAP", levels)

    def test_historical_validation_excludes_incomplete_current_bar_from_context(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = []
        for i in range(70):
            bars.append({"timestamp": (start + timedelta(days=i)).isoformat(), "open": 100+i, "high": 102+i, "low": 99+i, "close": 101+i, "volume": 100})
        # Actionable halfway through the bar whose timestamp is day 60. Conservative completed-bar logic should stop at day 59 or earlier.
        actionable = (start + timedelta(days=60, hours=12)).isoformat()
        claim = {
            "source_claim_id": "YTC-AAAAAAAAAAAAAAAAAAAA", "channel_id": "park_chart_center", "video_id": "v",
            "publicly_actionable_at": actionable, "resolved_asset_symbol": "005930.KS", "resolved_timeframe": "DAILY",
            "resolved_direction": "LONG", "speech_excerpt": "전고점 돌파하면 상승 가능성이 있습니다",
        }
        result = validate_historical_claim(claim, bars, REGISTRY, context_bars=20, horizon_bars=5)
        last_context = datetime.fromisoformat(result["point_in_time_context"]["last_timestamp"])
        self.assertLess(last_context, datetime.fromisoformat(actionable))
        self.assertEqual(result["point_in_time_context"]["future_bars_used_for_context"], 0)
        self.assertIn(result["primitive_mapping_status"], {"SUPPORTED_BY_POINT_IN_TIME_CHART", "NOT_OBSERVED_IN_POINT_IN_TIME_CHART"})

    def test_edge_summary_conditions_on_primitive_timeframe_and_regime(self):
        validations = [
            {"timeframe": "DAILY", "market_regime": "RISK_ON_TREND", "primitive_mapping_status": "SUPPORTED_BY_POINT_IN_TIME_CHART", "point_in_time_context": {"observed_primitives": [{"primitive_id": "BREAKOUT"}]}, "expert_primitive_candidates": [{"primitive_id": "BREAKOUT"}], "outcome": {"status": "SUCCESS", "forward_windows": [{"bars": 5, "status": "COMPLETE", "return_pct": 4.0}]}},
            {"timeframe": "DAILY", "market_regime": "RISK_ON_TREND", "primitive_mapping_status": "SUPPORTED_BY_POINT_IN_TIME_CHART", "point_in_time_context": {"observed_primitives": [{"primitive_id": "BREAKOUT"}]}, "expert_primitive_candidates": [{"primitive_id": "BREAKOUT"}], "outcome": {"status": "FAILURE", "forward_windows": [{"bars": 5, "status": "COMPLETE", "return_pct": -1.0}]}},
        ]
        result = build_edge_summary(validations)
        row = result["groups"][0]
        self.assertEqual(row["primitive_id"], "BREAKOUT")
        self.assertEqual(row["market_regime"], "RISK_ON_TREND")
        self.assertEqual(row["forward"]["5"]["positive_rate"], 0.5)
        self.assertEqual(row["promotion_status"], "RESEARCH_ONLY")

    def test_release_separates_chart_engine_namespace(self):
        self.assertTrue((ROOT / "market_morning_publisher/chart_insight").is_dir())
        policy = json.loads((ROOT / "config/chart_insight_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["namespace"], "chart_insight")
        self.assertIn("future bars are outcome-only", policy["point_in_time_rule"].casefold())


if __name__ == "__main__":
    unittest.main()
